"""In-memory actual-terrain context extension of the finite-inventory Z solver.
Preserves the approved near-ground checkpoint and native road; no scene is saved.
"""
from pathlib import Path
import gc, json, time, hashlib
import numpy as np
import bpy
from context_mesh_refine_ab import prepare_context_refinement,audit_context_projection,SourceSampler,RefineLimits,_read
from visible_shoulder_flow_ad import ContextSpec,context_axes,sample_triangle_grid,solve_context,sample_displacement
import prepare_physical_lenses as legacy
import context_field_cache_ad as cache

class Surface:
    def __init__(self,sampler):self.sampler=sampler
    def height(self,xy):
        p=np.asarray(xy);return self.sampler.height(p.reshape(-1,2)).reshape(p.shape[:-1])

def update_normals(mesh,plan,before,after,delta):
    """Rotate preserved corner detail by actual old/new area-weighted normals."""
    tri=plan.triangles;active=np.any(np.abs(delta[tri])>1e-12,axis=1);tri=tri[active]
    if not len(tri):return dict(changed_corner_normals=0)
    ids,inverse=np.unique(tri,return_inverse=True);t=inverse.reshape(-1,3)
    def broad(co):
        v=co[tri];face=np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0]);out=np.zeros((len(ids),3))
        for k in range(3):np.add.at(out,t[:,k],face)
        length=np.linalg.norm(out,axis=1);good=length>1e-15;out[good]/=length[good,None];out[~good]=[0,0,1];return out
    old,new=broad(before),broad(after);normal=_read(mesh.corner_normals,'vector',3)
    loops=_read(mesh.loops,'vertex_index',1,np.int32);pos=np.searchsorted(ids,loops);mask=pos<len(ids);rows=np.flatnonzero(mask);rows=rows[ids[pos[rows]]==loops[rows]]
    ix=pos[rows];k=np.cross(old[ix],new[ix]);d=np.sum(old[ix]*new[ix],axis=1)
    if np.any(d<-.5):raise AssertionError('Unexpected near-reversal in shallow sediment normals')
    v=normal[rows].astype(float);c=np.cross(k,v);v=v+c+np.cross(k,c)/(1+d[:,None]);v/=np.linalg.norm(v,axis=1)[:,None]
    normal[rows]=v;mesh.normals_split_custom_set(normal)
    return dict(changed_corner_normals=len(rows),policy='Shortest-arc rotation of preserved source corner normals by actual old/new local triangle normals',maximum_broad_rotation_degrees=float(np.rad2deg(np.arccos(np.clip(np.sum(old*new,axis=1),-1,1))).max()))

def apply(scene,config,output_directory):
    start=time.monotonic();out=Path(output_directory);ground=scene.objects['Graded shoulder and alluvial plain -1']
    # First context domain excludes the very dense approved near specimen and
    # stays outside the pavement-contact bank. No analytic height fallback.
    bounds=tuple(config.get('bounds_m',(-6.2,-3.45,-.60,8.20)))
    from flow_sediment_model_z import FlowConfig
    spec=ContextSpec(bounds_m=bounds,protected_bounds_m=(100.,101.,100.,101.),loose_layer_m=.060,retained_deposit_cap_m=.030,flow=FlowConfig(exchange_diameter_m=.15,boundary_band_m=.20,max_erosion_m=.045,max_deposition_m=.030,max_event_erosion_m=.010,rainfall_m=(.020,.035,.025,.040,.030)))
    print('AD_PREPARE',bounds,flush=True)
    prepared=prepare_context_refinement(ground,bounds=bounds,protected_bounds=spec.protected_bounds_m,contact_x=spec.protected_contact_x_min_m,max_edge_m=.07,limits=RefineLimits(max_local_source_triangles=450000,max_added_vertices=240000,max_output_triangles=800000))
    print('AD_REFINED',json.dumps(prepared['report']),flush=True)
    x,y=context_axes(spec);z=sample_triangle_grid(prepared['source_sampler'].height,x,y)
    if config.get('cache_path'):
        result=cache.read(config['cache_path'],x,y,z,spec,config['cache_sha256'])
        numeric_source=dict(path=config['cache_path'],sha256=config['cache_sha256'],guard='Actual sampled Z, axes, complete spec and two numerical source hashes match')
    else:
        result=solve_context(x,y,z,spec=spec)
        cache_path=out/'AD_PINNED_FIELD.npz';cache_sha=cache.write(cache_path,result)
        numeric_source=dict(path=str(cache_path),sha256=cache_sha,guard='Fresh actual-terrain solve')
    print('AD_TRANSPORT',json.dumps(result.receipt),flush=True)
    # Preserve the small numeric field even if a subsequent topology/contact
    # check rejects the scene; never label that numeric result a render.
    np.savez_compressed(out/'AD_SOLVED_FIELDS.npz',x_m=x,y_m=y,source_z_m=z,delta_m=result.flow.height_delta_m,retained_deposit_by_class_m=result.flow.retained_deposit_by_class_m,surface_fraction=result.flow.surface_fraction,lag=result.flow.lag_exposure,flow_strength=result.flow.flow_strength)
    co=prepared['coordinates'];delta=sample_displacement(result,co[:,:2]);audit=audit_context_projection(prepared['plan'],co,delta,result)
    print('AD_PROJECTION',json.dumps(audit),flush=True)
    if audit.get('maximum_protected_interpolated_displacement_m',0)>1e-10:raise AssertionError('Protected mesh interpolation changed')
    # Keep all audit fields explicit; no mass-fixing offset or output blur.
    for key,val in audit.items():
        if ('outside' in key or 'protected' in key) and ('volume' in key or 'displacement' in key) and isinstance(val,(float,int)) and abs(val)>1e-9:
            raise AssertionError('Projection leaks: '+key)
    new=prepared['mesh'];afterco=co.copy();afterco[:,2]+=delta
    new.vertices.foreach_set('co',afterco.astype('f4').ravel());new.update()
    normal_report=update_normals(new,prepared['plan'],co,afterco,delta)
    # Every retained loose body translates rigidly to the new actual triangles;
    # deposition buries the existing body instead of floating it on top.
    old_surface=Surface(prepared['source_sampler']);plan=prepared['plan']
    after_sampler=SourceSampler(afterco,plan.triangles,np.arange(len(plan.triangles)),max_triangles=800000,max_bin_entries=3000000)
    final_surface=Surface(after_sampler)
    legacy.EDIT_BOUNDS=bounds;legacy.PATCH_BOUNDS=(bounds[0]-.06,bounds[1]+.06,bounds[2]-.06,bounds[3]+.06);legacy.in_bounds.__defaults__=(bounds,0.)
    movement,roots,_,_=legacy.move_existing(scene,old_surface,final_surface,legacy.DiskIndex())
    # The supplemental origin mesh is an existing source-sized population.
    # Preserve all prototypes and instance IDs; sediment changes only support.
    supplemental=scene.objects['U approved R5D density / projected chip and grit supplement']
    sco=legacy.read_coordinates(supplemental.data);sw=legacy.world_coordinates(supplemental,sco)
    select=legacy.in_bounds(sw[:,:2],bounds);rows=np.flatnonzero(select);shift=np.zeros(len(sco))
    if len(rows):shift[rows]=legacy.loose_shift(final_surface.height(sw[rows,:2])-old_surface.height(sw[rows,:2]))
    legacy.write_world_z(supplemental,sco,shift)
    supplement=dict(object=supplemental.name,moved_origins=int(np.count_nonzero(shift)),shift_min_max_m=[float(shift.min()),float(shift.max())],prototype_identity_and_geometry_preserved=True)
    old=ground.data;ground.data=new
    if old.users==0:bpy.data.meshes.remove(old)
    fields=out/'AD_CONTEXT_FIELDS.npz'
    np.savez_compressed(fields,x_m=x,y_m=y,source_z_m=z,delta_m=result.flow.height_delta_m,retained_deposit_by_class_m=result.flow.retained_deposit_by_class_m,surface_fraction=result.flow.surface_fraction,lag=result.flow.lag_exposure,flow_strength=result.flow.flow_strength)
    report=dict(numeric_source=numeric_source,scope='Visible existing shoulder reconstruction from finite60mm erodible stock; road-contact bank and exact approved grain prototypes/maps preserved',bounds_m=bounds,refinement=prepared['report'],transport=result.receipt,projection=audit,normals=normal_report,moved_bodies=movement,moved_roots=roots,supplemental_origins=supplement,changed_vertices=int(np.count_nonzero(delta)),displacement_min_max_m=[float(delta.min()),float(delta.max())],new_ground_sheets=0,material_sources_modified=False,new_particles=0,field_sha256=hashlib.sha256(fields.read_bytes()).hexdigest(),elapsed_seconds=time.monotonic()-start,limits='Uncalibrated finite-inventory terrain transport. First visible geometry/contact diagnostic; existing source-sized particles are reseated/buried. Deposited-class population reallocation is not included yet. Visual acceptance separate.')
    del prepared,plan,co,afterco,delta,after_sampler,old_surface,final_surface,result,z;gc.collect()
    print('AD_ASSEMBLED',json.dumps(report),flush=True);return report
