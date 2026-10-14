# "Salt dissolving": narrated script (showcase video of the molecular-motion-video skill)

**Brief.**
- **Audience:** general / students, and the GitHub README of the skill (a showcase).
- **Duration:** ~32 s. **Language:** English (narration, captions, labels, title).
- **Voice:** Chatterbox Multilingual, `en`, exaggeration ~0.55, cfg 0.4; best-of-N, Whisper-verified.
- **Mandatory facts:**
  1. salt is an ionic crystal of Na⁺ and Cl⁻;
  2. water is polar (O δ−, H δ+);
  3. water orients (O → Na⁺, H → Cl⁻) and pulls edge/corner ions out;
  4. each ion leaves wrapped in a hydration shell.
- **Look:** 100 % molecular (no macro objects). This is the world the requesters liked: glossy CPK-like spheres, rim light, dark blue depth with mist and bokeh.
- **Motion:** driven by a REAL molecular-dynamics trajectory (`md/traj.npz`), not keyframed.
- **Stage:** low-res motion preview first (G2). The final render happens only after the requester watches and approves.

## Narration (~75 words)
1. "Drop a pinch of salt into water, and it seems to vanish. But where does it go?"
2. "Salt is a crystal: sodium and chloride ions, locked together by opposite charges."
3. "Water molecules are tiny magnets of charge: slightly negative at the oxygen, slightly positive at the hydrogens."
4. "At the edges of the crystal, they crowd in, oxygens toward sodium, hydrogens toward chloride, and tug."
5. "One by one, the ions break free, each wrapped in its own shell of water."
6. "That is dissolving: not vanishing, just spreading out, one ion at a time."

`narration.json` keywords per sentence:

| Sentence | Keywords |
|---|---|
| 1 | salt, vanish |
| 2 | crystal, sodium, chloride |
| 3 | negative, oxygen, positive, hydrogens |
| 4 | edges, oxygens, chloride |
| 5 | free, shell |
| 6 | dissolving, spreading |

## Scene table (one continuous camera)
| Scene | Sentence | Picture (what is in focus when the word is said) | Hook to the next scene | Events |
|---|---|---|---|---|
| A | 1 | Out of a deep blue haze (out of focus), a glittering cubic cluster appears, in a soft field of bokeh water molecules. Slow push-in. | Push into the crystal face. | `reveal=1:salt:start` |
| B | 2 | Crystal lattice close-up. Na⁺ (violet, smaller) and Cl⁻ (green, larger) alternate; a faint "charge glow" (Na⁺ warm, Cl⁻ cool) pulses once on "opposite charges". Labels Na⁺ / Cl⁻. | Camera tilts to one water molecule drifting in front. | `label_ions=2:sodium:start`, `charges=2:opposite:start` |
| C | 3 | Hero water molecule in sharp focus. δ− glow on O (red), δ+ glows on the H atoms (white/blue); a soft dipole arrow. Labels "δ−" and "δ+". | Water joins the crowd at the crystal corner. | `delta_minus=3:negative:start`, `delta_plus=3:positive:start` |
| D | 4 | Crystal corner with surrounding water from the MD: waters near Na⁺ point O inward, waters near Cl⁻ point H inward (highlight the first-shell waters, dim the rest). | Focus on the corner ion that is about to leave. | `orient=4:oxygens:start` |
| E | 5 | MD detach events: the first ion leaves the crystal with its hydration shell (shell waters highlighted, faint shell sphere); then a second ion. Label "hydration shell". | Pull back. | `detach=5:free:start`, `shell=5:shell:start` |
| F | 6 | Wide: crystal with scattered hydrated ions drifting out, depth haze. Title card on the left: "Dissolving" + "NaCl(s) → Na⁺(aq) + Cl⁻(aq)". | End. | `title=6:dissolving:start` |

## Scientific claims (G1: the requester validates)
| Claim | Source | Intentional simplification |
|---|---|---|
| NaCl is an ionic rocksalt crystal; Na–Cl distance ≈ 2.82 Å | Standard crystallography | Nanocrystal of 64 ions instead of a macroscopic grain. |
| Water is polar: O partial negative, H partial positive | Textbook | "Tiny magnets of charge" is a metaphor for a dipole. |
| Water orients O→Na⁺ and H→Cl⁻; first-shell coordination ≈ 6 for both | MD/neutron data (e.g. Joung–Cheatham ions) | Highlight shows only first-shell waters. |
| Edge and corner ions dissolve first and leave hydrated | MD literature on NaCl dissolution | Dissolution is accelerated (high T or gentle pulling) so it fits in nanoseconds; disclosed in the README. |
| Time compression | — | Picoseconds–nanoseconds shown in seconds; an on-screen time counter ("t = 0.0 ns") keeps it honest. |
