"""Closed heightfield water bounded by the actual irregular spring contour.

The former rectangular enclosing surface could emerge beyond the raised bank
of an elevated pool. This cap terminates inside an opaque, verified bank collar.
The bottom closure is an optical enclosure, not an estimate of water storage.
"""
from __future__ import annotations
import numpy as np


def closed_contour_water(pool, index, poolq, height, modes, scale):
    cx,cy,rx,ry,level,depth=pool
    nt,nr=(1024,360) if index==0 else (512,180)
    theta=np.arange(nt,dtype=np.float64)*(2*np.pi/nt)
    co,si=np.cos(theta),np.sin(theta)
    lo=np.full(nt,.35);hi=np.full(nt,2.)
    for _ in range(30):
        rr=(lo+hi)*.5
        q=poolq(cx+rx*rr*co,cy+ry*rr*si,index)
        lo=np.where(q<1.13,rr,lo);hi=np.where(q>=1.13,rr,hi)
    outer=(lo+hi)*.5
    radial=np.arange(1,nr+1,dtype=np.float64)[:,None]/nr*outer[None,:]
    x=cx+rx*radial*co;y=cy+ry*radial*si
    x=np.r_[cx,x.ravel()];y=np.r_[cy,y.ravel()]
    z=np.full_like(x,level);gx=np.zeros_like(x);gy=np.zeros_like(x)
    for kx,ky,amp,phase in modes:
        arg=kx*x+ky*y+phase+.37*index;a=amp*scale
        z+=a*np.sin(arg);c=a*np.cos(arg);gx+=kx*c;gy+=ky*c
    vertices=np.c_[x,y,z]
    normals=np.c_[-gx,-gy,np.ones_like(x)]
    normals/=np.linalg.norm(normals,axis=1)[:,None]
    j=np.arange(nt,dtype=np.int64);jp=(j+1)%nt
    center_faces=np.c_[np.zeros(nt,dtype=np.int64),1+j,1+jp]
    start=1+np.arange(nr-1,dtype=np.int64)[:,None]*nt
    aa=(start+j).ravel();bb=(start+jp).ravel();dd=aa+nt;cc=bb+nt
    faces=np.vstack((center_faces,np.c_[aa,dd,cc],np.c_[aa,cc,bb]))
    ring=1+(nr-1)*nt+j;ring_next=1+(nr-1)*nt+jp
    bottom_start=len(vertices);bottom_ids=bottom_start+j;bottom_next=bottom_start+jp
    bottom=vertices[ring].copy();bottom[:,2]=-3.
    bottom_center=bottom_start+nt
    faces=np.vstack((faces,np.c_[ring,bottom_ids,bottom_next],np.c_[ring,bottom_next,ring_next],
                     np.c_[np.full(nt,bottom_center,dtype=np.int64),bottom_next,bottom_ids]))
    vertices=np.vstack((vertices,bottom,[cx,cy,-3.]))
    normals=np.vstack((normals,np.tile([0.,0.,-1.],(nt+1,1))))
    margin=height(vertices[ring,0],vertices[ring,1])-vertices[ring,2]
    error=np.abs(poolq(vertices[ring,0],vertices[ring,1],index)-1.13)
    if float(margin.min())<.012:raise RuntimeError('Water enclosure is exposed outside its bank collar')
    if float(error.max())>1e-6:raise RuntimeError('Water contour solve did not converge')
    report={'optical_enclosure_not_storage_volume':True,'boundary_q':1.13,
            'boundary_samples':nt,'minimum_bank_cover_m':float(margin.min()),
            'maximum_boundary_q_error':float(error.max()),'boundary_contained':True}
    return vertices,faces,normals,report
