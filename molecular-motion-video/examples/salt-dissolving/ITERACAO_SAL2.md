# Iteration 2 of `scene/sal_en.py` (real MD)

Base: contact sheet `render/sal_en/folha_real2.png`. These are key frames 1, 30, 103, 132, 180, 200, 266, 301, 336, 389, 458, 499, 532, 552, 564 and 681, rendered with the real `md/traj.npz` (OpenMM, 400 K, 6403 atoms, 2113 waters, cubic box 40.2 Å).

Already fixed (keep it):
- the camera keyframing bug: every key was equal to frame 1. The fix re-applies `camera_pose` after `frame_set` in the keyframe loop;
- a post-bake check;
- the data-aware hydration check (median over 10 ps);
- a looser F tolerance.

KEEP:
- the ion look (green Cl⁻, violet Na⁺, glossy);
- the lattice close-up in B (excellent);
- the continuous camera;
- the time mapping;
- the anchors export.

## Problems and fixes (all testable in `--check`)

1. **Water clutter (most important).**
   - **Problem:** all 2113 waters are visible, so every frame is covered by red/white speckle and the story disappears. Close to the camera, big translucent blobs cover the subject (C, D).
   - **New visibility policy**, through the `fade` attribute that drives the instance *scale*, so faded waters are not rendered:
     - **Shell zone:** waters within 7.5 Å of the current subject are fully visible. The subject is the crystal ions still bound (A–D, F) or the focus ions (E).
     - **Haze zone:** between 7.5 and 12 Å, scale and opacity fall smoothly to 0.
     - **Beyond 12 Å:** nothing. The world background, mist and bokeh give the depth instead.
   - **Camera-side cull:** any water whose centre is within 6 Å of the camera ray to the subject (between camera and subject) fades out, so nothing blocks the subject.
   - **Report** in `--check`: visible waters per scene (A–F) and the fraction of the frame covered by water instances in front of the subject. Target: ≤ 350 visible waters, ≤ 5 % occluding.
2. **The hero water in C must be the star.**
   - It must be ≥ 18 % of the frame height, sharply focused, isolated: no other water within the shell zone of the hero is shown except the crystal behind it (out of focus).
   - Check that the measured value comes from the KEYED camera at the C mid-frame (as in the post-bake check), not from the solver.
3. **Framing uses only the ions still in the crystal.**
   - **A, B, D and F:** frame the bound ions only. Bound means within 3.6 Å of ≥ 3 other ions at that MD time. Ions that already left must not inflate the bounds.
   - **F target:** crystal height ≈ 0.40, centre x ≈ 0.68, with the hydrated ions drifting around it.
   - **A target:** ≈ 0.35.
4. **E: show the hydration shell clearly.**
   - The detaching ion (`ion1`, then `ion2`) keeps its first-shell waters (Cl⁻: H within 2.9 Å; Na⁺: O within 3.2 Å) fully visible with `highlight`: brighter, with a thin emissive rim.
   - Optional: a faint translucent sphere of radius 3.4 Å (Na⁺) or 3.9 Å (Cl⁻) around the ion, fading in on `shell`.
   - All other waters in E use the visibility policy relative to the focus ions.
5. **Ion colours.** Na⁺ reads dark blue: make it a clearer violet (`#8F6BFF`, slightly more emission or sheen) so it is distinct from the background.

## Validation
- Validate syntax with `python3 -m py_compile scene/sal_en.py`. Run `--check` and a small `--preview` within your configured resource budget.
- These notes describe one review of the public example. Adapt visual targets to your own brief; obtain G2 before final rendering.
