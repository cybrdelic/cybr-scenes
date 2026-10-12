"""X: expose transported grains on W's new sediment datum, without new bodies.

W terrain, approved prototype geometry/materials, old retained particles,
asphalt/contact, cameras and lighting remain exact. Only selected supplemental
instance origins change Z. Deposited solid-volume and area proxies bound this
representation selection; it is not additional mass in the transport solver.
"""
from pathlib import Path
import os,sys,json,time,hashlib,argparse
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='2'
import numpy as np
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
import prepare_physical_lenses as u
import approved_density_lod as lod
from flow_sediment_model_w import simulate_shoulder
from transported_grain_exposure import allocate_transported_grains
import bpy
SOURCE=R/'preview/road_r6_w_flow.blend'
SOURCE_SHA='fbff2b7f0380eac0ebfb3d08b5c00efe92d91ff52e692e81a822c589582ac81d'
OUTPUT=R/'preview/road_r6_x_transport_grains.blend'
RECEIPT=R/'receipts/transport_surface_grains_x.json'

def main():
    start=time.monotonic();assert not OUTPUT.exists() and not RECEIPT.exists()
    parser=argparse.ArgumentParser();parser.add_argument('--source-fingerprint',type=Path)
    a=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    source_sha=u.sha256(SOURCE)
    if source_sha!=SOURCE_SHA and not a.source_fingerprint:raise ValueError('Rebuilt W requires locked structure')
    flow_receipt=json.loads((R/'receipts/flow_shoulder_w.json').read_text())
    assert u.sha256(R/'src/flow_sediment_model_w.py')==flow_receipt['flow_model_sha256']
    fields=np.load(R/'receipts/flow_shoulder_w_fields.npz');x,y=fields['x_m'],fields['y_m']
    flow=simulate_shoulder(x,y,fields['source_z_m'])
    np.testing.assert_allclose(flow.height_delta_m,fields['delta_m'],rtol=0,atol=1e-12)
    for key in ('cumulative_erosion_m3','cumulative_deposition_m3','boundary_export_m3'):
        assert abs(flow.receipt[key]-flow_receipt['model'][key])<1e-11,key
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE));scene=bpy.context.scene
    scene.render.threads_mode='FIXED';scene.render.threads=2;scene.cycles.device='CPU'
    existing=list(bpy.data.objects)
    full=u.protected_snapshot(bpy,existing,set(),set())
    structural_sha=hashlib.sha256(json.dumps(full,sort_keys=True).encode()).hexdigest()
    if source_sha!=SOURCE_SHA and structural_sha!=json.loads(a.source_fingerprint.read_text())['source_scene_structural_sha256']:
        raise ValueError('Rebuilt W structural fingerprint differs')
    obj=scene.objects[lod.OUTPUT];co=lod._co(obj.data).copy();assert np.allclose(np.array(obj.matrix_world),np.eye(4))
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
    scene['scene_version']='R6 X transported-class surface exposure on unchanged W terrain'
    bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT),compress=True)
    report=dict(source_scene_sha256=source_sha,source_scene_structural_sha256=structural_sha,
        output_scene_sha256=u.sha256(OUTPUT),builder_sha256=u.sha256(Path(__file__)),
        allocation_source_sha256=u.sha256(R/'src/transported_grain_exposure.py'),flow_model_sha256=u.sha256(R/'src/flow_sediment_model_w.py'),
        W_flow_recomputed_exactly=True,terrain_and_old_retained_grains_unchanged=True,
        prototype_geometry_materials_camera_lighting_unchanged=True,total_supplemental_instances=len(co),
        promoted_supplemental_instances=int(selected.sum()),new_instances=0,
        upward_origin_shift_min_max_m=[float((new[:,2]-co[:,2]).min()),float((new[:,2]-co[:,2]).max())],
        allocation=allocation.receipt,contact_audited=len(audit),
        contact_floating_over20um=int(np.sum(audit[:,0]>.00002)) if len(audit) else 0,
        contact_fully_buried=int(np.sum(audit[:,1]<0)) if len(audit) else 0,
        contact_min_max_m=[float(audit[:,0].min()),float(audit[:,1].max())] if len(audit) else [],
        preserved_original_scene=SOURCE.name,CPU_threads=2,elapsed_seconds=time.monotonic()-start,
        limits='Representation selection debits transported class budgets but does not add solver mass. Unresolved grains and the source bake remain approximations. Candidate, not validated site simulation.')
    RECEIPT.write_text(json.dumps(report,indent=2)+'\n');print('X_READY',json.dumps(report),flush=True)
if __name__=='__main__':main()
