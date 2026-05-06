#!/usr/bin/env python
# -*- coding: utf-8 -*-

from os.path import *
from collections import defaultdict

import numpy as np
from monty.os import cd

from pymatgen.io.vasp.outputs import Eigenval, Outcar, Kpoints, Poscar
from pymatgen.core.lattice import Lattice
from pymatgen.electronic_structure.core import Spin
from pymatgen.electronic_structure.bandstructure import BandStructureSymmLine
from pymatgen.electronic_structure.plotter import BSPlotter


class MatGenBandStructureSymmLine:
    def __init__(self, work_dir):
        with cd(work_dir):
            self.ck()
            self.outcar = Outcar("OUTCAR")
            self.eigenval = Eigenval("EIGENVAL")
            self.crystal = Poscar.from_file("POSCAR").structure
            self.kpath = Kpoints.from_file("KPOINTS")

    @staticmethod
    def ck():
        for i in ["POSCAR", "KPOINTS", "OUTCAR", "EIGENVAL"]:
            if not exists(i):
                raise RuntimeError("Missing file: {}".format(i))

    @property
    def ispin(self):
        return self.outcar.spin

    @property
    def efermi(self):
        return self.outcar.efermi

    @property
    def kpoints(self):
        return self.eigenval.kpoints

    @property
    def nkpt(self):
        return self.eigenval.nkpt

    @property
    def nbands(self):
        return self.eigenval.nbands

    @property
    def eigenvalues(self):
        eigenval = defaultdict(list)
        for spin, v in self.eigenval.eigenvalues.items():
            # v = np.swapaxes(v, 0, 1)
            v = v.swapaxes(0, 1)
            eigenval[spin] = v[:, :, 0]
        return eigenval

    @property
    def bss(self):
        return BandStructureSymmLine(
            [np.asarray(k) for k in self.kpoints],
            self.eigenvalues,
            Lattice(self.crystal.as_dict()['lattice']['matrix']).reciprocal_lattice,
            self.efermi,
            labels_dict=dict(zip(self.kpath.labels, self.kpath.kpts)),
            structure=self.crystal
        )

    @property
    def bs_plotter(self):
        return BSPlotter(self.bss)

    def get_kpath(self):
        high_kpts_ticks = self.bs_plotter.get_ticks()
        high_kpt_distance = high_kpts_ticks['distance']
        high_kpt_label = high_kpts_ticks['label']

        def clb(lb):
            return lb.replace('\\', '').replace('$', '').replace('mid', '|')

        hkl, hkc = [clb(high_kpt_label[0])], [high_kpt_distance[0]]

        for i, coord in enumerate(high_kpt_distance[1:]):
            last = hkc[-1]
            if np.linalg.norm(last - coord) < 0.0001:
                continue
            hkl.append(clb(
                high_kpt_label[i + 1]
            ))
            hkc.append(coord)

        kpath = {'High_Kpoints_labels': hkl,
                 'High_Kpoints_coordinates': hkc}
        return kpath

    def get_band_gap(self):
        gap = self.bss.get_band_gap() if not self.bss.is_metal() else \
            {'direct': '', 'energy': 0.0, 'transition': ''}

        vbm_plot = []
        cbm_plot = []

        cbm = self.bss.get_cbm()
        vbm = self.bss.get_vbm()
        if not self.bss.is_metal():
            for index in cbm["kpoint_index"]:
                cbm_plot.append(
                    (
                        self.bss.distance[index],
                        cbm["energy"] - self.efermi
                    )
                )

            for index in vbm["kpoint_index"]:
                vbm_plot.append(
                    (
                        self.bss.distance[index],
                        vbm["energy"] - self.efermi
                    )
                )

        return {"cbm": cbm_plot,
                "vbm": vbm_plot,
                "fermi": self.efermi,
                "is_metal": self.bs_plotter.bs_plot_data()['is_metal'],
                "gap": gap}

    def get_matgen_results(self):
        kpath = self.get_kpath()
        d = self.bss.distance
        energy_data = {}
        if self.ispin:
            labels = ["Wave_vector", "spin_up", "spin_down"]
            spin_up, spin_down = self.eigenvalues[Spin.up], self.eigenvalues[Spin.down]
            for band_index in range(self.nbands):
                name = f"band_index_{band_index + 1}"
                vals = np.c_[np.asarray(d),
                             spin_up[band_index] - self.efermi,
                             spin_down[band_index] - self.efermi]
                energy_data.update({name: vals.tolist()})
        else:
            labels = ["Wave_vector", "Energy_level"]
            spin_up = self.eigenvalues[Spin.up]
            for band_index in range(self.nbands):
                key = f"band_index_{band_index + 1}"
                vals = np.c_[np.asarray(d),
                             spin_up[band_index] - self.efermi]
                energy_data.update({key: vals.tolist()})

        return {'Band_Structure': {
            'Band_Gap': self.get_band_gap(),
            'Energy_data_labels': labels,
            'Energy_data': energy_data,
            'Spin_state': self.ispin,
            'Hk_points': kpath}}

    def plot(self):
        import matplotlib.pyplot as plt
        band_data = self.get_matgen_results()
        bd_lbs = band_data.get('Band_Structure').get('Energy_data_labels')
        bd_arrary = band_data.get('Band_Structure').get('Energy_data')
        hklbs = band_data.get('Band_Structure').get('Hk_points')
        lbcoord = hklbs.get('High_Kpoints_coordinates')
        plt.title("Band_Structure")
        plt.xlabel("Wave_vector")
        plt.ylabel("Energy(eV)")
        plt.ylim(-15, 15)
        for bandi, bandd in bd_arrary.items():
            if len(bd_lbs) == 3:
                x, y1, y2 = np.asarray(bandd).T[0], np.asarray(bandd).T[1], np.asarray(bandd).T[2]
                plt.plot(x, y1, color='yellow')
                plt.plot(x, y2, color='blue')
            else:
                x, y = np.asarray(bandd).T[0], np.asarray(bandd).T[1]
                plt.plot(x, y, color='blue')
        for k, i in enumerate(lbcoord):
            plt.axvline(i, color='red')
        plt.show()


if __name__ == "__main__":
    t = r"../examples/icsd_624619-Sc2Co12P7/Band"
    m = MatGenBandStructureSymmLine(t)
    m.plot()
