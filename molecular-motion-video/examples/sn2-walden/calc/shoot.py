"""Etapa 2 (SN2): TS em aglomerado de águas explícitas (GFN2-xTB + ALPB fora) e disparos do TS.
1) monta N águas aleatórias numa esfera em volta do TS; parede harmônica nos O além de R_WALL;
2) equilibra 1 ps a 300 K (Langevin) com d(C–Br) e d(C–Cl) FIXOS no valor do TS;
3) de cada instantâneo: velocidades de Maxwell–Boltzmann a 300 K, integra +500 fs e, com −v, −500 fs (NVE);
   classifica cada ponta (reagente/produto) e salva a trajetória completa (−500…+500 fs, 1 fs).
Uso: python shoot.py [n_snap] [n_vel]   → shots/shot_<s>_<v>.npz, shots/resumo.json"""
import json, sys, time
from pathlib import Path
import numpy as np
from ase import Atoms, units
from ase.io import read, write
from ase.calculators.calculator import Calculator, all_changes
from ase.calculators.mixing import SumCalculator
from ase.constraints import FixInternals
from ase.md.langevin import Langevin
from ase.md.verlet import VelocityVerlet
from ase.md.velocitydistribution import MaxwellBoltzmannDistribution, Stationary, ZeroRotation
from ase.optimize import BFGS
from tblite.ase import TBLite

N_WAT, R_SPHERE, R_WALL, K_WALL = 40, 8.5, 9.5, 1.0
SEED = 2026_10_15
rng = np.random.default_rng(SEED)
OUT = Path("shots"); OUT.mkdir(exist_ok=True)

class Wall(Calculator):
    implemented_properties = ["energy", "forces"]
    def __init__(self, idx, center, r, k):
        super().__init__(); self.idx, self.center, self.r, self.k = idx, center, r, k
    def calculate(self, atoms=None, properties=("energy",), system_changes=all_changes):
        super().calculate(atoms, properties, system_changes)
        p = self.atoms.get_positions(); f = np.zeros_like(p); e = 0.0
        com = p[:6].mean(axis=0) if self.center is None else self.center
        for i in self.idx:
            d = p[i] - com; r = np.linalg.norm(d)
            if r > self.r:
                e += 0.5*self.k*(r-self.r)**2; f[i] -= self.k*(r-self.r)*d/r
        self.results = {"energy": e, "forces": f}

def calc(atoms):
    o_idx = [i for i, s in enumerate(atoms.get_chemical_symbols()) if s == "O"]
    xtb = TBLite(method="GFN2-xTB", charge=-1, multiplicity=1, solvation=("alpb", "water"), verbosity=0)
    return SumCalculator([xtb, Wall(o_idx, None, R_WALL, K_WALL)])

def random_rotation():
    q = rng.normal(size=4); q /= np.linalg.norm(q); a, b, c, d = q
    return np.array([[a*a+b*b-c*c-d*d, 2*(b*c-a*d), 2*(b*d+a*c)], [2*(b*c+a*d), a*a-b*b+c*c-d*d, 2*(c*d-a*b)],
                     [2*(b*d-a*c), 2*(c*d+a*b), a*a-b*b-c*c+d*d]])

def solvate(ts):
    w = np.array([[0, 0, 0], [0.7570, 0.5859, 0], [-0.7570, 0.5859, 0]])
    pos, sym = list(ts.get_positions()), list(ts.get_chemical_symbols())
    heavy = [p for p, s in zip(pos, sym) if s != "H"]
    oxygens = []
    while len(oxygens) < N_WAT:
        c = rng.uniform(-R_SPHERE, R_SPHERE, 3)
        if np.linalg.norm(c) > R_SPHERE: continue
        if min(np.linalg.norm(c - h) for h in heavy) < 3.0: continue
        if min(np.linalg.norm(c - h) for h in pos) < 2.2: continue
        if oxygens and min(np.linalg.norm(c - o) for o in oxygens) < 2.75: continue
        oxygens.append(c); pos += list(c + w @ random_rotation().T); sym += ["O", "H", "H"]
    return Atoms(sym, positions=pos)

def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)

def side(p):
    dbr, dcl = np.linalg.norm(p[1]-p[0]), np.linalg.norm(p[2]-p[0])
    if dbr < 2.15 and dcl > 2.9: return "R"
    if dcl < 2.05 and dbr > 3.0: return "P"
    return "?"

def run(atoms, steps, every):
    frames = [atoms.get_positions().copy()]
    dyn = VelocityVerlet(atoms, timestep=0.5*units.fs)
    for k in range(steps // every):
        dyn.run(every); frames.append(atoms.get_positions().copy())
    return np.array(frames)

def main():
    n_snap = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    n_vel = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    ts = read("ts_xtb.xyz")
    p = ts.get_positions(); d_br, d_cl = np.linalg.norm(p[1]-p[0]), np.linalg.norm(p[2]-p[0])
    if Path("ts_solv_eq.traj").exists():
        snaps = read("ts_solv_eq.traj", index=":")
        log(f"reaproveitando {len(snaps)} instantâneos")
    else:
        atoms = solvate(ts); atoms.calc = calc(atoms)
        atoms.set_constraint(FixInternals(bonds=[(d_br, [0, 1]), (d_cl, [0, 2])]))
        BFGS(atoms, logfile=None).run(fmax=0.15, steps=300); log("pré-otimização ok")
        MaxwellBoltzmannDistribution(atoms, temperature_K=300, rng=rng)
        dyn = Langevin(atoms, 0.5*units.fs, temperature_K=300, friction=0.02/units.fs, rng=rng)
        snaps = []
        for k in range(20):  # 20 × 50 fs = 1 ps
            dyn.run(100)
            log(f"equil {50*(k+1)} fs  T={atoms.get_temperature():.0f} K")
            if k >= 9 and (k - 9) % 2 == 0 and len(snaps) < n_snap:
                s = atoms.copy(); s.set_constraint(); s.set_velocities(np.zeros((len(s), 3))); snaps.append(s)
        write("ts_solv_eq.traj", snaps)
    summary = []
    for i, snap in enumerate(snaps[:n_snap]):
        for j in range(n_vel):
            name = OUT / f"shot_{i}_{j}.npz"
            if name.exists():
                continue
            a = snap.copy(); a.calc = calc(a)
            MaxwellBoltzmannDistribution(a, temperature_K=300, rng=rng); Stationary(a); ZeroRotation(a)
            v0 = a.get_velocities().copy()
            fwd = run(a, 1000, 2)               # +500 fs, quadro a cada 1 fs
            a.set_positions(snap.get_positions()); a.set_velocities(-v0)
            bwd = run(a, 1000, 2)               # −500 fs
            traj = np.concatenate([bwd[::-1], fwd[1:]])
            ends = (side(bwd[-1]), side(fwd[-1]))
            np.savez_compressed(name, positions=traj.astype(np.float32), symbols=np.array(a.get_chemical_symbols()),
                                time_fs=np.arange(-500, 501, 1.0), ends=np.array(ends))
            log(f"shot {i}.{j}: trás={ends[0]} frente={ends[1]} {'REATIVA' if set(ends) == {'R','P'} else ''}")
    for f in sorted(OUT.glob("shot_*.npz")):
        d = np.load(f); summary.append({"file": f.name, "ends": d["ends"].tolist(), "reactive": set(d["ends"].tolist()) == {"R", "P"}})
    json.dump(summary, open(OUT / "resumo.json", "w"), indent=1)
    log(f"reativas: {sum(s['reactive'] for s in summary)} de {len(summary)}")

if __name__ == "__main__":
    main()
