# DFTflow

DFTflow 是面向超算环境的 VASP DFT 自动化计算工作流框架，支持多步骤工作流模式与单步计算模式，并提供基于 Slurm 的作业自动提交与资源控制功能。

---

## 项目结构

```
dftflow/
├── vasp.py                   # 主 CLI 入口
├── submit_jobs.py            # Slurm 作业自动提交脚本
├── analyze.py                # 计算结果分析工具
├── crun.sh / monitor.sh      # 辅助运行脚本
├── config/
│   ├── condor.ini            # 全局配置文件（环境、资源、队列控制）
│   ├── workflow.json         # 工作流步骤定义
│   └── template/             # 各步骤 INCAR 模板（*.yaml）
├── calculation/
│   └── vasp/                 # VASP 输入生成、作业管理、输出解析
└── utils/                    # 通用工具模块
```

---

## 快速开始

### 1. 配置 `config/condor.ini`

```ini
[ENV]
CONDA_PATH = /path/to/miniconda3
CONDA_ENV  = dftflow

[VASP]
VASP_DIR              = /path/to/vasp/bin
VASP_EXE              = vasp_ncl
PSEUDO_POTENTIAL_DIR  = /path/to/pbe

[STRU]
PATH   =               # 默认结构文件目录（可留空，命令行指定）
SUFFIX = *.vasp

[METHOD]
DFT_U = False

[MODULE]
MODULES = intel/oneapi2023.2_noimpi mpi/mpich/4.1.2-icc-oneapi2023.2-ch4

[SOURCE]
FILES = activate dftflow

[ALLOW]
PARTITION             = mars
NODES                 = 1
CORES_PER_NODE        = 64
TOTAL_NODE            = 5      # 最大同时占用节点数
MAX_JOBS              = 10     # 队列最大任务数
INTERVAL_TIME         = 0.5   # 每次提交后等待秒数
CHECK_TIME            = 30    # 队列状态检查间隔（秒）
CONFIG_RELOAD_INTERVAL = 60   # 配置热加载间隔（秒）
```

### 2. 定义工作流 `config/workflow.json`

每个键为一个计算步骤名称，需在 `config/template/` 下有同名 YAML 文件作为 INCAR 模板。

```json
{
  "Test_spin":    { "node": 2, "core": 128, "try_num": 2, "ktype": "M", "kval": [0] },
  "Coarse_relax": { "node": 2, "core": 128, "try_num": 2, "ktype": "M", "kval": [0, 0.08],
                    "parent": "Test_spin", "parent_files": ["POTCAR", "CONTCAR"] },
  "Relax":        { "node": 2, "core": 128, "parent": "Coarse_relax", ... },
  "Scf":          { "node": 2, "core": 128, "parent": "Relax", ... },
  "Band":         { "node": 2, "core": 128, "parent": "Scf",
                    "parent_files": ["POTCAR", "CONTCAR", "CHGCAR", "CHG"] },
  "Dos":          { "node": 2, "core": 128, "parent": "Scf", ... }
}
```

步骤参数说明：

| 参数 | 说明 |
|---|---|
| `node` / `core` | 计算节点数 / 总核心数 |
| `try_num` | 最大重试次数 |
| `ktype` | K 点类型（`M`=Monkhorst-Pack, `G`=Gamma, `L`=Line mode） |
| `kval` | K 点间距列表（逐步细化） |
| `incar_paras` | 各次重试时覆盖的 INCAR 参数列表 |
| `parent` | 依赖的上游步骤名 |
| `parent_files` | 从上游步骤复制的文件列表 |
| `ignore_error` | 遇到错误时是否忽略并继续（`"True"` / `"False"`） |

---

## vasp.py — 主 CLI

```
python vasp.py <command> [options]
```

### 工作流模式

#### `run` — 首次提交（工作流）

扫描结构文件目录，按 `workflow.json` 定义自动生成各步骤输入文件并提交作业。

```bash
python vasp.py run --stru_dir <*.vasp 文件目录>
```

#### `crun` — 续算（工作流）

对已有计算目录中失败或被取消的作业重新生成并提交。

```bash
python vasp.py crun --cdir <计算目录>
```

### 单步计算模式

#### `single` — 单步批量计算

批量读取 CIF/mcif 结构文件，为每个结构生成独立的 POSCAR、INCAR、KPOINTS、POTCAR 及提交脚本，不经过 workflow 流程。

```bash
# 非共线 SOC，k 间距 0.02
python vasp.py single cif_success/ mag_soc_vasp/ -t Scf-Soc -k 0.02 -spin soc

# 共线自旋，k 间距 0.03
python vasp.py single InputPoscar/ work_out/ -t Scf -k 0.03 -spin 2
```

| 选项 | 说明 |
|---|---|
| `-t / --template` | INCAR 模板名（对应 `config/template/<name>.yaml`） |
| `-k / --kval` | K 点间距（Å⁻¹），默认 0.02 |
| `-spin / --spin` | 自旋类型：`1`=非磁，`2`=共线，`soc`=非共线 SOC |
| `--dry-run` | 只生成文件，不提交 |

### 作业管理命令

| 命令 | 功能 |
|---|---|
| `converge --work_dir <dir>` | 检查计算是否收敛 |
| `spin --work_dir <dir>` | 检查计算是否有自旋 |
| `errors --work_dir <dir>` | 自动检查计算错误 |
| `match --work_dir <dir> --log_name <log>` | 匹配日志中的错误信息 |
| `summary --root <dir>` | 汇总目录下所有作业状态 |
| `generate --work_dir <dir>` | 生成输入文件 |
| `update --work_dir <dir>` | 更新已有输入文件 |
| `flush` | 刷新/清理超出节点限制的排队作业 |
| `limit --day/--hour/--mins/--sec` | 取消超过时间限制的作业 |
| `clear --job_id <id>` | 清除指定作业节点上的僵尸进程 |

---

## submit_jobs.py — Slurm 自动提交器

独立的批量提交脚本，适合对已生成的提交脚本进行托管式自动提交，支持资源限制控制和失败重试。

```bash
python submit_jobs.py <work_directory> [选项]
```

### 提交模式

| 命令示例 | 说明 |
|---|---|
| `python submit_jobs.py work_dir/` | 工作流模式（提交普通 `.sh`，排除 `*_resume.sh` 和 `*_single.sh`） |
| `python submit_jobs.py work_dir/ --single` | 单步模式（仅提交 `*_single.sh`） |
| `python submit_jobs.py work_dir/ --resume` | 续算模式（仅提交 `*_resume.sh`） |

### 选项

| 选项 | 说明 |
|---|---|
| `--single` | 提交单步脚本 `*_single.sh` |
| `--resume` | 提交续算脚本 `*_resume.sh` |
| `--config <file>` | 指定配置文件（默认 `config/condor.ini`） |
| `--max-retries <n>` | 最大重试次数（默认 3） |
| `--help / -h` | 显示帮助 |

### 核心功能

- **自动资源控制**：实时查询 Slurm 队列，当占用节点数或任务数接近上限时自动等待
- **配置热加载**：运行期间修改 `condor.ini` 后自动生效，并打印变更 diff
- **失败重试**：提交失败的作业按 `--max-retries` 自动重入队列
- **日志记录**：运行日志保存至 `logs/submit_<timestamp>.log`
- **结束统计**：输出成功/失败/剩余作业数汇总

---

## 依赖

- Python 3.8+
- [click](https://click.palletsprojects.com/)
- VASP 5.x / 6.x
- Slurm 作业调度系统（`sbatch` / `squeue`）
