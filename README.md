# MGE Molecular Motion Video

**English** · [Português](README.pt-BR.md)

An agent skill for narrated molecular motion videos, built while doing real research work. The
`molecular-motion-video/` folder is a self-contained skill (a `SKILL.md` plus references,
templates and scripts) that Claude Code, or any agent that reads `SKILL.md`, can load.

For presentation slides, see [MGE-SciSlides](https://github.com/MrGoulart3/MGE-SciSlides); for
animated matplotlib charts, see [mpl-animation](https://github.com/hugogontijomachado/mpl-animation).

| Skill | What it does |
|---|---|
| [`molecular-motion-video`](molecular-motion-video/) | Narrated, scientifically accurate motion-graphics videos of molecules, materials and reactions (Blender/Cycles). **The atoms move along real calculations**: MD trajectories, IRC/NEB reaction paths, normal modes. It also handles verified local TTS in any language, word-by-word captions, data-driven labels, human approval gates and automated QA. |

## Showcase

[![Salt dissolving: motion replayed from a real MD simulation](molecular-motion-video/examples/salt-dissolving/media/salt_dissolving.gif)](molecular-motion-video/examples/salt-dissolving/)

*Salt dissolving*, made with `molecular-motion-video`. A NaCl nanocrystal dissolves in water, and every atom follows a real OpenMM trajectory.

[![SN2: the Walden inversion, a reactive xTB trajectory shot from the transition state](molecular-motion-video/examples/sn2-walden/media/sn2_walden.gif)](molecular-motion-video/examples/sn2-walden/)

*SN2: the Walden inversion*, made with `molecular-motion-video`. Cl⁻ attacks CH₃Br from the back in water, and the atoms follow a real GFN2-xTB trajectory launched from the transition state.

## Install (Claude Code)

```bash
git clone https://github.com/MrGoulart3/MGE-MolecularMotionVideo.git ~/MGE-MolecularMotionVideo
~/MGE-MolecularMotionVideo/install.sh                          # link every skill into ~/.claude/skills/
~/MGE-MolecularMotionVideo/install.sh molecular-motion-video   # or just one
```

Update with `git -C ~/MGE-MolecularMotionVideo pull`; the symlinks pick up the changes.

## Quick setup

```bash
cd ~/MGE-MolecularMotionVideo/molecular-motion-video/env
conda env create -f environment-render.yml     # or: micromamba create -f ...
conda env create -f environment-tts.yml
conda env create -f environment-calc.yml
# Linux x86_64 example: official Blender 4.2 LTS tarball
BLENDER_DIR=$HOME/blender; mkdir -p "$BLENDER_DIR"
curl -L https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz | tar -xJ -C "$BLENDER_DIR" --strip-components=1
export BLENDER="$BLENDER_DIR/blender"
bash doctor.sh        # checks only, installs nothing; prints OK/MISSING
```

Optional cluster: copy `cluster/cluster.example.yaml` to `cluster.yaml`, then
`python3 cluster/run_remote.py submit <job_dir> -- <command>` (see `status`, `fetch`, `wait`, `--dry-run`).
Workflow tips: `molecular-motion-video/references/iteration-loop.md`.

## Adapt to your environment

All host aliases and `/opt/...` paths in `cluster/cluster.example.yaml` are fictional. Copy it
to a local `cluster.yaml` and replace them with your own settings. Run the runner from that
folder, or pass `--config /path/to/cluster.yaml` before the subcommand. `--dry-run` prints
commands without connecting. Local configs, job records and generated trajectories are ignored by Git.

| Setting | Default | How to change it |
|---|---|---|
| Skill installation directory | `~/.claude/skills` | `CLAUDE_SKILLS_DIR=/path/to/skills ./install.sh` |
| Remote CPUs per job | 4 | `threads` in `cluster.yaml` (exported as `MMV_THREADS`) |
| Remote load admission threshold | 60% | `max_cpu_percent`; load average / CPU count, only with `scheduler: none`. This is a start check, not a runtime CPU cap. |
| OpenMM example threads | 4 | `NT` (legacy option), then `MMV_THREADS` |
| Blender scene threads | 4 | `--threads N`; also pass Blender `-t N` |
| Post-production workers | 2 | `--procs N` |
| Media executables | `ffmpeg`, `ffprobe` on `PATH` | `FFMPEG`, `FFPROBE` (executable paths) |
| Caption and symbol fonts | `DejaVuSans.ttf`, `DejaVuSans-Bold.ttf` | `FONT`, `SYMBOL_FONT` (font filenames or paths supported by Pillow; install fonts separately) |
| Background music | None | `MUSIC=/path/to/licensed-music.wav`; narration is still required |
| Resource checks | 20 GB disk, 8 GB RAM | `MIN_DISK_GB`, `MIN_RAM_GB` for `env/doctor.sh` |

The conda environment names in `env/*.yml` are suggested defaults. Run commands in the
appropriate environment; no script requires a personal environment name. `ENV_RENDER`,
`ENV_TTS` and `ENV_CALC` select environment names for `doctor.sh`. Choose local/remote execution,
concurrency and schedules according to your own hardware and site allocation.
Scientific parameters and recorded results in the examples describe those demonstrations;
they are not machine policies. Human scientific review (G1) and preview approval (G2) remain part of the skill.

Existing Portuguese command names are preserved: `montar_sal.py` means “assemble the salt
video”, `montar_sn2.py` means “assemble the SN2 video”; `--quadros` is the input frames folder,
`--saida` the output MP4 and `--teste` the self-test. `md_sal.py` is the salt MD simulation, `shots/resumo.json` is the shooting summary,
and `ITERACAO_SAL2.md` contains salt iteration notes. See the example READMEs for commands.

## Tests

```bash
python3 -m unittest discover -s molecular-motion-video/cluster -p 'test*.py' -v
python3 -m unittest discover -s molecular-motion-video/scripts -p 'test*.py' -v
```

The example runtime tests use NumPy and Pillow from the render environment. They do not
require Blender, SSH access or a new simulation. This repository has no Node test suite.

## Principles shared by these skills
- **Real science first:** geometry from crystallographic or computed data, motion from actual
  calculations, every claim listed with its source and validated by a human.
- **Cheap → expensive, with human gates:** previews before final renders and computations.
- **Verified by numbers:** every stage has a check mode that prints what a reviewer needs.

## License
MIT (see `LICENSE`).

## Related

- [MGE-AgentPortal](https://github.com/MrGoulart3/MGE-AgentPortal): authenticated browser access to agents and an optional PC resources panel.
- [MGE-LocalCompute](https://github.com/MrGoulart3/MGE-LocalCompute): shared PC resource budgets, nighttime queue and thermal guard.
- [MGE-UAH-Orquestra](https://github.com/MrGoulart3/MGE-UAH-Orquestra): generic multi-agent orchestration, project templates and deterministic watchers.
