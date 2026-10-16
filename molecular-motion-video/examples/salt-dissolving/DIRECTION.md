# Direction: "Salt dissolving" (Blender 4.2 / Cycles), showcase video of the molecular-motion-video skill

Read first:
- `../../SKILL.md`, plus `../../references/protocol.md` and `../../references/critique-rubric.md`;
- `SCRIPT.md`: scenes A–F, events and claims;
- `MD_SPEC.md`: the data contract of `md/traj.npz` and `md/events.json`;
- `scene/style.json`: colours. Adapt `../../templates/style.json`, adding Na `#8F6BFF` (violet), Cl `#39D98A` (green), δ− `#FF5A4E`, δ+ `#7FD0EC`.

Adapt the public `scene/sal_en.py`. Reusable utilities include: Timeline (reads `timing/timing.json` with keys `scenes`, `events`, `duration`, `frames`, `fps`; times are NEVER hand-coded), `ease`, materials, World and compositor (Glare/bloom, AgX, mist), camera with DoF, `solve_framing`, `project_anchor`/`export_anchors`, `frame_range`, `thread_count`, `parse_arguments`, and the modes/arguments.
- Example look: glossy spheres, coral O, pearl H, blue mist and soft bokeh. Adjust these choices to your own brief.
- This example stays at the molecular scale.

## Data-driven motion (the core)
- **Loading:** load `md/traj.npz` with numpy (`positions` (F, N, 3) Å, `time_ps`, `element`, `molecule`) and `md/events.json`.
- **Geometry:** do NOT create one Blender object per atom with keyframes (thousands of objects × 800 frames is too heavy). Use:
  - ONE point mesh per species group (Na, Cl, water O, water H), whose vertex positions are set by a `bpy.app.handlers.frame_change_pre` handler registered by the script (it works in `-b -P` renders). It must be subframe-aware (float frame) so that Cycles motion blur in `--final` works.
  - Geometry Nodes "Instance on Points" with UV spheres (smooth shading). Display radii: Na⁺ 0.62 Å, Cl⁻ 1.05 Å (ionic-size ratio kept), O 0.40 Å, H 0.24 Å.
  - O–H bonds as a GN mesh (edges updated by the same handler) → Curve → Curve to Mesh with a 0.09 Å circle profile.
  - No Na–Cl bonds (ionic crystal).
- **Per-point attributes** set by the handler and read by the materials (Attribute node): `highlight` (0–1), `glow` (0–1), `fade` (0–1). They drive:
  - first-shell waters (Na–O < 3.2 Å, Cl–H < 2.9 Å) of the focused ion(s) brighter, with a thin emissive rim;
  - bulk water dimmed and more transparent/defocused, so the eye reads the crystal and the shells;
  - the charge glow on ions in scene B (Na⁺ warm, Cl⁻ cool, one gentle pulse on `charges`);
  - δ− (red) on the hero water O and δ+ (blue) on its H in scene C, timed to `delta_minus` and `delta_plus`.
- **Time mapping MD → video:** monotonic, smooth (piecewise cubic) and exported in `anchors.json` per frame as `md_time_ps`, so the post can show "t = 0.42 ns". Interpolate positions between MD frames with Catmull-Rom on unwrapped coordinates, with no popping.
  - A–D: slow passage through the early window (crystal intact, waters jiggling).
  - E: the first detach event (`events.json`) lands right after the `detach` word; the second detach happens before the end of E.
  - F: continue (or gently hold) so the hydrated ions drift away.
- **Vibration:** the MD already has thermal motion. Smooth it slightly (a temporal filter on the waters) so it reads as calm but alive, never frozen.

## Look
- **World:** deep teal → indigo gradient, mist (depth), ≤ 20 far bokeh orbs; no visible planes; key + cool rim light.
- **Ions:** Na⁺ satin violet, Cl⁻ satin green, slight subsurface/sheen, thin rim emission.
- **Waters:** coral O / pearl H as specified in `scene/style.json`; highlighted shells slightly brighter. Optional: a very faint translucent "shell bubble" (sphere, radius ≈ first-shell distance) around a detaching ion during E, on `shell`.
- **Camera:** one continuous camera with eased curves, DoF always on. Framing:
  - **A:** start defocused (bokeh) and pull focus onto the crystal on `reveal`; crystal ≈ 35 % of the frame height.
  - **B:** close on a crystal face, lattice filling ≈ 70 % of the height.
  - **C:** the hero water ≥ 18 % of the height, in sharp focus, crystal soft behind it. The hero water is an MD water that is in a first shell during D/E: choose it automatically.
  - **D:** the corner that will release the first ion.
  - **E:** follow the detaching ion with its shell (it must stay inside the central 60 % of the frame).
  - **F:** pull back; crystal in the right third (centre x ≈ 0.68, height ≈ 45 %); clean left half for the title. Solve framings numerically (`solve_framing`).

## Anchors (`anchors.json`, per frame, px at 1920×1080)
- `crystal_center`;
- `label_na` (a surface Na⁺ facing the camera in B) and `label_cl`;
- `hero_o`, `hero_h1`, `hero_h2`;
- `ion1`, `ion2` (the detaching ions);
- `md_time_ps`.

## Modes
- **`--check`:**
  - counts per species;
  - Na–Cl nearest distance in frame 1 (≈ 2.8 Å) and O–H ≈ 0.96 Å;
  - number of first-shell waters around `ion1` at the detach frame (5–7);
  - projected radius in px at 1080p of Na⁺ in B and of the hero water in C (≥ 14 px and ≥ 40 px);
  - framing numbers for A–F;
  - that `ion1`/`ion2` stay inside the safe area during E;
  - the MD time-mapping table;
  - a mean-brightness estimate for each scene (no scene darker than 0.03).
- **`--preview`:** ~12 key frames (the scene starts/ends and the events).
- **`--motion`:** all frames at 640×360, 16 spp, OIDN on, no motion blur.
- **`--final`:** 1920×1080, 64 spp, adaptive 0.02, OIDN, motion blur, `use_persistent_data=True`, `use_overwrite=False`, `use_placeholder=True`.
- **Output:** `render/sal_en/<mode>/####.png`, relative to this example directory. Fixed seeds.

## Testing without the real MD
- Run `md/fake_traj.py`. It generates a synthetic `md/traj_fake.npz` + `md/events_fake.json` that follows the contract:
  - 4×4×4 rocksalt;
  - ~600 random rigid waters with small thermal jitter;
  - one Na⁺ and one Cl⁻ leaving the corner with 6 waters carried along;
  - 300 frames at 1 ps.
- `sal_en.py` takes `--traj <path>`, defaulting to `md/traj.npz` and falling back to the fake one if the real one is absent.
- If `timing/timing.json` does not exist yet, create a provisional one with ~32 s, scenes A 0–5, B 5–10.5, C 10.5–17, D 17–23, E 23–28, F 28–32.5, and plausible event times. Mark it `"provisional": true`.

## Execution settings
- Run locally or remotely according to your allocation. `--threads N` controls scene threads (default 4); also pass `-t N` to Blender. Start with `--check` and a few `--preview` frames before longer jobs.
- For remote jobs, adapt `../../cluster/cluster.example.yaml` and use `../../cluster/run_remote.py`. CPU/load budgets are configurable; site scheduler rules take precedence.
- Keep work in your project directory and obtain G2 before final rendering. Record the validation output and known limitations.
