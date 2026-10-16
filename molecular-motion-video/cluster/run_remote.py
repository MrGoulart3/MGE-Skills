#!/usr/bin/env python3
"""Generic remote job runner (ssh + rsync). Never deletes remote data.
Runner remoto genérico (ssh + rsync). Nunca apaga dados remotos.

  run_remote.py [--config cluster.yaml] [--dry-run] submit <job_dir> -- <command...>
  run_remote.py status <job_id> | fetch <job_id> <remote_subpath> <local_dir> | wait <job_id>
"""
import argparse, json, os, shlex, subprocess, sys, time

JOBS = ".mmv_jobs.json"
SSH = ["ssh", "-o", "BatchMode=yes"]


def load_config(path):
    text = open(path).read()
    try:
        import yaml
        return yaml.safe_load(text)
    except ImportError:
        return tiny_yaml(text)


def tiny_yaml(text):
    """Parse the flat/one-level-nested subset used by cluster.example.yaml."""
    cfg, cur = {}, None
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        key, _, val = line.strip().partition(":")
        val = val.strip()
        if raw.startswith((" ", "\t")) and cur is not None:
            cfg[cur][key] = _scalar(val)
        elif val == "":
            cfg[key] = {}
            cur = key
        else:
            cfg[key] = _scalar(val)
            cur = None
    return cfg


def _scalar(v):
    v = v.strip().strip("'\"")
    try:
        return int(v)
    except ValueError:
        return v


def stamp():
    return time.strftime("%Y%m%d_%H%M%S")


def remote_path(cfg, *parts):
    return "/".join([cfg["remote_workdir"].rstrip("/")] + list(parts))


def rsync_up_cmd(cfg, job_dir, rdir):
    src = job_dir.rstrip("/") + "/"
    # no --delete: remote data is never removed
    return ["rsync", "-az", "-e", "ssh -o BatchMode=yes", src, "%s:%s/" % (cfg["host"], rdir)]


def rsync_down_cmd(cfg, rdir, sub, local_dir):
    return ["rsync", "-az", "-e", "ssh -o BatchMode=yes",
            "%s:%s/%s" % (cfg["host"], rdir, sub.lstrip("/")), local_dir.rstrip("/") + "/"]


def env_prefix(cfg):
    e = cfg.get("envs") or {}
    parts = []
    if cfg.get("blender_path"):
        parts.append("BLENDER=%s" % shlex.quote(cfg["blender_path"]))
    if cfg.get("conda_path"):
        parts.append("MMV_CONDA=%s" % shlex.quote(cfg["conda_path"]))
    for k, v in e.items():
        parts.append("MMV_ENV_%s=%s" % (k.upper(), shlex.quote(str(v))))
    parts.append("MMV_THREADS=%s" % cfg.get("threads", 4))
    return " ".join(parts)


def script_body(cfg, rdir, command):
    return "#!/bin/bash\ncd %s || exit 1\nexport %s\n( %s ) > job.log 2>&1\necho $? > job.exit\n" % (
        shlex.quote(rdir), env_prefix(cfg), command)


def submit_remote_cmd(cfg, rdir, command):
    """Return the remote shell command string that launches the job. Prints job-id marker."""
    sched = cfg.get("scheduler", "none")
    thr = int(cfg.get("threads", 4))
    q = shlex.quote
    body = script_body(cfg, rdir, command)
    write = "cat > %s/job.sh <<'MMV_EOF'\n%sMMV_EOF\n" % (q(rdir), body)
    if sched == "slurm":
        hdr = "#!/bin/bash\n#SBATCH --cpus-per-task=%d\n#SBATCH --output=%s/slurm.out\n" % (thr, rdir)
        write = "cat > %s/job.sh <<'MMV_EOF'\n%s%sMMV_EOF\n" % (q(rdir), hdr, body.split("\n", 1)[1])
        return write + "sbatch --parsable %s/job.sh" % q(rdir)
    if sched == "pbs":
        hdr = "#!/bin/bash\n#PBS -l select=1:ncpus=%d\n#PBS -o %s/pbs.out\n#PBS -j oe\n" % (thr, rdir)
        write = "cat > %s/job.sh <<'MMV_EOF'\n%s%sMMV_EOF\n" % (q(rdir), hdr, body.split("\n", 1)[1])
        return write + "qsub %s/job.sh" % q(rdir)
    maxp = int(cfg.get("max_cpu_percent", 60))
    check = ('ncpu=$(nproc); awk -v n=$ncpu -v m=%d \'{ if ($1/n*100 > m) exit 1 }\' /proc/loadavg '
             '|| { echo "LOAD_TOO_HIGH"; exit 3; }; ' % maxp)
    return (write + check +
            "cd %s && nohup nice -n 10 bash job.sh > /dev/null 2>&1 & echo $!" % q(rdir))


def status_remote_cmd(cfg, job):
    q, rdir, sched = shlex.quote, job["remote_dir"], job["scheduler"]
    base = "cd %s; " % q(rdir)
    done = 'if [ -f job.exit ]; then echo "DONE exit=$(cat job.exit)"; '
    if sched == "slurm":
        return base + done + 'else squeue -h -j %s -o %%T 2>/dev/null | grep . || echo UNKNOWN; fi' % q(job["remote_id"])
    if sched == "pbs":
        return base + done + 'else qstat %s 2>/dev/null | tail -1 || echo UNKNOWN; fi' % q(job["remote_id"])
    return base + done + 'elif kill -0 %s 2>/dev/null; then echo RUNNING; else echo UNKNOWN; fi' % q(job["remote_id"])


def ssh_cmd(cfg, remote):
    return SSH + [cfg["host"], remote]


def load_jobs():
    return json.load(open(JOBS)) if os.path.exists(JOBS) else {}


def save_jobs(j):
    json.dump(j, open(JOBS, "w"), indent=1)


def run(cmd, dry):
    print("+", " ".join(shlex.quote(c) for c in cmd))
    if dry:
        return ""
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit("command failed (%d): %s" % (r.returncode, r.stderr.strip() or r.stdout.strip()))
    return r.stdout.strip()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default="cluster.yaml")
    ap.add_argument("--dry-run", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("submit"); s.add_argument("job_dir"); s.add_argument("command", nargs=argparse.REMAINDER)
    for n in ("status", "wait"):
        p = sub.add_parser(n); p.add_argument("job_id")
        if n == "wait": p.add_argument("--interval", type=int, default=60)
    f = sub.add_parser("fetch"); f.add_argument("job_id"); f.add_argument("remote_subpath"); f.add_argument("local_dir")
    a = ap.parse_args(argv)
    cfg = load_config(a.config)
    jobs = load_jobs()

    if a.cmd == "submit":
        command = a.command[1:] if a.command[:1] == ["--"] else a.command
        if not command:
            sys.exit("usage: submit <job_dir> -- <command>")
        jid = "%s_%s" % (os.path.basename(os.path.abspath(a.job_dir)), stamp())
        rdir = remote_path(cfg, jid)  # always a NEW folder
        run(ssh_cmd(cfg, "mkdir -p %s" % shlex.quote(rdir)), a.dry_run)
        run(rsync_up_cmd(cfg, a.job_dir, rdir), a.dry_run)
        out = run(ssh_cmd(cfg, submit_remote_cmd(cfg, rdir, " ".join(shlex.quote(c) for c in command))), a.dry_run)
        if out.strip().startswith("LOAD_TOO_HIGH") or "LOAD_TOO_HIGH" in out:
            sys.exit("remote load above max_cpu_percent; job not started")
        jobs[jid] = {"remote_dir": rdir, "remote_id": out.splitlines()[-1] if out else "DRY",
                     "scheduler": cfg.get("scheduler", "none"), "command": command, "submitted": stamp()}
        if not a.dry_run:
            save_jobs(jobs)
        print("job_id:", jid)
    else:
        if a.job_id not in jobs and not a.dry_run:
            sys.exit("unknown job_id (see %s)" % JOBS)
        job = jobs.get(a.job_id, {"remote_dir": remote_path(cfg, a.job_id), "remote_id": "0",
                                  "scheduler": cfg.get("scheduler", "none")})
        if a.cmd == "status":
            print(run(ssh_cmd(cfg, status_remote_cmd(cfg, job)), a.dry_run))
        elif a.cmd == "fetch":
            os.makedirs(a.local_dir, exist_ok=True)
            run(rsync_down_cmd(cfg, job["remote_dir"], a.remote_subpath, a.local_dir), a.dry_run)
        elif a.cmd == "wait":
            while True:
                st = run(ssh_cmd(cfg, status_remote_cmd(cfg, job)), a.dry_run)
                print(st)
                if a.dry_run or st.startswith("DONE") or st == "UNKNOWN":
                    break
                time.sleep(a.interval)


if __name__ == "__main__":
    main()
