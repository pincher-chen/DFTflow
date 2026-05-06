#!/usr/bin/env python
# -*- coding: UTF-8 -*-
import os
import re
import shutil
import logging
import numpy as np

from analysis.wash import read_line_from_file

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def ch_pwd_dir():
    pwd_dir = os.path.split(__file__)[0]
    os.chdir(pwd_dir)
    return


def join_dir(src_dir, files):
    jd = lambda tupleX: os.path.join(tupleX[0], tupleX[1])
    if isinstance(src_dir, list) or isinstance(src_dir, tuple):
        if len(src_dir) == 1:
            return list(map(jd, zip(src_dir * len(files), files)))
        else:
            return [join_dir(i_dir, files) for i_dir in src_dir]
    elif isinstance(src_dir, str):
        return list(map(jd, zip([src_dir, ] * len(files), files)))
    else:
        return None


def create_struct_root(src_file):
    if not os.path.isfile(src_file):
        return None
    str_root = os.path.splitext(src_file)[0]
    if not os.path.exists(str_root):
        os.makedirs(str_root)
    des_file = os.path.join(str_root, os.path.basename(src_file))
    try:
        shutil.move(src_file, des_file)
    except:
        logger.warning("initialize {} root directory failed".format(str_root))
        return None
    else:
        logger.info("initialize {} root directory success".format(str_root))
        return str_root


def create_dirs(dirs_list):
    if dirs_list is not None and isinstance(dirs_list, list):
        return list(map(os.makedirs, dirs_list))
    elif dirs_list is not None and isinstance(dirs_list, str):
        os.makedirs(dirs_list)
        return dirs_list
    else:
        return None


def ensure_filepath_strings(filein):
    if isinstance(filein, list):
        if len(filein) == 1:
            fn = filein[0]
        else:
            return False
    elif isinstance(filein, str):
        fn = filein
    else:
        raise Exception("InvalidFileName!")
    return fn


def move_file(file_dir, file_name, new_file_dir, new_file_name):
    file_dir, file_name, new_file_dir, new_file_name = list(map(ensure_filepath_strings,
                                                                [file_dir, file_name, new_file_dir, new_file_name]))

    src_file_name = os.path.basename(file_name)
    if src_file_name not in os.listdir(file_dir):
        raise FileNotFoundError

    src, des = list(zip([file_dir, new_file_dir], [src_file_name, new_file_name]))
    join_file = lambda x: os.path.join(x[0], x[1])
    sf, df = join_file(src), join_file(des)
    try:
        shutil.copy(sf, df)
    except IOError:
        os.chmod(df, 777)
        shutil.copy(sf, df)

    return


def find_id_from_path_strings(filepath, id_type='icsd'):
    struct_id = None
    wkl = filepath.split(os.sep)
    for i in wkl:
        if bool(re.match(r"/?.*?[_|-]\d+[-|_].*".format(id_type), i)):
            struct_id = int(re.split(r'[-|_]', i)[1])
            break
    if struct_id is not None:
        return struct_id
    else:
        return -1
        #raise Exception("{}_IDError".format(id_type))


def find_specific_files(inf, suffix=None, keyword=None):
    if suffix is None and keyword is None:
        suffix = ".poscar"
        keyword = "POSCAR"
    if os.path.isfile(inf):
        src_suffix = os.path.splitext(inf)[-1]
        if suffix is not None and keyword is not None:
            if suffix == src_suffix or keyword in inf:
                return inf
            else:
                return False
        elif suffix is not None and keyword is None:
            if suffix == src_suffix:
                return inf
            else:
                return False
        elif suffix is None and keyword is not None:
            if keyword in inf:
                return inf
            else:
                return False
        else:
            return False
    elif os.path.isdir(inf):
        under_inf_files = join_dir(inf, os.listdir(inf))
        true_File = []
        for i in under_inf_files:
            if not os.path.isfile(i):
                continue
            ff = find_specific_files(i, suffix=suffix, keyword=keyword)
            true_File.append(ff)
        while False in true_File:
            true_File.remove(False)
        return true_File
    else:
        return False


def make_array_to_list(my_dict):
    for i in my_dict:
        if isinstance(my_dict[i], dict):
            make_array_to_list(my_dict[i])
        else:
            if type(my_dict[i]) is np.ndarray:
                my_dict[i] = my_dict[i].tolist()

    return my_dict


if __name__ == '__main__':
    # res = find_specific_files("1321jf.poscar")
    fnm = r"E:\vaspAst\ts\1"
    files = find_specific_files(fnm, suffix=".log", keyword="calc")
