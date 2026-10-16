#!/usr/bin/env python3
"""Offline tests of command construction. Run: python3 test_run_remote.py"""
import run_remote as r

CFG = {"host": "h", "remote_workdir": "jobs", "scheduler": "none", "threads": 8,
       "max_cpu_percent": 50, "blender_path": "/opt/b/blender", "conda_path": "/opt/c",
       "envs": {"render": "mmv-render"}}

up = r.rsync_up_cmd(CFG, "job/", "jobs/j1")
assert up[0] == "rsync" and up[-2] == "job/" and up[-1] == "h:jobs/j1/" and "--delete" not in up

dn = r.rsync_down_cmd(CFG, "jobs/j1", "out/x", "loc")
assert dn[-2] == "h:jobs/j1/out/x" and dn[-1] == "loc/"

s = r.submit_remote_cmd(CFG, "jobs/j1", "blender -b")
assert "nohup nice" in s and "/proc/loadavg" in s and "-v m=50" in s and "rm " not in s

sl = r.submit_remote_cmd(dict(CFG, scheduler="slurm"), "jobs/j1", "x")
assert "--cpus-per-task=8" in sl and "sbatch --parsable" in sl
pb = r.submit_remote_cmd(dict(CFG, scheduler="pbs"), "jobs/j1", "x")
assert "ncpus=8" in pb and "qsub" in pb

assert r.ssh_cmd(CFG, "ls")[:3] == ["ssh", "-o", "BatchMode=yes"]
job = {"remote_dir": "jobs/j1", "remote_id": "42", "scheduler": "none"}
assert "kill -0 42" in r.status_remote_cmd(CFG, job)
assert "squeue" in r.status_remote_cmd(CFG, dict(job, scheduler="slurm"))

t = r.tiny_yaml("host: a # c\nthreads: 4\nenvs:\n  render: x\n")
assert t == {"host": "a", "threads": 4, "envs": {"render": "x"}}
assert r.remote_path(CFG, "a") == "jobs/a"
print("all tests passed")
