# Protocol: stage by stage (what was done in v1, and what to do)

Reference run: "HDL capturing SOₓ". 30.6 s, 735 frames at 24 fps, 1920×1080, Portuguese narration.
- **Final render:** Blender 4.2.3 Cycles CPU on a 64-core cluster node with 12 threads, ~44–88 s/frame, about 8.4 h in two sequential halves.
- **Post-production:** composed on a 4-core desktop.

## 0. Brief
Ask once, then decide sensible defaults:
- the audience and the venue (journal video-abstract specs differ: check the publisher page for length, size and format);
- the length;
- the language;
- the voice (stock TTS voice vs. clone);
- the 1–3 facts the viewer must leave with;
- the visual reference the requester likes.

Record the answers at the top of `SCRIPT.md`.

## 1. Script and science check
- **Size:** 4–7 sentences, about 2.4–2.8 words/s. 30 s ≈ 70 words.
- **Arc:**
  1. hook/problem (real-world stake);
  2. the material/idea;
  3. how it works (structure);
  4. the mechanism (the money shot);
  5. the payoff/closing line.
- **Scene table:** for each scene, give narration, image and the *hook to the next scene* (a moving object or the camera carries the eye; no cuts).
- **Claims list:** every factual statement, its source, and simplifications made on purpose (e.g. "calcined LDH not mentioned"). The requester validates this at **G1**.
- **Write for the voice:**
  - avoid words the TTS will garble or that become homophones (v1: "para um ar mais limpo" was heard as "uma arma" and was reworded);
  - spell out formulas ("dióxido de enxofre", not "SO₂").

## 2. Narration (`scripts/tts_verified.py`)
- **Engine:** Chatterbox Multilingual, `language_id` per language. Natural-sounding settings were `exaggeration=0.7`, `cfg_weight=0.4`.
- **Keywords:** every sentence gets required keywords (technical terms). Whisper (small, int8) transcribes each take. The best of N takes wins, by missing keywords first and then WER.
  - v1 accepted the *first* passing take; best-of-N is better.
- **Failures** seen in Portuguese: "queima" → "quema", "octaedros" → "octaítios", "um ar" → "uma arma". Fixes:
  - new seeds;
  - phonetic respelling in the TTS text only (captions use the script text);
  - or rewording.
- **Voice cloning:** pass `--voice ref.wav`. Use 10–15 s of clean speech, no music, mono, quiet room. A recording web page failed on both desktop and phone in v1, so accept an uploaded phone recording instead.
- **Whole sentences:** generate sentence by sentence. Pacing and pauses are then controlled in the timeline, and one bad sentence is regenerated alone.

## 3. Timeline (`scripts/build_timing.py`)
- **Layout:** sentences placed end to end with lead-in 0.6 s, gaps 0.3–0.45 s and tail 1.5 s. The trailing silence of each take is ignored.
- **Scenes** start half a gap before their sentence.
- **Events** are anchored to a spoken word, e.g. `co2_leaves=4:carbonato:end+0.3`.
- **Outputs** (the single source of truth):
  - `timing.json`;
  - `words.json`, for karaoke captions;
  - `captions.srt`, a soft-subtitle sidecar;
  - `narration.wav`.

## 4. Direction (`templates/DIRECTION_TEMPLATE.md`)
One document a coding agent can implement without questions. It covers:
- **Global look:**
  - palette from `style.json`;
  - materials (v1: glass octahedra with emissive edges, Mg blue #1E9FD0, Al amber #FF9A33);
  - lighting;
  - background;
  - depth of field;
  - mist;
  - bloom;
  - AgX view transform.
- **Chemistry:** structure source (CIF/COD id), lattice parameters, bond lengths/angles, element colours, and vibrations.
  - Vibrations use real IR normal modes, mass-weighted with the centre of mass fixed.
  - Visual frequency is 1.5–4 Hz and amplitude 5–8 % of the bond.
- **Per scene:** beats tied to named events, camera path, focus target, and what is in focus when the narration names it.
- **Anchors to export:** points whose projected 2D position post-production needs, written per frame to `anchors.json`.
- **Modes and validation:**
  - `--check`: counts, bond lengths, framing numbers, molecules inside the frustum;
  - `--preview`: ~10 key frames, including the last;
  - `--motion`: all frames, 640×360, 8 spp;
  - `--final`: 1080p, 64 spp, OIDN, motion blur, persistent data;
  - plus `--frames a-b` and `--threads N`.
  - Deterministic seeds.

## 5. Scene code
> The `examples/hdl-sox/` files come from the original production and stay private until that paper is out. The public showcase example is `examples/salt-dissolving/`, a computed-motion scene driven by MD (see `computed-motion.md`).

- **Starting point:** `examples/hdl-sox/hdl_sox.py` (1.3 k lines, written by a coding agent from the direction doc). Reusable parts:
  - `Timeline` (reads `timing.json`; `frame()`, `at(scene, fraction)`);
  - `ease`, `sample_path` (smooth camera knots);
  - `normal_modes` / `vibrational_positions`;
  - `make_molecule` / `set_bond`;
  - `solve_framing` (puts the subject at a target screen fraction and width);
  - `project_anchor` / `export_anchors`;
  - `validate_frame` / `check_geometry`;
  - `cloud_in_frustum`.
- **Base structure:** the approved earlier look `examples/hdl-sox/hdl_previa.py` (hydrotalcite R-3m, a = 3.07 Å, c = 23.3 Å) is imported, not modified.
- **Always run** `blender -b -t 2 -P scene.py -- --check` before any render.

## 6. Look iterations
- **Each round:** `--preview` on the cluster (~1–2 min), then a contact sheet:
  `ffmpeg -pattern_type glob -i '*.png' -vf "scale=640:-1,tile=3xR" -frames:v 1 sheet.png`
- **Notes:** the lead agent reviews with the rubric and writes `ITERATION_N.md` with numbered, testable fixes, each saying what to KEEP and what to change.
- **v1 needed 3 rounds.** Typical defects:
  - a visible hard-edged "glow" plane (make glows with World/lights only, never with geometry);
  - bokeh orbs that looked like confetti (fewer, very near or very far from the focus plane, low emission, alpha 0.15–0.35);
  - dark, unlit molecules (add rim light, sheen, slight emission);
  - the final framing too small (solve framing numerically);
  - a missing molecule cloud (count molecules inside the frustum in `--check`);
  - blurry dark background fragments reading as "dirt" (removed).

## 7. Motion preview → G2
- **Render:** `--motion`, all frames, at ~1/9 of the final cost (v1: minutes on the cluster).
- **Post:** apply the FULL post-production to it (captions, labels, music). The requester judges rhythm, sync and legibility here.
- **Publish and wait:** send the preview, then **wait for an explicit "watched and liked it"**.
  - In v1 the final started before this approval. It worked out, but it risked ~8 h of compute.

## 8. Final render
- **Cost and settings:** 64 spp with adaptive sampling (threshold 0.02), OIDN, motion blur, `render.use_persistent_data = True` (avoids rebuilding the BVH every frame).
- **Chunks:** split into chunks with `frame_ranges.py split`.
  - With a quota (e.g. ≤70 % of a shared node), chunks run sequentially with a fixed thread count; otherwise run them in parallel on several nodes.
  - Make chunks resumable: `scene.render.use_overwrite = False` and `use_placeholder = True`, then re-run `frame_ranges.py missing` and render only the gaps.
- **Watching the job:** v1 watched the cluster scratch directory disappearing as the "job done" signal, because the job wrapper rewrote its own log at the end. Trust the produced files, not logs.
- **Before post:** merge the chunks into one folder and run `frame_ranges.py check` (detects missing or truncated frames).

## 9. Post-production and delivery
- **Composer:** `examples/hdl-sox/montar_sox.py` (Pillow layers, then ffmpeg overlay). It takes as input:
  - the frames folder;
  - `timing.json`;
  - `anchors.json`;
  - the narration WAVs;
  - music;
  - the font.
- **Layers:**
  1. **Karaoke captions** at 88 % of the height, max ~6 words per block, current word in amber. A soft bottom scrim (0 → 60 % opacity over the bottom 32 %) keeps them legible over bright frames; it was added after review.
  2. **Technical labels:** pills with leader lines to anchors, time windows from events, no overlaps (checked numerically).
  3. **Title card** on the clean side of the final frame. The final frame is held 2 s; the title fades in after the last sentence and the captions are off during the title.
  4. **Grain and vignette** only if the render has none.
- **Music:** ambient bed at ~0.28, ducked under the voice with `sidechaincompress`, fades in/out. No whooshes or transition sound effects (rejected by reviewers as cheap).
- **Delivery:** `deliver.py finalize` produces:
  - loudness-normalized `master.mp4` (CRF 16);
  - `web.mp4` (CRF 23, faststart; v1 web version was 6.7 MB for 30 s);
  - optionally a 9:16 crop;
  - an embedded subtitle track.
- **QA:** `deliver.py qa` checks the specs, black and frozen segments, loudness and true peak.
- **Sharing:** for people outside the organisation, offer the MP4 itself (messaging apps preview it), not an HTML page wrapping it.
