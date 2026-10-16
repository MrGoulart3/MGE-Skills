"""Etapa 1 (SN2 Cl⁻ + CH3Br): varredura relaxada de ξ = d(C–Br) − d(C–Cl) com GFN2-xTB/ALPB(água) via tblite,
máximo da curva = estimativa do TS; Hessiana numérica no máximo (deve ter 1 frequência imaginária).
Saída: scan.json (ξ, E, geometrias), ts_xtb.xyz, ts_freq.txt."""
import json, numpy as np
from ase import Atoms
from ase.optimize import BFGS
from ase.constraints import FixInternals
from ase.vibrations import Vibrations
from ase.io import write
from tblite.ase import TBLite

HARTREE_KCAL = 627.509
def calc():
    return TBLite(method="GFN2-xTB", charge=-1, multiplicity=1, solvation=("alpb", "water"), verbosity=0)

# Cl ... C(H3) ... Br ao longo de z; C na origem.
def guess(dcl, dbr, umbrella):
    hz = umbrella  # componente z dos H (positivo = H apontando para o Cl, como no reagente)
    r = 1.09
    hxy = np.sqrt(r**2 - hz**2)
    H = [(hxy*np.cos(a), hxy*np.sin(a), hz) for a in np.radians([0, 120, 240])]
    return Atoms("CBrClH3", positions=[(0, 0, 0), (0, 0, -dbr), (0, 0, dcl), *H])

atoms = guess(3.2, 1.97, 0.36)
atoms.calc = calc()
results = []
for xi in np.round(np.arange(-1.40, 1.41, 0.05), 3):  # ξ<0: reagente; ξ>0: produto
    # restrição combinada: d(C–Br) − d(C–Cl) = ξ (FixInternals bondcombo)
    atoms.set_constraint(FixInternals(bondcombos=[(xi, [[0, 1, 1.0], [0, 2, -1.0]])]))
    # empurra a geometria para o ξ alvo antes de otimizar
    p = atoms.get_positions(); dbr = np.linalg.norm(p[1]-p[0]); dcl = np.linalg.norm(p[2]-p[0])
    s = 0.5*((xi) - (dbr-dcl)); p[1] = p[0] + (p[1]-p[0])/dbr*(dbr+s); p[2] = p[0] + (p[2]-p[0])/dcl*(dcl-s)
    atoms.set_constraint(); atoms.set_positions(p)
    atoms.set_constraint(FixInternals(bondcombos=[(xi, [[0, 1, 1.0], [0, 2, -1.0]])]))
    BFGS(atoms, logfile=None).run(fmax=0.01, steps=400)
    p = atoms.get_positions()
    e = atoms.get_potential_energy()/27.211386*HARTREE_KCAL  # eV → kcal/mol
    results.append({"xi": float(xi), "E_kcal": e, "d_CBr": float(np.linalg.norm(p[1]-p[0])),
                    "d_CCl": float(np.linalg.norm(p[2]-p[0])), "pos": p.tolist()})
    print(f"xi={xi:+.2f}  E={e:.2f}  C–Br={results[-1]['d_CBr']:.3f}  C–Cl={results[-1]['d_CCl']:.3f}", flush=True)
E0 = min(r["E_kcal"] for r in results[:10])
for r in results: r["E_rel"] = r["E_kcal"] - E0
k = int(np.argmax([r["E_rel"] for r in results]))
json.dump({"method": "GFN2-xTB/ALPB(water), tblite 0.7.0", "symbols": list(atoms.get_chemical_symbols()), "scan": results}, open("scan.json", "w"))
ts = atoms.copy(); ts.set_constraint(); ts.set_positions(results[k]["pos"]); ts.calc = calc()
write("ts_xtb.xyz", ts)
print(f"MAX: xi={results[k]['xi']:+.2f} (scan maximum)", flush=True)
vib = Vibrations(ts, name="vib_ts", delta=0.005); vib.run()
f = vib.get_frequencies()
open("ts_freq.txt", "w").write("\n".join(f"{x:.1f}" for x in f))
print("FREQ (cm-1):", [f"{x:.1f}" for x in f[:8]])
vib.clean()
