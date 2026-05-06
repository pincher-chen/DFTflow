#!/usr/bin/env /XYFS01/nscc-gz_pinchen_1/sf_install/miniconda3/envs/dftflow/bin/python3
# -*- coding: utf-8 -*-

import os
from config import WORKFLOW, CONDOR, PACKAGE_ROOT
from utils.spath import SPath


class WorkflowParser:
    def __init__(self, work_root: SPath, comment=None, source=None,
                 modules=None, workflow=None, prog=None, name=None):
        self.work_root = work_root.absolute()
        if comment is None:
            comment = "#!/bin/sh"
        self.comment = comment
        if prog is None:
            prog = CONDOR.get('VASP', 'VASP_EXE')
        self.prog = prog
        if workflow is None:
            workflow = WORKFLOW
            print(workflow)
        self.workflow = workflow
        self._py = PACKAGE_ROOT / "vasp.py"
        self.name = name
        if source is None:
            self.source = CONDOR.get('SOURCE', 'FILES')
            if self.source:
                self.source = f"source {self.source}"
        if modules is None:
            self.module = CONDOR.get('MODULE', 'MODULES')
            if self.module:
                self.module = f"module load {self.module}"

    def yield_job(self):
        for job_name, job_paras in self.workflow.items():
            yield job_name, job_paras

    def yhrun_prog(self, node, core, partition):
        return f"yhrun -N {node} -n {core} -p {partition} {CONDOR['VASP']['VASP_DIR']}/{self.prog}"

    def parser(self, job_name, job_paras):
        #temp = ['prefix=/APP/u22/x86/intel/oneapi2023.2\n', 'TBBROOT=${prefix}/tbb/2021.10.0/env/..\n', 'DAALROOT=${prefix}/dal/2023.2.0\n', 'DPCT_BUNDLE_ROOT=${prefix}/dpcpp-ct/2023.2.0\n', 'INSPECTOR_2023_DIR=${prefix}/inspector/2023.2.0\n', 'ONEAPI_ROOT=${prefix}\n', 'PKG_CONFIG_PATH=${prefix}/vtune/2023.2.0/include/pkgconfig/lib64:${prefix}/tbb/2021.10.0/env/../lib/pkgconfig:${prefix}/mkl/2023.2.0/lib/pkgconfig:${prefix}/ippcp/2021.8.0/lib/pkgconfig:${prefix}/inspector/2023.2.0/include/pkgconfig/lib64:${prefix}/dpl/2022.2.0/lib/pkgconfig:${prefix}/dnnl/2023.2.0/cpu_dpcpp_gpu_dpcpp/../lib/pkgconfig:${prefix}/dal/2023.2.0/lib/pkgconfig:${prefix}/compiler/2023.2.0/lib/pkgconfig:${prefix}/ccl/2021.10.0/lib/pkgconfig:${prefix}/advisor/2023.2.0/include/pkgconfig/lib64:\n', 'export LIBRARY_PATH=${prefix}/tbb/2021.10.0/env/../lib/intel64/gcc4.8:${prefix}/mkl/2023.2.0/lib/intel64:${prefix}/ipp/2021.9.0/lib/intel64:${prefix}/ippcp/2021.8.0/lib/intel64:${prefix}/ipp/2021.9.0/lib/intel64:${prefix}/dnnl/2023.2.0/cpu_dpcpp_gpu_dpcpp/lib:${prefix}/dal/2023.2.0/lib/intel64:${prefix}/compiler/2023.2.0/linux/compiler/lib/intel64_lin:${prefix}/compiler/2023.2.0/linux/lib:${prefix}/ccl/2021.10.0/lib/cpu_gpu_dpcpp:${LIBRARY_PATH}\n', 'export PATH=/APP/u22/x86/mpi/mpich-4.1.2-icc-oneapi2023.2-ch4/bin:/APP/u22/x86/mpi/ucx-1.15.0-icc-oneapi2023.2-ch4/bin:${prefix}/vtune/2023.2.0/bin64:${prefix}/mkl/2023.2.0/bin/intel64:${prefix}/itac/2021.10.0/bin:${prefix}/inspector/2023.2.0/bin64:${prefix}/dpcpp-ct/2023.2.0/bin:${prefix}/dev-utilities/2021.10.0/bin:${prefix}/debugger/2023.2.0/gdb/intel64/bin:${prefix}/compiler/2023.2.0/linux/lib/oclfpga/bin:${prefix}/compiler/2023.2.0/linux/bin/intel64:${prefix}/compiler/2023.2.0/linux/bin:${prefix}/advisor/2023.2.0/bin64:$PATH\n', 'export CPATH=/APP/u22/x86/mpi/mpich-4.1.2-icc-oneapi2023.2-ch4/include:/APP/u22/x86/mpi/ucx-1.15.0-icc-oneapi2023.2-ch4/include:${prefix}/tbb/2021.10.0/env/../include:${prefix}/mkl/2023.2.0/include:${prefix}/ipp/2021.9.0/include:${prefix}/ippcp/2021.8.0/include:${prefix}/ipp/2021.9.0/include:${prefix}/dpl/2022.2.0/linux/include:${prefix}/dpcpp-ct/2023.2.0/include:${prefix}/dnnl/2023.2.0/cpu_dpcpp_gpu_dpcpp/include:${prefix}/dev-utilities/2021.10.0/include:${prefix}/dal/2023.2.0/include:${prefix}/compiler/2023.2.0/linux/lib/oclfpga/include:${prefix}/ccl/2021.10.0/include/cpu_gpu_dpcpp:$CPATH\n', 'export LD_LIBRARY_PATH=/APP/u22/x86/mpi/mpich-4.1.2-icc-oneapi2023.2-ch4/lib:/APP/u22/x86/mpi/ucx-1.15.0-icc-oneapi2023.2-ch4/lib:${prefix}/tbb/2021.10.0/env/../lib/intel64/gcc4.8:${prefix}/mkl/2023.2.0/lib/intel64:${prefix}/itac/2021.10.0/slib:${prefix}/ipp/2021.9.0/lib/intel64:${prefix}/ippcp/2021.8.0/lib/intel64:${prefix}/ipp/2021.9.0/lib/intel64:${prefix}/dnnl/2023.2.0/cpu_dpcpp_gpu_dpcpp/lib:${prefix}/debugger/2023.2.0/gdb/intel64/lib:${prefix}/debugger/2023.2.0/libipt/intel64/lib:${prefix}/debugger/2023.2.0/dep/lib:${prefix}/dal/2023.2.0/lib/intel64:${prefix}/compiler/2023.2.0/linux/lib:${prefix}/compiler/2023.2.0/linux/lib/x64:${prefix}/compiler/2023.2.0/linux/lib/oclfpga/host/linux64/lib:${prefix}/compiler/2023.2.0/linux/compiler/lib/intel64_lin:${prefix}/ccl/2021.10.0/lib/cpu_gpu_dpcpp:${prefix}/compiler/2023.2.0/linux/compiler/lib/intel64_lin:${prefix}/ccl/2021.10.0/lib/cpu_gpu_dpcpp:$LD_LIBRARY_PATH\n', 'export MANPATH=/APP/u22/x86/mpi/mpich-4.1.2-icc-oneapi2023.2-ch4/share/man:/APP/u22/x86/mpi/ucx-1.15.0-icc-oneapi2023.2-ch4/share/man:${prefix}/itac/2021.10.0/man:${prefix}/debugger/2023.2.0/documentation/man:${prefix}/compiler/2023.2.0/documentation/en/man/common:$MANPATH\n', 'SLURM_MPI_TYPE=pmix\n']
        #flow = ''.join(temp)
        flow = ''
        #task_dir = self.work_root / job_name
        task_dir =  SPath("./")
        converge_txt = task_dir / "converge.txt"
        flow += f"echo \'[...]start {job_name} task\'\n"
        flow += f"if [ ! -d {job_name} ];then\n"
        flow += f"  mkdir {job_name} && cd {job_name} || exit\n"
        flow += f"else\n"
        flow += f"  cd {job_name}\n"
        flow += f"fi\n"
        node = job_paras.get("node")
        core = job_paras.get("core")
        partition = job_paras.get("partition")
        if node is None:
            node = 1
            core = 48
        if core is None:
            core = 48 * node
        if partition is None:
            partition = "mars"
        try_num_param = job_paras.get("try_num")
        if try_num_param is None:
            try_num = 1
        else:
            try_num = " ".join([str(i) for i in range(try_num_param)])
        ignore_txt = task_dir / "ignore.txt"
        flow += f"echo \'[...]prepare {job_name} inputs.\'\n"
        flow += f"/XYFS01/nscc-gz_pinchen_1/sf_install/miniconda3/envs/dftflow/bin/python {self._py} generate --work_dir {task_dir}\n"
        flow += f"for try_num in {try_num} \n"
        flow += "  do\n"
        flow += f"  echo \"[...]task {job_name} round: $try_num on {node} node {core} core\"\n"
        flow += f"  {self.yhrun_prog(node, core,partition)} > yh.log\n" #2>&1\n"
        flow += f"  if [ $? -eq 0 ]; then\n"
        flow += f"    echo \"[...]calc step: $try_num completed!\"\n"
        flow += f"    echo \"[...]check calculation result...\"\n"
        flow += f"    /XYFS01/nscc-gz_pinchen_1/sf_install/miniconda3/envs/dftflow/bin/python {self._py} errors --work_dir {task_dir}\n"
        flow += f"    /XYFS01/nscc-gz_pinchen_1/sf_install/miniconda3/envs/dftflow/bin/python {self._py} converge --work_dir {task_dir}\n"
        flow += f"    if [ -f \"{converge_txt}\" ];then\n"
        flow += f"      /XYFS01/nscc-gz_pinchen_1/sf_install/miniconda3/envs/dftflow/bin/python {self._py} spin --work_dir {task_dir}\n"
        flow += f"      break\n"
        flow += f"    fi\n"
        flow += f"  else\n"
        flow += f"    echo \'[...]yhrun command failed! check errors\'\n"
        flow += f"    /XYFS01/nscc-gz_pinchen_1/sf_install/miniconda3/envs/dftflow/bin/python {self._py} errors --work_dir {task_dir}\n"
        flow += f"    /XYFS01/nscc-gz_pinchen_1/sf_install/miniconda3/envs/dftflow/bin/python {self._py} converge --work_dir {task_dir}\n"
        flow += f"  fi\n"
        flow += f"  echo \'[...]calculation not done, prepare to next loop\'\n"
        flow += f"  /XYFS01/nscc-gz_pinchen_1/sf_install/miniconda3/envs/dftflow/bin/python {self._py} update --work_dir {task_dir}\n"
        flow += f"done\n"
        flow += f"if [ ! -f \"{converge_txt}\" ];then\n"
        flow += f"  echo \'[...]The job in the specified setting is not completed, " \
                f"       check if it can be ignored\' \n"
        flow += f"  if [ ! -f \"{ignore_txt}\" ];then\n"
        flow += f"    echo \'[...]subsequent calculations are not allowed, job exits...\'\n"
        flow += f"    echo '{job_name}\t failed' >> ../stat.log\n"
        flow += f"    exit\n"
        flow += f"  else\n"
        flow += f"    echo \'[...]errors can be ignored, preparing for the next calculation\'\n"
        flow += f"    /XYFS01/nscc-gz_pinchen_1/sf_install/miniconda3/envs/dftflow/bin/python {self._py} spin --work_dir {task_dir}\n"
        flow += f"    echo '{job_name}\t successed' >> ../stat.log\n"
        flow += f"  fi\n"
        flow += f"else\n"
        flow += f"  echo \'[...]{job_name} job done!\'\n"
        flow += f"  /XYFS01/nscc-gz_pinchen_1/sf_install/miniconda3/envs/dftflow/bin/python {self._py} spin --work_dir {task_dir}\n"
        flow += f"  echo '{job_name}\t successed' >> ../stat.log\n"
        flow += f"fi\n"
        flow += f"cd ..\n"

        return flow

    def _get(self):
        b = ''
        b += f"{self.comment}\n"
        b += f"{self.source}\n"
        #b += f"{self.module}\n"
        temp=['/XYFS01/nscc-gz_pinchen_1/sf_install/miniconda3/condabin/conda activate dftflow\n','prefix=/APP/u22/x86/intel/oneapi2023.2\n', 'TBBROOT=${prefix}/tbb/2021.10.0/env/..\n', 'DAALROOT=${prefix}/dal/2023.2.0\n', 'DPCT_BUNDLE_ROOT=${prefix}/dpcpp-ct/2023.2.0\n', 'INSPECTOR_2023_DIR=${prefix}/inspector/2023.2.0\n', 'ONEAPI_ROOT=${prefix}\n', 'PKG_CONFIG_PATH=${prefix}/vtune/2023.2.0/include/pkgconfig/lib64:${prefix}/tbb/2021.10.0/env/../lib/pkgconfig:${prefix}/mkl/2023.2.0/lib/pkgconfig:${prefix}/ippcp/2021.8.0/lib/pkgconfig:${prefix}/inspector/2023.2.0/include/pkgconfig/lib64:${prefix}/dpl/2022.2.0/lib/pkgconfig:${prefix}/dnnl/2023.2.0/cpu_dpcpp_gpu_dpcpp/../lib/pkgconfig:${prefix}/dal/2023.2.0/lib/pkgconfig:${prefix}/compiler/2023.2.0/lib/pkgconfig:${prefix}/ccl/2021.10.0/lib/pkgconfig:${prefix}/advisor/2023.2.0/include/pkgconfig/lib64:\n', 'export LIBRARY_PATH=${prefix}/tbb/2021.10.0/env/../lib/intel64/gcc4.8:${prefix}/mkl/2023.2.0/lib/intel64:${prefix}/ipp/2021.9.0/lib/intel64:${prefix}/ippcp/2021.8.0/lib/intel64:${prefix}/ipp/2021.9.0/lib/intel64:${prefix}/dnnl/2023.2.0/cpu_dpcpp_gpu_dpcpp/lib:${prefix}/dal/2023.2.0/lib/intel64:${prefix}/compiler/2023.2.0/linux/compiler/lib/intel64_lin:${prefix}/compiler/2023.2.0/linux/lib:${prefix}/ccl/2021.10.0/lib/cpu_gpu_dpcpp:${LIBRARY_PATH}\n', 'export PATH=/APP/u22/x86/mpi/mpich-4.1.2-icc-oneapi2023.2-ch4/bin:/APP/u22/x86/mpi/ucx-1.15.0-icc-oneapi2023.2-ch4/bin:${prefix}/vtune/2023.2.0/bin64:${prefix}/mkl/2023.2.0/bin/intel64:${prefix}/itac/2021.10.0/bin:${prefix}/inspector/2023.2.0/bin64:${prefix}/dpcpp-ct/2023.2.0/bin:${prefix}/dev-utilities/2021.10.0/bin:${prefix}/debugger/2023.2.0/gdb/intel64/bin:${prefix}/compiler/2023.2.0/linux/lib/oclfpga/bin:${prefix}/compiler/2023.2.0/linux/bin/intel64:${prefix}/compiler/2023.2.0/linux/bin:${prefix}/advisor/2023.2.0/bin64:$PATH\n', 'export CPATH=/APP/u22/x86/mpi/mpich-4.1.2-icc-oneapi2023.2-ch4/include:/APP/u22/x86/mpi/ucx-1.15.0-icc-oneapi2023.2-ch4/include:${prefix}/tbb/2021.10.0/env/../include:${prefix}/mkl/2023.2.0/include:${prefix}/ipp/2021.9.0/include:${prefix}/ippcp/2021.8.0/include:${prefix}/ipp/2021.9.0/include:${prefix}/dpl/2022.2.0/linux/include:${prefix}/dpcpp-ct/2023.2.0/include:${prefix}/dnnl/2023.2.0/cpu_dpcpp_gpu_dpcpp/include:${prefix}/dev-utilities/2021.10.0/include:${prefix}/dal/2023.2.0/include:${prefix}/compiler/2023.2.0/linux/lib/oclfpga/include:${prefix}/ccl/2021.10.0/include/cpu_gpu_dpcpp:$CPATH\n', 'export LD_LIBRARY_PATH=/APP/u22/x86/mpi/mpich-4.1.2-icc-oneapi2023.2-ch4/lib:/APP/u22/x86/mpi/ucx-1.15.0-icc-oneapi2023.2-ch4/lib:${prefix}/tbb/2021.10.0/env/../lib/intel64/gcc4.8:${prefix}/mkl/2023.2.0/lib/intel64:${prefix}/itac/2021.10.0/slib:${prefix}/ipp/2021.9.0/lib/intel64:${prefix}/ippcp/2021.8.0/lib/intel64:${prefix}/ipp/2021.9.0/lib/intel64:${prefix}/dnnl/2023.2.0/cpu_dpcpp_gpu_dpcpp/lib:${prefix}/debugger/2023.2.0/gdb/intel64/lib:${prefix}/debugger/2023.2.0/libipt/intel64/lib:${prefix}/debugger/2023.2.0/dep/lib:${prefix}/dal/2023.2.0/lib/intel64:${prefix}/compiler/2023.2.0/linux/lib:${prefix}/compiler/2023.2.0/linux/lib/x64:${prefix}/compiler/2023.2.0/linux/lib/oclfpga/host/linux64/lib:${prefix}/compiler/2023.2.0/linux/compiler/lib/intel64_lin:${prefix}/ccl/2021.10.0/lib/cpu_gpu_dpcpp:${prefix}/compiler/2023.2.0/linux/compiler/lib/intel64_lin:${prefix}/ccl/2021.10.0/lib/cpu_gpu_dpcpp:$LD_LIBRARY_PATH\n', 'export MANPATH=/APP/u22/x86/mpi/mpich-4.1.2-icc-oneapi2023.2-ch4/share/man:/APP/u22/x86/mpi/ucx-1.15.0-icc-oneapi2023.2-ch4/share/man:${prefix}/itac/2021.10.0/man:${prefix}/debugger/2023.2.0/documentation/man:${prefix}/compiler/2023.2.0/documentation/en/man/common:$MANPATH\n']

        #, 'SLURM_MPI_TYPE=pmix\n']
        b += ''.join(temp)
        b += f"echo \'[...]TASK START!\'\n"

        for step, paras in self.yield_job():
            b += self.parser(step, paras)
        b += f"/XYFS01/nscc-gz_pinchen_1/sf_install/miniconda3/envs/dftflow/bin/python {self._py} summary --root {self.work_root}\n"
        b += f"echo \'[...]TASK DONE!\'"
        return b

    def write_sh(self):
        filename = self.work_root.name + ".sh"
        sh_path = self.work_root / filename
        sh_path.write_text(self._get())
        return self.work_root, filename


if __name__ == '__main__':
    pass
