#!/usr/bin/env python
# -*- coding: utf-8 -*-

from os.path import *

import numpy as np
from collections import defaultdict
from functools import reduce

from monty.os import cd
from pymatgen.electronic_structure.dos import Dos
from pymatgen.electronic_structure.core import Spin, Orbital, OrbitalType
from pymatgen.io.vasp.inputs import Poscar
from pymatgen.io.vasp.outputs import Outcar

"""
Orbs11 = ["s", "p_y", "p_z", "p_x", "d_xy", "d_yz", "d_z^2",
          "d_xz", "d_x^2-y^2", "f_y(3x^2-y^2)", "f_xyz",
          "f_yz^2", "f_z^3", "f_xz^2", "f_z(x^2-y^2)", "f_x(x^2-3y^2)"]

Orbs10 = ["s", "p", "d", "f"]

"""


class MatGenDos:
    def __init__(self, work_directory):
        self.wd = work_directory
        with cd(self.wd):
            self.ck()
            self.outcar = Outcar("OUTCAR")
            self.crystal = Poscar.from_file("POSCAR").structure
            self.raw_tdos, self.raw_pdos = self.read_doscar("DOSCAR")
            self.dos_type = self.get_dos_type("INCAR")

    @staticmethod
    def ck():
        for i in ["POSCAR", "DOSCAR", "OUTCAR"]:
            if not exists(i):
                raise RuntimeError("Missing file: {}".format(i))

    @property
    def tdos_label(self):
        if self.ispin:
            return ["energy", "dos_up", "dos_down", "int_dos_up", "int_dos_down"]
        return ["energy", "dos", "int_dos"]

    @property
    def energies(self):
        return self.raw_tdos[0] - self.efermi

    @property
    def lm(self):
        return False if self.dos_type != 11 else True

    @property
    def tdos(self):
        tdensities = {}
        for i in range(self.nspin):
            spin = Spin.up if i == 0 else Spin.down
            tdensities[spin] = self.raw_tdos[1:][i]
        return Dos(self.efermi, self.energies, tdensities)

    @property
    def idos(self):
        idensities = {}
        for i in range(self.nspin):
            spin = Spin.up if i == 0 else Spin.down
            idensities[spin] = self.raw_tdos[1:][i + self.nspin]
        return Dos(self.efermi, self.energies, idensities)

    @property
    def pdos(self):
        pdoss = []
        pdos = defaultdict(dict)

        def ddos(dat, lm):
            n_row, n_col = dat.shape
            for x in range(1, n_col):
                if lm:
                    orb = Orbital(x - 1)
                else:
                    orb = OrbitalType(x - 1)
                yield orb, dat[:, x]

        for atom_pdos in self.raw_pdos:
            data = atom_pdos.T
            if not self.ispin:
                for i, di in ddos(data, self.lm):
                    pdos[i][Spin.up] = di
            else:
                e = data[:, 0]
                _dos_dat = data[:, 1:]
                up_dat, down_dat = _dos_dat[:, 1::2], _dos_dat[:, ::2]
                for i, di in ddos(np.c_[e, up_dat], self.lm):
                    pdos[i][Spin.up] = di
                for j, dj in ddos(np.c_[e, down_dat], self.lm):
                    pdos[j][Spin.down] = dj
            pdoss.append(pdos)
        return pdoss

    @property
    def ispin(self):
        return self.outcar.spin

    @property
    def efermi(self):
        return self.outcar.efermi

    @property
    def nspin(self):
        return 2 if self.ispin else 1

    @staticmethod
    def get_dos_type(incar):
        with open(incar, "r") as f:
            for i in f:
                if "LORBIT" in i:
                    return int(i.strip().split('=')[-1])

    @staticmethod
    def read_doscar(fname):
        """Read a VASP DOSCAR file"""
        with open(fname) as f:
            natoms, *_ = [int(i) for i in f.readline().split()]
            [f.readline() for _ in range(4)]  # Skip next 4 lines.
            # First we have a block with total and total integrated DOS
            ndos = int(f.readline().split()[2])
            _dos = []
            for nd in range(ndos):
                _dos.append(np.array([float(x) for x in f.readline().split()]))
            _total_dos = np.array(_dos).T
            # Next we have one block per atom, if INCAR contains the stuff
            # necessary for generating site-projected DOS
            _dos = []
            for na in range(natoms):
                line = f.readline()
                if line == '':
                    # No site-projected DOS
                    break
                ndos = int(line.split()[2])
                line = f.readline().split()
                cdos = np.empty((ndos, len(line)))
                cdos[0] = np.array(line)
                for nd in range(1, ndos):
                    line = f.readline().split()
                    cdos[nd] = np.array([float(x) for x in line])
                _dos.append(cdos.T)
            _site_dos = np.array(_dos)
        return _total_dos, _site_dos

    def _get_tdos(self):
        tdos_dict = self.tdos.as_dict()
        tdensities = tdos_dict['densities']
        idos_dict = self.idos.as_dict()
        idensities = idos_dict['densities']
        if not self.ispin:
            tden = tdensities['1']
            iden = idensities['1']
        else:
            tden_up, tden_down = tdensities['1'], tdensities['-1']
            tden = np.c_[np.asarray(tden_up), np.asarray(tden_down) * -1]
            iden_up, iden_down = idensities['1'], idensities['-1']
            iden = np.c_[np.asarray(iden_up), np.asarray(iden_down)]

        tdos_data = np.c_[self.energies, tden, iden]
        return tdos_data

    def _get_matgen_tdos_old_style(self):
        tdos_dat = self._get_tdos()
        return {
            "TDOS": {
                "tdos_labels": self.tdos_label,
                "tdos_data": tdos_dat.tolist()}

        }

    def _get_pdos(self):
        element_dat = {}
        for index, element in enumerate(self.crystal.species):
            name = str(element)
            if element_dat.get(name) is None:
                element_dat[name] = [self.pdos[index]]
            else:
                element_dat[name].append(self.pdos[index])

        def _merge_ele(data, ispin):
            up_data = {}
            if ispin:
                down_data = {}
                for na in data:
                    for _o, val in na.items():
                        orb = str(_o)[0]
                        _up, _down = val[Spin.up], val[Spin.down]
                        if up_data.get(orb) is None:
                            up_data[orb] = _up
                        else:
                            up_data[orb] += _up
                        if down_data.get(orb) is None:
                            down_data[orb] = _down
                        else:
                            down_data[orb] += _down
                return up_data, down_data
            else:
                for na in data:
                    for _o, val in na.items():
                        orb = str(_o)[0]
                        _up = val[Spin.up]
                        if up_data.get(orb) is None:
                            up_data[orb] = _up
                        else:
                            up_data[orb] += _up
                return up_data

        up_pdos = {}
        down_pdos = {}
        for k, v in element_dat.items():
            if self.ispin:
                up, down = _merge_ele(v, self.ispin)
                up_pdos[k] = up
                down_pdos[k] = down
            else:
                up = _merge_ele(v, self.ispin)
                up_pdos[k] = up

        if self.ispin:
            return up_pdos, down_pdos
        return up_pdos

    def _get_matgen_pdos_old_style(self):
        def _add(dat, k, e):
            r = {}
            for nu, vu in dat.items():
                nu += k
                nu_lbs = list(vu.keys())
                nu_lbs.insert(0, "Energy(eV)")
                nu_lbs.append("total")
                p_orb = np.asarray(list(vu.values()))
                if 'down' in k:
                    p_orb = np.asarray([i * -1 for i in p_orb])
                tu = np.asarray(reduce(lambda x, y: x + y, p_orb))
                vu = np.c_[e, p_orb.T, tu.T]
                r[nu] = {
                    "pdos_label": nu_lbs,
                    "pdos_data": vu.tolist()
                }
            return r

        if self.ispin:
            up, down = self._get_pdos()
            dup = _add(up, '_up', self.energies)
            ddo = _add(down, '_down', self.energies)
            dup.update(ddo)
            return {"PDOS": dup}
        up = self._get_pdos()
        up = _add(up, '', self.energies)
        return {"PDOS": up}

    def get_matgen_results(self):
        tdos = self._get_matgen_tdos_old_style()
        pdos = self._get_matgen_pdos_old_style()
        tdos.update(pdos)
        return {"Density_of_states": tdos}

    def plot(self):
        import matplotlib.pyplot as plt
        dos_data = self.get_matgen_results()
        pdos_data = dos_data.get('Density_of_states').get('PDOS')
        all_atoms = list(pdos_data.keys())
        for at in all_atoms:
            plt.xlabel("Energy(eV)")
            plt.ylabel("electrons/eV")
            plt.title(at.split('_')[0] + "_Density_of_states")
            dlb = pdos_data.get(at).get('pdos_label')
            dd = pdos_data.get(at).get('pdos_data')
            Energy = dd.T[0]
            for i in range(1, len(dlb)):
                plt.plot(Energy, dd.T[i])
            # if at.split('_')[-1] == 'up':
            #    continue
            plt.show()
        plt.title("Total_Density_of_states")
        plt.xlabel("Energy(eV)")
        plt.ylabel("electrons/eV")
        tdos_data = dos_data.get('Density_of_states').get('TDOS')
        tlb = tdos_data.get('tdos_labels')
        td = tdos_data.get('tdos_data')
        if len(tlb) > 3:
            Energy, dos_up, dos_down = td.T[:3]
            plt.plot(Energy, dos_up, color='red')
            plt.plot(Energy, dos_down, color='blue')
        else:
            Energy, dos_up = td.T[:2]
            plt.plot(Energy, dos_up, color='red')
        plt.show()


if __name__ == "__main__":
    pass
