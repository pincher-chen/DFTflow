#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import json
import os
from .log import LogCsv
from .spath import SPath

PROG_ROOT = SPath(__file__).parent.parent
TH_LOCAL = PROG_ROOT / ".local"
TH_LOCAL.mkdir(exist_ok=True)
#print("TH_LOCAL",TH_LOCAL)
YHQ_LABEL = ["JOBID", "PARTITION", "NAME", "USER", "ST", "TIME", "NODE", "NODELIST(REASON)"]
YHI_LABEL = ["CLASS", "ALLOC", "IDLE", "DRAIN", "TOTAL"]
RUNNING_JOB_LOG = LogCsv(SPath(TH_LOCAL / "running_job.csv"))
HPC_LOG = LogCsv(SPath(TH_LOCAL / "hpc.csv"))
TEMP_FILE = SPath(TH_LOCAL / "tmp.txt")
ALL_JOB_LOG = LogCsv(SPath(TH_LOCAL / "all_job.csv"))
ALL_JOB_LABEL = ["JOBID", "ST", "WORKDIR", "NAME", "RESULT"]
ERROR_JOB_LABEL = ["JOB_PATH", "ERROR_CODE", "ERROR_NAME"]
ERROR_JOB_LOG = LogCsv(SPath(TH_LOCAL / "error_job.csv"))

file = os.path.split(os.path.abspath(__file__))[0] + "/" + "baseline.json"
with open(file, "r") as f:
    BASELINE = json.load(f)

if __name__ == '__main__':
    pass
