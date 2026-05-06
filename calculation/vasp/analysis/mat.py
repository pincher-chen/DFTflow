#!/usr/bin/env python
# -*- coding: utf-8 -*-

from monty.os import cd
from os.path import *
import numpy as np

from pymatgen.core.structure import Structure
from pymatgen.symmetry.analyzer import SpacegroupAnalyzer
from pymatgen.io import cif
from pymatgen.io.vasp.outputs import Outcar


class MatGenStruct:
    def __init__(self, work_dir):
        self.work_dir = work_dir
        with cd(self.work_dir):
            self.crystal = Structure.from_file("CONTCAR")
            self.outcar = Outcar("OUTCAR")

    @property
    def group(self):
        return SpacegroupAnalyzer(self.crystal)

    @property
    def conv_cell(self):
        return self.group.get_conventional_standard_structure()

    @property
    def formula(self):
        return self.conv_cell.composition.formula

    @property
    def conv_cell_lattice(self):
        return self.conv_cell.as_dict()['lattice']

    def get_spacegroup(self):
        return self.conv_cell.get_space_group_info()

    @property
    def prmi_cell(self):
        return self.group.get_primitive_standard_structure()

    @property
    def prmi_cell_lattice(self):
        return self.prmi_cell.as_dict()['lattice']

    @property
    def system(self):
        return self.group.get_crystal_system()

    @property
    def group_symbol(self):
        return self.group.get_point_group_symbol()

    @property
    def conv_cell_elements(self):
        return self.conv_cell.sites

    @property
    def prmi_cell_elements(self):
        return self.prmi_cell.sites

    @property
    def density(self):
        return self.crystal.density

    def get_property(self):
        def get_sp_and_coord(elements):
            sp, coord = [], []
            for i in elements:
                coord.append(i.frac_coords.tolist())
                sp.append(i.species_string)
            return {'atoms_order': sp, 'atoms_coordinates': coord}

        c_cell_res = get_sp_and_coord(self.conv_cell_elements)
        p_cell_res = get_sp_and_coord(self.prmi_cell_elements)

        return {"formula": self.formula, "conventional_cell": self.conv_cell_lattice,
                "conventional_cell_site": c_cell_res,
                "primitive_cell": self.prmi_cell_lattice,
                "primitive_cell_site": p_cell_res, "crystal_system": self.system,
                "density": self.density, "point_group": self.group_symbol,
                "spacegroup": self.get_spacegroup(),
                "elements": list(set(c_cell_res['atoms_order']))}

    def get_cif(self):
        cf_data = cif.CifWriter(self.crystal)
        cf = str(cf_data).replace('# generated using pymatgen',
                                  '# geometry optimization by matgen')

        return {'cif_data': cf}

    def get_mag(self):
        if not self.outcar.magnetization:
            return {"magnetization_(x)": 0}
        mag_dat = {}
        label = {"labels": list(self.outcar.magnetization[0].keys())}
        for index, site in enumerate(self.crystal.sites):
            e = str(site.specie)
            mag = np.asarray(list(self.outcar.magnetization[index].values()))
            if mag_dat.get(e) is None:
                mag_dat[e] = mag
            else:
                mag_dat[e] += mag
        label.update(mag_dat)
        total = sum(list(mag_dat.values()))
        label.update({"total": total})

        return {"magnetization_(x)": label}

    @staticmethod
    def read(filename):
        with open(filename, 'r') as f:
            info = f.read()
        return info

    @staticmethod
    def get_poscar(work_dir):
        with cd(work_dir):
            pos = MatGenStruct.read("POSCAR")
        return {"POSCAR": pos}

    @staticmethod
    def get_MatGen_kpt_files(calc_root):
        name = ["KPOINTS_relax", "KPOINTS_scf", "KPATH"]
        relax = join(calc_root, "Relax/KPOINTS")
        scf = join(calc_root, "Scf/KPOINTS")
        kpa = join(calc_root, "Band/KPOINTS")
        return dict(zip(name, [MatGenStruct.read(relax),
                               MatGenStruct.read(scf),
                               MatGenStruct.read(kpa)]))


if __name__ == "__main__":
    pass

