#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import sys
import re
import numpy as np
from functools import reduce
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def read_line_from_file(fn):
    try:
        with open(fn, 'r', encoding='utf-8', errors='ignore') as f:
            dt = f.readlines()
    except:
        logger.warning("{} Read failed.".format(fn))
        sys.exit(1)
    else:
        cldt = [i.rstrip('\n') for i in dt if i != '' and i != ' ']

        return cldt


def read_from_file(fn):
    try:
        with open(fn, 'r', encoding='utf-8', errors='ignore') as f:
            dt = f.read()
    except:
        logger.warning("{} Read failed.".format(fn))
        sys.exit(1)
    else:
        return dt


def data_fmt_trans(**kwargs):
    fmt_type = kwargs.get('fmt_type')
    input_data = kwargs.get('input')
    #print(input_data)

    def clean_data(data):

        def split_string_line(instr):

            return [k for k in re.split(r"\s+", instr) if k != '' and k != ' ']

        if isinstance(data, str):
            lines = input_data.splitlines(keepends=False)
            cdl = [split_string_line(i) for i in lines]
        elif isinstance(data, list) or isinstance(data, tuple):
            try:
                cdl = [split_string_line(i) for i in data]
            except:
                cdl = data
        else:
            logger.warning("{} is not support.".format(type(input_data)))
            sys.exit(1)

        return cdl

    my_cdl = clean_data(input_data)
    shape = np.shape(np.asarray(my_cdl))[-1]

    def make_float(dimesion, l):
        float_result = []
        if dimesion == 1:
            one_cdl = merge_into_one(l)
            clean_number = [float(item) for item in one_cdl]
            float_result.append(clean_number)
        else:
            for word_list in l:
                clean_word = [float(item) for item in word_list]
                float_result.append(clean_word)

        return float_result

    _clean = []
    if fmt_type == 'float':
        _clean = make_float(shape, my_cdl)
    elif fmt_type == 'str':
        for word_list in my_cdl:
            clean_word_list = [item.strip(' ') for item in word_list]
            _clean.append(clean_word_list)
    elif fmt_type == 'int':
        for word_list in my_cdl:
            clean_number_list = [int(item) for item in word_list]
            _clean.append(clean_number_list)
    elif fmt_type == 'array':
        clean_result = make_float(shape, my_cdl)
        _array = np.asanyarray(clean_result)

        return _array
    else:
        logger.warning("{} is not support.".format(fmt_type))

    while [] in _clean:
        _clean.remove([])

    if len(_clean) == 1:

        return _clean[0]
    else:

        return _clean


def merge_into_one(many_data):
    def comb(d1, d2):
        if isinstance(d1, dict) and isinstance(d2, dict):
            return dict(d1, **d2)
        elif isinstance(d1, list) and isinstance(d2, list):
            return d1 + d2
        else:
            return

    return reduce(comb, many_data)


def zip_data(*args):
    return dict(reduce(zip, args))


def split_data(data, split_num):
    less_data_list = [data[i] for i in range(0, len(data), split_num + 1)]
    domain_data_list = [item for item in data if item not in less_data_list]

    return less_data_list, domain_data_list


def union_data(data, union_num):
    return [data[i:i + union_num] for i in range(0, len(data), union_num)]


def union_diff_data(data, union_num_lst):
    fl = []
    for i in union_num_lst:
        k = data[:i]
        data = data[i:]
        fl.append(k)

    while [] in fl:
        fl.remove([])

    return fl


def sum_same_data(data_list):
    tl = []
    for i in data_list:
        pvs = 0
        head = i[0][:, 0]
        for v in i:
            pv = v[:, 1:]
            pvs += pv
        nv = np.column_stack((head, pvs))
        tl.append(nv)

    return tl


if __name__ == "__main__":
    pass
