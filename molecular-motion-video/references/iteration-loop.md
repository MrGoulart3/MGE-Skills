# Iteration loop: how the lead agent iterates efficiently

What made the two examples (`examples/salt-dissolving`, `examples/sn2-walden`) good was a short,
repeatable loop with a cheap look at every step. The lead agent (the one that owns the science)
**looks and decides**; a coding agent **edits code**. Save credits by delegating the long edits.

## The loop
1. **Preview key frames** (about 10 stills at 320x180 or 640x360, low samples): `scene.py --preview`.
2. **Numbered contact sheet** so feedback can cite a frame:
   ```bash
   ffmpeg -y -pattern_type glob -i 'preview/frame_*.png' \
     -vf "drawtext=text='%{frame_num}':x=8:y=8:fontsize=28:fontcolor=white:box=1:boxcolor=black@0.6,scale=480:-1,tile=4x3:padding=6:color=black" \
     -frames:v 1 contact.png
   ```
   (If drawtext lacks a font, add `fontfile=/path/to/font.ttf`.) Look at it against `critique-rubric.md`.
3. **Write `ITERATION_N.md`**: numbered, concrete fixes ("frame 5: ion hidden behind water, move camera 15 degrees
   up", not "improve the camera"), each with the check that proves it is fixed.
4. **Hand to a coding agent** (Codex / Claude subagent) with: `ITERATION_N.md`, the files it may touch, the rule
   "edit code only; do not render; validate with `python3 -m py_compile` and `scene.py --check/--teste`".
5. **Re-run the preview**, compare contact sheets, repeat. Usually 3-5 rounds.

Gates: **G1** = requester validates the scientific claims (before narration/rendering).
**G2** = requester WATCHED the low-res motion preview and approved it (before any final render).

## Delegation economy
- Lead agent: direction, reading contact sheets, science decisions, final check. Never trust a number or a
  decision that came only from a cheap/free model.
- Coding agent: all long edits to `scene.py` / post scripts. Cheap models: summarize logs, simple scripts.
- Run long jobs detached (`nohup`, or `cluster/run_remote.py`) and poll with a no-AI status script.

## Checks that assert visual honesty (put them in `--check`)
- **Occlusion of the subject:** fraction of the subject's silhouette covered by foreground objects stays under a
  threshold on every key frame (see pitfall below on how to measure).
- **Framing:** every subject point projects inside the title-safe area on every frame; labels never leave it.
- **Time-map monotonic:** the map from video time to trajectory time never decreases; report max speed-up.
- **Events pinned to words:** each named event (e.g. `ion_leaves`) occurs within a tolerance of its spoken word's
  start in `words.json`; print the offsets.
- **Data untouched:** coordinates in the render equal `traj.npz` (hash or max-diff print).

## Pitfalls learned
- **F-curves overwrite handler poses.** Blender animation curves are evaluated after your frame-change handler.
  Re-apply the pose immediately before every `keyframe_insert`, otherwise keys capture stale positions.
- **Multiprocessing initializer errors loop forever.** If a `Pool` initializer raises, workers respawn endlessly.
  Fail fast: run the same setup once in the parent *before* creating the Pool.
- **One periodic image per solvent molecule.** With periodic boundaries, wrap each molecule as a whole (choose the
  image nearest the subject) rather than each atom, or molecules appear torn apart.
- **Smoothstep-per-segment time maps stall at pins.** Zero slope at every pinned point makes the motion freeze at each
  event. Use a monotone PCHIP interpolant through the (video time, trajectory time) pins.
- **Occlusion metrics must use the subject silhouette.** Measure overlap with the subject's projected silhouette, not
  "all water in front of the camera", which is always large and hides real problems.
- **TTS hard words need respelling.** Keep variants per word and let `tts_verified.py` pick the take that Whisper
  hears correctly, e.g. "bromine" -> "bro-meen" / "brohmeen"; keep the caption text unchanged and respell only the audio.
- Re-recording changes timing: always rebuild `timing.json` and re-run the events check afterwards.
