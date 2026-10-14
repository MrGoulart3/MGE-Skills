# Computed motion: driving the video with molecular behaviour that was actually calculated

The strongest scientific animations do not *invent* how atoms move. They **replay a calculation**.
That calculation can be a molecular-dynamics trajectory, a reaction path, a vibrational mode or a
set of optimised structures. The animation then becomes evidence, not just illustration: every
position on screen exists in a data file that a reviewer can open.

This skill treats computed motion as the default whenever the story is about *how molecules
behave*: dissolution, diffusion, binding, a reaction, a conformational change. Keyframed motion is
the fallback, and only for things that have no meaningful dynamics.

## What can drive a scene

| Story beat | Calculation | Typical tools | What it gives the video |
|---|---|---|---|
| Dissolution, solvation, diffusion, adsorption, self-assembly | Classical MD (NVT/NPT); enhanced sampling if the event is rare | OpenMM, GROMACS, LAMMPS, CP2K | Real thermal motion, real solvent orientation, real event order |
| A chemical reaction | IRC or NEB (reactant → TS → product) | xTB, ORCA, Gaussian, ASE-NEB | Correct bond breaking/forming geometry and the transition state |
| "The molecule vibrates / absorbs IR" | Frequency calculation (normal modes) | ORCA, Gaussian, xTB `--hess` | Mode shapes with correct relative amplitudes and directions |
| Flexibility, conformers | Conformer search + optimisation | CREST, RDKit + xTB | Real low-energy shapes; morph between them along an interpolated path |
| Mechanism with intermediates | DFT-optimised intermediates (+ IRCs between them) | ORCA, Gaussian, VASP | Every frame of the mechanism is a computed structure |
| Crystal or surface | CIF/COD structure, relaxed slab | ASE, pymatgen, VASP/QE | Correct lattice and surface termination |

## The data contract (`traj.npz`)

The scene code never parses MD or QM formats itself. A converter writes one neutral file:

- `positions`: float32 (F, N, 3) in Å, **unwrapped** (whole molecules, no periodic jumps) and
  centred on the subject;
- `time_ps`: (F,) for MD; for paths, use `reaction_coordinate` (F,) in bohr·amu½, or an image index;
- `element`: (N,) chemical symbols;
- `molecule`: (N,) molecule id (solvent molecules, ions and solute each get their own id);
- optional: `energy` (F,) in kJ/mol or eV, `box` (3,), `charges` (N,);
- plus `events.json`: named, *computed* events with a frame index. Examples: an ion detaching
  (distance threshold), a bond breaking (the bond order or distance crosses a threshold), the TS
  (maximum energy). Detect events with code, not by eye.

`scripts/traj_to_npz.py` converts anything ASE can read (xyz/extxyz, ORCA `.trj`/IRC, Gaussian
IRC, CP2K, VASP XDATCAR, LAMMPS dumps, ...) and can trim the solvent to a radius around the
subject. For GROMACS/AMBER trajectories, use MDAnalysis to write extxyz first, or save `.npz`
directly from OpenMM.

## Rules of honesty
1. **Never edit atomic positions to fit the story.** You may choose *which* window to show, the
   camera, colours, highlights and the playback speed, but not the coordinates.
2. **Light smoothing only**:
   - a short temporal filter on solvent jitter, or
   - Catmull-Rom interpolation between saved frames.

   Never smooth through an event (bond breaking, ion leaving).
3. **Time is compressed, and the video says so.**
   - Show an on-screen clock ("t = 0.42 ns") from the exported per-frame `md_time_ps`, or a
     reaction-coordinate bar for paths.
4. **Disclose acceleration.** Rare events need high temperature, steered MD, metadynamics or
   biased sampling to fit in nanoseconds. Name the method:
   - in the claims table (G1);
   - in the README of the data;
   - if the venue demands it, in a small on-screen note.
5. **Validate before rendering.** `--check` must print physical sanity numbers taken from the
   data, for example:
   - nearest-neighbour distances (Na–Cl ≈ 2.8 Å; O–H ≈ 0.96 Å);
   - coordination numbers of the first solvation shell;
   - bond lengths at the TS;
   - water density.
6. **The calculation is a source.** The claims table cites it: method, force field/functional,
   basis, temperature, length, software version. Keep the input files and the converter command
   next to the scene, so the video can be regenerated.

## Rendering architecture (Blender, thousands of atoms)
- Do not create one object per atom with keyframes. Use **one point mesh per species group** and
  update its vertex positions in a `frame_change_pre` handler. The handler reads the `.npz`
  (memory-mapped) and interpolates at the *float* frame, so it is subframe-aware and Cycles motion
  blur still works.
- **Geometry Nodes** instance spheres on the points and draw bonds as edges → curve → tube.
  Bonds come from a distance criterion per frame, so they really break and form in reactive
  trajectories.
- **Per-point attributes** (`highlight`, `glow`, `fade`) are written by the same handler and read
  by the materials. Use them to highlight first-shell solvent, pulse partial charges, or dim
  the bulk.
- **Time mapping** (MD time → video time) is a smooth, monotonic function that pins the computed
  events to narration words in `timing.json` (e.g. the `detach` event lands right after the word
  "free"). Export it per frame in `anchors.json` for the on-screen clock.
- **Pitfall: handler + keyframes.** If you bake the camera (or anything) into keyframes by looping `frame_set()`, the F-curves created in earlier iterations overwrite what the `frame_change_pre` handler just set, so every key ends up equal to frame 1. Re-apply the pose after `frame_set()` before `keyframe_insert()`, and add a post-bake check that compares the keyed camera with the validated one, and that it actually moves.
- Trim the solvent to what the camera can see (radius around the subject): thousands of molecules
  outside the frame cost render time and add nothing.

## Checklist for a computed-motion video
- [ ] Calculation chosen to match the story beat (table above), with acceleration disclosed.
- [ ] `traj.npz` + `events.json` + data `README.md` (method, versions, validation numbers).
- [ ] The scene reads the data; `--check` prints sanity numbers and the time-mapping table.
- [ ] Events pinned to narration words; on-screen clock or reaction-coordinate bar.
- [ ] Claims table cites the calculation; G1 approved.
