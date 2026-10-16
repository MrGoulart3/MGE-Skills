#!/usr/bin/env python3
"""Offline command tests: python3 -m unittest discover -s this_directory -v."""
import unittest

import run_remote as r

CFG = {"host": "example-cluster", "remote_workdir": "jobs", "scheduler": "none",
       "threads": 8, "max_cpu_percent": 50, "blender_path": "/opt/blender/blender",
       "conda_path": "/opt/conda", "envs": {"render": "mmv-render"}}


class RemoteCommandsTest(unittest.TestCase):
    """Check transfers, scheduler selection and configurable resource budgets."""

    def test_transfers_preserve_remote_data(self):
        up = r.rsync_up_cmd(CFG, "job/", "jobs/j1")
        self.assertEqual(up[0], "rsync")
        self.assertEqual(up[-2:], ["job/", "example-cluster:jobs/j1/"])
        self.assertNotIn("--delete", up)
        down = r.rsync_down_cmd(CFG, "jobs/j1", "out/x", "loc")
        self.assertEqual(down[-2:], ["example-cluster:jobs/j1/out/x", "loc/"])

    def test_local_scheduler_uses_configured_load(self):
        command = r.submit_remote_cmd(CFG, "jobs/j1", "blender -b")
        for fragment in ("nohup nice", "/proc/loadavg", "-v m=50"):
            self.assertIn(fragment, command)
        self.assertNotIn("rm ", command)

    def test_scheduler_cpu_allocations(self):
        for scheduler, allocation, launcher in (
                ("slurm", "--cpus-per-task=8", "sbatch --parsable"),
                ("pbs", "ncpus=8", "qsub")):
            with self.subTest(scheduler=scheduler):
                command = r.submit_remote_cmd(dict(CFG, scheduler=scheduler), "jobs/j1", "x")
                self.assertIn(allocation, command)
                self.assertIn(launcher, command)

    def test_resource_defaults_and_overrides(self):
        minimal = {"host": "example-cluster", "remote_workdir": "jobs"}
        self.assertIn("MMV_THREADS=4", r.env_prefix(minimal))
        self.assertIn("-v m=60", r.submit_remote_cmd(minimal, "jobs/j1", "x"))
        self.assertIn("MMV_THREADS=8", r.env_prefix(CFG))

    def test_ssh_and_status(self):
        self.assertEqual(r.ssh_cmd(CFG, "ls")[:3], ["ssh", "-o", "BatchMode=yes"])
        job = {"remote_dir": "jobs/j1", "remote_id": "42", "scheduler": "none"}
        self.assertIn("kill -0 42", r.status_remote_cmd(CFG, job))
        self.assertIn("squeue", r.status_remote_cmd(CFG, dict(job, scheduler="slurm")))

    def test_config_parser_and_paths(self):
        parsed = r.tiny_yaml("host: example-cluster # comment\nthreads: 4\nenvs:\n  render: x\n")
        self.assertEqual(parsed, {"host": "example-cluster", "threads": 4,
                                  "envs": {"render": "x"}})
        self.assertEqual(r.remote_path(CFG, "a"), "jobs/a")


if __name__ == "__main__":
    unittest.main()
