# "SN2: the Walden inversion" — narrated script (2nd showcase of the molecular-motion-video skill)

**Brief:** second example for the public skill repo, after "Salt dissolving". High quality; a first light version is sent for review before any final render.
- **Audience:** students / general science, GitHub README showcase. **Language:** English. **Length:** ~28–32 s.
- **Story:** Cl⁻ + CH₃Br → ClCH₃ + Br⁻ in water: backside attack, C–Cl forms while C–Br stretches, trigonal-bipyramidal transition state (planar CH₃), umbrella inversion, Br⁻ leaves.
- **Motion:** a REAL reactive trajectory (GFN2-xTB, explicit water cluster + ALPB), shot from the transition state forward and backward in time (transition-path shooting), with an on-screen femtosecond clock. Energy curve: relaxed scan of ξ = d(C–Br) − d(C–Cl), shown qualitatively (no energy values are cited).
- **Look:** same world as the salt video (dark blue depth, glossy spheres, rim light); Cl green as in the salt video, Br dark red-brown, C grey, H white; waters faint.

## Narration (~75 words; sentence 6 respells "SN2" for the TTS)
1. This is a chemical reaction, replayed from a real simulation, femtosecond by femtosecond.
2. A chloride ion closes in on methyl bromide, always from the side opposite the bromine.
3. As the new carbon–chlorine bond forms, the old carbon–bromine bond stretches.
4. At the top of the energy barrier, the carbon is shared, and its three hydrogens lie flat.
5. Then they flip, like an umbrella in the wind, and bromide is pushed out.
6. One step, one inversion. That is an SN2 reaction.

## Scene table (one continuous camera)
| Scene | Sentence | Picture | Events |
|---|---|---|---|
| A | 1 | Out of the haze: CH₃Br in a faint water cluster, Cl⁻ in the distance; clock "t = −… fs" appears. | `reveal`, `clock` |
| B | 2 | Camera aligns with the Cl···C–Br axis; Cl⁻ approaching along it; dashed axis line; labels Cl⁻, CH₃Br. | `label_cl`, `axis` (on "opposite") |
| C | 3 | Side view: C–Cl bond grows in (dashed → solid), C–Br elongates; live distance readouts in Å from the data. | `bonds` |
| D | 4 | Transition state: CH₃ planar; "‡" mark; inset energy curve with a dot at the top. Slow-motion around the TS (time mapping, disclosed by the clock). | `ts` (on "top"), `flat` |
| E | 5 | Umbrella flips; Br⁻ drifts away and picks up waters; label Br⁻. | `flip`, `leave` |
| F | 6 | Wide, title card: "SN2" + "Cl⁻ + CH₃Br → ClCH₃ + Br⁻" + "one step · inversion of configuration"; footnote "GFN2-xTB trajectory launched from the transition state". | `title` |

## Scientific claims (G1: human validates)
| Claim | Source | Simplification |
|---|---|---|
| SN2 is concerted: bond formation and bond breaking in one step | Textbook (Ingold); our scan has one maximum | — |
| Backside attack, ~180° Cl–C–Br at the TS | Textbook; checked in our TS geometry | — |
| TS: trigonal bipyramid, CH₃ planar, one imaginary frequency | Our TS + Hessian (ts_freq.txt) | GFN2-xTB level; DFT refinement planned |
| Walden inversion (umbrella flip) | Textbook | CH₃ has no stereocentre: the inversion is shown as the umbrella flip |
| Real time | Trajectory in fs | Reaction is rare in reality; we show a trajectory launched AT the TS (standard transition-path shooting) and say so on screen |

**G1/G2:** the light preview was approved by the human reviewer; no energy values are cited anywhere (video, page, README).
