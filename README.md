# MGE Skills

**English** · [Português](README.pt-BR.md)

Agent skills for computational chemistry and science communication, built while doing real
research work. Each folder is one self-contained skill (a `SKILL.md` plus references, templates
and scripts) that Claude Code, or any agent that reads `SKILL.md`, can load.

| Skill | What it does |
|---|---|
| [`molecular-motion-video`](molecular-motion-video/) | Narrated, scientifically accurate motion-graphics videos of molecules, materials and reactions (Blender/Cycles). **The atoms move along real calculations**: MD trajectories, IRC/NEB reaction paths, normal modes. It also handles verified local TTS in any language, word-by-word captions, data-driven labels, human approval gates and automated QA. |

More skills will be added as subfolders.

## Install (Claude Code)

```bash
git clone https://github.com/MrGoulart3/MGE-Skills.git ~/MGE-Skills
~/MGE-Skills/install.sh                          # link every skill into ~/.claude/skills/
~/MGE-Skills/install.sh molecular-motion-video   # or just one
```

Update with `git -C ~/MGE-Skills pull`; the symlinks pick up the changes.

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
