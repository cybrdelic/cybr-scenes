"""Exact piecewise-linear bank/road overlap audit in a bounded full-strength ROI.
Checks every XY intersection-polygon vertex, where linear clearance extrema lie.
This proves only the provided mesh pair and region, not arbitrary particles.
"""
import numpy as np

def _clip(poly,a,b):
    out=[]
    for p,q in zip(poly,np.roll(poly,-1,axis=0)):
        fp=(b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]);fq=(b[0]-a[0])*(q[1]-a[1])-(b[1]-a[1])*(q[0]-a[0]);ip=fp>=-1e-12;iq=fq>=-1e-12
        if ip:out.append(p)
        if ip!=iq:out.append(p+(q-p)*(fp/(fp-fq)))
    return np.asarray(out).reshape(-1,3)

def _area(p):
    if len(p)<3:return 0.
    p=p[:,:2]-p[0,:2];return .5*abs(float(np.sum(p[:,0]*np.roll(p[:,1],-1)-p[:,1]*np.roll(p[:,0],-1))))

def exact_clearance(co,triangles,road_sampler,bounds):
    xmin,xmax,ymin,ymax=bounds;minimum=np.inf;polygons=vertices=0;area=0.;bad=0
    box=np.array([[xmin,ymin],[xmax,ymin],[xmax,ymax],[xmin,ymax]])
    for ids in triangles:
        p=np.asarray(co[ids],float);lo=p[:,:2].min(0);hi=p[:,:2].max(0)
        if hi[0]<xmin or lo[0]>xmax or hi[1]<ymin or lo[1]>ymax or _area(p)<1e-14:continue
        for a,b in zip(box,np.roll(box,-1,axis=0)):
            p=_clip(p,a,b)
            if len(p)<3:break
        if len(p)<3:continue
        lo=np.floor((p[:,:2].min(0)-1e-10)/road_sampler.cell).astype(int);hi=np.floor((p[:,:2].max(0)+1e-10)/road_sampler.cell).astype(int)
        candidates=set()
        for x in range(lo[0],hi[0]+1):
            for y in range(lo[1],hi[1]+1):candidates.update(road_sampler.bins.get((x,y),()))
        for k in candidates:
            r=road_sampler.tri[k];signed=np.cross(r[1,:2]-r[0,:2],r[2,:2]-r[0,:2]);r=r if signed>0 else r[::-1];poly=p
            for a,b in zip(r,np.roll(r,-1,axis=0)):
                poly=_clip(poly,a,b)
                if len(poly)<3:break
            overlap=_area(poly)
            if overlap<1e-14:continue
            d=poly[:,:2]-r[0,:2];u=r[1,:2]-r[0,:2];v=r[2,:2]-r[0,:2];det=u[0]*v[1]-u[1]*v[0];uu=(d[:,0]*v[1]-d[:,1]*v[0])/det;vv=(u[0]*d[:,1]-u[1]*d[:,0])/det
            height=r[0,2]+uu*(r[1,2]-r[0,2])+vv*(r[2,2]-r[0,2]);gap=height-poly[:,2]
            minimum=min(minimum,float(gap.min()));polygons+=1;vertices+=len(poly);area+=overlap;bad+=int(np.any(gap < -1e-7))
    return dict(roi_xy_m=list(bounds),overlap_polygons=polygons,overlap_vertices=vertices,overlap_area_m2=area,minimum_linear_mesh_clearance_m=minimum if polygons else None,penetrating_overlap_polygons=bad,method='Exact XY polygon intersections, extrema of linear road-minus-bank planes at every polygon vertex; tolerance1e-7m',scope='Full-strength mesh region only; excludes onset/fade, particles and subpixel shader normals')
