#!/bin/bash

while true
do
    pkill -f "python vasp.py"
    echo "已重新执行"
    python vasp.py crun --cdir /GLOBALFS/nscc-gz_pinchen3/vasprun/vaspdata2/folder_15/ >> crun.log 2>&1 &
    sleep 1200 # 1800 秒等于半小时
done
