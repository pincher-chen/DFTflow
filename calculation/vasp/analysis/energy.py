#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os.path as osp
from pymatgen.io.vasp.outputs import Outcar
from utils import BASELINE


class Property:
    def __init__(self, scf, stru_id: int):
        self.stru_id = stru_id
        self.outcar = osp.join(scf, "OUTCAR")
        self.poscar = osp.join(scf, "POSCAR")
        self.atom_symbol, self.atoms_num = self.read_poscar()
        self.is_sim = True if len(self.atom_symbol) == 1 else False

    def get_energy(self):

        try:
            x = Outcar(self.outcar)
        except:
            from monty.re import reverse_readfile
            for info in reverse_readfile(self.outcar):
                # if 'energy  without entropy' in info:
                if 'free  energy   TOTEN' in info:
                    #energy = info.split('=')[-1].strip(' ')
                    energy = info.split('=')[-1].strip(' ').split()[0]
                    return float(energy)
        else:
            return x.final_energy

    def read_poscar(self):
        with open(self.poscar, "r") as poscar:
            for i, line in enumerate(poscar):
                if i == 5:
                    symbol = line.strip().split()
                if i == 6:
                    num = [int(j) for j in line.strip().split()]
                    break
        return symbol, num

    @property
    def energy(self):
        return self.get_energy()

    @property
    def n(self):
        return sum(self.atoms_num)

    @property
    def energy_per_atom(self):
        if self.energy is not None:
            return self.energy / self.n

    def get_fermi_energy(self):
        return Outcar(self.outcar).efermi

    @property
    def efermi(self):
        return self.get_fermi_energy()

    def get_magnetization(self):
        return Outcar(self.outcar).magnetization

    @property
    def total_magnetization(self):
        m = self.get_magnetization()
        total = 0
        if m:
            for e in self.get_magnetization():
                total += e['tot']

        return total

    def __call__(self, *args, **kwargs):
        return {
            "id": self.stru_id,
            "energy": self.energy,
            "energy_per_atom": self.energy_per_atom,
            "symbol": dict(zip(self.atom_symbol, self.atoms_num)),
            "is_sim": self.is_sim
        }


class MatEnergy:
    def __init__(self, work_dir, stru_id):
        self._id = int(stru_id)
        self.propt = Property(work_dir, stru_id)()

    def get_total_energy_per_atom(self):
        return self.propt["energy_per_atom"]

    def get_formation_energy(self):
        if self.propt['is_sim'] == 'True':
            syb = list(self.propt['symbol'].keys())[0]
            te = float(self.propt['energy'])
            s2_id = BASELINE[syb][1]

            if int(self.propt["id"]) == int(s2_id):
                foe = 0
            else:
                s2_e = BASELINE[syb][0]
                v = int(list(self.propt['symbol'].values())[0])
                foe = (te - v * s2_e) / v
        else:
            syb = self.propt['symbol']
            te = float(self.propt['energy'])
            an = 0
            for a, v in syb.items():
                ie = int(v) * BASELINE[a][0]
                te -= ie
                an += int(v)
            foe = round(te / an, 4)

        return foe

    def get_results(self):
        energy = {"stru_id": self._id,
                  "energy": self.get_total_energy_per_atom(),
                  "formation_energy":self.get_formation_energy()}
        return energy


if __name__ == '__main__':
    pass
