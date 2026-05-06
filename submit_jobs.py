#!/usr/bin/env python3
"""
DFTflow Slurm 自动提交脚本
============================

使用方法:
    # 提交单步计算作业（*_single.sh）
    python submit_jobs.py mag_soc_vasp/ --single

    # 提交工作流模式作业（排除 *_resume.sh / *_single.sh）
    python submit_jobs.py work_dir/

    # 提交续算作业（*_resume.sh）
    python submit_jobs.py work_dir/ --resume

功能：
  1. 扫描工作目录下符合条件的 .sh 脚本
  2. 解析脚本中的节点/核心数配置
  3. 根据 config/condor.ini 自动控制提交节奏，避免超出资源限制
  4. 支持作业失败重试
"""

import os
import re
import sys
import time
import logging
import subprocess
import configparser
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass, field
from collections import deque


# ── 配置文件路径（与 vasp.py 保持一致） ────────────────────────────────────────
DFTFLOW_ROOT = Path(__file__).parent.absolute()
DEFAULT_CONFIG = str(DFTFLOW_ROOT / "config" / "condor.ini")


# ─────────────────────────────────────────────────────────────────────────────
# 数据类
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class JobInfo:
    """单个作业的描述信息"""
    script_path: str
    job_dir: str
    job_name: str
    nodes: int
    cores: int
    partition: str
    job_id: Optional[str] = None
    status: str = "pending"     # pending / submitted / failed
    retry_count: int = 0


# ─────────────────────────────────────────────────────────────────────────────
# 配置管理
# ─────────────────────────────────────────────────────────────────────────────

class ConfigManager:
    """读取并动态热更新 condor.ini"""

    def __init__(self, config_file: str = DEFAULT_CONFIG):
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self._last_mtime: float = 0
        self.load_config()

    def load_config(self):
        try:
            self.config.read(self.config_file)
            self._last_mtime = os.path.getmtime(self.config_file)
        except Exception as e:
            logging.warning(f"无法读取配置文件 {self.config_file}: {e}")

    def check_and_reload(self) -> bool:
        """如配置文件有更新则热加载，返回是否有实质性参数变化，并逐项打印 diff"""
        try:
            mtime = os.path.getmtime(self.config_file)
            if mtime <= self._last_mtime:
                return False

            _fields = {
                "TOTAL_NODE":            lambda: self.total_nodes,
                "MAX_JOBS":              lambda: self.max_jobs,
                "INTERVAL_TIME":         lambda: self.interval_time,
                "CHECK_TIME":            lambda: self.check_time,
                "CONFIG_RELOAD_INTERVAL": lambda: self.config_reload_interval,
            }
            before = {k: v() for k, v in _fields.items()}
            self.load_config()
            after = {k: v() for k, v in _fields.items()}

            changed = {k for k in _fields if before[k] != after[k]}
            if changed:
                logging.getLogger("DFTflowSubmitter").info("检测到配置变更，已热加载:")
                for k in sorted(changed):
                    logging.getLogger("DFTflowSubmitter").info(
                        f"  {k}: {before[k]} → {after[k]}"
                    )
                return True

        except Exception as e:
            logging.warning(f"检查配置更新时出错: {e}")
        return False

    def _get(self, section, key, default=None):
        try:
            return self.config.get(section, key)
        except Exception:
            return default

    def _getint(self, section, key, default=0):
        try:
            return self.config.getint(section, key)
        except Exception:
            return default

    def _getfloat(self, section, key, default=0.0):
        try:
            return self.config.getfloat(section, key)
        except Exception:
            return default

    @property
    def partition(self) -> str:
        return self._get("ALLOW", "PARTITION", "default")

    @property
    def total_nodes(self) -> int:
        return self._getint("ALLOW", "TOTAL_NODE", 10)

    @property
    def max_jobs(self) -> int:
        return self._getint("ALLOW", "MAX_JOBS", 1000)

    @property
    def interval_time(self) -> float:
        return self._getfloat("ALLOW", "INTERVAL_TIME", 0.5)

    @property
    def check_time(self) -> float:
        return self._getfloat("ALLOW", "CHECK_TIME", 60)

    @property
    def config_reload_interval(self) -> float:
        return self._getfloat("ALLOW", "CONFIG_RELOAD_INTERVAL", 600)


# ─────────────────────────────────────────────────────────────────────────────
# Slurm 队列监控
# ─────────────────────────────────────────────────────────────────────────────

class SlurmMonitor:
    def __init__(self, config: ConfigManager, logger: logging.Logger):
        self.config = config
        self.logger = logger

    def get_queue_status(self) -> Tuple[int, int, int]:
        """返回 (total_jobs, running_jobs, used_nodes)"""
        try:
            partition_name = self.config.partition.split()[0]
            cmd = f"squeue -u $USER -h -o '%T %D' -p {partition_name}"
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                self.logger.warning(f"squeue 失败: {result.stderr}")
                return 0, 0, 0

            total_jobs = running_jobs = used_nodes = 0
            for line in result.stdout.strip().splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    status, nodes = parts[0], int(parts[1])
                    total_jobs += 1
                    if status in ("RUNNING", "R"):
                        running_jobs += 1
                        used_nodes += nodes
            return total_jobs, running_jobs, used_nodes

        except subprocess.TimeoutExpired:
            self.logger.error("squeue 命令超时")
            return 0, 0, 0
        except Exception as e:
            self.logger.error(f"获取队列状态失败: {e}")
            return 0, 0, 0

    def can_submit(self, job: JobInfo) -> Tuple[bool, str]:
        total_jobs, _running, used_nodes = self.get_queue_status()
        if total_jobs >= self.config.max_jobs:
            return False, f"已达最大任务数 {self.config.max_jobs}"
        if used_nodes + job.nodes > self.config.total_nodes:
            return False, (
                f"节点不足 (已用:{used_nodes}, 需要:{job.nodes}, "
                f"限制:{self.config.total_nodes})"
            )
        return True, "资源充足"


# ─────────────────────────────────────────────────────────────────────────────
# 脚本解析
# ─────────────────────────────────────────────────────────────────────────────

class ScriptParser:
    @staticmethod
    def parse_script(script_path: str) -> Tuple[int, int]:
        """从脚本中提取 (nodes, cores)，默认 (1, 16)"""
        nodes, cores = 1, 16
        try:
            content = Path(script_path).read_text()

            # #SBATCH -N / --nodes
            m = re.search(r"#SBATCH\s+(?:-N\s*|--nodes=?)(\d+)", content)
            if m:
                nodes = int(m.group(1))

            # #SBATCH -n / --ntasks
            m = re.search(r"#SBATCH\s+(?:-n\s*|--ntasks=?)(\d+)", content)
            if m:
                cores = int(m.group(1))

            # yhrun/srun -N ... -n ...
            m = re.search(r"(?:yhrun|srun)\s+.*?-N\s+(\d+).*?-n\s+(\d+)", content)
            if m:
                nodes, cores = int(m.group(1)), int(m.group(2))

            # 注释行: # Resources: 1 node(s), 32 processes
            m = re.search(r"#\s*Resources:\s*(\d+)\s*node\(s\),\s*(\d+)\s*processes", content)
            if m:
                nodes, cores = int(m.group(1)), int(m.group(2))

        except Exception as e:
            logging.warning(f"解析脚本失败 {script_path}: {e}")
        return nodes, cores

    @staticmethod
    def get_job_name(script_path: str) -> str:
        return Path(script_path).parent.name


# ─────────────────────────────────────────────────────────────────────────────
# 作业队列
# ─────────────────────────────────────────────────────────────────────────────

class JobQueue:
    def __init__(self, logger: logging.Logger):
        self._queue: deque = deque()
        self.submitted: dict = {}
        self.failed: list = []
        self.logger = logger

    def add_job(self, job: JobInfo):
        self._queue.append(job)

    def add_jobs(self, jobs: List[JobInfo]):
        self._queue.extend(jobs)

    def get_next(self) -> Optional[JobInfo]:
        return self._queue.popleft() if self._queue else None

    def mark_submitted(self, job: JobInfo, job_id: str):
        job.job_id = job_id
        job.status = "submitted"
        self.submitted[job_id] = job
        self.logger.info(f"已提交: {job.job_name} (ID: {job_id})")

    def mark_failed(self, job: JobInfo, reason: str):
        job.status = "failed"
        self.failed.append((job, reason))
        self.logger.error(f"提交失败: {job.job_name} — {reason}")

    @property
    def pending_count(self) -> int:
        return len(self._queue)

    @property
    def submitted_count(self) -> int:
        return len(self.submitted)

    @property
    def failed_count(self) -> int:
        return len(self.failed)


# ─────────────────────────────────────────────────────────────────────────────
# 自动提交器
# ─────────────────────────────────────────────────────────────────────────────

class AutoSubmitter:
    def __init__(self, config_file: str = DEFAULT_CONFIG):
        self.config = ConfigManager(config_file)
        self.logger = self._setup_logger()
        self.monitor = SlurmMonitor(self.config, self.logger)
        self.queue = JobQueue(self.logger)
        self.running = False

    def _setup_logger(self) -> logging.Logger:
        logger = logging.getLogger("DFTflowSubmitter")
        logger.setLevel(logging.INFO)
        if logger.handlers:
            return logger

        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                                datefmt="%Y-%m-%d %H:%M:%S")
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        logger.addHandler(ch)

        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        fh = logging.FileHandler(log_dir / f"submit_{time.strftime('%Y%m%d_%H%M%S')}.log")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
        return logger

    def scan_scripts(
        self,
        work_dir: str,
        include_resume: bool = False,
        include_single: bool = False,
    ) -> List[JobInfo]:
        work_path = Path(work_dir)
        if not work_path.exists():
            self.logger.error(f"工作目录不存在: {work_dir}")
            return []

        all_sh = list(work_path.rglob("*.sh"))

        if include_resume:
            scripts = [f for f in all_sh if f.name.endswith("_resume.sh")]
            self.logger.info(f"模式: 续算脚本 (*_resume.sh) — 找到 {len(scripts)} 个")
        elif include_single:
            scripts = [f for f in all_sh if f.name.endswith("_single.sh")]
            self.logger.info(f"模式: 单步脚本 (*_single.sh) — 找到 {len(scripts)} 个")
        else:
            scripts = [
                f for f in all_sh
                if not f.name.endswith("_resume.sh") and not f.name.endswith("_single.sh")
            ]
            self.logger.info(f"模式: 工作流脚本 — 找到 {len(scripts)} 个")

        jobs = []
        for sf in sorted(scripts):
            try:
                nodes, cores = ScriptParser.parse_script(str(sf))
                jobs.append(JobInfo(
                    script_path=str(sf),
                    job_dir=str(sf.parent),
                    job_name=ScriptParser.get_job_name(str(sf)),
                    nodes=nodes,
                    cores=cores,
                    partition=self.config.partition,
                ))
            except Exception as e:
                self.logger.error(f"解析脚本失败 {sf}: {e}")
        return jobs

    def submit_job(self, job: JobInfo) -> Tuple[bool, str]:
        try:
            script_path = Path(job.script_path).absolute()
            job_dir = Path(job.job_dir).absolute()

            cmd = ["sbatch", "-N", str(job.nodes), "-n", str(job.cores)]
            partition_parts = job.partition.split()
            if partition_parts:
                cmd += ["-p", partition_parts[0]]
                if len(partition_parts) > 1:
                    cmd += partition_parts[1:]
            cmd += ["--job-name", job.job_name, str(script_path)]

            self.logger.debug(f"提交命令: {' '.join(cmd)}")
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, cwd=str(job_dir)
            )

            if result.returncode != 0:
                return False, result.stderr.strip()

            m = re.search(r"Submitted batch job (\d+)", result.stdout)
            if m:
                return True, m.group(1)
            return False, f"无法解析作业 ID: {result.stdout.strip()}"

        except subprocess.TimeoutExpired:
            return False, "sbatch 命令超时"
        except Exception as e:
            return False, str(e)

    def run(
        self,
        work_dir: str,
        max_retries: int = 3,
        include_resume: bool = False,
        include_single: bool = False,
    ):
        self.running = True
        sep = "=" * 70
        self.logger.info(sep)
        self.logger.info("DFTflow Slurm 自动提交器启动")
        self.logger.info(sep)
        self.logger.info(f"工作目录   : {work_dir}")
        self.logger.info(f"配置文件   : {self.config.config_file}")
        self.logger.info(f"分区       : {self.config.partition}")
        self.logger.info(f"节点限制   : {self.config.total_nodes}")
        self.logger.info(f"任务上限   : {self.config.max_jobs}")
        self.logger.info(f"提交间隔   : {self.config.interval_time} 秒")
        self.logger.info(f"检查间隔   : {self.config.check_time} 秒")
        self.logger.info(sep)

        jobs = self.scan_scripts(work_dir, include_resume=include_resume, include_single=include_single)
        if not jobs:
            self.logger.warning("没有找到可提交的作业，退出。")
            return

        self.queue.add_jobs(jobs)
        self.logger.info(f"共 {self.queue.pending_count} 个作业加入队列")

        last_check = 0.0
        last_reload = time.time()

        try:
            while self.running and self.queue.pending_count > 0:
                now = time.time()

                # 热更新配置（diff 日志在 check_and_reload 内输出）
                if now - last_reload >= self.config.config_reload_interval:
                    self.config.check_and_reload()
                    last_reload = now

                # 定期打印队列摘要
                if now - last_check >= self.config.check_time:
                    total, running, nodes = self.monitor.get_queue_status()
                    self.logger.info(
                        f"队列摘要 — 总:{total}  运行:{running}  "
                        f"节点:{nodes}/{self.config.total_nodes}  "
                        f"待提交:{self.queue.pending_count}"
                    )
                    last_check = now

                job = self.queue.get_next()
                if not job:
                    break

                ok, reason = self.monitor.can_submit(job)
                if not ok:
                    self.logger.info(f"资源不足，等待 {self.config.check_time}s … ({reason})")
                    self.queue.add_job(job)
                    time.sleep(self.config.check_time)
                    continue

                success, result = self.submit_job(job)
                if success:
                    self.queue.mark_submitted(job, result)
                else:
                    if job.retry_count < max_retries:
                        job.retry_count += 1
                        self.logger.warning(
                            f"重试 ({job.retry_count}/{max_retries}): {job.job_name} — {result[:80]}"
                        )
                        self.queue.add_job(job)
                    else:
                        self.queue.mark_failed(job, result)

                time.sleep(self.config.interval_time)

        except KeyboardInterrupt:
            self.logger.info("用户中断，停止提交。")
            self.running = False

        # 结果摘要
        self.logger.info("=" * 70)
        self.logger.info("提交结束统计:")
        self.logger.info(f"  成功提交 : {self.queue.submitted_count}")
        self.logger.info(f"  仍待提交 : {self.queue.pending_count}")
        self.logger.info(f"  提交失败 : {self.queue.failed_count}")
        self.logger.info("=" * 70)

        if self.queue.failed:
            self.logger.info("失败作业列表:")
            for j, r in self.queue.failed:
                self.logger.info(f"  {j.job_name}: {r}")

    def stop(self):
        self.running = False


# ─────────────────────────────────────────────────────────────────────────────
# CLI 入口
# ─────────────────────────────────────────────────────────────────────────────

def print_help():
    print("使用方法: python submit_jobs.py <work_directory> [--single | --resume]")
    print()
    print("选项:")
    print("  --single      提交单步计算作业（*_single.sh）")
    print("  --resume      提交续算作业（*_resume.sh）")
    print("  --config <f>  指定配置文件（默认: config/condor.ini）")
    print("  --max-retries 最大重试次数（默认: 3）")
    print("  --help, -h    显示此帮助")
    print()
    print("示例:")
    print("  # VASP 单步 SOC 批量提交")
    print("  python submit_jobs.py mag_soc_vasp/ --single")
    print()
    print("  # 工作流模式")
    print("  python submit_jobs.py work_dir/")
    print()
    print("配置文件: config/condor.ini")
    print("  TOTAL_NODE    — 最大占用节点数")
    print("  MAX_JOBS      — 队列最大任务数")
    print("  INTERVAL_TIME — 每次提交后等待秒数")
    print("  CHECK_TIME    — 队列状态检查间隔秒数")


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print_help()
        sys.exit(0)

    if len(sys.argv) < 2 or sys.argv[1].startswith("-"):
        print_help()
        sys.exit(1)

    work_dir = sys.argv[1]
    include_resume = "--resume" in sys.argv
    include_single = "--single" in sys.argv

    # 可选 --config
    config_file = DEFAULT_CONFIG
    if "--config" in sys.argv:
        idx = sys.argv.index("--config")
        if idx + 1 < len(sys.argv):
            config_file = sys.argv[idx + 1]

    # 可选 --max-retries
    max_retries = 3
    if "--max-retries" in sys.argv:
        idx = sys.argv.index("--max-retries")
        if idx + 1 < len(sys.argv):
            max_retries = int(sys.argv[idx + 1])

    submitter = AutoSubmitter(config_file=config_file)
    try:
        submitter.run(
            work_dir,
            max_retries=max_retries,
            include_resume=include_resume,
            include_single=include_single,
        )
    except KeyboardInterrupt:
        print("\n用户中断，停止提交。")
        submitter.stop()


if __name__ == "__main__":
    main()
