#!/usr/bin/env python
# -*- coding: UTF-8 -*-

from analysis import vasp_read
from analysis import wash

from input.vasp import poscar
from input.vasp import kpoints
from crystal import struct

import os
import numpy as np
from functools import reduce


def find_necessary_file_for_analysis(calctype, rtpth):
    files = os.listdir(rtpth)
    if calctype == "band":
        ndf = ["POSCAR", "KPOINTS", "EIGENVAL", "OUTCAR", "DOSCAR"]
    elif calctype == "dos":
        ndf = ["INCAR", "DOSCAR", "POSCAR"]
    elif calctype =="sp" or calctype ==  "opt_cif" or calctype ==  "un_opt_str" or calctype == "structure":
        ndf = ["POSCAR"]
    elif calctype == "magx":
        ndf = ["OUTCAR", "POSCAR"]
    elif calctype == "KPOINTS_relax" or calctype == "KPOINTS_scf" or  calctype == "KPATH":
        ndf = ["KPOINTS"]
    else:
        raise Exception("necessary file invalid input")

    if set(ndf).issubset(files):
        return dict(zip(ndf, list(map(os.path.join, [rtpth, ] * len(ndf), ndf))))
    else:
        raise Exception("necessary file is missing")


class band_str:
    def __init__(self, **kwargs):
        self.pos_pth = kwargs.get('POSCAR')
        self.kpf_pth = kwargs.get('KPATH')
        self.eig_pth = kwargs.get('EIGENVAL')
        self.out_pth = kwargs.get('OUTCAR')
        self.dos_pth = kwargs.get('DOSCAR')

    def get_rec_vector_from_poscar(self):

        return poscar.poscar(self.pos_pth).get_reciprocal_vector_from_poscar()

    def get_kline_from_kpoints(self):

        return vasp_read.read_kpath(self.kpf_pth)

    def get_band_data_from_eigenval(self):

        return vasp_read.read_eignval(self.eig_pth)

    def get_fermi_level_from_outcar(self):

        return vasp_read.read_outcar(OUTCAR=self.out_pth).read_fermi_level_from_outcar()

    def get_fermi_level_from_doscar(self):

        return vasp_read.read_doscar(self.dos_pth)

    def analysis_kpath_from_kpoints_file(self):
        ptl = self.get_kline_from_kpoints()
        ks, ksi, hkl = [.0, .0, .0], .0, [.0, ]
        middle = ptl[1:-1]
        head, tail = [True, ptl[0][-1], ptl[0][0][0]], [True, ptl[-1][-1], ptl[-1][0][0]]
        mid_num = len(middle)
        middle_k_comb = [middle[i:i + 2] for i in range(0, mid_num, 2)]

        def same_or_not(k_comb_list):
            lba, lbb = k_comb_list[0][-1], k_comb_list[1][-1]
            coorda, coordb = k_comb_list[0][0], k_comb_list[1][0]
            if lba != lbb:
                comb_lb = "|".join([lba, lbb])
                return [False, comb_lb, np.vstack([coorda, coordb])]
            else:
                return [True, "".join({lba, lbb}), np.vstack([coorda, coordb])[-1]]

        k_pool = list(map(same_or_not, middle_k_comb))
        k_pool.insert(0, head), k_pool.append(tail)
        kdr = len(k_pool)
        # rec_vector = self.get_rec_vector_from_poscar()
        crystal_lattice = vasp_read.read_outcar(OUTCAR=self.out_pth).read_lattice_from_outcar()
        rec_vector_from_outcar = crystal_lattice.get("reciprocal")
        for i in range(1, kdr):
            this_state, last_state = k_pool[i][0], k_pool[i - 1][0]
            if this_state and last_state:
                this_coord, previous_coord = k_pool[i][-1], k_pool[i - 1][-1]
            elif not this_state and last_state:
                this_coord, previous_coord = k_pool[i][-1][0], k_pool[i - 1][-1]
            elif not this_state and not last_state:
                this_coord, previous_coord = k_pool[i][-1][0], k_pool[i - 1][-1][1]
            else:
                this_coord, previous_coord = k_pool[i][-1], k_pool[i - 1][-1][1]

            ki, ks = struct.reciprocal(this_coord, rec_vector_from_outcar), \
                     struct.reciprocal(previous_coord, rec_vector_from_outcar)

            dhk = np.linalg.norm(ki - ks)
            ksi += dhk
            hkl.append(ksi)

        kp_labels = [i[1] for i in k_pool]

        return {'High_Kpoints_labels': kp_labels,
                'High_Kpoints_coordinates': np.asanyarray(hkl)}

    def analysis_band_from_eigenval_file(self):
        eig_data = self.get_band_data_from_eigenval()
        para_name = ['spin', 'nbands', 'band_data', 'integral_kpoints_number', 'integral_kpoints_list']
        is_spin, nbands, array_data, kpnum, kpl = list(map(eig_data.get, para_name))

        if not is_spin:
            bds = array_data[:, 1]
        else:
            bds = array_data[:, 1:3]
        try:
            fermi = self.get_fermi_level_from_outcar().get('E-fermi')
        except:
            fermi = self.get_fermi_level_from_doscar().get('E-fermi')

        revised_band = bds - fermi

        def clear_task(task):
            return wash.union_data(task[0], task[1])

        def wash_band(data_list):
            return map(clear_task, data_list)

        def get_band_gap(band_eig, bdnum):
            if bdnum % 2 != 0:
                gap = 0
                return gap
            else:
                cbl, vbl = [], []
                for kpe in band_eig:
                    try:
                        cbl.extend([min([i for i in kpe if i >= 0])])
                        vbl.extend([max([j for j in kpe if j <= 0])])
                    except:
                        gap = 0
                        return gap

                cbm, vbm = min(cbl), max(vbl)
                gap = cbm - vbm
                cbm_index, vbm_index = cbl.index(cbm), vbl.index(vbm)
                if cbm_index == vbm_index:
                    band_type = 'direct'
                else:
                    band_type = 'indirect'
                return gap, band_type

        def band_analysis(revised_band_data, spin, band_number):
            if spin:
                up_band_data, down_band_data = revised_band_data[:, 0], revised_band_data[:, 1]
                bd_data = [(up_band_data, band_number), (down_band_data, band_number)]
                union_up, union_down = wash_band(bd_data)
                up_eig, down_eig = map(np.asanyarray, [union_up, union_down])
                up_band_gap, down_band_gap = get_band_gap(up_eig, band_number), \
                                             get_band_gap(down_eig, band_number)

                return (up_eig, up_band_gap), (down_eig, down_band_gap)

            else:
                union_data = clear_task((revised_band_data, band_number))
                bd_eig = np.asanyarray(union_data)
                bd_gap = get_band_gap(bd_eig, band_number)

                return bd_eig, bd_gap

        band_analysis_result = band_analysis(revised_band, is_spin, nbands)
        # band_analysis_result = band_analysis(bds, is_spin, nbands)
        kpath = self.analysis_kpath_from_kpoints_file()
        hkcoord = kpath.get('High_Kpoints_coordinates')
        klen = kpoints.calc_kpath_coord(kpnum, hkcoord)

        def plus_wave_vector(up_band, my_wv, down_band=None):
            all_data, result_band, band_index = [], {}, 1
            index = up_band.shape[1]
            for i in range(index):
                try:
                    up_bd = np.vstack((my_wv, up_band[:, i]))
                    if down_band is not None:
                        up_bd = np.vstack((up_bd, down_band[:, i]))
                except:
                    raise Exception("EIGENVAL Kpoints number can't match eigenvalue! SOMETHING WRONG IN THIS "
                                    "CALCULATION")
                else:
                    my_key = "band_index_" + str(band_index)
                    result_band[my_key] = up_bd.T
                    band_index += 1
                    all_data.append(result_band)

            return wash.merge_into_one(all_data)

        if is_spin:
            result = plus_wave_vector(np.asanyarray(band_analysis_result[0][0]), klen,
                                      down_band=np.asanyarray(band_analysis_result[1][0]))
            # result_spin_down = plus_wave_vector(np.asanyarray(band_analysis_result[1][0]), klen)
            labels = ["Wave_vector", "spin_up", "spin_down"]
            band_gap = (band_analysis_result[0][1], band_analysis_result[1][1])
            # result = {"spin_up": result_spin_up,
            #           "spin_down": result_spin_down}

        else:

            result = plus_wave_vector(np.asanyarray(band_analysis_result[0]), klen)
            labels = ["Wave_vector", "Energy_level"]
            band_gap = band_analysis_result[1]

        return {'Band_Structure': {
            'Band_Gap': band_gap,
            'Energy_data_labels': labels,
            'Energy_data': result,
            'Spin_state': is_spin,
            'Hk_points': kpath}}


class dos:
    def __init__(self, **kwargs):
        self.pos_pth = kwargs.get('POSCAR')
        self.inc_pth = kwargs.get('INCAR')
        self.out_pth = kwargs.get('OUTCAR')
        self.dos_pth = kwargs.get('DOSCAR')
        self.orb_labs = ["s", "p_y", "p_z", "p_x", "d_xy", "d_yz", "d_z^2",
                         "d_xz", "d_x^2-y^2", "f_y(3x^2-y^2)", "f_xyz",
                         "f_yz^2", "f_z^3", "f_xz^2", "f_z(x^2-y^2)", "f_x(x^2-3y^2)"]
        self.tdos_labs = ['dos', 'int_dos']
        self.is_spin = self.get_spin_from_incar()
        self.all_orb_labs, self.all_tdos_labs = self.dos_labels()
        self.is_partial = self.get_dos_mode_from_incar()
        self.dos_data = self.read_dos_data_from_doscar()

    def get_spin_from_incar(self):
        spin_para = vasp_read.read_incar(self.inc_pth).get("ISPIN")
        if spin_para == "2":
            return True
        elif spin_para == "1" or spin_para is None:
            return False
        else:
            raise Exception("INCAR ISPIN error")

    def species_labels(self):
        at_nms = self.read_atoms_from_poscar().unique_atom_nms
        species_labels = []
        if self.is_spin:
            for sp in at_nms:
                species_labels.extend(['{}_up'.format(sp), '{}_down'.format(sp)])
            return species_labels
        else:
            return at_nms

    def dos_labels(self):
        self.all_orb_labs, self.all_tdos_labs = [], []
        if self.is_spin:
            for orb_nm in self.orb_labs:
                self.all_orb_labs.extend(['{}_up'.format(orb_nm), '{}_down'.format(orb_nm)])
            for tdos_nm in self.tdos_labs:
                self.all_tdos_labs.extend(['{}_up'.format(tdos_nm), '{}_down'.format(tdos_nm)])
        else:
            self.all_orb_labs, self.all_tdos_labs = self.orb_labs, self.tdos_labs
        self.all_tdos_labs.insert(0, "Energy(eV)")
        self.all_orb_labs.insert(0, "Energy(eV)")

        return self.all_orb_labs, self.all_tdos_labs

    def get_dos_mode_from_incar(self):
        mode_para = vasp_read.read_incar(self.inc_pth).get("LORBIT")
        if mode_para in ["11", "12"]:
            return True
        elif mode_para == "10":
            return False
        else:
            raise Exception("INCAR LORBIT error")

    def read_atoms_from_poscar(self):

        return poscar.poscar(poscar=self.pos_pth)

    def read_dos_data_from_doscar(self):

        return vasp_read.read_doscar(self.dos_pth)

    def tdos(self):
        tdos_data, efermi = self.dos_data.get('tdos_data'), self.dos_data.get('E-fermi')
        correct_englv = tdos_data[:, 0] - efermi
        if self.is_spin:
            down_tdos = tdos_data[:, 2] * -1
            mid_tdos = np.column_stack((tdos_data[:, 1], down_tdos))
            tdos = np.column_stack((np.column_stack((correct_englv, mid_tdos)), tdos_data[:, 3:]))
        else:
            tdos = np.column_stack((correct_englv, tdos_data[:, 1:]))

        return {
            "tdos_labels": self.all_tdos_labs,
            "tdos_data": tdos
        }

    def raw_pdos(self):
        pdos_data, efermi = self.dos_data.get('pdos_data'), self.dos_data.get('E-fermi')
        lb_dim = pdos_data.shape[-1]
        raw_pdos_lbs = self.all_orb_labs[:lb_dim]
        correct_englv = pdos_data[:, 0] - efermi
        pdos = np.column_stack((correct_englv, pdos_data[:, 1:]))
        try:
            raw_pdos_data = dict(zip(raw_pdos_lbs, pdos.T))
        except:
            raise Exception("PDOS labels Value DimErr")
        else:
            return raw_pdos_data

    @staticmethod
    def sum_same_orbits(labels_comb, raw_data):
        smv = lambda x, y: x + y
        total_pdos_list = []
        for lbc in labels_comb:
            lbv = []
            for lbnm in lbc:
                rpv = raw_data.get(lbnm)
                if rpv is not None:
                    lbv.append(rpv)
                else:
                    continue
            tlbv = reduce(smv, lbv)
            total_pdos_list.append(tlbv)
        total_sum = reduce(smv, total_pdos_list)

        return total_pdos_list, total_sum

    def plus_same_orbit(self):
        orb_lbs = self.all_orb_labs[1:]
        raw_pdos_data = self.raw_pdos()
        porb_num = np.asanyarray([1, 3, 5, 7])  # s_orb, p_orb, d_orb, f_orb
        sum_orb_all_lbs = ['Energy(eV)', 's', 'p', 'd', 'f']

        raw_pdos_dim = len(raw_pdos_data)

        if not self.is_spin:
            lb_comb = wash.union_diff_data(orb_lbs[:raw_pdos_dim - 1], porb_num)
            sum_pdo_lbs = sum_orb_all_lbs[:len(lb_comb) + 1]
            tlvbl, total = dos.sum_same_orbits(lb_comb, raw_pdos_data)
            pdnt = np.column_stack((raw_pdos_data.get("Energy(eV)"), np.asanyarray(tlvbl).T))
            pdt = np.column_stack((pdnt, np.asanyarray(total).T))
            sum_pdo_lbs.append("total")

            return sum_pdo_lbs, pdt
        else:
            uplbs, downlbs = [], []
            for lb in orb_lbs[:raw_pdos_dim - 1]:
                if lb.endswith("up"):
                    uplbs.append(lb)
                elif lb.endswith("down"):
                    downlbs.append(lb)
                else:
                    raise Exception("PDOS Labels Err")
            uplb_comb, downlb_comb = wash.union_diff_data(uplbs, porb_num), wash.union_diff_data(downlbs, porb_num)

            tlvbl_up, total_up = dos.sum_same_orbits(uplb_comb, raw_pdos_data)
            tlvbl_down, total_down = dos.sum_same_orbits(downlb_comb, raw_pdos_data)
            pdnt_up = np.column_stack((raw_pdos_data.get("Energy(eV)"), np.asanyarray(tlvbl_up).T))
            pdt_up = np.column_stack((pdnt_up, np.asanyarray(total_up).T))
            pdnt_down = np.column_stack((raw_pdos_data.get("Energy(eV)"), np.asanyarray(tlvbl_down).T * -1))
            pdt_down = np.column_stack((pdnt_down, np.asanyarray(total_down).T * -1))
            sum_pdo_lbs = sum_orb_all_lbs[:len(uplb_comb) + 1]
            sum_pdo_lbs.append("total")

            return sum_pdo_lbs, pdt_up, pdt_down

    @staticmethod
    def divide_pdos_space(all_pdos_array, dd_num, atindex):
        dpt = wash.union_data(all_pdos_array, dd_num)
        dsp_dpt = wash.union_diff_data(dpt, atindex)

        return wash.sum_same_data(dsp_dpt)

    # def atoms_pdos(self):
    #    atoms_name_with_index = poscar.poscar(poscar=self.pos_pth).atoms_nms_from_poscar
    #    space_num = self.dos_data.get("nedos")

    def elements_pdos(self):
        at_index = self.read_atoms_from_poscar().atoms_nms_index
        space_num = self.dos_data.get("nedos")
        spnms = self.species_labels()
        dl = []
        if not self.is_spin:
            pdos_lb, pdos_dt = self.plus_same_orbit()
            divide_pdos = dos.divide_pdos_space(pdos_dt, space_num, at_index)
            for index in range(len(at_index)):
                sp_data = {spnms[index]: {'pdos_label': pdos_lb, 'pdos_data': divide_pdos[index]}}
                dl.append(sp_data)
        else:
            up_sp_nm, down_sp_nm = [], []
            for i in spnms:
                if i.endswith("up"):
                    up_sp_nm.append(i)
                else:
                    down_sp_nm.append(i)
            pdos_lb, pdos_dt_up, pdos_dt_down = self.plus_same_orbit()
            divide_up = dos.divide_pdos_space(pdos_dt_up, space_num, at_index)
            divide_down = dos.divide_pdos_space(pdos_dt_down, space_num, at_index)
            dl = []
            for index in range(len(at_index)):
                sp_data = dict(zip([up_sp_nm[index], down_sp_nm[index]],
                                   [{'pdos_label': pdos_lb, 'pdos_data': divide_up[index]},
                                    {'pdos_label': pdos_lb, 'pdos_data': divide_down[index]}]))
                dl.append(sp_data)
        pdos = wash.merge_into_one(dl)

        return pdos

    def analysis_dos_from_doscar_file_for_species(self):

        return {'Density_of_states': {
            'TDOS': self.tdos(),
            'PDOS': self.elements_pdos(),
        }
        }


class magx:
    def __init__(self, **kwargs):
        self.out_pth = kwargs.get("OUTCAR")
        self.pos_pth = kwargs.get('POSCAR')

    def raw_magx_from_outcar(self):
        return vasp_read.read_outcar(OUTCAR=self.out_pth).read_mag_from_outcar()

    def analysis_magx_for_species(self):
        try:
            magx_table = self.raw_magx_from_outcar()
        except:
            return {"magnetization_(x)": 0}

        crystal = poscar.poscar(self.pos_pth)
        unique_atnms = crystal.unique_atom_nms
        unique_atindex = crystal.atoms_nms_index
        same_atmagx_list = wash.union_diff_data(magx_table.get("atoms_mag"), unique_atindex)

        sum_dim = lambda x: [sum(i) for i in (list(zip(*x)))]
        resl = []
        for i in range(len(same_atmagx_list)):
            res = sum_dim(same_atmagx_list[i])[1:]
            resl.append(res)

        magxd = dict(zip(unique_atnms, resl))
        magx_fd = wash.merge_into_one([{"labels": magx_table.get("orbit_symbol")},
                                       magxd,
                                       {"total": magx_table.get("total_mag").tolist()[0]}])

        return {"magnetization_(x)": magx_fd}


if __name__ == "__main__":
    bd_dir = r"..\examples\icsd-192844-Ba2Ca1O6Os1\Band"
    bdpth = find_necessary_file_for_analysis("band", bd_dir)
    band = band_str(POSCAR=bdpth.get("POSCAR"),
                    KPATH=bdpth.get("KPOINTS"),
                    EIGENVAL=bdpth.get("EIGENVAL"),
                    OUTCAR=bdpth.get("OUTCAR"),
                    DOSCAR=bdpth.get("DOSCAR"))

    band_data = band.analysis_band_from_eigenval_file()
    print(band_data)

