#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import os
import logging

from utils import assistant

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class workSpaceCreator:
    def __init__(self, CalculationRootDir, PropertyPath=None):
        self.work_path = CalculationRootDir
        if PropertyPath is None:
            self.property_path = ["Test_spin", "Relax", "Scf", "Band", "Dos"]
        else:
            self.property_path = PropertyPath

    def find_poscar(self):

        return assistant.find_specific_files(self.work_path)

    def create_struct_dir(self):
        return list(map(assistant.create_struct_root, self.find_poscar()))

    def init_work(self):
        try:
            struct_path_list = self.create_struct_dir()
            all_dirs = assistant.join_dir(struct_path_list, self.property_path)
            _dirs = list(map(assistant.create_dirs, all_dirs))
            return True
        except:
            logger.warning("Create calculation directory failed")
            return None


class repeatSteps:
    def copy_file_from(self):
        pass


if __name__ == '__main__':
    rtd = r"E:\vaspAst\ts\createdir"
    t = workSpaceCreator(CalculationRootDir=rtd, PropertyPath=None)
    t.init_work()
