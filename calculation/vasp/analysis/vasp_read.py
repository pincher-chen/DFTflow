#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import multiprocessing
import numpy as np
from analysis import wash
import copy
from crystal import struct
import re


def read_osizcar(osi_pth, mag=True):
    oszicar = wash.read_line_from_file(osi_pth)
    opt_step = [i for i in oszicar if "F=" in i]
    regex_list = [r"(\d+?)\s+?F",
                  r"mag=\s+(-?\d+.\d+)",
                  r"F=\s+?(-?.*)\s+E0",
                  r"E0=\s+?(-?.*)\s+d E",
                  r" d E =(.*)\s+?mag"]
    info = ['step', 'mag', 'F', 'E0', 'dE']
    if not mag:
        info = info[:-1]
    odl = []
    for j in range(len(regex_list)):
        try:
            opt_data = [float("".join(re.findall(regex_list[j], i))) for i in opt_step]
        except:
            continue
        else:
            od = {info[j]: opt_data}
            odl.append(od)
    total_od = wash.merge_into_one(odl)

    return total_od


def read_kpath(kph_pth):
    un_prc_kpath = wash.read_line_from_file(kph_pth)
    prc_kpath = wash.data_fmt_trans(fmt_type='str', input=un_prc_kpath)

    def if_file_correct(cldt):
        for i in cldt:
            i_string = " ".join(i)
            if re.search(r"rec", i_string, re.I):
                head_index = cldt.index(i)
                return head_index

        return None

    index = if_file_correct(prc_kpath)
    if index is not None:
        hk_file_body = prc_kpath[index + 1:]
    else:
        raise Exception("KPOINTS FileTypeError")

    try:
        y = lambda x: ((wash.data_fmt_trans(fmt_type='array', input=x[:3])), x[-1].strip('\\'))
    except:
        raise Exception("KPOINTS kpath error")
    else:
        ptl = list(map(y, hk_file_body))

    return ptl


def read_eignval(eig_pth):
    un_prc_eig = wash.read_line_from_file(eig_pth)
    prc_eig = wash.data_fmt_trans(fmt_type='str', input=un_prc_eig)
    spin_symbol = prc_eig[0][-1]
    try:
        if spin_symbol == '1':
            spin = False
        elif spin_symbol == '2':
            spin = True
        else:
            raise Exception("EIGENVAL spin symbol error")
    except:
        raise Exception("EIGENVAL spin symbol error")

    try:
        nbands = int(prc_eig[5][-1])
    except:
        raise Exception("EIGENVAL nbands error")
    try:
        integral_kpoints_num = int(prc_eig[5][1])
    except:
        raise Exception("EIGENVAL integral_kpoints_number error")

    integral_kpoints_list, \
    integral_kpoints_band_data = wash.split_data(prc_eig[6:], nbands)

    array_kpl = wash.data_fmt_trans(fmt_type='array', input=integral_kpoints_list)
    array_kbd = wash.data_fmt_trans(fmt_type='array', input=integral_kpoints_band_data)

    return {'spin': spin,
            'nbands': nbands,
            'integral_kpoints_number': integral_kpoints_num,
            'integral_kpoints_list': array_kpl,
            'band_data': array_kbd}


def read_doscar(dos_pth):
    un_prc_dos = wash.read_line_from_file(dos_pth)
    prc_dos = wash.data_fmt_trans(fmt_type='str', input=un_prc_dos)
    nedos, e_fermi = int(prc_dos[5][2]), float(prc_dos[5][3])
    try:
        tdos_data = wash.data_fmt_trans(fmt_type='array', input=prc_dos[6: 6 + nedos])
        diff_atoms_para_list, pdos_data_list = wash.split_data(prc_dos[6 + nedos:], nedos)
        pdos_data = wash.data_fmt_trans(fmt_type='array', input=pdos_data_list)
    except:
        raise Exception("DOSCAR error")
    else:
        return {'nedos': nedos,
                'E-fermi': e_fermi,
                'tdos_data': tdos_data,
                'pdos_data': pdos_data}


def read_incar(inca_pth):
    un_prc_incar = wash.read_line_from_file(inca_pth)
    prc_incar = wash.data_fmt_trans(fmt_type='str', input=un_prc_incar)

    def count_equal_sign(in_string):

        def find_para(para_str):
            return re.findall(r"(.*?)[=](.*)", para_str)

        eq_num = in_string.count("=")
        if eq_num == 1:
            pct = find_para(in_string)
        else:
            all_pct = in_string.split(";")
            pct = list(map(find_para, all_pct))
        z = lambda x: {x[0]: x[1]}
        if len(pct) == 1:
            p = list(map(z, pct))
        else:
            p = []
            for i in pct:
                pi = list(map(z, i))
                p.append(pi)
        merge_p = wash.merge_into_one(p)

        while isinstance(merge_p, list):
            merge_p = wash.merge_into_one(merge_p)

        return merge_p

    para_total_list = []
    for para_setting in prc_incar:
        string_para = "".join(para_setting)
        _para = count_equal_sign(string_para)
        para_total_list.append(_para)

    incar_para_dict = wash.merge_into_one(para_total_list)

    return incar_para_dict


def read_table_from_file(un_prc_file, table_key_word_start, table_key_word_end, flag=False):
    magical_table_list = []
    switch = False

    for i in un_prc_file:
        if table_key_word_start in i or switch:
            magical_table_list.append(i)
            switch = True
        if not flag:
            if i.startswith(table_key_word_end):
                switch = False
        else:
            if len(magical_table_list) == 5:
                break
        if not switch and len(magical_table_list) != 0:
            break

    return wash.data_fmt_trans(fmt_type='str', input=magical_table_list)


class read_outcar:
    def __init__(self, **kwargs):
        self.out_pth = kwargs.get('OUTCAR')
        self.un_prc_out = self.wash_outcar()

    def wash_outcar(self):

        return wash.read_line_from_file(self.out_pth)

    def read_atoms_type_from_outcar(self):
        potcar_type = []
        for l in self.un_prc_out:
            if "VRHFIN =" in l:
                potcar_type.append(l)
        atl = wash.data_fmt_trans(input=potcar_type, fmt_type="str")

        if not isinstance(atl[0], str):
            atp = []
            for i in atl:
                for j in i:
                    if "=" in j:
                        atp.append(j.strip("=").strip(":"))
        else:
            atp = [atl[1].strip("=").strip(":")]

        return atp

    def read_mag_from_outcar(self):
        if len(self.read_atoms_type_from_outcar()) != 1:
            wash_mag_table = read_table_from_file(self.un_prc_out,
                                                  "magnetization (x)",
                                                  "tot")
        else:

            wash_mag_table = read_table_from_file(self.un_prc_out,
                                                  "magnetization (x)",
                                                  "tot", flag=True)
        atoms_mag, tb_name, orb_lb_name, total_mag = [], None, None, None
        for i in wash_mag_table:
            if i[0] == "magnetization":
                tb_name = "_".join(i)
            elif i[0] == "#":
                orb_lb_name = i[3:]
            elif len(i) == 1:
                continue
            elif i[0] == "tot":
                total_mag = i[1:]
            else:
                atoms_mag.append(i)

        if total_mag is None and len(atoms_mag) == 1:
            total_mag = copy.deepcopy(atoms_mag)[0][1:]

        if None not in [tb_name, orb_lb_name, atoms_mag] and len(atoms_mag) != 0:
            return {'table_name': tb_name,
                    'orbit_symbol': orb_lb_name,
                    'total_mag': wash.data_fmt_trans(input=total_mag, fmt_type="array"),
                    'atoms_mag': wash.data_fmt_trans(input=atoms_mag, fmt_type="array")}
        elif tb_name is None:
            raise Exception("Magx not found")
        else:
            raise Exception("OUTCAR mag not found")

    def read_lattice_from_outcar(self):
        wash_lattice_table = read_table_from_file(self.un_prc_out,
                                                  "VOLUME and BASIS-vectors are now :",
                                                  "  length of vectors")
        l_switch = False
        ls, volume = [], None
        for i in wash_lattice_table:
            if i[0] == "length":
                l_switch = False
            if i[0] == "volume":
                volume = i[-1]
            elif i[0] == "direct":
                l_switch = True
                continue
            if l_switch:
                ls.append(i)
        try:
            lattice_vector = wash.data_fmt_trans(fmt_type="array", input=ls)
        except:
            raise Exception("OUTCAR lattice error")

        real_space_lattice = lattice_vector[:, :3]
        rec_space_lattice = lattice_vector[:, 3:]

        if volume is not None and len(ls) != 0:
            return {"real": real_space_lattice,
                    "reciprocal": rec_space_lattice}
        else:
            raise Exception("OUTCAR lattice error")

    def read_fermi_level_from_outcar(self):
        for line in self.un_prc_out:
            if "E-fermi" in line:
                fml = wash.data_fmt_trans(fmt_type='str', input=line)

                return {'E-fermi': float(fml[2])}

        return None


if __name__ == "__main__":
    # osz_pth = r"../examples/out/OSZICAR_1"
    # read_osizcar(osz_pth)
    # kph_pth = r"../examples/ex1/KPOINTS"
    # pos_pth = r"../examples/ex1/POSCAR"
    # kl = read_kpath(kph_pth)
    # eig_pth = r"../examples/ex1/EIGENVAL"
    # inc = r"../examples/ex3/INCAR"
    # read_incar(inc)
    out_pth = r"C:\Users\SenGao.LAPTOP-C08N9B58\Desktop\myVaspht\vaspht-3-26\examples\magx\OUTCAR"
    mag = read_outcar(OUTCAR=out_pth).read_mag_from_outcar()
    print(mag)
    #rec = read_outcar(OUTCAR=out_pth).read_lattice_from_outcar()
