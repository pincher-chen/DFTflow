#!/bin/bash
for i in `squeue | grep num[24] | awk '{print $1}'`;do
  workdir=`scontrol show job=$i | grep WorkDir | awk -F '=' '{print $2}'`
  #echo $workdir
  logfile=${workdir}"/yh.log"
  if [ ! -f $logfile ];then
    yhcancel $i
    continue
  fi
  last_modified=`stat -c %Y $logfile`
  current_time=$(date +%s)
  time_difference=$((${current_time} - ${last_modified}))
  #echo $time_difference
  if [ ${time_difference} -gt 3600 ]; then 
     echo "***************************************************************" 
     echo "jobid: "$i" which worked in "$workdir"/yh.log was not modified in 60 minutes"
     tail $logfile
     read -r -p "Do you want to check the stat of yh.log?[Y/n]" check
     case $check in 
       [yY][eE][sS]|[yY])
         #cd ${workdir}
         /usr/bin/stat ${workdir}/yh.log
	 ;;
     esac
     read -r -p "Do you want to cancel this job?[Y/n]" job_cancel
     case $job_cancel in
       [yY][eE][sS]|[yY])
         yhcancel $i
	 echo "canceled this job"
	 ;;
       [nN][oO]|[nN])
         echo "Did not cancel this job"
     esac
     read -r -p "Do you want to prepare for retrying?[Y/n]" file_remove
     case $file_remove in
       [yY][eE][sS]|[yY])
         if [ ! -f "retry" ];then
           #rm "error" "yh.log" "running" "WAVECAR"
	   cd ${workdir}
	   find . -type f ! -name "POSCAR" -exec rm -f {} \;
           touch "retry"
	   echo "after preparation"
	   ls
	   cd "/GLOBALFS/nscc-gz_pinchen3/vasprun"
	 else
           echo "this job cannot be retried again"
         fi
	 ;;
       [nN][oO]|[nN])
         echo "Did not prepare for retrying"
         ;;
     esac
  fi
done
