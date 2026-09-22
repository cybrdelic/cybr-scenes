"""Deterministic planar rigid contact, SI units, convex polygons.

Independent numerical backend for CYBR GEO contact studies. A body has planar
translation and rotation; slider constraints remove inverse-mass components.
This is NOT a six-DOF, compliant-material or structural solver. Payloads are
never attached to grippers. Normal impulses are unilateral; Coulomb impulses
are bounded by the normal impulse. Static joint brakes have finite capacity.
"""
from __future__ import annotations
import numpy as np
from numba import njit

@njit(cache=True)
def cross2(a,b): return a[0]*b[1]-a[1]*b[0]

@njit(cache=True)
def world_vertices(local,nv,q):
    out=np.zeros_like(local)
    for i in range(len(q)):
        c=np.cos(q[i,2]);s=np.sin(q[i,2])
        for k in range(nv[i]):
            out[i,k,0]=q[i,0]+c*local[i,k,0]-s*local[i,k,1]
            out[i,k,1]=q[i,1]+s*local[i,k,0]+c*local[i,k,1]
    return out

@njit(cache=True)
def face_separation(a,na,b,nb):
    best=-1.e30;edge=0;normal=np.zeros(2)
    for i in range(na):
        j=(i+1)%na; dx=a[j,0]-a[i,0];dy=a[j,1]-a[i,1]
        l=np.sqrt(dx*dx+dy*dy);nx=dy/l;ny=-dx/l;sep=1.e30
        for k in range(nb):
            d=(b[k,0]-a[i,0])*nx+(b[k,1]-a[i,1])*ny
            sep=min(sep,d)
        if sep>best:best=sep;edge=i;normal[0]=nx;normal[1]=ny
    return best,edge,normal

@njit(cache=True)
def clip_segment(points,count,n,offset):
    out=np.zeros((2,2));num=0
    if count<2:return out,0
    d0=points[0,0]*n[0]+points[0,1]*n[1]-offset
    d1=points[1,0]*n[0]+points[1,1]*n[1]-offset
    if d0<=0:out[num]=points[0];num+=1
    if d1<=0:out[num]=points[1];num+=1
    if d0*d1<0:
        alpha=d0/(d0-d1)
        out[num]=points[0]+alpha*(points[1]-points[0]);num+=1
    return out,num

@njit(cache=True)
def manifold(a,na,b,nb,margin):
    pts=np.zeros((2,2));deps=np.zeros(2)
    sa,ea,an=face_separation(a,na,b,nb)
    if sa>margin:return pts,deps,an,0
    sb,eb,bn=face_separation(b,nb,a,na)
    if sb>margin:return pts,deps,an,0
    flip=sb>sa+1.e-7
    if flip:r=b;nr=nb;i=a;ni=na;e=eb;n=bn
    else:r=a;nr=na;i=b;ni=nb;e=ea;n=an
    min_dot=1.e30;incident=0
    for k in range(ni):
        edge=i[(k+1)%ni]-i[k];l=np.sqrt(np.dot(edge,edge))
        d=(edge[1]*n[0]-edge[0]*n[1])/l
        if d<min_dot:min_dot=d;incident=k
    seg=np.empty((2,2));seg[0]=i[incident];seg[1]=i[(incident+1)%ni]
    v1=r[e];v2=r[(e+1)%nr];t=v2-v1;t/=np.sqrt(np.dot(t,t))
    p,c=clip_segment(seg,2,-t,-np.dot(t,v1))
    if c<2:return pts,deps,n,0
    p,c=clip_segment(p,c,t,np.dot(t,v2))
    if c<2:return pts,deps,n,0
    count=0
    for k in range(c):
        separation=np.dot(n,p[k]-v1)
        if separation<=margin:
            pts[count]=p[k]-.5*separation*n;deps[count]=separation;count+=1
    if flip:n=-n
    return pts,deps,n,count

@njit(cache=True)
def impulse(v,inv,i,j,ra,rb,n,amount):
    px=n[0]*amount;py=n[1]*amount
    v[i,0]-=inv[i,0]*px;v[i,1]-=inv[i,1]*py
    v[i,2]-=inv[i,2]*(ra[0]*py-ra[1]*px)
    v[j,0]+=inv[j,0]*px;v[j,1]+=inv[j,1]*py
    v[j,2]+=inv[j,2]*(rb[0]*py-rb[1]*px)

@njit(cache=True)
def relative(v,i,j,ra,rb,n):
    dx=v[j,0]-v[j,2]*rb[1]-v[i,0]+v[i,2]*ra[1]
    dy=v[j,1]+v[j,2]*rb[0]-v[i,1]-v[i,2]*ra[0]
    return dx*n[0]+dy*n[1]

@njit(cache=True)
def effective(inv,i,j,ra,rb,n):
    ca=cross2(ra,n);cb=cross2(rb,n)
    return (inv[i,0]+inv[j,0])*n[0]*n[0]+(inv[i,1]+inv[j,1])*n[1]*n[1]+inv[i,2]*ca*ca+inv[j,2]*cb*cb

@njit(cache=True)
def step(q,v,inv,local,nv,pairs,friction,force,brakes,lower,upper,limit_velocity,dt,iterations=40,slop=2e-6,beta=.12):
    """One symplectic step. q and v mutate. Returns forces and penetration.

    No persistent contact cache is used. The small fixed timestep and converged
    velocity sweeps are preferred to potentially stale warm starts in this
    deliberately limited implementation. Friction is solved twice per contact.
    """
    n=len(q);world=world_vertices(local,nv,q)
    maxc=2*len(pairs);ids=np.zeros((maxc,2),np.int64)
    points=np.zeros((maxc,2));normal=np.zeros((maxc,2));gap=np.zeros(maxc)
    lamb=np.zeros((maxc,2));mu=np.zeros(maxc);nc=0
    for k in range(len(pairs)):
        a=pairs[k,0];b=pairs[k,1]
        # Cheap AABB broad phase, preserving near contacts.
        amin0=1.e9;amax0=-1.e9;amin1=1.e9;amax1=-1.e9
        bmin0=1.e9;bmax0=-1.e9;bmin1=1.e9;bmax1=-1.e9
        for j in range(nv[a]):
            amin0=min(amin0,world[a,j,0]);amax0=max(amax0,world[a,j,0]);amin1=min(amin1,world[a,j,1]);amax1=max(amax1,world[a,j,1])
        for j in range(nv[b]):
            bmin0=min(bmin0,world[b,j,0]);bmax0=max(bmax0,world[b,j,0]);bmin1=min(bmin1,world[b,j,1]);bmax1=max(bmax1,world[b,j,1])
        margin=3e-6
        if amin0>bmax0+margin or bmin0>amax0+margin or amin1>bmax1+margin or bmin1>amax1+margin:continue
        p,d,norm,c=manifold(world[a],nv[a],world[b],nv[b],margin)
        for j in range(c):
            ids[nc,0]=a;ids[nc,1]=b;points[nc]=p[j];gap[nc]=d[j];normal[nc]=norm
            mu[nc]=friction[k];nc+=1
    for i in range(n):v[i]+=dt*inv[i]*force[i]
    brake_imp=np.zeros((n,3))
    lower_imp=np.zeros((n,3));upper_imp=np.zeros((n,3))
    for it in range(iterations):
        for i in range(n):
            for d in range(3):
                # Unilateral generalized-coordinate end stops.  A prismatic
                # slider has the same response whether its stop face is at the
                # pad or at the guide carriage: its transverse DOFs are removed.
                if inv[i,d]>0:
                    if np.isfinite(lower[i,d]):
                        gaplo=q[i,d]-lower[i,d]
                        target=-max(gaplo,0.)/dt-beta*min(gaplo+slop,0.)/dt
                        new=max(0.,lower_imp[i,d]+(target-v[i,d]+limit_velocity[i,d])/inv[i,d])
                        v[i,d]+=inv[i,d]*(new-lower_imp[i,d]);lower_imp[i,d]=new
                    if np.isfinite(upper[i,d]):
                        gaphi=upper[i,d]-q[i,d]
                        target=-max(gaphi,0.)/dt-beta*min(gaphi+slop,0.)/dt
                        new=max(0.,upper_imp[i,d]+(target+v[i,d]-limit_velocity[i,d])/inv[i,d])
                        v[i,d]-=inv[i,d]*(new-upper_imp[i,d]);upper_imp[i,d]=new
                if brakes[i,d]>0 and inv[i,d]>0:
                    new=max(-brakes[i,d]*dt,min(brakes[i,d]*dt,brake_imp[i,d]-v[i,d]/inv[i,d]))
                    v[i,d]+=inv[i,d]*(new-brake_imp[i,d]);brake_imp[i,d]=new
        for k in range(nc):
            i=ids[k,0];j=ids[k,1];ra=points[k]-q[i,:2];rb=points[k]-q[j,:2];norm=normal[k]
            kn=effective(inv,i,j,ra,rb,norm)
            if kn<1e-16:continue
            bias=beta*min(gap[k]+slop,0.)/dt
            vn=relative(v,i,j,ra,rb,norm)
            new=max(0.,lamb[k,0]-(vn+bias)/kn)
            impulse(v,inv,i,j,ra,rb,norm,new-lamb[k,0]);lamb[k,0]=new
            tang=np.array([-norm[1],norm[0]])
            kt=effective(inv,i,j,ra,rb,tang)
            if kt>1e-16:
                vt=relative(v,i,j,ra,rb,tang);limit=mu[k]*lamb[k,0]
                new=max(-limit,min(limit,lamb[k,1]-vt/kt))
                impulse(v,inv,i,j,ra,rb,tang,new-lamb[k,1]);lamb[k,1]=new
    for i in range(n):q[i]+=dt*v[i]
    contact_force=(lower_imp-upper_imp)/dt;max_pen=0.;fric_violation=0.
    for k in range(nc):
        i=ids[k,0];j=ids[k,1];ra=points[k]-q[i,:2];rb=points[k]-q[j,:2]
        nn=normal[k];tt=np.array([-nn[1],nn[0]])
        f=(nn*lamb[k,0]+tt*lamb[k,1])/dt
        contact_force[i,:2]-=f;contact_force[j,:2]+=f
        contact_force[i,2]-=cross2(ra,f);contact_force[j,2]+=cross2(rb,f)
        max_pen=max(max_pen,-gap[k]);fric_violation=max(fric_violation,abs(lamb[k,1])-mu[k]*lamb[k,0])
    return contact_force,max_pen,nc,fric_violation

def box(hx:float,hy:float)->np.ndarray:
    if hx<=0 or hy<=0:raise ValueError('Positive half extents required')
    return np.array([[-hx,-hy],[hx,-hy],[hx,hy],[-hx,hy]],float)

def polygon_inertia(poly:np.ndarray,mass:float)->float:
    # Area second moment about the specified body origin; accepts CCW shapes.
    b=np.roll(poly,-1,axis=0);c=poly[:,0]*b[:,1]-b[:,0]*poly[:,1]
    area=.5*c.sum()
    if area<=0:raise ValueError('Polygon must have positive CCW area')
    return float(mass*np.sum(c*(np.sum(poly*poly,axis=1)+np.sum(poly*b,axis=1)+np.sum(b*b,axis=1)))/(12*area))

class World:
    def __init__(self):
        self.names=[];self.polys=[];self.q=[];self.v=[];self.inv=[];self.masses=[];self.pairs=[];self.friction=[]
    def add(self,name,poly,pos=(0,0),angle=0.,mass=0.,dof=(1,1,1)):
        if name in self.names:raise ValueError('Duplicate body '+name)
        if not np.isfinite(mass) or mass<0:raise ValueError('Mass must be finite and nonnegative')
        if len(pos)!=2 or not np.isfinite(pos).all() or not np.isfinite(angle):raise ValueError('Invalid initial pose')
        if len(dof)!=3 or any(d not in (0,1) for d in dof):raise ValueError('DOF mask must contain three zeros or ones')
        p=np.asarray(poly,float)
        if len(p)<3 or len(p)>32 or not np.isfinite(p).all():raise ValueError('Invalid convex polygon')
        if np.min(np.linalg.norm(np.roll(p,-1,axis=0)-p,axis=1))<1e-12:raise ValueError('Degenerate polygon edge')
        polygon_inertia(p,1.) # validate positive area even for static bodies
        # Reject nonconvex input rather than silently taking its convex hull.
        for i in range(len(p)):
            edge_a=p[(i+1)%len(p)]-p[i];edge_b=p[(i+2)%len(p)]-p[(i+1)%len(p)]
            if edge_a[0]*edge_b[1]-edge_a[1]*edge_b[0] < -1e-12:raise ValueError('Non-convex polygon')
        I=polygon_inertia(p,mass) if mass else 1.
        inv=np.array([1/mass,1/mass,1/I])*dof if mass else np.zeros(3)
        self.names.append(name);self.polys.append(p);self.q.append([*pos,angle]);self.v.append([0.,0.,0.]);self.inv.append(inv);self.masses.append(mass)
        return len(self.names)-1
    def contact(self,a,b,mu):
        if a==b or not (0<=a<len(self.names) and 0<=b<len(self.names)) or not np.isfinite(mu) or mu<0:raise ValueError('Invalid contact pair')
        self.pairs.append((a,b));self.friction.append(mu)
    def compile(self):
        n=len(self.names);self.local=np.zeros((n,32,2));self.nv=np.zeros(n,np.int64)
        for i,p in enumerate(self.polys):self.local[i,:len(p)]=p;self.nv[i]=len(p)
        self.q=np.array(self.q,float);self.v=np.array(self.v,float);self.inv=np.array(self.inv,float)
        self.masses=np.array(self.masses);self.pairs=np.array(self.pairs,np.int64).reshape(-1,2);self.friction=np.array(self.friction,float)
        self.force=np.zeros_like(self.q);self.brakes=np.zeros_like(self.q)
        self.lower=np.full_like(self.q,-np.inf);self.upper=np.full_like(self.q,np.inf);self.limit_velocity=np.zeros_like(self.q)
        return self
    def advance(self,dt,iterations=40):
        if dt<=0 or iterations<1:raise ValueError('Positive dt and iteration count required')
        if np.any(self.lower>self.upper):raise ValueError('Inverted coordinate limits')
        return step(self.q,self.v,self.inv,self.local,self.nv,self.pairs,self.friction,self.force,self.brakes,
                    self.lower,self.upper,self.limit_velocity,dt,iterations)
