"""Y shared transported-grain exposure; extracted unchanged from the tested X placement path.
Only budgeted supplemental origins move Z. Immutable prototype bank and scene materials remain exact.
"""
import numpy as np
import bpy
import prepare_physical_lenses as u
import approved_density_lod as lod
from transported_grain_exposure import allocate_transported_grains

def apply_transported_exposure(scene,flow,x,y):
    obj=scene.objects[lod.OUTPUT];co=lod._co(obj.data).copy();assert np.allclose(np.array(obj.matrix_world),np.eye(4))
    existing=list(bpy.data.objects)
    protected=u.protected_snapshot(bpy,existing,{obj.data.name},set())
    pi=np.empty(len(co),np.int32);obj.data.attributes['prototype'].data.foreach_get('value',pi)
    yaw=np.empty((len(co),3),np.float32);obj.data.attributes['yaw'].data.foreach_get('vector',yaw.ravel())
    records,_,_=lod._bank(scene.objects[lod.ORIGINS]);volumes=[];zbound=[]
    for rec in records:
        mesh=bpy.data.objects[rec['name']].data;mesh.calc_loop_triangles()
        tri=np.empty((len(mesh.loop_triangles),3),np.int32);mesh.loop_triangles.foreach_get('vertices',tri.ravel())
        v=rec['vertices'];tv=v[tri]
        edges=np.sort(np.concatenate((tri[:,[0,1]],tri[:,[1,2]],tri[:,[2,0]])),axis=1)
        _,edge_counts=np.unique(edges,axis=0,return_counts=True)
        if np.any(edge_counts!=2):raise AssertionError('Prototype is not closed for a solid-volume budget: '+rec['name'])
        volume=abs(float(np.einsum('ij,ij->i',tv[:,0],np.cross(tv[:,1],tv[:,2])).sum()/6))
        assert 1e-14<volume<1e-6,(rec['name'],volume)
        volumes.append(volume);zbound.append([float(v[:,2].min()),float(v[:,2].max())])
    cls=np.array([2 if rec['band']=='chips' else 1 for rec in records],np.int32)
    surface=u.exact_patch(scene.objects[u.GROUND],(-6.25,-3.17,-.70,8.32),220000)
    final=lod._height(surface,co[:,:2])
    # W's retained-origin rule is invertible in net-deposition zones. Scours
    # have final==origin and correctly get zero, without inventing old Z.
    local_net=np.maximum(final-co[:,2],0)/.85
    allocation=allocate_transported_grains(xy_m=co[:,:2],flow_class=cls[pi],
        solid_volume_m3=np.asarray(volumes)[pi],diameter_m=np.array([q['diameter'] for q in records])[pi],
        footprint_area_m2=np.array([q['footprint_area'] for q in records])[pi],
        local_z_bounds_m=np.asarray(zbound)[pi],final_surface_m=final,x_m=x,y_m=y,
        retained_deposit_by_class_m=flow.retained_deposit_by_class_m,net_deposit_m=flow.height_delta_m,
        local_net_deposit_m=local_net)
    selected=allocation.transported
    new=co.copy();new[selected,2]=(final[selected]-allocation.extra_embedment_m[selected]).astype('f4')
    assert np.array_equal(new[:,:2],co[:,:2]) and np.array_equal(new[~selected],co[~selected])
    assert np.isfinite(new).all()
    obj.data.vertices.foreach_set('co',new.ravel());obj.data.update()
    assert u.protected_snapshot(bpy,existing,{obj.data.name},set())==protected,'Protected W scene data changed'
    # Bounded actual metric contact audit, not evaluated instance expansion.
    indices=np.flatnonzero(selected);audit=[]
    if len(indices):
        chosen=indices[np.unique(np.linspace(0,len(indices)-1,min(384,len(indices)),dtype=int))]
        for i in chosen:
            v=records[int(pi[i])]['vertices'].copy();c,s=np.cos(yaw[i,2]),np.sin(yaw[i,2])
            v[:,:2]=v[:,:2]@np.array([[c,-s],[s,c]]).T;v+=new[i]
            contact=v[:,2]-lod._height(surface,v[:,:2],allow_missing=True);contact=contact[np.isfinite(contact)]
            if len(contact):audit.append([float(contact.min()),float(contact.max())])
    audit=np.asarray(audit).reshape(-1,2)
    if len(audit) and np.any(audit[:,0]>.00002):raise AssertionError('Promoted grain floats more than20um above actual triangles')
    return dict(allocation=allocation.receipt,total_supplemental_instances=len(co),promoted_supplemental_instances=int(selected.sum()),new_instances=0,
        upward_origin_shift_min_max_m=[float((new[:,2]-co[:,2]).min()),float((new[:,2]-co[:,2]).max())],
        contact_audited=len(audit),contact_floating_over20um=int(np.sum(audit[:,0]>.00002)) if len(audit) else 0,
        contact_fully_buried=int(np.sum(audit[:,1]<0)) if len(audit) else 0,
        contact_min_max_m=[float(audit[:,0].min()),float(audit[:,1].max())] if len(audit) else [],
        limits='Representation selection uses deposited-class solid-volume budgets; it does not add solver mass. Unresolved grains and the source bake remain approximate.')
