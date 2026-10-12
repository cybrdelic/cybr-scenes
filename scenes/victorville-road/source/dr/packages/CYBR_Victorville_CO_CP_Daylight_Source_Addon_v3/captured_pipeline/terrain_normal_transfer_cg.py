"""CG preserves finite corner vectors before geometry-dependent custom-normal decoding changes."""
import numpy as np
from context_mesh_refine_ab import _read

def update_normals(mesh,plan,before,after,delta,preserved_normals):
    """Rotate preserved corner detail by actual old/new area-weighted normals."""
    tri=plan.triangles;active=np.any(np.abs(delta[tri])>1e-12,axis=1);tri=tri[active]
    if not len(tri):return dict(changed_corner_normals=0)
    ids,inverse=np.unique(tri,return_inverse=True);t=inverse.reshape(-1,3)
    def broad(co):
        v=co[tri];face=np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0]);out=np.zeros((len(ids),3))
        for k in range(3):np.add.at(out,t[:,k],face)
        length=np.linalg.norm(out,axis=1);good=length>1e-15;out[good]/=length[good,None];out[~good]=[0,0,1];return out
    old,new=broad(before),broad(after);normal=np.array(preserved_normals,copy=True)
    if normal.shape!=(len(mesh.loops),3):raise ValueError('Pre-deformation corner vectors required')
    loops=_read(mesh.loops,'vertex_index',1,np.int32);pos=np.searchsorted(ids,loops);mask=pos<len(ids);rows=np.flatnonzero(mask);rows=rows[ids[pos[rows]]==loops[rows]]
    ix=pos[rows];k=np.cross(old[ix],new[ix]);d=np.sum(old[ix]*new[ix],axis=1)
    if np.any(d<-.5):raise AssertionError('Unexpected near-reversal in shallow sediment normals')
    v=normal[rows].astype(float);assert np.isfinite(v).all(),'Nonfinite source corner normal';c=np.cross(k,v);v=v+c+np.cross(k,c)/(1+d[:,None]);length=np.linalg.norm(v,axis=1);valid=length>1e-12;v[valid]/=length[valid,None];v[~valid]=new[ix[~valid]]
    normal[rows]=v;assert np.isfinite(normal).all(),'Nonfinite resulting corner normal';mesh.normals_split_custom_set(normal)
    return dict(changed_corner_normals=len(rows),policy='Preserved pre-deformation vectors; one shortest-arc rotation of preserved source corner normals by actual old/new local triangle normals',zero_source_corner_normals_using_actual_broad_fallback=int((~valid).sum()),nonfinite_output_normals=0,maximum_broad_rotation_degrees=float(np.rad2deg(np.arccos(np.clip(np.sum(old*new,axis=1),-1,1))).max()))
