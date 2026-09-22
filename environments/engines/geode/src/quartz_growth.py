"""Deterministic mesoscopic faceted growth in a diffusing solute field.

The finite-volume reservoir evolves by six-neighbor fluxes. Facet velocities
depend on nearby supersaturation and direction-dependent attachment rates.
Crystal geometry is the intersection of moving half-spaces. This is a visual
mesoscale model, not atomistic quartz chemistry or a calibrated geological clock.
"""
from pathlib import Path
import itertools
import json
import numpy as np
from scipy.spatial import ConvexHull
from scipy.ndimage import map_coordinates, gaussian_filter

ROOT=Path(__file__).resolve().parent
ASSETS=ROOT/'assets'
ASSETS.mkdir(exist_ok=True)


def normalize(x):
    x=np.asarray(x,dtype=float)
    return x/np.linalg.norm(x)


def rotation(axis, spin):
    z=normalize(axis)
    x=normalize(np.cross([0,1,0],z))
    y=np.cross(z,x)
    a=np.array([[np.cos(spin),-np.sin(spin),0],
                [np.sin(spin),np.cos(spin),0],[0,0,1]])
    return np.stack([x,y,z],axis=1)@a


ANGLES=np.arange(6)*np.pi/3
NORMALS=np.array([[np.cos(a),np.sin(a),0] for a in ANGLES]+
                 [[.78*np.cos(a),.78*np.sin(a),.625] for a in ANGLES]+
                 [[0,0,-1]],dtype=float)
TRIPLES=np.array(list(itertools.combinations(range(13),3)))
GOOD=np.abs(np.linalg.det(NORMALS[TRIPLES]))>1e-8
TRIPLES=TRIPLES[GOOD]
INVERSES=np.linalg.inv(NORMALS[TRIPLES])


def polyhedron(offsets):
    v=np.einsum('ijk,ik->ij',INVERSES,np.asarray(offsets)[TRIPLES])
    v=v[np.all(v@NORMALS.T<=offsets[None,:]+1e-7,axis=1)]
    v=np.unique(np.round(v,9),axis=0)
    hull=ConvexHull(v)
    faces=hull.simplices.copy()
    centers=v[faces].mean(axis=1)
    normals=np.cross(v[faces[:,1]]-v[faces[:,0]],v[faces[:,2]]-v[faces[:,0]])
    flip=np.einsum('ij,ij->i',normals,centers-v.mean(axis=0))<0
    faces[flip]=faces[flip][:,::-1]
    return v,faces,hull.volume


def face_samples(offsets):
    vertices,triangles,vol=polyhedron(offsets)
    centers=np.zeros((13,3))
    areas=np.zeros(13)
    for tri in triangles:
        points=vertices[tri]
        center=points.mean(axis=0)
        face=int(np.argmin(np.abs(NORMALS@center-offsets)))
        area=np.linalg.norm(np.cross(points[1]-points[0],points[2]-points[0]))*.5
        centers[face]+=area*center
        areas[face]+=area
    for k in range(13):
        centers[k]=centers[k]/areas[k] if areas[k]>1e-12 else NORMALS[k]*offsets[k]/np.dot(NORMALS[k],NORMALS[k])
    return centers,areas,vol


def seeds():
    rng=np.random.default_rng(82911)
    # The major nuclei have different attachment coefficients, not animated scales.
    layout=[(-.55,.35,1.0,.92),(.33,.46,.84,1.10),(.95,.12,.61,.83),
            (-1.29,.01,.63,.86),(-.35,-.56,.50,.83),(.46,-.55,.46,.88),
            (1.48,.60,.42,.72),(-1.04,.96,.56,.84),(.0,1.17,.55,.86),
            (1.1,-.72,.33,.64),(-1.62,-.65,.38,.66),(-.98,-1.03,.27,.63),
            (.03,-1.09,.29,.68),(1.77,-.31,.29,.66),(-1.80,.66,.31,.70),
            (.77,1.09,.42,.73),(1.64,1.27,.22,.42),(-1.95,1.24,.22,.40)]
    result=[]
    for i,(x,y,speed,width) in enumerate(layout):
        axis=normalize([x*.16+rng.uniform(-.07,.07),y*.15+rng.uniform(-.06,.06),1.0])
        R=rotation(axis,rng.uniform(0,2*np.pi))
        z=.26+.14*np.exp(-(x*x+y*y)/2)
        result.append({'id':i,'origin':[x,y,z],'rotation':R.tolist(),
                       'speed':speed,'width':width,'birth':float(rng.uniform(0,.9)),
                       'phase':float(rng.uniform(0,2*np.pi))})
    return result


def simulate(steps=480,dt=.032):
    specs=seeds()
    n=len(specs)
    origins=np.array([s['origin'] for s in specs])
    rotations=np.array([s['rotation'] for s in specs])
    h=np.tile(np.array([.045]*6+[.071]*6+[.20]),(n,1))
    h[:,6:12]+=np.array([0,.003,0,.003,0,.003])
    lo=np.array([-3.3,-2.9,-.2]); dx=.11
    shape=(62,54,52)
    coords=np.indices(shape).transpose(1,2,3,0)*dx+lo
    C=np.ones(shape,dtype=np.float64)
    X,Y,Z=np.moveaxis(coords,-1,0)
    # Impermeable mineral matrix; upper/lateral boundaries contact the reservoir.
    solid=Z < (.12+.08*np.exp(-(X*X+Y*Y)/3))
    C[solid]=0.0
    D=.036
    courant=D*dt/dx**2
    assert courant<1/6
    histories=[h.copy()]
    masses=[]
    centers=np.zeros((n,13,3));areas=np.zeros((n,13))
    removed=0.0; reservoir_added=0.0
    norms=np.linalg.norm(NORMALS,axis=1)
    normed=NORMALS/norms[:,None]
    rates=np.zeros((n,13))
    for k,s in enumerate(specs):
        rates[k,:6]=.0245*s['width']*(1+.06*np.sin(ANGLES+s['phase']))
        rates[k,6:12]=.151*s['speed']*(1+.013*np.cos(ANGLES*3+s['phase']))
    initial_mass=C.sum()*dx**3
    for it in range(steps):
        # Conservative pairwise diffusion flux; no flux through the matrix.
        dC=np.zeros_like(C)
        for axis in range(3):
            a=[slice(None)]*3;b=a.copy();a[axis]=slice(None,-1);b[axis]=slice(1,None)
            a=tuple(a);b=tuple(b)
            flux=courant*(C[b]-C[a])*(~solid[a])*(~solid[b])
            dC[a]+=flux;dC[b]-=flux
        C+=dC
        boundary=np.zeros(shape,bool)
        boundary[0,:,:]=True;boundary[-1,:,:]=True
        boundary[:,0,:]=True;boundary[:,-1,:]=True;boundary[:,:,-1]=True
        boundary &= ~solid
        reservoir_added+=float(np.sum(1.0-C[boundary])*dx**3)
        C[boundary]=1.0
        if it%8==0:
            for k in range(n):
                centers[k],areas[k],_=face_samples(h[k])
        sample_local=centers+normed[None,:,:]*.13
        sample_world=np.einsum('nij,nkj->nki',rotations,sample_local)+origins[:,None,:]
        grid=(sample_world-lo)/dx
        concentration=map_coordinates(C,grid.reshape(-1,3).T,order=1,mode='nearest').reshape(n,13)
        active=np.array([it*dt>=s['birth'] for s in specs])[:,None]
        velocity=rates*np.maximum(concentration-.14,0)*active
        dh=velocity*dt
        # Volume swept by a face = area * normal displacement. Concentration
        # sinks are distributed to a 3x3x3 stencil, and limited by local solute.
        uptake=areas*(dh/norms)*.31/dx**3
        demand=np.zeros(shape)
        idx=np.rint(grid).astype(int).reshape(-1,3)
        weights=uptake.ravel()
        kernel=[]
        for shift in itertools.product([-1,0,1],repeat=3):
            weight=np.exp(-np.dot(shift,shift)*.8)
            kernel.append((np.array(shift),weight))
        norm=sum(w for _,w in kernel)
        for shift,w in kernel:
            ix=np.clip(idx+shift,0,np.array(shape)-1)
            np.add.at(demand,tuple(ix.T),weights*w/norm)
        demand[solid]=0
        actual=np.minimum(demand,C*.23)
        removed+=float(actual.sum()*dx**3)
        C-=actual
        h+=dh
        histories.append(h.copy())
        if it%40==0 or it==steps-1:
            volumes=[polyhedron(x)[2] for x in h]
            balance=C.sum()*dx**3+removed-initial_mass-reservoir_added
            masses.append({'step':it,'solute':float(C.sum()*dx**3),'uptake':removed,
                           'reservoir_added':reservoir_added,'balance_error':float(balance),
                           'crystal_volume':float(sum(volumes)),'min_c':float(C.min()),'max_c':float(C.max())})
            print('growth',it,'volume',round(sum(volumes),3),'balance',f'{balance:.2e}',flush=True)
    history=np.array(histories)
    np.savez_compressed(ASSETS/'growth.npz',history=history,concentration=C,grid_origin=lo,dx=dx,dt=dt)
    (ASSETS/'seeds.json').write_text(json.dumps(specs,indent=2))
    record={'model':'anisotropic moving-facet kinetics coupled to a diffusing finite-volume solute reservoir',
            'calibrated':False,'steps':steps,'dt':dt,'grid_shape':shape,'dx':dx,'diffusion_coefficient':D,
            'diffusion_courant':courant,'seed_count':n,'mass_diagnostics':masses,
            'limitations':['Nondimensional illustrative parameters; no physical time mapping.',
                           'Diffusion field uses a coarse mesoscopic matrix mask and facet-centered sinks; moving crystal interiors are not cut cells.',
                           'Swept facet volume approximates uptake. Concentration is bounded but kinetics are not a thermodynamic quartz model.',
                           'No atomistic nucleation, elastic stress, latent heat, or geochemical species reactions.']}
    (ASSETS/'growth_diagnostics.json').write_text(json.dumps(record,indent=2))
    return history,specs


def load_growth(t=1):
    data=np.load(ASSETS/'growth.npz')
    h=data['history']
    pos=np.clip(t,0,1)*(len(h)-1)
    a=int(pos);b=min(a+1,len(h)-1)
    offsets=(1-(pos-a))*h[a]+(pos-a)*h[b]
    return offsets,json.loads((ASSETS/'seeds.json').read_text())


if __name__=='__main__':
    simulate()
