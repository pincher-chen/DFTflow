#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import click
from queue import Queue
from calculation.vasp.job import VaspRunningJob, RunningRoot
from calculation.npc import Submitter, Producer, Npc
from config import CONDOR
from utils.yhurm import TianHeTime, TianHeWorker, TianHeNodes
from utils.spath import SPath


@click.group()
def vasp():
    pass


@vasp.command()
@click.option("--work_dir", help="work directory")
def converge(work_dir):
    return VaspRunningJob(SPath(work_dir)).is_converge()


@vasp.command()
@click.option("--work_dir", help="work directory")
def spin(work_dir):
    return VaspRunningJob(SPath(work_dir)).is_spin()


@vasp.command()
@click.option("--work_dir", help="work directory")
def errors(work_dir):
    return VaspRunningJob(SPath(work_dir)).automatic_check_errors()


@vasp.command()
@click.option("--log_name", help="log filename")
@click.option("--work_dir", help="work directory")
def match(work_dir, log_name):
    return VaspRunningJob(SPath(work_dir)).get_errors(log_name)


@vasp.command()
@click.option("--root", help="root directory")
def summary(root):
    return RunningRoot(SPath(root)).summary()


@vasp.command()
@click.option("--work_dir", help="work directory")
def generate(work_dir):
    return VaspRunningJob(SPath(work_dir)).get_inputs_file()


@vasp.command()
@click.option("--work_dir", help="work directory")
def update(work_dir):
    return VaspRunningJob(SPath(work_dir)).update_input_files()


@vasp.command()
def flush():
    control_paras = {
        "partition": CONDOR.get("ALLOW", "PARTITION"),
        "total_allowed_node": CONDOR.getint("ALLOW", "TOTAL_NODE"),
    }
    worker = TianHeWorker(**control_paras)
    worker.flush()


@vasp.command()
@click.option("--sec", help="sec limit", default=0)
@click.option("--mins", help="mins limit", default=0)
@click.option("--hour", help="hour limit", default=0)
@click.option("--day", help="day limit", default=0)
def limit(day, hour, mins, sec):
    th_time = TianHeTime(day, hour, mins, sec)
    control_paras = {
        "partition": CONDOR.get("ALLOW", "PARTITION"),
        "total_allowed_node": CONDOR.getint("ALLOW", "TOTAL_NODE"),
    }
    for job in TianHeWorker(**control_paras).yield_time_limit_exceed_jobs(th_time):
        job.yhcancel()


@vasp.command()
@click.option("--job_id", help="job id")
@click.option("--keyword", help="keyword of process name",
              default=CONDOR.get("VASP", "VASP_EXE"))
def clear(job_id, keyword):
    thn = TianHeNodes(job_id)
    thn.kill_zombie_process_on_nodes(key_word=keyword)


@vasp.command()
@click.option("--stime", help="interval time(sec) between submit job", default=0.5)
@click.option("--ftime", help="interval time(sec) between yhi", default=60)
@click.option("--qsize", help="queue size, default: 20", default=20)
@click.option("--process", help="multiprocessing num, default: 4", default=4)
@click.option("--pat", help="structure files type, default: *.vasp",
              default=f"{CONDOR.get('STRU', 'SUFFIX')}")
@click.option("--stru_dir", help="structure files directory",
              default=f"{CONDOR.get('STRU', 'PATH')}")
def run(stru_dir, pat, process=4, qsize=20, stime=0.5, ftime=60):
    job_queue = Queue(maxsize=qsize)
    control_paras = {
        "partition": CONDOR.get("ALLOW", "PARTITION"),
        "total_allowed_node": CONDOR.getint("ALLOW", "TOTAL_NODE"),
    }

    mana = Npc(SPath(stru_dir), interval_time=stime)
    mana.init_jobs(pat, process)
    producer = Producer(queue=job_queue)
    submitter = Submitter(job_queue, stime, ftime, **control_paras)

    producer.start()
    submitter.start()

@vasp.command()
@click.option("--cdir", help="calculation dir")
def crun(cdir, process=4, qsize=20, stime=0.5, ftime=60):
    job_queue = Queue(maxsize=qsize)
    control_paras = {
        "partition": CONDOR.get("ALLOW", "PARTITION"),
        "total_allowed_node": CONDOR.getint("ALLOW", "TOTAL_NODE"),
    }
    mana = Npc(SPath(cdir), interval_time=stime)
    mana.cinit_jobs(process)
    producer = Producer(queue=job_queue)
    submitter = Submitter(job_queue, stime, ftime, **control_paras)

    producer.start()
    submitter.start()

@vasp.command()
@click.argument("stru_path")
@click.argument("work_dir")
@click.option("-t", "--template", required=True,
              help="INCAR 模板名（对应 config/template/<name>.yaml，如 Scf-Soc）")
@click.option("-k", "--kval", default=0.02, show_default=True,
              help="K 点间距（Å⁻¹）")
@click.option("-spin", "--spin", default="1", show_default=True,
              type=click.Choice(["1", "2", "soc"]),
              help="自旋设置：1=非磁, 2=共线自旋, soc=非共线 SOC (LSORBIT+LNONCOLLINEAR)")
@click.option("--dry-run", is_flag=True, default=False,
              help="只生成输入文件和脚本，不打印提交提示")
def single(stru_path, work_dir, template, kval, spin, dry_run):
    """单步计算模式 - 不使用 workflow，只执行一个 step。

    批量读取 STRU_PATH 目录中的 CIF/mcif 文件，为每个结构在 WORK_DIR 下
    创建独立作业目录，生成 POSCAR / INCAR / KPOINTS / POTCAR 及提交脚本。

    示例：

    \b
      # 非共线 SOC，k 间距 0.02
      python vasp.py single cif_success/ mag_soc_vasp/ -t Scf-Soc -k 0.02 -spin soc

    \b
      # 共线自旋，k 间距 0.03
      python vasp.py single InputPoscar/ work_out/ -t Scf -k 0.03 -spin 2
    """
    from calculation.vasp.single_generator import VaspSingleGenerator
    # 统一转为内部整数表示：1/2/soc→1/2/4
    _spin_map = {"1": 1, "2": 2, "soc": 4}
    gen = VaspSingleGenerator(
        stru_path=stru_path,
        work_dir=work_dir,
        template=template,
        kval=kval,
        spin=_spin_map[spin],
        dry_run=dry_run,
    )
    gen.run()


if __name__ == '__main__':
    vasp()
