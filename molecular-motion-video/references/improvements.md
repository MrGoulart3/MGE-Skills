# Improving the result

These improvements are ranked by impact per unit of effort. Items marked ✅ are already built into this skill's scripts and protocol.

## High impact, low effort
1. ✅ **Hard approval gate before the final render (G2).** Wait for the requester to watch and approve the motion preview.
2. ✅ **Loudness normalisation and audio QA.** Measure loudness before delivery; a mix at −18 LUFS is 2 dB below the default target of −16 LUFS (`--lufs` overrides it). Web and social platforms normalise to about −14/−16 LUFS, so an unnormalised mix plays too quiet or clips. `deliver.py finalize` does two-pass EBU R128; `qa` checks LUFS and true peak.
3. ✅ **Best-of-N narration takes.** Score every take by keywords and WER instead of keeping the first acceptable one.
4. ✅ **Subtitle sidecar (`captions.srt`) and soft-subtitle track.** Burned captions alone are not accessible or searchable, and journals often ask for captions.
5. ✅ **Resumable chunked renders and a frame audit.** Large render chunks lose more work on failure. Use `use_overwrite=False` + `use_placeholder=True` and `frame_ranges.py missing/check`.
6. ✅ **Automatic black/frozen-frame detection** on the final file.
7. **One `style.json` for scene and post.** Duplicated hex colours in scene and compositor can drift apart. Shared tokens keep them identical when the palette changes.
8. ✅ **Respelling for synthesis only.** A sentence in `narration.json` may carry `"tts"` (a respelled text, or a list of variants cycled over the takes), e.g. "ên-bolo" for "êmbolo"; captions, keywords and WER always use `"text"`. Keyword/WER checks are accent-insensitive, because Whisper often drops diacritics ("embolo"). Next step: a reusable per-language lexicon.

## High impact, medium effort
9. **Animatic before any 3D.** Build a 2D animatic (still frames or simple shapes on the real narration and timing) and get the requester's OK on rhythm and shot order before modelling. It is the cheapest way to avoid re-timing scenes later.
10. **Rubric-based, blind review.** Score each contact sheet with `critique-rubric.md`. Better still, have a second model score it without seeing the direction notes, to avoid self-approval. A second reviewer can catch problems missed by the first.
11. **Structure straight from CIF.** Load the crystal with ASE/pymatgen from the CIF/COD entry and export positions to Blender, instead of hand-coding lattice maths. This gives fewer errors and makes it trivial to switch materials (a salt, a MOF, a zeolite).
12. **Render less, denoise smarter.** Two things cut cost without visible loss:
    - **Fewer samples on soft frames.** Measure frames at 32 vs 64 spp with OIDN plus albedo/normal passes; for heavily defocused/bokeh frames 32 spp is often indistinguishable. A per-scene sample count can cut 30–40 % of render time.
    - **Static background as one pre-rendered plate.** Keeping only the moving subject in the main render also cuts render time.
13. **Parallel chunks across nodes when the quota allows.** Benchmark scaling and follow the site allocation; additional nodes may reduce wall time.
14. **Platform-specific cuts.** Lay out captions and titles for 16:9 and 9:16 (and 1:1) from the same timeline. The post composer takes the canvas size, and the camera keeps the subject inside the 9:16 safe column. The `deliver.py` crop is only a fallback.

## Quality ceiling (bigger effort)
15. **Professional voice.** A cloned voice of the presenter (from a clean 15 s sample) or a human read improves credibility more than any visual change. TTS is the weakest link a listener notices.
16. **Original score cut to the edit.** A music bed whose swells line up with the events in `timing.json` (e.g. the capture moment) can be generated or edited to the timeline. Even a simple swell lined up with the mechanism beat helps.
17. **Sound design restraint.** Use subtle, physically motivated sounds (soft chime on capture, airy texture in the gas cloud) mixed at −20 dB under the voice. Choose transition effects according to the brief; keep them unobtrusive.
18. **GPU or EEVEE for previews.** Where a GPU exists, EEVEE Next previews make look iterations near real-time; keep Cycles for the final.
19. **Data-faithful motion.** Where available, drive the mechanism from simulation output (MD trajectories, NEB images, DFT-optimised intermediates) instead of keyframed interpolation. This turns the video into evidence, not illustration.

## Additional visual checks
- **Small details need a close-up.** A small feature can occupy only 1–3 px in a medium shot. Make the `--check` print the projected size (px at 1080p) of the detail the narration names, and require ≥ 12 px.
- **Defocus transitions must not go to flat black or a flat bright card.** Use a deep tinted veil (luminance ≈ 0.1) that still lets a little of the defocused image show through, and keep the brightness change between neighbouring frames < 10 %.
- **Retime with the real narration before any preview.** The provisional timing hid an event that ended after its scene; `--check` assertions caught it.
