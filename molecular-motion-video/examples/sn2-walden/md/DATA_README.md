# Data notes

`traj.npz` (the trajectory the scene reads) is not committed. To regenerate it, use an environment with `tblite-python` (tblite 0.7), `ase`, `numpy` and `scipy`, then run from `calc/`:

1. `python ts_scan.py` : relaxed scan of ξ = d(C–Br) − d(C–Cl), TS guess, frequency check, solvent equilibration (writes `scan.json`, `ts_freq.txt`).
2. `python shoot.py` : trajectories shot forward and backward in time from the TS (`shots/`).
3. `python make_traj.py shots/shot_5_0.npz` : converts the chosen reactive shot to `md/traj.npz` and `md/events.json`.

`events.json` holds the events detected in code (times in fs relative to the TS crossing).
