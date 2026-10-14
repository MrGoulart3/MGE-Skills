"""Post-process the raw MD (traj_raw.npz) into the scene contract (traj.npz):
time-unwrap per atom, whole molecules, ONE constant periodic image per water chosen so that it sits next
to the ions when it is close to them (mode of the min-image shift over frames with d < 6 Å), centre on the
smoothed centroid of the 30 least-mobile ions, and keep waters that come within 13 Å of any ion."""
import numpy as np
d=np.load('traj_raw.npz'); P=d['positions'].astype(np.float64); L=d['box'].astype(np.float64); el=d['element']; mol=d['molecule']
F,N,_=P.shape
for f in range(1,F): P[f]-=np.round((P[f]-P[f-1])/L)*L
first={}
for i,m in enumerate(mol): first.setdefault(m,i)
anc=np.array([first[m] for m in mol]); P-=np.round((P-P[:,anc])/L)*L
ions=np.flatnonzero(np.isin(el,['Na','Cl'])); O=np.flatnonzero(el=='O')
for o in O:
    v=P[:,o,None,:]-P[:,ions,:]; s=np.round(v/L); dmin=np.linalg.norm(v-s*L,axis=2)
    j=dmin.argmin(axis=1); dd=dmin[np.arange(F),j]; sf=s[np.arange(F),j]; close=dd<6
    if close.any():
        vals,cnt=np.unique(sf[close],axis=0,return_counts=True); sh=vals[cnt.argmax()]
    else: sh=sf[dd.argmin()]
    P[:,mol==mol[o]]-=sh*L
core=ions[np.argsort(np.linalg.norm(P[-1,ions]-P[0,ions],axis=1))[:30]]
c=P[:,core].mean(axis=1); k=np.ones(21)/21
cs=np.vstack([np.convolve(np.pad(c[:,j],10,mode='edge'),k,'valid') for j in range(3)]).T
P-=cs[:,None,:]
W=np.flatnonzero(~np.isin(el,['Na','Cl'])); near=np.zeros(N,bool)
for f in range(F):
    dd=np.sqrt(((P[f,W][:,None,:]-P[f,ions][None,:,:])**2).sum(-1)).min(1); near[W[dd<13]]=True
keep=np.isin(np.arange(N),ions)|np.isin(mol,np.unique(mol[near]))
st=np.linalg.norm(np.diff(P[:,keep],axis=0),axis=2)
print('kept',int(keep.sum()),'waters',int((keep&(el=='O')).sum()),'max step Å/ps',st.max().round(2),'p99',np.percentile(st,99).round(2))
np.savez_compressed('traj.npz',positions=P[:,keep].astype(np.float32),time_ps=d['time_ps'],element=el[keep],molecule=mol[keep],box=d['box'],orig_index=np.flatnonzero(keep))
