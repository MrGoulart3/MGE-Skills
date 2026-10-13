#!/usr/bin/env python3
"""Convert a computed trajectory (MD, IRC, NEB, normal-mode scan...) into the neutral traj.npz
contract read by the Blender scene (see references/computed-motion.md).

Reads anything ASE can read (xyz/extxyz, ORCA .trj / IRC xyz, Gaussian IRC .log, CP2K, VASP
XDATCAR, LAMMPS dumps, ASE .traj). Molecules are rebuilt from covalent bonds and unwrapped across
periodic boundaries (whole molecules, no jumps), then centred on a chosen subject.

Example:
  python3 traj_to_npz.py md.extxyz --out traj.npz --dt-ps 1.0 \
      --subject "Na,Cl" --keep-within 14
  python3 traj_to_npz.py irc.xyz --out traj.npz --path          # reaction path (index axis)
Requires: numpy, ase (pip install ase).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def molecules(symbols: list[str], positions: np.ndarray, cell, pbc) -> np.ndarray:
    """Molecule id per atom from covalent radii (ASE neighbour list, first frame)."""
    from ase import Atoms
    from ase.neighborlist import natural_cutoffs, NeighborList
    atoms = Atoms(symbols, positions=positions, cell=cell, pbc=pbc)
    nl = NeighborList(natural_cutoffs(atoms, mult=1.1), self_interaction=False, bothways=True)
    nl.update(atoms)
    ids = -np.ones(len(atoms), int)
    current = 0
    for start in range(len(atoms)):
        if ids[start] >= 0:
            continue
        stack, ids[start] = [start], current
        while stack:
            i = stack.pop()
            for j in nl.get_neighbors(i)[0]:
                if ids[j] < 0:
                    ids[j] = current
                    stack.append(j)
        current += 1
    return ids


def unwrap(frames: np.ndarray, cell: np.ndarray | None, mol: np.ndarray) -> np.ndarray:
    """Remove periodic jumps over time and keep each molecule whole (orthorhombic/triclinic)."""
    if cell is None or not np.any(cell):
        return frames
    inv = np.linalg.inv(cell)
    out = frames.copy()
    # 1) time continuity, atom by atom
    for f in range(1, len(out)):
        d = (out[f] - out[f - 1]) @ inv
        out[f] -= np.round(d) @ cell
    # 2) whole molecules: each atom nearest-image to the first atom of its molecule
    first = {m: np.flatnonzero(mol == m)[0] for m in np.unique(mol)}
    anchor = np.array([first[m] for m in mol])
    d = (out - out[:, anchor]) @ inv
    out -= np.round(d) @ cell
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input")
    ap.add_argument("--out", required=True)
    ap.add_argument("--format", help="ASE format name if it cannot be guessed")
    ap.add_argument("--stride", type=int, default=1)
    ap.add_argument("--dt-ps", type=float, help="time between saved frames (MD)")
    ap.add_argument("--path", action="store_true", help="reaction path: store an image index axis")
    ap.add_argument("--subject", help="comma-separated elements or atom indices to centre on (default: all)")
    ap.add_argument("--keep-within", type=float, help="drop solvent molecules never closer than this (Å) to the subject")
    args = ap.parse_args()

    from ase.io import read
    images = read(args.input, index=f"::{args.stride}", format=args.format)
    symbols = images[0].get_chemical_symbols()
    pos = np.array([a.get_positions() for a in images], dtype=np.float64)
    cell = np.array(images[0].get_cell()) if any(images[0].pbc) else None
    mol = molecules(symbols, pos[0], images[0].get_cell(), images[0].pbc)
    pos = unwrap(pos, cell, mol)

    if args.subject:
        tokens = [t.strip() for t in args.subject.split(",") if t.strip()]
        subject = np.array([i for i, s in enumerate(symbols)
                            if s in tokens or str(i) in tokens])
    else:
        subject = np.arange(len(symbols))
    pos -= pos[:, subject].mean(axis=1, keepdims=True)

    keep = np.ones(len(symbols), bool)
    if args.keep_within:
        near = np.zeros(len(symbols), bool)
        for f in range(len(pos)):
            d = np.linalg.norm(pos[f][:, None, :] - pos[f][None, subject, :], axis=2).min(axis=1)
            near |= d < args.keep_within
        keep = np.isin(mol, np.unique(mol[near])) | np.isin(np.arange(len(symbols)), subject)

    data = {
        "positions": pos[:, keep].astype(np.float32),
        "element": np.array(symbols)[keep],
        "molecule": mol[keep],
    }
    if args.path:
        data["reaction_coordinate"] = np.arange(len(pos), dtype=np.float32)
    else:
        dt = args.dt_ps if args.dt_ps else 1.0
        data["time_ps"] = (np.arange(len(pos)) * dt * args.stride).astype(np.float32)
    energies = [a.calc.get_potential_energy() if a.calc else np.nan for a in images]
    if np.isfinite(energies).any():
        data["energy"] = np.array(energies, dtype=np.float64)
    if cell is not None:
        data["box"] = np.diag(cell).astype(np.float32)
    np.savez_compressed(args.out, **data)
    info = {k: list(v.shape) for k, v in data.items()}
    print(json.dumps({"out": str(Path(args.out)), "frames": len(pos), "atoms_kept": int(keep.sum()),
                      "atoms_total": len(symbols), "arrays": info}, indent=1))


if __name__ == "__main__":
    main()
