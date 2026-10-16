"""Converte o disparo reativo escolhido em md/traj.npz + md/events.json (contrato da skill). Eventos detectados por código."""
import json, sys
import numpy as np
SHOT = sys.argv[1] if len(sys.argv) > 1 else "shots/shot_5_0.npz"
d = np.load(SHOT); p = d["positions"].astype(np.float32); t = d["time_fs"]; el = d["symbols"]
mol = np.zeros(len(el), dtype=np.int32); mol[6:] = 1 + (np.arange(len(el) - 6) // 3)
dbr = np.linalg.norm(p[:, 1] - p[:, 0], axis=1); dcl = np.linalg.norm(p[:, 2] - p[:, 0], axis=1); xi = dbr - dcl
ax = p[:, 1] - p[:, 2]; ax /= np.linalg.norm(ax, axis=1)[:, None]
umb = np.einsum("ij,ij->i", p[:, 0] - p[:, 3:6].mean(axis=1), ax)
ang = np.degrees(np.arccos(np.einsum("ij,ij->i", (p[:, 2] - p[:, 0]) / dcl[:, None], (p[:, 1] - p[:, 0]) / dbr[:, None])))
XI_TS = json.load(open("scan.json"))
k = max(XI_TS["scan"], key=lambda r: r["E_rel"]); xi_ts = k["xi"]
def first(cond, after=None):
    idx = np.flatnonzero(cond if after is None else cond & (t >= after)); return int(idx[0])
i_ts = first(np.r_[False, np.diff(np.sign(xi - xi_ts)) != 0])
neg = umb < 0
i_flip = next(i for i in range(i_ts - 50, len(t) - 50) if neg[i:i + 50].all())
events = {
    "approach": {"frame": first(dcl < 4.0), "desc": "d(C–Cl) < 4.0 Å"},
    "backside": {"frame": first(ang > 150), "desc": "Cl–C–Br angle > 150° (backside alignment)"},
    "ts": {"frame": i_ts, "desc": f"ξ = d(C–Br) − d(C–Cl) crosses ξ‡ = {xi_ts:+.2f} Å (scan maximum)"},
    "bond": {"frame": first(dcl < 2.0, t[i_ts]), "desc": "d(C–Cl) < 2.0 Å after the TS"},
    "flip": {"frame": i_flip, "desc": "umbrella inversion: C crosses the H3 plane and stays (50 fs)"},
    "leave": {"frame": first(dbr > 3.0, t[i_ts]), "desc": "d(C–Br) > 3.0 Å after the TS"},
}
for e in events.values(): e["time_fs"] = float(t[e["frame"]])
np.savez_compressed("../md/traj.npz", positions=p, time_fs=t.astype(np.float32), element=el, molecule=mol,
                    d_CCl=dcl.astype(np.float32), d_CBr=dbr.astype(np.float32), xi=xi.astype(np.float32),
                    umbrella=umb.astype(np.float32), angle=ang.astype(np.float32))
json.dump({"source": SHOT, "xi_ts": xi_ts, "events": events}, open("../md/events.json", "w"), indent=1, ensure_ascii=False)
for n, e in events.items(): print(f"{n:9s} {e['time_fs']:+6.0f} fs  {e['desc']}")
print(f"TS frame: CCl={dcl[i_ts]:.3f} CBr={dbr[i_ts]:.3f} ang={ang[i_ts]:.1f} umb={umb[i_ts]:+.3f}")
