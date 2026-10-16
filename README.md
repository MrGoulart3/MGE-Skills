# MGE Skills

**English** · [Português](README.pt-BR.md)

Agent skills for computational chemistry and science communication, built while doing real
research work. Each folder is one self-contained skill (a `SKILL.md` plus references, templates
and scripts) that Claude Code, or any agent that reads `SKILL.md`, can load.

| Skill | What it does |
|---|---|
| [`molecular-motion-video`](molecular-motion-video/) | Narrated, scientifically accurate motion-graphics videos of molecules, materials and reactions (Blender/Cycles). **The atoms move along real calculations**: MD trajectories, IRC/NEB reaction paths, normal modes. It also handles verified local TTS in any language, word-by-word captions, data-driven labels, human approval gates and automated QA. |

## Showcase

[![Salt dissolving: motion replayed from a real MD simulation](molecular-motion-video/examples/salt-dissolving/media/salt_dissolving.gif)](molecular-motion-video/examples/salt-dissolving/)

*Salt dissolving*, made with `molecular-motion-video`. A NaCl nanocrystal dissolves in water, and every atom follows a real OpenMM trajectory.

[![SN2: the Walden inversion, a reactive xTB trajectory shot from the transition state](molecular-motion-video/examples/sn2-walden/media/sn2_walden.gif)](molecular-motion-video/examples/sn2-walden/)

*SN2: the Walden inversion*, made with `molecular-motion-video`. Cl⁻ attacks CH₃Br from the back in water, and the atoms follow a real GFN2-xTB trajectory launched from the transition state.

More skills will be added as subfolders.

## Install (Claude Code)

```bash
git clone https://github.com/MrGoulart3/MGE-Skills.git ~/MGE-Skills
~/MGE-Skills/install.sh                          # link every skill into ~/.claude/skills/
~/MGE-Skills/install.sh molecular-motion-video   # or just one
```

Update with `git -C ~/MGE-Skills pull`; the symlinks pick up the changes.

## Quick setup

```bash
cd MGE-Skills/molecular-motion-video/env
conda env create -f environment-render.yml     # or: micromamba create -f ...
conda env create -f environment-tts.yml
conda env create -f environment-calc.yml
# Blender is not on conda: official 4.2 LTS tarball
BLENDER_DIR=$HOME/blender; mkdir -p "$BLENDER_DIR"
curl -L https://download.blender.org/release/Blender4.2/blender-4.2.3-linux-x64.tar.xz | tar -xJ -C "$BLENDER_DIR" --strip-components=1
export BLENDER="$BLENDER_DIR/blender"
bash doctor.sh        # checks only, installs nothing; prints OK/MISSING
```

Optional cluster: copy `cluster/cluster.example.yaml` to `cluster.yaml`, then
`python3 cluster/run_remote.py submit <job_dir> -- <command>` (see `status`, `fetch`, `wait`, `--dry-run`).
Workflow tips: `molecular-motion-video/references/iteration-loop.md`.

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
