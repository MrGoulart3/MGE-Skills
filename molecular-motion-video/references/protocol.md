# Protocol: stage by stage

Use the public `examples/salt-dissolving/` and `examples/sn2-walden/` as starting points.
Duration, resolution, language, thread counts and execution location belong to your project
brief and configuration. Benchmark representative frames on your own hardware before
estimating the final render cost.

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
- **Claims list:** every factual statement, its source, and simplifications made on purpose (e.g. a solvent represented only as a background). The requester validates this at **G1**.
- **Write for the voice:**
  - avoid words the TTS will garble or that become homophones (e.g. Portuguese "um ar" can be misheard as "uma arma");
  - spell out formulas ("dióxido de enxofre", not "SO₂").

## 2. Narration (`scripts/tts_verified.py`)
- **Engine:** Chatterbox Multilingual, `language_id` per language. Natural-sounding settings were `exaggeration=0.7`, `cfg_weight=0.4`.
- **Keywords:** every sentence gets required keywords (technical terms). Whisper (small, int8) transcribes each take. The best of N takes wins, by missing keywords first and then WER.
- **Failures** seen in Portuguese: "queima" → "quema", "octaedros" → "octaítios", "um ar" → "uma arma". Fixes:
  - new seeds;
  - phonetic respelling in the TTS text only (captions use the script text);
  - or rewording.
- **Voice cloning:** pass `--voice ref.wav`. Use 10–15 s of clean speech, no music, mono, quiet room. Accept a clean recording from any suitable device.
- **Whole sentences:** generate sentence by sentence. Pacing and pauses are then controlled in the timeline, and one bad sentence is regenerated alone.

## 3. Timeline (`scripts/build_timing.py`)
- **Layout:** use `build_timing.py --lead`, `--gap` and `--tail` to set pacing (defaults: 0.6 s, 0.45 s and 1.5 s). The trailing silence of each take is ignored.
- **Scenes** start half a gap before their sentence.
- **Events** are anchored to a spoken word, e.g. `detach=5:free:end+0.3`.
- **Outputs** (the single source of truth):
  - `timing.json`;
  - `words.json`, for karaoke captions;
  - `captions.srt`, a soft-subtitle sidecar;
  - `narration.wav`.

## 4. Direction (`templates/DIRECTION_TEMPLATE.md`)
One document a coding agent can implement without questions. It covers:
- **Global look:**
  - palette from `style.json`;
  - materials and element colours appropriate to the scientific subject;
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
- **Starting point:** `examples/salt-dissolving/scene/sal_en.py` or
  `examples/sn2-walden/scene/sn2_en.py` (see `computed-motion.md`). Reusable parts:
  - `Timeline` (reads `timing.json`; `frame()`, `at(scene, fraction)`);
  - `ease`, `sample_path` (smooth camera knots);
  - trajectory interpolation, point meshes and Geometry Nodes;
  - `solve_framing` (puts the subject at a target screen fraction and width);
  - `project_anchor` / `export_anchors`;
  - geometry, camera and time-map validation.
- **Base structure:** load the computed data for your subject and adapt the example scene and `style.json`.
- **Always run** `blender -b -t 2 -P scene.py -- --check` before any render.

## 6. Look iterations
- **Each round:** `--preview` locally or remotely, within your configured resource budget, then a contact sheet:
  `ffmpeg -pattern_type glob -i '*.png' -vf "scale=640:-1,tile=3xR" -frames:v 1 sheet.png`
- **Notes:** the lead agent reviews with the rubric and writes `ITERATION_N.md` with numbered, testable fixes, each saying what to KEEP and what to change.
- **Typical defects:**
  - a visible hard-edged "glow" plane (make glows with World/lights only, never with geometry);
  - bokeh orbs that looked like confetti (fewer, very near or very far from the focus plane, low emission, alpha 0.15–0.35);
  - dark, unlit molecules (add rim light, sheen, slight emission);
  - the final framing too small (solve framing numerically);
  - a missing molecule cloud (count molecules inside the frustum in `--check`);
  - blurry dark background fragments reading as "dirt" (removed).

## 7. Motion preview → G2
- **Render:** `--motion`, all frames, at ~1/9 of the final cost (benchmark on your hardware).
- **Post:** apply the FULL post-production to it (captions, labels, music). The requester judges rhythm, sync and legibility here.
- **Publish and wait:** send the preview, then **wait for an explicit "watched and liked it"**.

## 8. Final render
- **Cost and settings:** 64 spp with adaptive sampling (threshold 0.02), OIDN, motion blur, `render.use_persistent_data = True` (avoids rebuilding the BVH every frame).
- **Chunks:** split into chunks with `frame_ranges.py split`.
  - Set thread counts and concurrent chunks according to your allocation. For remote execution, configure `threads` (default 4) and `max_cpu_percent` (default 60, load-average admission check for `scheduler: none`) in `cluster.yaml`; Slurm/PBS quotas follow the site scheduler.
  - Make chunks resumable: `scene.render.use_overwrite = False` and `use_placeholder = True`, then re-run `frame_ranges.py missing` and render only the gaps.
- **Watching the job:** use `cluster/run_remote.py status` or `wait` for remote jobs, then check the produced files. For local jobs, check the process exit status and frame audit.
- **Before post:** merge the chunks into one folder and run `frame_ranges.py check` (detects missing or truncated frames).

## 9. Post-production and delivery
- **Composer:** `examples/salt-dissolving/post/montar_sal.py` or `examples/sn2-walden/post/montar_sn2.py` (Pillow layers, then ffmpeg overlay). It takes as input:
  - the frames folder;
  - `timing.json`;
  - `anchors.json`;
  - the narration WAVs;
  - optional music (`MUSIC`, unset by default);
  - fonts (`FONT` and `SYMBOL_FONT`; defaults: `DejaVuSans.ttf` and `DejaVuSans-Bold.ttf`, resolved by Pillow).
- **Layers:**
  1. **Karaoke captions** at 88 % of the height, max ~6 words per block, current word in amber. A soft bottom scrim (0 → 60 % opacity over the bottom 32 %) keeps them legible over bright frames; it was added after review.
  2. **Technical labels:** pills with leader lines to anchors, time windows from events, no overlaps (checked numerically).
  3. **Title card** on the clean side of the final frame. The final frame is held 2 s; the title fades in after the last sentence and the captions are off during the title.
  4. **Grain and vignette** only if the render has none.
- **Music:** ambient bed at ~0.28, ducked under the voice with `sidechaincompress`, fades in/out. Choose sound effects according to the project brief; keep them below the narration.
- **Delivery:** `deliver.py finalize` produces:
  - loudness-normalized `master.mp4` (CRF 16);
  - `web.mp4` (CRF 23, faststart);
  - optionally a 9:16 crop;
  - an embedded subtitle track.
- **QA:** `deliver.py qa` checks the specs, black and frozen segments, loudness and true peak.
- **Sharing:** deliver the MP4 and caption sidecar through the channel agreed with the requester.
