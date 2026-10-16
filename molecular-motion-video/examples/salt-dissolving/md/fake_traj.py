"""Trajetória SINTÉTICA para QA visual; não representa uma simulação de MD.

Uso: python3 md/fake_traj.py [--out md] (na pasta do exemplo).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

SEED = 104524


def rotation(axis: np.ndarray, angle: float) -> np.ndarray:
    axis = axis / np.linalg.norm(axis)
    x, y, z = axis
    cross = np.array([[0, -z, y], [z, 0, -x], [-y, x, 0]])
    return np.eye(3) + np.sin(angle) * cross + (1 - np.cos(angle)) * cross @ cross


def generate(out: Path) -> None:
    """Gera 64 íons, 600 águas rígidas e dois eventos com seis águas cada."""
    rng = np.random.default_rng(SEED)
    lattice = np.indices((4, 4, 4)).reshape(3, -1).T
    ions = (lattice - 1.5) * 2.82
    elements = ['Na' if row.sum() % 2 == 0 else 'Cl' for row in lattice]
    ion_indices = [0, 63]
    shell_directions = np.concatenate((np.eye(3), -np.eye(3)))
    angle = np.deg2rad(104.52 / 2)
    water = np.array([[0, 0, 0],
                      [0.9572 * np.cos(angle), 0.9572 * np.sin(angle), 0],
                      [0.9572 * np.cos(angle), -0.9572 * np.sin(angle), 0]])
    waters = []
    for number in range(600):
        if number < 12:
            ion = ion_indices[number // 6]
            outward = shell_directions[number % 6]
            # Na: bissetriz H aponta para fora; Cl: um H aponta para dentro.
            center = ions[ion] + outward * (2.65 if ion == 0 else 3.15)
            local = water.copy()
            local_axis = np.array([1., 0, 0]) if ion == 0 else -water[1] / 0.9572
            cross = np.cross(local_axis, outward)
            if np.linalg.norm(cross) < 1e-8:
                orient = np.eye(3) if np.dot(local_axis, outward) > 0 else rotation(np.array([0., 0, 1]), np.pi)
            else:
                orient = rotation(cross, np.arccos(np.clip(np.dot(local_axis, outward), -1, 1)))
            waters.append(local @ orient.T + center)
        else:
            for _ in range(10000):
                center = rng.uniform(-18, 18, 3)
                if np.linalg.norm(center) < 18 and np.min(np.linalg.norm(ions - center, axis=1)) > 4.0:
                    if np.min(np.linalg.norm(ions[ion_indices] - center, axis=1)) > 6:
                        break
            else:
                raise RuntimeError('Não foi possível distribuir águas sintéticas.')
            orient = rotation(rng.normal(size=3), rng.uniform(0, 2 * np.pi))
            waters.append(water @ orient.T + center)
    waters = np.array(waters)
    positions = np.empty((300, 1864, 3), dtype=np.float32)
    phase = rng.uniform(0, 2 * np.pi, (600, 3))
    axes = rng.normal(size=(600, 3))
    centers = waters[:, 0].copy()
    local = waters - centers[:, None]
    for frame in range(300):
        current_ions = ions.copy()
        shift = np.zeros((600, 3))
        for slot, (start, stop) in enumerate(((100, 220), (165, 285))):
            ratio = np.clip((frame - start) / (stop - start), 0, 1)
            displacement = (ratio * ratio * (3 - 2 * ratio)) * 11
            direction = np.array([-1., -1., -1.]) if slot == 0 else np.array([1., 1., 1.])
            delta = direction / np.sqrt(3) * displacement
            current_ions[ion_indices[slot]] += delta
            shift[slot * 6:slot * 6 + 6] = delta
        current_waters = np.empty_like(waters)
        for index in range(600):
            orient = rotation(axes[index], 0.035 * np.sin(frame * 0.18 + phase[index, 0]))
            jitter = 0.035 * np.sin(frame * 0.23 + phase[index])
            current_waters[index] = local[index] @ orient.T + centers[index] + jitter + shift[index]
        positions[frame] = np.concatenate((current_ions, current_waters.reshape(-1, 3)))
    element = np.array(elements + ['O', 'H', 'H'] * 600)
    molecule = np.concatenate((np.arange(64), np.repeat(np.arange(64, 664), 3)))
    events = []
    for ion in ion_indices:
        others = [index for index in range(64) if index != ion]
        distance = np.linalg.norm(positions[:, others] - positions[:, ion, None], axis=-1).min(axis=1)
        detached = np.flatnonzero(distance > 5)
        frame = int(detached[0])
        hydration = []
        for p in positions:
            w = p[64:].reshape(600, 3, 3)
            if element[ion] == 'Na':
                inside = np.linalg.norm(w[:, 0] - p[ion], axis=-1) < 3.2
            else:
                inside = (np.linalg.norm(w[:, 1:] - p[ion], axis=-1) < 2.9).any(axis=1)
            hydration.append(int(inside.sum()))
        events.append({'kind': 'detach', 'ion': str(element[ion]), 'index': ion,
                       'frame': frame, 'time_ps': float(frame), 'hydration': hydration})
    out.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out / 'traj_fake.npz', positions=positions,
                        time_ps=np.arange(300, dtype=float), element=element,
                        molecule=molecule, box=np.full(3, 48.), synthetic=True)
    (out / 'events_fake.json').write_text(json.dumps(events, indent=2) + '\n')
    print(f'SINTÉTICA: {positions.shape}, eventos: {[(e["ion"], e["frame"], e["hydration"][e["frame"]]) for e in events]}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=Path(__file__).resolve().parents[1] / 'md')
    generate(parser.parse_args().out)


if __name__ == '__main__':
    main()
