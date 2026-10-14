"""post.py raw.npz out_dir : unwrap, center, detect detach events, trim waters, write traj.npz/events.json"""
import sys, json, numpy as np
d = np.load(sys.argv[1]); out = sys.argv[2]
P = d['positions'].astype(np.float64); t = d['time_ps']; box = d['box']; el = d['element']; rid = d['resid']
NI = int(d['nions']); F, N, _ = P.shape
# unwrap: make every molecule whole (ref atom = first), then continuous in time
mols = {}
for i, r in enumerate(rid): mols.setdefault(r, []).append(i)
first = np.array([m[0] for m in mols.values()])
def mic(x): return x - box * np.round(x / box)
U = P.copy()
for m in mols.values():
    if len(m) > 1:
        U[:, m[1:]] = U[:, [m[0]]] + mic(P[:, m[1:]] - P[:, [m[0]]])
# ions: time-continuous (single atoms); waters are re-imaged per frame later (see below)
ref = U[:, :NI]; dif = ref[1:] - ref[:-1]; k = np.round(dif / box)
U[:, :NI] += np.concatenate([np.zeros((1, NI, 3)), -np.cumsum(k, 0) * box])
# cluster = ions near the crystal: nearest-ion distance
ion = U[:, :NI]
def nn_dist(f):
    x = ion[f]; r = np.linalg.norm(x[:, None] - x[None], axis=-1); np.fill_diagonal(r, 1e9); return r
# crystal membership at frame 0 = all; detached when min distance to any not-yet-detached ion > 5 A (crystal = largest cluster)
from collections import deque
def crystal(f, cut=4.0):
    r = nn_dist(f); adj = r < cut
    seen = np.zeros(NI, bool); best = []
    for s in range(NI):
        if seen[s]: continue
        comp = []; q = deque([s]); seen[s] = True
        while q:
            a = q.popleft(); comp.append(a)
            for b in np.where(adj[a] & ~seen)[0]: seen[b] = True; q.append(b)
        if len(comp) > len(best): best = comp
    return np.array(best)
cry = [crystal(f) for f in range(F)]
dmin = np.zeros((F, NI))
for f in range(F):
    c = cry[f]; x = ion[f]
    r = np.linalg.norm(x[:, None] - x[c][None], axis=-1); r[c, np.arange(len(c))] = 1e9
    dmin[f] = r.min(1)
events = []; det = {}
for i in range(NI):
    # first frame after which ion stays > 5 A from crystal for the rest of the window... use first frame > 5 A sustained >= 5 frames
    far = dmin[:, i] > 5.0
    for f in range(F - 4):
        if far[f:f + 5].all() and i not in cry[f]:
            det[i] = f; break
ions_el = el[:NI]
# center: remaining crystal COM at origin per frame
cen = np.array([ion[f][cry[f]].mean(0) for f in range(F)])
U -= cen[:, None, :]
# waters: per frame, image of each molecule nearest to its closest ion (O atom reference)
W = np.array([m[0] for r_, m in mols.items() if len(m) > 1])
for f in range(F):
    dlt = U[f, W][:, None] - U[f, :NI][None]; dlt -= box * np.round(dlt / box)
    j = np.linalg.norm(dlt, axis=-1).argmin(1)
    tgt = U[f, :NI][j] + dlt[np.arange(len(W)), j]
    sh = tgt - U[f, W]
    for n, r_ in enumerate([r_ for r_, m in mols.items() if len(m) > 1]):
        U[f, mols[r_]] += sh[n]
# window selection
dets = sorted(det.items(), key=lambda kv: kv[1])
print('detached', [(i, ions_el[i], f, t[f]) for i, f in dets])
f0 = 0; f1 = F
if len(dets) >= 2:
    f0 = 0; f1 = min(F, dets[min(len(dets), 3) - 1][1] + 100)
sel = slice(f0, f1)
U = U[sel]; tt = t[sel] - t[sel][0]; Fn = len(U)
# hydration + trimming waters
O = np.where(el == 'O')[0]; H = np.where(el == 'H')[0]
wm = np.array([rid[o] for o in O])
need = [i for i, _ in dets] if dets else []
keepw = np.zeros(len(O), bool)
ionpos = U[:, :NI]
for n, o in enumerate(O):
    dd = np.linalg.norm(U[:, o][:, None] - ionpos, axis=-1)
    if (dd < 14).any(): keepw[n] = True
keep_atoms = list(range(NI))
for n, o in enumerate(O):
    if keepw[n]: keep_atoms += mols[rid[o]]
keep_atoms = np.array(keep_atoms)
hyd = {}
def hydr(i):
    h = []
    for f in range(Fn):
        if ions_el[i] == 'Na':
            dd = np.linalg.norm(U[f, O] - U[f, i], axis=-1); h.append(int((dd < 3.2).sum()))
        else:
            dd = np.linalg.norm(U[f, H] - U[f, i], axis=-1); h.append(int((dd < 2.9).sum()))
    return h
ev = []
for i, f in dets:
    if f0 <= f < f1:
        fr = f - f0
        ev.append({"kind": "detach", "ion": str(ions_el[i]), "index": int(i), "frame": int(fr), "time_ps": float(tt[fr]), "hydration": hydr(i)})
# molecule ids: ions own id, waters renumbered
molid = np.array([rid[a] for a in keep_atoms]); _, molid = np.unique(molid, return_inverse=True)
import os; os.makedirs(out, exist_ok=True)
np.savez_compressed(os.path.join(out, 'traj.npz'), positions=U[:, keep_atoms].astype(np.float32), time_ps=tt.astype(np.float32),
                    element=el[keep_atoms].astype(str), molecule=molid.astype(int), box=box.astype(np.float32))
json.dump(ev, open(os.path.join(out, 'events.json'), 'w'))
print('frames', Fn, 'atoms', len(keep_atoms), 'waters kept', int(keepw.sum()))
# validation
r0 = np.linalg.norm(U[0, :NI][:, None] - U[0, :NI][None], axis=-1); np.fill_diagonal(r0, 1e9)
nn = r0.min(1); print('frame0 nearest ion-ion mean (Na-Cl) A', nn.mean())
f = Fn - 1
fr_ions = [i for i, _ in dets if det[i] - f0 <= f]
for i in fr_ions:
    if ions_el[i] == 'Na': print('Na', i, 'CN(O<3.2)', hydr(i)[-1])
    else: print('Cl', i, 'CN(H<2.9)', hydr(i)[-1], 'CN(O<3.8)', int((np.linalg.norm(U[f, O] - U[f, i], axis=-1) < 3.8).sum()))
