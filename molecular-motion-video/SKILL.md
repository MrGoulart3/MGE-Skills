---
name: molecular-motion-video
description: Produce a professional, narrated, scientifically accurate motion-graphics video (10–90 s) about molecules, materials or reactions — video abstracts, graphical-abstract videos, outreach and teaching clips. Uses Blender/Cycles (headless, CPU or cluster) with real crystal/molecular geometry and motion replayed from actual calculations (MD trajectories, IRC/NEB reaction paths, normal modes, optimised intermediates), a narration-driven timeline, verified local text-to-speech (any language, incl. Portuguese), word-by-word captions, data-driven labels and automated QA. Use whenever someone asks for a "video abstract", "animação científica", "vídeo narrado", "molecular animation", "explainer video about a material/reaction", a "Blender scene of a crystal/molecule", or wants to turn a paper/mechanism into a short video — even if they don't say "skill".
---

# Molecular motion video

A gated, iterative protocol for narrated scientific animations. It was distilled from real
productions (a 30 s, 1080p video abstract with Portuguese narration, and an English showcase of
salt dissolving driven by molecular dynamics: `examples/salt-dissolving/`). The protocol is application-agnostic: swap the
chemistry, keep the gates.

**Core ideas**
1. **The narration is the clock.** Script → verified voice → `timing.json`. The 3D scene and the
   post-production only *read* that timeline (scenes and named events anchored to spoken words), so
   re-recording never breaks sync.
2. **Real science, real scale.** 1 Blender unit = 1 Å. Geometry from crystallographic data
   (COD/CIF) or measured bond lengths/angles; `--check` mode prints them for review.
3. **Text never lives in 3D.** The scene exports projected 2D anchors per frame; labels, captions
   and titles are composited in post (crisp, editable, translatable, no re-render for a typo).
4. **Cheap → expensive, with human gates.** Stills → low-res motion → final. **Never start the
   final render before the requester has WATCHED the low-res motion preview and approved it.**
5. **Computed motion, not invented motion.** Whenever the story is about how molecules behave
   (dissolving, binding, reacting, vibrating), the atoms move along a *real calculation*: an MD
   trajectory, an IRC/NEB path, normal modes or optimised intermediates, converted to `traj.npz` with
   `scripts/traj_to_npz.py`. Positions are never edited to fit the story; time compression and any
   acceleration (high T, steered MD) are disclosed, and an on-screen clock shows real time.
   See `references/computed-motion.md`.
6. **Every claim verified by numbers or eyes.** Whisper checks the voice; `--check` checks geometry
   and framing; contact sheets are reviewed against a rubric; `deliver.py qa` checks the file.

## Stages and gates

| # | Stage | Output | Gate (who approves) |
|---|---|---|---|
| 0 | Brief | audience, venue (journal spec?), length, language, voice, must-show facts | requester answers |
| 1 | Script + science check | `SCRIPT.md`: 4–7 sentences (~2.6 words/s), scene table A–E with "hook to next scene", claims list with sources | **G1: requester validates the scientific claims** |
| 2 | Narration | `tts_verified.py` → `sentNN.wav/json` (best of N takes, keywords verified) | listen once; respell/reword failures |
| 3 | Timeline | `build_timing.py` → `timing.json`, `words.json`, `captions.srt`, `narration.wav` | automatic |
| 3b | Computed motion (if the story is about behaviour) | MD / IRC / modes → `traj.npz` + `events.json` + data README (`references/computed-motion.md`) | `--check` sanity numbers from the data |
| 4 | Direction | `DIRECTION.md` (look, chemistry, camera, per-scene beats, anchors to export) | — |
| 5 | Scene code | `scene.py` with `--check/--preview/--motion/--final`, `--frames a-b --threads N` | `--check` passes |
| 6 | Look iterations | `--preview` stills (~10 key frames) + contact sheet; `ITERATION_N.md` notes | rubric score ≥ target |
| 7 | Motion preview | `--motion` (640×360, 8 spp, all frames) + full post → `preview.mp4` | **G2: requester watched it and approved** |
| 8 | Final render | `--final` (1080p, 64 spp, OIDN) in resumable chunks | `frame_ranges.py check` |
| 9 | Post + delivery | compose captions/labels/title/music → `deliver.py finalize` + `qa` | `qa` all OK + final look |

Details, commands and pitfalls for each stage: `references/protocol.md`.
Review rubric for stages 6–9: `references/critique-rubric.md`.
How to beat the original result: `references/improvements.md`.

## Quick start (new topic)

1. Copy `templates/` into the project (`SCRIPT_TEMPLATE.md`, `DIRECTION_TEMPLATE.md`, `style.json`).
2. Write the script; list every scientific claim with a source; get G1.
3. `python3 scripts/tts_verified.py --script narration.json --out narration/ --lang pt`
4. `python3 scripts/build_timing.py --narration narration/ --out timing/ --scenes A=1 B=2 ... --events name=4:word:start`
5. If molecules must *behave* (dissolve, react, vibrate), compute it first (MD, IRC/NEB, normal
   modes) and convert with `python3 scripts/traj_to_npz.py <traj> --out traj.npz --subject ...`;
   detect the story events in code (`events.json`).
6. Write `DIRECTION.md`; have a coding agent write `scene.py` (timeline class, easing, data-driven
   point meshes + Geometry Nodes, camera solver, anchor export, validation). Reuse a previous scene
   if you have one — adapt, don't start from zero.
7. Iterate looks with `--preview` + contact sheet (`ffmpeg ... tile`), one `ITERATION_N.md` per round.
8. `--motion` + post (captions/labels/title composited from anchors) → send preview → **wait for G2**.
9. Final: split with `scripts/frame_ranges.py split`, render chunks (resumable), `check`, compose,
   then `scripts/deliver.py finalize` and `scripts/deliver.py qa`.

## Setup
Environment kit in `env/` (conda YAMLs for render, TTS and calculation, plus `env/doctor.sh`, which only checks and
never installs). Optional remote execution: `cluster/` (`cluster.example.yaml`, `run_remote.py`). How to iterate
efficiently with a coding agent: `references/iteration-loop.md`. Run `bash env/doctor.sh` first.

## Tooling assumptions
- Blender 4.2 LTS headless (`blender -b -t N -P scene.py -- --mode`); Cycles CPU is fine.
  Needs glibc ≥ 2.28 (old cluster nodes may only run Blender ≤ 3.x).
- Python 3.11 env with `torch` (CPU), `chatterbox-tts`, `faster-whisper` for narration
  (`setuptools<81` is required by the watermarker).
- ffmpeg ≥ 6, Pillow ≥ 10 (variable fonts via `set_variation_by_axes`), numpy; ASE for `traj_to_npz.py`.
- For computed motion: an MD engine (OpenMM/GROMACS/LAMMPS) or a QM code with IRC/NEB/frequencies (xTB, ORCA, Gaussian).
- A coding agent (Codex/Claude) writes the long scene/post scripts from the direction docs;
  the lead agent writes direction, reviews contact sheets and owns scientific decisions.

## Non-negotiables
- Do not render the final before G2. Do not publish claims not validated at G1.
- No hard cuts/flashes between scenes: one continuous camera move with eased curves.
- Captions inside the title-safe area; labels never overlap each other or the caption band.
- Never edit computed coordinates to fit the narration; choose the window, camera and speed instead.
- Keep a single source of truth for colors/fonts (`style.json`) shared by scene and post.
- Check that the font has every glyph you need (subscripts like ₂ and ²⁻ are often missing:
  draw them as smaller, offset runs).
