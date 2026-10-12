"""Angular compacted interstitial sand relief, not a replacement for loose grains.
The visible granules are bounded by an irregular Voronoi fracture/contact field.
This sub-millimetre bed is resolved as actual fine substrate geometry.
"""
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
R=Path(__file__).resolve().parents[1];rng=np.random.default_rng(51856);N=1101;side=.18;axis=np.linspace(-side/2,side/2,N);x,y=np.meshgrid(axis,axis);xy=np.c_[x.ravel(),y.ravel()];p=rng.uniform(-.092,.092,(112000,2));d,idx=cKDTree(p).query(xy,k=2,workers=2)
gap=np.maximum(0,d[:,1]-d[:,0]);heights=np.minimum(gap,.000045)*rng.uniform(1.3,2.2,len(p))[idx[:,0]]
# Different exposed phases of very compacted granitic grit, subdued by fines.
base=np.array([.282,.224,.151]);pal=np.array([[.35,.30,.225],[.26,.225,.17],[.22,.20,.17],[.33,.265,.18],[.42,.385,.31]])
phase=rng.integers(0,len(pal),len(p));rgb=base*.60+pal[phase[idx[:,0]]]*.40;rgb*=rng.uniform(.92,1.08,len(p))[idx[:,0],None]
np.savez_compressed(R/'prototypes/microbed.npz',height=heights.reshape(N,N).astype('f4'),color=rgb.reshape(N,N,3).astype('f4'),side_m=side)
print('MICROBED',N,'height_m',float(heights.max()),'nominal_cell_pitch_m',float(np.sqrt(side*side/len(p))))
