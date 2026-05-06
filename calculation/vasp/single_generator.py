#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VaspSingleGenerator
-------------------
批量将 CIF/mcif 结构转换为 VASP 单步计算作业目录，并生成 *_single.sh 提交脚本。

用法（通过 vasp.py single 调用）：
    python vasp.py single <stru_path> <work_dir> -t Scf-Soc -k 0.02 -spin soc

参数：
    stru_path   : 包含 CIF/mcif 文件的目录（或单个文件）
    work_dir    : 输出作业目录
    template    : config/template/ 下的 YAML 模板名（如 Scf-Soc）
    kval        : k 间距，单位 Å⁻¹（默认 0.02）
    spin        : 1=非磁, 2=共线, soc=非共线 SOC（默认 1）
    dry_run     : 仅生成脚本，不打印提交提示
"""

import math
import stat
from datetime import datetime
from pathlib import Path

import numpy as np

from config import CONDOR, INCAR_TEMPLATE
from utils.spath import SPath
from calculation.vasp.inputs import INCAR, KPOINTS, POSCAR, POTCAR, KPOINTSModes
from calculation.vasp.inputs.potcar import DEFAULT_PP


def _read_magmoms_from_cif(cif_path):
    """
    直接解析 CIF/mcif 文件中的 _atom_site_moment 字段，读取磁矩信息。

    兼容 CIF v1（下划线）和 CIF v2/MCIF（点号）两种命名风格，
    以及带不确定度的数值格式（如 '3.96(5)'）。

    Returns
    -------
    list[float]       共线磁性：[m1, m2, ...]
    list[list[float]] 非共线磁性：[[mx1,my1,mz1], [mx2,my2,mz2], ...]
    None              文件中无磁矩信息
    """
    def _cif_float(s):
        s = s.strip()
        if '(' in s:
            s = s.split('(', 1)[0]
        return float(s)

    def _parse_loop(lines, start_idx):
        headers, rows, i = [], [], start_idx
        while i < len(lines):
            s = lines[i].strip()
            if not s:
                i += 1; continue
            if s.startswith('_'):
                headers.append(s.split()[0]); i += 1; continue
            break
        while i < len(lines):
            s = lines[i].strip()
            if not s or s.startswith('#') or s.startswith('loop_') or s.startswith('_'):
                break
            rows.append(s.split()); i += 1
        return headers, rows, i

    try:
        with open(str(cif_path), 'r') as f:
            lines = f.read().splitlines()

        # 1. 解析 atom_site loop，获取 (label, occupancy) 列表
        #    保留占位率用于后续过滤混占副标签
        atom_site_rows = []   # [(label, occupancy), ...]
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if s == 'loop_':
                headers, rows, next_i = _parse_loop(lines, i + 1)
                hn = [h.replace('.', '_') for h in headers]
                _label_key = next((h for h in hn if h == '_atom_site_label'), None)
                if _label_key:
                    label_col = hn.index(_label_key)
                    # 尝试读占位率列
                    occ_key = next(
                        (h for h in hn if 'occupancy' in h or '_atom_site_occupancy' == h),
                        None
                    )
                    occ_col = hn.index(occ_key) if occ_key else None
                    for r in rows:
                        if label_col < len(r):
                            lab = r[label_col]
                            try:
                                occ = _cif_float(r[occ_col]) if occ_col is not None else 1.0
                            except Exception:
                                occ = 1.0
                            atom_site_rows.append((lab, occ))
                i = next_i
            else:
                i += 1

        # ── 混占位过滤 ──────────────────────────────────────────────────────
        # 同一位置上多个标签共享（部分占位），只保留每组中占位率最高的标签。
        # 判断依据：对每个 (fractional_x, fractional_y, fractional_z) 坐标，
        # 取 occupancy 最大的那个标签作为"主标签"。
        # 若 atom_site 没有坐标列，则退化为：相同元素符号+相近编号的标签只取一个。
        #
        # 简洁实现：坐标不方便在此直接获取，因此用"按位置去重"的策略：
        # 先解析一遍带坐标的 atom_site，建立 (frac_x,frac_y,frac_z) → (label, occ) 映射。
        atom_site_coord_rows = []   # [(label, occ, x, y, z), ...]
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if s == 'loop_':
                headers, rows, next_i = _parse_loop(lines, i + 1)
                hn = [h.replace('.', '_') for h in headers]
                lk  = next((h for h in hn if h == '_atom_site_label'), None)
                xk  = next((h for h in hn if h in ('_atom_site_fract_x', '_atom_site_fract_x')), None)
                yk  = next((h for h in hn if h in ('_atom_site_fract_y',)), None)
                zk  = next((h for h in hn if h in ('_atom_site_fract_z',)), None)
                ok  = next((h for h in hn if 'occupancy' in h), None)
                if lk and xk and yk and zk:
                    li, xi, yi, zi = hn.index(lk), hn.index(xk), hn.index(yk), hn.index(zk)
                    oi = hn.index(ok) if ok else None
                    for r in rows:
                        try:
                            lab = r[li]
                            x, y, z = _cif_float(r[xi]), _cif_float(r[yi]), _cif_float(r[zi])
                            occ = _cif_float(r[oi]) if oi is not None else 1.0
                            atom_site_coord_rows.append((lab, occ, x, y, z))
                        except Exception:
                            pass
                i = next_i
            else:
                i += 1

        # 将同一坐标位置（精度 1e-3）的标签聚合，保留占位率最大者为"主标签"
        primary_labels = set()
        if atom_site_coord_rows:
            site_map = {}  # (ix,iy,iz) → (label, occ)
            for lab, occ, x, y, z in atom_site_coord_rows:
                key = (round(x, 3), round(y, 3), round(z, 3))
                if key not in site_map or occ > site_map[key][1]:
                    site_map[key] = (lab, occ)
            primary_labels = {v[0] for v in site_map.values()}

        # 2. 只保留主标签的 atom_labels（用于后续展开）
        if primary_labels:
            atom_labels = [lab for lab, occ in atom_site_rows if lab in primary_labels]
        else:
            atom_labels = [lab for lab, occ in atom_site_rows]

        # 2. 解析 moment loop：label -> (mx, my, mz)
        moment_map = {}
        i = 0
        while i < len(lines):
            s = lines[i].strip()
            if s == 'loop_':
                headers, rows, next_i = _parse_loop(lines, i + 1)
                _mh   = {h.replace('.', '_') for h in headers}
                _hmap = {h.replace('.', '_'): h for h in headers}
                if ('_atom_site_moment_label' in _mh and
                        '_atom_site_moment_crystalaxis_x' in _mh and
                        '_atom_site_moment_crystalaxis_y' in _mh and
                        '_atom_site_moment_crystalaxis_z' in _mh):
                    c_lab = headers.index(_hmap['_atom_site_moment_label'])
                    c_x   = headers.index(_hmap['_atom_site_moment_crystalaxis_x'])
                    c_y   = headers.index(_hmap['_atom_site_moment_crystalaxis_y'])
                    c_z   = headers.index(_hmap['_atom_site_moment_crystalaxis_z'])
                    for r in rows:
                        try:
                            moment_map[r[c_lab]] = (
                                _cif_float(r[c_x]),
                                _cif_float(r[c_y]),
                                _cif_float(r[c_z]),
                            )
                        except Exception:
                            continue
                i = next_i
            else:
                i += 1

        if not moment_map:
            return None

        # 3. 按过滤后的 atom_labels 顺序展开
        #    若某主标签不在 moment_map，尝试用同一位置的副标签磁矩补全
        if primary_labels and atom_site_coord_rows:
            # 建立 主标签 → 同坐标所有标签 的映射，用于回退查找
            coord_to_all = {}
            for lab, occ, x, y, z in atom_site_coord_rows:
                key = (round(x, 3), round(y, 3), round(z, 3))
                coord_to_all.setdefault(key, []).append(lab)
            lab_to_coord = {
                lab: (round(x, 3), round(y, 3), round(z, 3))
                for lab, occ, x, y, z in atom_site_coord_rows
            }

            def _get_moment(lab):
                if lab in moment_map:
                    return list(moment_map[lab])
                # 回退：同位置的其他标签有磁矩？
                coord = lab_to_coord.get(lab)
                if coord:
                    for sibling in coord_to_all.get(coord, []):
                        if sibling in moment_map:
                            return list(moment_map[sibling])
                return [0.0, 0.0, 0.0]

            magmoms_vec = [_get_moment(lab) for lab in atom_labels]
        else:
            magmoms_vec = [
                list(moment_map[lab]) if lab in moment_map else [0.0, 0.0, 0.0]
                for lab in atom_labels
            ]

        # 共线判断（全部磁矩的 x/y 分量近零）
        if all(abs(m[0]) < 1e-6 and abs(m[1]) < 1e-6 for m in magmoms_vec):
            return [m[2] for m in magmoms_vec]
        return magmoms_vec

    except Exception as e:
        print(f"[WARNING] Failed to read magnetic moments from CIF: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# CIF 预检：检测 ASE mcif 读取可能导致内存爆炸的危险特征
# ─────────────────────────────────────────────────────────────────────────────

def _cif_preflight(cif_path: Path):
    """
    快速扫描 CIF/mcif 文件，检测已知会导致 ASE 对称展开爆炸的特征：

    1. 多 k 矢量（2k/3k 磁结构）：ASE 会尝试构造容纳所有 k 的超胞
    2. 反平移对称（anti-centering，centering 操作含 ,+1 与 ,-1 同时出现）：
       ASE 会再次翻倍晶胞以容纳磁矩反向位点

    这两类特征会使原子数指数增长，导致 [Errno 12] Cannot allocate memory
    并最终引发 C 层 segfault（无法被 Python 的 try/except 捕获）。

    返回 (safe: bool, reason: str)
      safe=True  → 可以用 format="mcif" 安全读取
      safe=False → 应改用 format="cif" 只读晶体结构，磁矩另行解析
    """
    try:
        content = cif_path.read_text(errors='replace')

        # 1. 多 k 矢量：_parent_propagation_vector loop 中有 2 行以上 k 数据
        kvec_lines = re.findall(
            r'^\s*k\d+\s+\[', content, re.MULTILINE
        )
        if len(kvec_lines) > 1:
            return False, f"多 k 矢量磁结构（{len(kvec_lines)}k）"

        # 2. 反平移对称：centering 操作中同时出现 ,+1 和 ,-1
        centering_block = re.search(
            r'_space_group_symop_magn_centering\.xyz(.*?)(?=loop_|\Z)',
            content, re.DOTALL
        )
        if centering_block:
            ops = centering_block.group(1)
            if re.search(r',\s*-1', ops) and re.search(r',\s*\+?1\b', ops):
                return False, "含反平移对称（anti-centering，,-1）"

    except Exception:
        pass

    return True, ""


# ─────────────────────────────────────────────────────────────────────────────
# 结构读取：CIF / mcif → dftflow POSCAR
# ─────────────────────────────────────────────────────────────────────────────

def _read_structure(cif_path: Path):
    """
    读取 CIF/mcif 文件，返回 (ase_atoms, dftflow_poscar, magmoms_3d)。

    磁矩优先从 _atom_site_moment 字段读取（MAGNDATA mcif 格式），
    ASE 读不到时全零填充。

    对多 k / 反平移等危险 CIF，跳过 mcif 展开，改用 cif 格式只读晶体结构，
    避免 ASE 对称展开导致内存溢出与 segfault。

    magmoms_3d : ndarray, shape (N, 3)
    """
    from ase.io import read
    from ase.io.vasp import write_vasp
    import io
    import warnings

    # ── 预检：检测危险 CIF 特征 ──────────────────────────────────────────────
    safe, reason = _cif_preflight(cif_path)
    if not safe:
        print(f"  [INFO] {cif_path.stem}: {reason}，跳过 mcif 对称展开，改用 cif 格式读取晶体结构")

    # 读结构（抑制 CIF v2.0 和 token 警告）
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        # 危险 CIF 直接用 cif 格式（只读晶体结构，跳过磁对称展开）
        # 安全 CIF 优先尝试 mcif（保留更多磁性信息）
        if not safe:
            try:
                atoms = read(str(cif_path), format="cif")
            except Exception as e:
                raise RuntimeError(f"cif 格式读取失败: {e}") from e
        else:
            try:
                atoms = read(str(cif_path), format="mcif")
            except Exception:
                atoms = read(str(cif_path), format="cif")

    # 写成 VASP POSCAR，再用 dftflow POSCAR 解析（保持 dftflow 内部一致性）
    buf = io.StringIO()
    write_vasp(buf, atoms, direct=True, sort=False, vasp5=True)
    buf.seek(0)
    poscar_text = buf.read()

    tmp_poscar = Path("/tmp") / f"_dftflow_tmp_{cif_path.stem}.POSCAR"
    tmp_poscar.write_text(poscar_text)
    poscar = POSCAR.from_file(SPath(str(tmp_poscar)))
    tmp_poscar.unlink(missing_ok=True)

    # ── 磁矩：优先用 CIF 解析函数 ──────────────────────────────────────────
    natoms = len(atoms)
    cif_magmoms = _read_magmoms_from_cif(cif_path)  # list or None

    if cif_magmoms is not None:
        # read_magmoms_from_cif 返回的可能是共线 [m1, m2, ...] 或
        # 非共线 [[mx,my,mz], ...]，统一扩展到 (N, 3)
        raw = np.array(cif_magmoms, dtype=float)
        if raw.ndim == 1:
            # 共线值是沿各晶轴方向的标量——此处默认沿 z（通常已是共线情形）
            magmoms_3d_crys = np.column_stack([np.zeros(natoms), np.zeros(natoms), raw])
        else:
            magmoms_3d_crys = raw  # shape (N, 3)，晶轴坐标分量

        # ── 长度对齐：CIF atom_site 条目数可能与 ASE 解析的原子数不一致
        # 典型场景：混占位（如 Fe/Mo 共占同一位置）在 mcif 中被展开为两条
        # atom_site 记录，但 ASE 合并为一个原子。此时 CIF 侧条目数 > natoms，
        # 需截断到 natoms；反之若 CIF 条目较少，则补零。
        n_cif = len(magmoms_3d_crys)
        if n_cif != natoms:
            print(f"  [INFO] CIF atom_site 条目数({n_cif}) ≠ ASE 原子数({natoms})，"
                  f"可能存在混占位合并，磁矩将{'截断' if n_cif > natoms else '补零'}至 {natoms} 个原子。")
            if n_cif > natoms:
                magmoms_3d_crys = magmoms_3d_crys[:natoms]
            else:
                pad = np.zeros((natoms - n_cif, 3))
                magmoms_3d_crys = np.vstack([magmoms_3d_crys, pad])

        # ── crystal axes → Cartesian 坐标变换 ─────────────────────────────
        # mcif 的 crystalaxis_x/y/z 是沿晶轴**单位向量**方向的分量（μB）
        # VASP MAGMOM 需要笛卡尔分量；对正交晶系两者相同，对斜方/三斜则不同
        latt = poscar.lattice.lattice          # 3×3，行向量 [a; b; c]（Å）
        a_hat = latt[0] / np.linalg.norm(latt[0])
        b_hat = latt[1] / np.linalg.norm(latt[1])
        c_hat = latt[2] / np.linalg.norm(latt[2])
        M_crys2cart = np.column_stack([a_hat, b_hat, c_hat])  # (3,3)

        # 批量变换：(N,3) × (3,3)^T = (N,3)
        magmoms_3d = (M_crys2cart @ magmoms_3d_crys.T).T

    else:
        # 回退：从 ASE 读取（已是笛卡尔坐标）
        raw_mag = atoms.get_initial_magnetic_moments()
        if raw_mag.ndim == 1:
            magmoms_3d = np.column_stack([
                np.zeros(natoms), np.zeros(natoms), raw_mag
            ])
        else:
            magmoms_3d = np.asarray(raw_mag, dtype=float)

    return atoms, poscar, magmoms_3d


# ─────────────────────────────────────────────────────────────────────────────
# INCAR 生成
# ─────────────────────────────────────────────────────────────────────────────

def _build_incar(template_name: str, spin: int, poscar: POSCAR,
                 magmoms_3d: np.ndarray) -> INCAR:
    """
    从 template_name.yaml 读取 INCAR 参数，然后根据 spin 设置添加/覆盖参数。

    spin=1  : 非磁（ISPIN=1）
    spin=2  : 共线磁（ISPIN=2，MAGMOM 为标量）
    spin=4  : 非共线 SOC（ISPIN=2, LSORBIT=T, LNONCOLLINEAR=T, MAGMOM 3 分量）
    """
    incar_paras = INCAR_TEMPLATE.get(template_name)
    if incar_paras is None:
        available = list(INCAR_TEMPLATE.keys())
        raise KeyError(
            f"Template '{template_name}' not found. "
            f"Available templates: {available}"
        )
    incar = INCAR(**incar_paras)

    if spin == 1:
        incar["ISPIN"] = 1
        # 确保删除磁性相关参数
        for key in ("LSORBIT", "LNONCOLLINEAR", "MAGMOM", "LMAXMIX"):
            incar._paras.pop(key, None)

    elif spin == 2:
        incar["ISPIN"] = 2
        incar._paras.pop("LSORBIT", None)
        incar._paras.pop("LNONCOLLINEAR", None)
        # MAGMOM 标量，直接写入 _paras（绕过 __setitem__ 的 str 转换）
        magmom_flat = []
        for idx, num in enumerate(poscar.symbol_num):
            start = sum(poscar.symbol_num[:idx])
            vals = magmoms_3d[start: start + num, 2]  # 取 z 分量
            magmom_flat.extend([round(float(v), 3) for v in vals])
        incar._paras["MAGMOM"] = magmom_flat

    elif spin == 4:
        incar["ISPIN"] = 2
        # 直接写入 _paras 以保留 VASP 格式的 .TRUE. 字符串（而非 Python bool）
        incar._paras["LSORBIT"] = ".TRUE."
        incar._paras["LNONCOLLINEAR"] = ".TRUE."
        incar["LMAXMIX"] = 4
        # MAGMOM：每原子 3 分量，展平为 [mx1, my1, mz1, ...]
        # 直接写入 _paras 绕过 __setitem__ 的 str() 转换问题
        magmom_flat = []
        for row in magmoms_3d:
            magmom_flat.extend([round(float(v), 4) for v in row])
        incar._paras["MAGMOM"] = magmom_flat

    else:
        raise ValueError(f"spin must be 1, 2 or 4, got {spin}")

    # DFT+U
    dft_u = CONDOR.get("METHOD", "DFT_U", fallback="False")
    if dft_u.lower()[0] == "t":
        hubbard_u = poscar.get_hubbard_u_if_need()
        if hubbard_u is not None:
            for lb, v in hubbard_u.items():
                incar[lb] = v

    return incar


# ─────────────────────────────────────────────────────────────────────────────
# 自动资源分配
# ─────────────────────────────────────────────────────────────────────────────

def _auto_resource(natoms: int):
    """根据原子数估算所需节点数和进程数。

    分档规则（参考 abacusflow.auto_select_resources）：
      ≤  3 原子 : 1 节点, 16 进程
      ≤  8 原子 : 1 节点, 32 进程
      ≤ 20 原子 : 1 节点, 64 进程（受 CORES_PER_NODE 上限）
      ≤ 60 原子 : 1 节点, 满节点（CORES_PER_NODE）
      > 60 原子 : 2 节点, 2 × CORES_PER_NODE 进程

    `CORES_PER_NODE` 取自 config/condor.ini [ALLOW] 节，默认 64。
    """
    cores_per_node = int(CONDOR.get("ALLOW", "CORES_PER_NODE", fallback=64))

    if natoms <= 3:
        nodes, procs = 1, 16
    elif natoms <= 8:
        nodes, procs = 1, 32
    elif natoms <= 20:
        nodes, procs = 1, 64
    elif natoms <= 60:
        nodes, procs = 1, cores_per_node
    else:
        nodes, procs = 2, 2 * cores_per_node

    # 单节点时进程数不超过该节点的核心数上限
    if nodes == 1:
        procs = min(procs, cores_per_node)

    return nodes, procs


# ─────────────────────────────────────────────────────────────────────────────
# Shell 提交脚本生成
# ─────────────────────────────────────────────────────────────────────────────

def _build_single_sh(job_name: str, job_dir: Path,
                     nodes: int, cores: int,
                     partition: str, vasp_exe: str,
                     modules: str, template_name: str, kval: float,
                     conda_path: str, conda_env: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    mod_list = modules.split()
    mod_load_lines = "\n".join(f"module load {m}" for m in mod_list)

    return f"""\
#!/bin/bash
# VASP single-step calculation: {job_name}
# Template : {template_name}
# K-spacing: {kval} Å⁻¹
# Generated: {now}
# Resources: {nodes} node(s), {cores} cores

export OMP_NUM_THREADS=1

source {conda_path}/etc/profile.d/conda.sh
conda activate {conda_env}

# 加载 module 环境
export MODULESHOME=/usr/share/modules
export MODULEPATH=/APP/u22/x86/modulepath/Compilers:/APP/u22/x86/modulepath/application
export MODULES_CMD=/usr/lib/x86_64-linux-gnu/modulecmd.tcl
ml() {{ module ml "$@"; }}
module() {{ _module_raw "$@" 2>&1; }}
_module_raw() {{ eval `/usr/bin/tclsh8.6 /usr/lib/x86_64-linux-gnu/modulecmd.tcl bash "$@"`; }}
{mod_load_lines}

cd "{job_dir}" || exit 1

echo "[...] VASP SINGLE START: {job_name}"
echo "[...] Template  : {template_name}"
echo "[...] K-spacing : {kval} Å⁻¹"
echo "[...] WorkDir   : $(pwd)"

START_TIME=$(date +%s)
echo "[INFO] Started at $(date '+%Y-%m-%d %H:%M:%S')"

yhrun -N {nodes} -n {cores} -p {partition} {vasp_exe} > vasp.log 2>&1
EXIT_CODE=$?

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
HOURS=$(awk "BEGIN {{printf \\"%.2f\\", $DURATION/3600}}")
CORE_HOURS=$(awk "BEGIN {{printf \\"%.2f\\", {nodes}*{cores}*$HOURS}}")

echo ""
echo "============================================================"
echo "                 VASP CALCULATION SUMMARY"
echo "============================================================"
echo "[INFO] Job      : {job_name}"
echo "[INFO] Template : {template_name}"
echo "[INFO] Duration : ${{DURATION}}s (${{HOURS}}h)"
echo "[INFO] CoreHours: ${{CORE_HOURS}}"

# 判断收敛
if grep -q "reached required accuracy" vasp.log 2>/dev/null; then
    echo "[✓] SCF CONVERGED"
    echo "success" > status.txt
elif [ $EXIT_CODE -ne 0 ]; then
    echo "[✗] VASP exited with error (code $EXIT_CODE)"
    echo "failed" > status.txt
elif grep -q "General timing and accounting" vasp.log 2>/dev/null || \\
     grep -q "General timing and accounting" OUTCAR 2>/dev/null; then
    echo "[?] VASP finished but convergence unclear – check OUTCAR"
    echo "finished" > status.txt
else
    echo "[✗] VASP did not finish normally"
    echo "unknown" > status.txt
fi

echo "============================================================"
echo "[...] VASP SINGLE DONE: {job_name}"
"""


# ─────────────────────────────────────────────────────────────────────────────
# 主生成器类
# ─────────────────────────────────────────────────────────────────────────────

class VaspSingleGenerator:
    """
    批量生成 VASP 单步计算作业目录。

    Parameters
    ----------
    stru_path : str | Path
        CIF/mcif 文件所在目录（或单个文件路径）。
    work_dir : str | Path
        作业输出根目录，每个结构在此下创建子目录。
    template : str
        INCAR 模板名，对应 config/template/<template>.yaml。
    kval : float
        k 间距（Å⁻¹），默认 0.02。
    spin : int
        1=非磁, 2=共线, 4=非共线 SOC。
    dry_run : bool
        若为 True，只生成文件不打印提交提示。
    """

    # CIF 文件后缀
    CIF_SUFFIXES = (".cif", ".mcif")

    def __init__(self, stru_path, work_dir, template: str,
                 kval: float = 0.02, spin: int = 1, dry_run: bool = False):
        self.stru_path = Path(stru_path)
        self.work_dir = Path(work_dir)
        self.template = template
        self.kval = kval
        self.spin = spin
        self.dry_run = dry_run

        # 从 condor.ini 读取配置
        self.vasp_exe = str(
            Path(CONDOR.get("VASP", "VASP_DIR")) /
            CONDOR.get("VASP", "VASP_EXE")
        )
        self.potcar_lib = SPath(CONDOR.get("VASP", "PSEUDO_POTENTIAL_DIR").strip())
        self.partition  = CONDOR.get("ALLOW", "PARTITION")
        self.modules    = CONDOR.get("MODULE", "MODULES")
        self.conda_path = CONDOR.get("ENV", "CONDA_PATH", fallback="/opt/miniconda3")
        self.conda_env  = CONDOR.get("ENV", "CONDA_ENV",  fallback="base")

    # ── 收集结构文件 ─────────────────────────────────────────────────────────

    def _collect_structures(self):
        if self.stru_path.is_file():
            return [self.stru_path]
        files = []
        for suf in self.CIF_SUFFIXES:
            files.extend(sorted(self.stru_path.glob(f"*{suf}")))
        return files

    # ── 单个结构处理 ─────────────────────────────────────────────────────────

    def _process_one(self, cif_path: Path) -> bool:
        job_name = cif_path.stem
        job_dir = self.work_dir / job_name
        job_dir.mkdir(parents=True, exist_ok=True)

        poscar_file = job_dir / "POSCAR"
        incar_file  = SPath(str(job_dir / "INCAR"))
        kpoints_file = SPath(str(job_dir / "KPOINTS"))
        potcar_file  = SPath(str(job_dir / "POTCAR"))
        sh_file      = job_dir / f"{job_name}_single.sh"

        # 跳过已成功的作业
        status_file = job_dir / "status.txt"
        if status_file.exists() and status_file.read_text().strip() == "success":
            print(f"  [SKIP] {job_name} (already success)")
            return True

        try:
            # 1. 读取结构
            atoms, poscar, magmoms_3d = _read_structure(cif_path)
            natoms = len(atoms)

            # 2. 写 POSCAR（若不存在）
            # 使用 ASE write_vasp 直接写出，保证 VASP 标准格式（空格分隔元素符号）。
            # dftflow POSCAR.__repr__ 用 tab 分隔元素行，VASP 解析器遇 tab 会截断，
            # 导致 "type information not consistent" 报错。
            if not poscar_file.exists():
                from ase.io.vasp import write_vasp
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    with open(poscar_file, 'w') as _pf:
                        write_vasp(_pf, atoms, direct=True, sort=False, vasp5=True)

            # 3. 生成 INCAR（已有文件自动备份为 INCAR_step_0）
            incar = _build_incar(self.template, self.spin, poscar, magmoms_3d)
            incar.write(incar_file)

            # 4. 生成 KPOINTS（已有文件自动备份为 KPOINTS_step_0）
            kpoints = KPOINTS(style=KPOINTSModes.Gamma)
            kpoints.get_kmesh(poscar, self.kval)
            kpoints.write(kpoints_file)
            kx, ky, kz = kpoints.kmesh
            print(f"  [{job_name}] natoms={natoms}, K={kx}x{ky}x{kz}")

            # 5. 生成 POTCAR（若不存在）
            if not potcar_file.exists():
                POTCAR(lib=self.potcar_lib).cat(poscar, potcar_file)

            # 6. 生成提交脚本（总是覆盖，确保与最新 condor.ini 一致）
            nodes, cores = _auto_resource(natoms)
            script = _build_single_sh(
                job_name=job_name,
                job_dir=job_dir,
                nodes=nodes,
                cores=cores,
                partition=self.partition,
                vasp_exe=self.vasp_exe,
                modules=self.modules,
                template_name=self.template,
                kval=self.kval,
                conda_path=self.conda_path,
                conda_env=self.conda_env,
            )
            sh_file.write_text(script)
            sh_file.chmod(sh_file.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

            return True

        except Exception as exc:
            print(f"  [ERROR] {job_name}: {exc}")
            return False

    # ── 批量入口 ─────────────────────────────────────────────────────────────

    def run(self):
        self.work_dir.mkdir(parents=True, exist_ok=True)
        cif_files = self._collect_structures()

        if not cif_files:
            print(f"[WARN] No CIF/mcif files found in: {self.stru_path}")
            return

        print(f"[INFO] Found {len(cif_files)} structure file(s) in {self.stru_path}")
        print(f"[INFO] Template={self.template}, kval={self.kval}, spin={self.spin}")
        print(f"[INFO] Work dir: {self.work_dir}")
        print()

        ok, fail = 0, 0
        for cif in cif_files:
            if self._process_one(cif):
                ok += 1
            else:
                fail += 1

        print()
        print(f"[INFO] Done: {ok} prepared, {fail} failed")
        if not self.dry_run:
            print(f"[INFO] Submit with:")
            print(f"       python <abacusflow>/submit_jobs.py {self.work_dir} --single")
