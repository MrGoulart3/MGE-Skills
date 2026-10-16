# Direction — "SN2: the Walden inversion" (scene `sn2_en.py`)

Base: `../salt-dissolving/scene/sal_en.py` (same architecture: point meshes per element + Geometry Nodes,
`frame_change_pre` handler subframe-aware, per-point attributes `highlight`/`glow`/`fade`,
continuous camera sampled per frame then keyframed, anchors exported per frame, `--check/--preview/--motion/--final`,
`--frames a-b`, `--threads N`, `--samples N`). Adapt, do not start from zero. Same `style.json` world (copy and extend).

## Data (real, never edited)
- `md/traj.npz`: `positions` (F,N,3) Å, `time_fs` (F,) 1 fs apart, `element` (N,), `molecule` (N,)
  (0 = CH3Br/Cl solute: atom order C, Br, Cl, H, H, H; then one id per water).
  GFN2-xTB + ALPB(water) with 40 explicit waters, trajectory shot from the transition state
  (backward half reversed + forward half), 300 K, NVE, 0.5 fs step, saved every 1 fs.
- `md/events.json`: computed events in fs (e.g. `approach`, `ts` = crossing of ξ = ξ‡, `flip` = umbrella
  inversion (signed height of C above the H3 plane changes sign), `leave` = d(C–Br) > 3.0 Å).
- `calc/scan.json`: relaxed scan ξ = d(C–Br) − d(C–Cl) vs energy for the qualitative energy inset (post; no values shown).

## Look
- Atoms: C grey `#8A9099`, H white, Cl green (same as salt video), Br deep copper-red `#A4452C`,
  water O red / H white like the salt video but **faint** (fade ≈ 0.35, smaller), solute full.
- Radii (Å, display): C 0.55, H 0.30, Cl 0.95, Br 1.05, O 0.40 (water), H 0.24 (water).
- **Bonds are data-driven**: Pauling bond order n = exp((r0 − r)/0.30) with r0 C–H 1.09, C–Cl 1.79, C–Br 1.95.
  Tube radius ∝ n (max 0.16 Å), opacity ∝ n, drawn only when n > 0.08. So C–Cl visibly *grows in*
  and C–Br *thins out* — straight from the distances. Water O–H bonds as in salt.
- At the TS (event `ts`): a soft glow on C (glow attribute) and on the forming/breaking bonds.
- Background, mist, bokeh, DOF, AgX look: as in salt.

## Camera (one continuous move)
- A (reveal): wide, out of the haze, solute centred; waters as faint cloud.
- B (axis): camera moves so the Cl···C–Br axis is horizontal across the frame (Cl left, Br right),
  ~3/4 view (axis tilted 20° toward camera) so CH3 umbrella reads.
- C (bonds): slow push-in on C; frame Cl–C–Br span ≈ 60 % of width.
- D (TS, slow motion): close, the three H in profile so "lie flat" is visible: view direction ⟂ to the axis.
- E (flip/leave): follow the leaving Br⁻ a little (pan right) while CH3Cl stays in frame.
- F: pull back, solute on the right third (x ≈ 0.66), room for the title on the left.
- Camera tracks the solute centroid (Cl, C, Br) each frame (data moves).

## Time mapping (fs → video s)
Monotonic piecewise-smooth map pinning computed events to words in `timing.json`:
`approach`→`label_cl`, `ts`→`ts` word ("top"), `flip`→`flip`, `leave`→`leave` ("bromide").
Slow motion around the TS (≈ 10–20 fs of data over ~4 s of video); faster away from it.
Export per frame `t_fs` for the on-screen clock.

## Anchors to export (per frame, 1920×1080 px, with `visivel`)
`C`, `Cl`, `Br`, `H1`, `H2`, `H3`, `mid_CCl`, `mid_CBr`, plus per-frame data: `t_fs`, `d_CCl`, `d_CBr`,
`xi`, `umbrella` (signed C height above H3 plane, Å).

## Post (labels/inset; text never in 3D)
- Labels: "Cl⁻", "CH₃Br", later "Br⁻", "‡" near C at TS; live distance readouts "C–Cl 2.41 Å" /
  "C–Br 2.30 Å" near the bond midpoints during C–D.
- Inset (top-right, D–E): energy vs ξ from `scan.json`, dot at current ξ(t) (interpolated on the scan).
- Clock "t = −120 fs" (bottom-right or top-right) + "GFN2-xTB · 300 K · launched from the transition state".
- Title (F): "SN2" big, "Cl⁻ + CH₃Br → ClCH₃ + Br⁻", "one step · inversion of configuration".

## Checks (`--check`, numbers from the data)
- C–H ≈ 1.09 Å; at TS frame: d(C–Cl), d(C–Br), Cl–C–Br angle (> 165°), umbrella ≈ 0.
- ends: frame 0 is reactant (d C–Br < 2.15, d C–Cl > 2.9), last is product.
- framing per scene (solute span), DOF focus on C, no water occluding C (> 8 %).
