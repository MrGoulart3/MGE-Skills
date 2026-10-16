# Example: "Salt dissolving" (computed-motion showcase)

**English** · [Português](README.pt-BR.md)

![Salt dissolving](media/salt_dissolving.gif)

A 28 s narrated English video in which a NaCl nanocrystal dissolves in water. **Every atom moves along a real molecular-dynamics trajectory**, not keyframed animation. Final render (v2, 1920×1080, Cycles with denoising and motion blur), made after the low-resolution preview passed the human review gate (G2). Video: [`media/salt_dissolving_1080p.mp4`](media/salt_dissolving_1080p.mp4).

v2 changes after review: larger δ−/δ+ labels pushed outside the highlighted water, a camera that follows that water through its close-up, and a close-up on the leaving Cl⁻ with the rest of the crystal dimmed.

## What it shows
1. A salt crystal in water.
2. The Na⁺/Cl⁻ lattice.
3. One polar water molecule (δ−/δ+).
4. Water orienting at the crystal edge (O → Na⁺, H → Cl⁻).
5. Ions leaving with their hydration shells.
6. Title card "Dissolving", with NaCl(s) → Na⁺(aq) + Cl⁻(aq).

An on-screen clock shows the **simulated** time (picoseconds), so the time compression is honest.

## The calculation
| Item | Value |
|---|---|
| Engine | OpenMM 8.6 (CPU) |
| Force field | TIP3P water, Joung–Cheatham ions (`amber14/tip3p.xml`) |
| System | 4×4×4 NaCl (64 ions) + 2113 waters (6403 atoms) in a 40.2 Å cubic box |
| Electrostatics and integration | PME, 2 fs, rigid water |
| Protocol | minimisation → NVT 300 K (100 ps) → NPT 1 bar (150 ps) → **NVT 400 K production** (300 ps, 1 frame/ps) |
| Acceleration (disclosed) | elevated temperature, so that dissolution fits in ~10² ps. TIP3P also over-diffuses. |
| Events (detected in code) | first Cl⁻ leaves at 44 ps, then 6 more ions by 198 ps; first-shell hydration ≈ 6 waters |

Post-processing (`md/fix_traj.py`) does four things:
- unwraps the trajectory in time;
- keeps molecules whole;
- picks **one** fixed periodic image per water, so that it sits next to the ions it hydrates;
- centres the frame on the least-mobile ions.

## Files
| Path | What it is |
|---|---|
| `SCRIPT.md` | Script, scene table A–F (narration events) and scientific-claims table (G1) |
| `narration.json` | Sentences + keywords for `scripts/tts_verified.py` (6/6 takes verified by Whisper) |
| `timing/` | `timing.json`, `words.json`, `captions.srt` from `scripts/build_timing.py` |
| `MD_SPEC.md` | Data contract given to the agent that ran the MD (in Portuguese) |
| `md/md_sal.py`, `md/post.py` | OpenMM simulation and raw post-processing |
| `md/fix_traj.py`, `md/events.json`, `md/DATA_README.md` | Final data preparation, computed events, data notes |
| `md/fake_traj.py` | Synthetic trajectory with the same contract (develop the scene before the MD finishes) |
| `DIRECTION.md`, `ITERACAO_SAL2.md` | Direction given to the coding agent, plus the review iteration (rubric-driven fixes) |
| `scene/sal_en.py`, `scene/style.json` | Blender 4.2 scene: point meshes + Geometry Nodes, `frame_change_pre` handler, numeric camera solver, data-aware `--check` |
| `post/montar_sal.py` | Captions, labels, MD clock and title card (Pillow + ffmpeg), with sidechain-ducked music |

The trajectories (`traj.npz`, about 14 MB each) are not stored here. Rerun `md/md_sal.py` and then `md/fix_traj.py`.

## Lessons recorded in the skill
- Baking a camera driven by a `frame_change_pre` handler: re-apply the pose after `frame_set()`, because existing F-curves overwrite it. Add a post-bake check.
- Show only the water near the subject (≈ 7.5 Å shell, fading out by 12 Å) and cull water between the camera and the subject. Otherwise thousands of molecules become noise.
- Calibrate `--check` thresholds on real data (hydration numbers fluctuate ps by ps; use a median window).

## Run in your own environment

Run commands from this example directory, using the calculation, TTS or render environment as
appropriate (see the repository README). To regenerate the trajectory, run from `md/`:

```bash
MMV_THREADS=4 python3 md_sal.py 400 300 1
python3 post.py prod_raw.npz .
mv traj.npz traj_raw.npz
python3 fix_traj.py
```

The three simulation arguments are production temperature (K), maximum production time (ps)
and equilibration scale (`1` for full equilibration). `NT` overrides `MMV_THREADS` for
compatibility; the default is 4 threads. The scientific settings above reproduce this example;
choose new settings and validate the results for another system.

Back in this example directory, synthesize narration and rebuild its timing:

```bash
python3 ../../scripts/tts_verified.py --script narration.json --out narration --lang en
python3 ../../scripts/build_timing.py --narration narration --out timing \
  --scenes A=1 B=2 C=3 D=4 E=5 F=6 \
  --events reveal=1:salt label_ions=2:sodium charges=2:charges \
  delta_minus=3:negative delta_plus=3:positive orient=4:oxygens \
  detach=5:free shell=5:shell title=6:dissolving
blender -b -t 4 -P scene/sal_en.py -- --check --threads 4
blender -b -t 4 -P scene/sal_en.py -- --preview --threads 4
```

The scene reads `md/` and `timing/`, writes `anchors.json` at the example root and puts frames
in `render/sal_en/<mode>/`. After rendering all frames of an approved mode, assemble them:

```bash
python3 post/montar_sal.py --quadros render/sal_en/motion --saida preview.mp4 --procs 2
```

`montar_sal` means “assemble the salt video”; `--quadros` selects input frames, `--saida` the
output, and `--teste` a compositor check requiring timing, narration and real anchors. Use
`--motion` for a full low-resolution preview, obtain G2, then use `--final`. Set `FONT` and
`SYMBOL_FONT` to installed font files if needed (defaults: DejaVu Sans regular/bold). Media tools
use `PATH` or `FFMPEG`/`FFPROBE`; `MUSIC` optionally adds a licensed soundtrack. Without `MUSIC`,
the video contains narration alone. No private assets or fixed conda environment name are required.
