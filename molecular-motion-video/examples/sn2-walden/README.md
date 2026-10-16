# Example: "SN2: the Walden inversion" (reactive-trajectory showcase)

**English** · [Português](README.pt-BR.md)

![SN2: the Walden inversion](media/sn2_walden.gif)

A 26 s narrated English video of the reaction Cl⁻ + CH₃Br → ClCH₃ + Br⁻ in water. The chloride attacks the carbon from the side opposite the bromine (backside attack), the C–Cl bond forms while the C–Br bond stretches, the CH₃ group passes through a planar transition state and flips like an umbrella, and Br⁻ leaves. **Every atom moves along a real quantum-chemical trajectory**, and the bond lengths on screen are measured from it. Video: [`media/sn2_walden_1080p.mp4`](media/sn2_walden_1080p.mp4).

Final render: 1920×1080, Cycles 32 spp + OpenImageDenoise, motion blur. Audio QA: −16.2 LUFS, true peak −1.43 dBTP. Made after the low-resolution preview passed the human review gate (G2).

## What it shows
1. Reactants in water: Cl⁻ and CH₃Br with a few waters.
2. Approach and backside alignment (Cl–C–Br close to 180°).
3. The transition state: carbon shared between Cl and Br, three hydrogens flat.
4. Bond forming and breaking, with C–Cl and C–Br distances read from the trajectory.
5. Umbrella inversion of CH₃ (the Walden inversion).
6. Br⁻ leaving, and the product ClCH₃.

An on-screen femtosecond clock shows the **simulated** time, with slow motion around the TS. A small energy curve is shown qualitatively (no energy values are quoted).

## The calculation
| Item | Value |
|---|---|
| Engine | GFN2-xTB via tblite 0.7, ALPB implicit water |
| System | Cl⁻ + CH₃Br + 40 explicit waters, with a harmonic wall to keep the cluster together |
| TS search | Relaxed scan of ξ = d(C–Br) − d(C–Cl); the maximum was verified as a saddle point by **one imaginary frequency** |
| Solvent | Equilibrated for 1 ps at 300 K with the TS distances fixed |
| Dynamics | 12 trajectories shot from the TS forward and backward in time (NVE, 0.5 fs step); 2 were reactive, and one was chosen for the video |
| Time map | Slow motion around the TS, with the fs clock on screen |

**Disclosure:** the reaction is a rare event at 300 K. The trajectory shown was launched from the transition state (transition-path shooting), a standard technique, and the video says so on screen ("launched from the transition state").

### Computed events (detected in code, time relative to the TS crossing)
| Event | Definition | Time (fs) |
|---|---|---|
| approach | d(C–Cl) < 4.0 Å | −196 |
| backside | Cl–C–Br angle > 150° | −115 |
| ts | ξ crosses the scan maximum | +1 |
| flip | umbrella inversion: C crosses the H₃ plane and stays | +18 |
| bond | d(C–Cl) < 2.0 Å after the TS | +36 |
| leave | d(C–Br) > 3.0 Å after the TS | +52 |

## Files
| Path | What it is |
|---|---|
| `SCRIPT.md` | Script, scene table and scientific-claims table (G1) |
| `DIRECTION.md` | Direction given to the coding agent |
| `narration.json` | Sentences + keywords for `scripts/tts_verified.py` |
| `calc/ts_scan.py`, `calc/shoot.py`, `calc/make_traj.py` | TS scan and frequency check, shooting from the TS, conversion to the skill's trajectory contract |
| `calc/scan.json`, `calc/ts_freq.txt` | Scan results and TS frequencies |
| `md/events.json`, `md/DATA_README.md` | Computed events, how to regenerate the data |
| `scene/sn2_en.py`, `scene/style.json` | Blender scene (trajectory replay, bonds from distances, camera) |
| `post/montar_sn2.py` | Captions, labels, fs clock, energy inset and title (Pillow + ffmpeg) |
| `media/` | Final 1080p video, poster, GIF |

The trajectory (`traj.npz`) is not stored here. See [`md/DATA_README.md`](md/DATA_README.md).
