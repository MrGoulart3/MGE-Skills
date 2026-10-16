# Direction: <title> (Blender 4.2 / Cycles)

Read first: `SCRIPT.md`, `timing.json` (scenes and events in seconds; never hard-code times), `style.json`.

## Chemistry (1 unit = 1 Å)
- **Structure source:** CIF/COD id; lattice parameters; how many cells.
- **Molecules:** bond lengths and angles; element colours (from `style.json`).
- **Vibrations:** IR normal modes (cm⁻¹ → visual 1.5–4 Hz); amplitude 5–8 % of the bond; mass-weighted, centre of mass fixed.
- **Mechanism, step by step:** positions interpolate smoothly, with no jumps; each step is keyed to an event.

## Look
- **Materials and lighting:** key + rim; World gradient; glow only from lights/World, never from visible planes.
- **Background:** depth via mist; ≤ 25 soft bokeh orbs placed far from the focus plane.
- **Finish:** DoF, bloom (Glare), AgX.

## Camera (single continuous move, eased)
Per scene: path knots, focus target, and the framing goal (subject centre x/y as a fraction of the frame, width fraction). Solve framing numerically.

## Anchors to export (`anchors.json`, per frame, 1920×1080 px)
- name → object/point

## Modes
- **`--check`:** counts, bond lengths, framing numbers, objects in the frustum for 3 frames per scene.
- **`--preview`:** ~10 key frames, including the last.
- **`--motion`:** all frames, 640×360, 8 spp.
- **`--final`:** 1920×1080, 64 spp, adaptive 0.02, OIDN, motion blur, persistent data, `use_overwrite=False`, `use_placeholder=True`.
- **Arguments:** `--frames a-b`, `--threads N`. Fixed seeds. Output to `render/<mode>/####.png`.

## Execution settings
- Local or remote execution, scheduler/allocation and thread count:
- Preview/final resolution and samples (the values above are starting defaults):
- Review responsibilities and approval gates: validate with `--check`, then obtain G2 before final rendering.
