"""NaCl 4x4x4 nanocrystal in TIP3P water (OpenMM, amber14/tip3p.xml, Joung-Cheatham ions).
usage: md_sal.py <prod_T_K> <max_prod_ps> <equil_scale>   (equil_scale=1 full, 0.05 smoke test)"""
import sys, time, numpy as np
import openmm as mm, openmm.app as app
from openmm import unit as u

T = float(sys.argv[1]); MAXPS = float(sys.argv[2]); ES = float(sys.argv[3])
A = 5.64; BOX_NM = 4.1
log = lambda *a: print(time.strftime('%H:%M:%S'), *a, flush=True)

top = app.Topology(); pos = []
ch = top.addChain()
els = {'NA': app.Element.getBySymbol('Na'), 'CL': app.Element.getBySymbol('Cl')}
for i in range(4):
    for j in range(4):
        for k in range(4):
            nm = 'NA' if (i + j + k) % 2 == 0 else 'CL'
            r = top.addResidue(nm, ch); top.addAtom(nm, els[nm], r)
            pos.append([i * A / 2, j * A / 2, k * A / 2])
pos = np.array(pos) / 10.0  # nm
pos += 0.5 * BOX_NM - pos.mean(0)
mod = app.Modeller(top, pos * u.nanometer)
ff = app.ForceField('amber14/tip3p.xml')
mod.addSolvent(ff, model='tip3p', boxSize=mm.Vec3(BOX_NM, BOX_NM, BOX_NM) * u.nanometer, neutralize=False)
top = mod.topology
nions = 64
log('atoms', top.getNumAtoms(), 'waters', (top.getNumAtoms() - nions) // 3)
system = ff.createSystem(top, nonbondedMethod=app.PME, nonbondedCutoff=1.0 * u.nanometer,
                         constraints=app.HBonds, rigidWater=True)
import os; prop = {'Threads': os.environ.get('NT', '16')}
plat = mm.Platform.getPlatformByName('CPU')

def mk(temp, npt):
    s = system
    integ = mm.LangevinMiddleIntegrator(temp * u.kelvin, 1.0 / u.picosecond, 0.002 * u.picoseconds)
    return integ

integ = mk(300, False)
sim = app.Simulation(top, system, integ, plat, prop)
sim.context.setPositions(mod.positions)
sim.minimizeEnergy(maxIterations=2000)
sim.context.setVelocitiesToTemperature(300 * u.kelvin)
nvt = int(100 / 0.002 * ES); npt = int(150 / 0.002 * ES)
t0 = time.time(); sim.step(nvt); log('NVT300 done', nvt, 'steps', time.time() - t0, 's')
baro = mm.MonteCarloBarostat(1 * u.bar, 300 * u.kelvin, 25); system.addForce(baro)
sim.context.reinitialize(preserveState=True)
sim.step(npt)
st = sim.context.getState(getEnergy=False)
bv = st.getPeriodicBoxVectors(); L = bv[0][0].value_in_unit(u.nanometer)
nw = (top.getNumAtoms() - nions) // 3
mass = 18.0154 * nw / 6.02214e23 * 1e-3  # kg
dens = mass / ((L * 1e-9) ** 3) / 1000
log('NPT done, box nm', L, 'approx density g/cc (waters only, ions ignored)', dens)
# production NVT: freeze box
system.removeForce(system.getNumForces() - 1)
sim.integrator.setTemperature(T * u.kelvin)
sim.context.reinitialize(preserveState=True)
sim.context.setPeriodicBoxVectors(*bv)
box = np.array([L * 10] * 3)
frames = []; tps = []
isidx = np.arange(nions)
def isolated(p):
    ip = p[:nions]; d = ip[:, None] - ip[None]; d -= box * np.round(d / box)
    r = np.linalg.norm(d, axis=-1); np.fill_diagonal(r, 1e9)
    return int((r.min(1) > 5.0).sum())
nstep_ps = 500; done = 0; stop_at = None
while done < MAXPS:
    sim.step(nstep_ps); done += 1
    p = sim.context.getState(getPositions=True).getPositions(asNumpy=True).value_in_unit(u.angstrom)
    frames.append(p.astype(np.float32)); tps.append(done)
    if done % 50 == 0:
        ni = isolated(p); log('prod ps', done, 'isolated ions', ni)
        if ni >= 4 and stop_at is None: stop_at = done + 150
    if stop_at and done >= stop_at: break
np.savez('prod_raw.npz', positions=np.array(frames), time_ps=np.array(tps, float), box=box,
         resname=np.array([a.residue.name for a in top.atoms()]), element=np.array([a.element.symbol for a in top.atoms()]),
         resid=np.array([a.residue.index for a in top.atoms()]), T=T, nions=nions)
log('saved', len(frames))
