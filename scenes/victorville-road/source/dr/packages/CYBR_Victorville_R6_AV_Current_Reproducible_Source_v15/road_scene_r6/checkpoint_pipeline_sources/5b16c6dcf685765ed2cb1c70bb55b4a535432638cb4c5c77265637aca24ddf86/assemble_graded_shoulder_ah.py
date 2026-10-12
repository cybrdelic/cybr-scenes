"""AH: authored road earthwork plus restrained finite-stock AE weathering.
Geometry is reconstructed in memory from pinned Z; source materials retained.
"""
from pathlib import Path
from dataclasses import asdict
import gc,json,time,hashlib
import numpy as np
import bpy
from context_mesh_refine_ab import prepare_context_refinement,audit_context_projection,SourceSampler,RefineLimits
from visible_shoulder_flow_ad import ContextSpec,context_axes,sample_triangle_grid,sample_displacement,sample_field
from flow_transport_ae import solve_context
from flow_sediment_model_z import FlowConfig
from graded_shoulder_foundation_ah import evaluate_mesh_target,FoundationSpec
from assemble_visible_shoulder_ad import Surface
from terrain_normal_transfer_ah import update_normals
from context_mesh_refine_ab import _read
import prepare_physical_lenses as legacy


def move_existing(scene,old,foundation,final,bounds):
    def shift(xy):
        a=old.height(xy);b=foundation.height(xy);c=final.height(xy)
        return (b-a)+legacy.loose_shift(c-b)
    records=[]
    for name in (legacy.ORIGINS,'U approved R5D density / projected chip and grit supplement'):
        obj=scene.objects[name];co=legacy.read_coordinates(obj.data);world=legacy.world_coordinates(obj,co)
        rows=np.flatnonzero(legacy.in_bounds(world[:,:2],bounds));dz=np.zeros(len(co))
        if len(rows):dz[rows]=shift(world[rows,:2])
        legacy.write_world_z(obj,co,dz)
        records.append(dict(object=name,moved_origins=int(np.count_nonzero(dz)),shift_min_max_m=[float(dz.min()),float(dz.max())],prototype_geometry_material_and_ids_preserved=True))
    legacy.EDIT_BOUNDS=bounds;legacy.PATCH_BOUNDS=(bounds[0]-.06,bounds[1]+.06,bounds[2]-.06,bounds[3]+.06);legacy.in_bounds.__defaults__=(bounds,0.)
    for name in legacy.RIGID:
        obj=scene.objects[name];co=legacy.read_coordinates(obj.data);world=legacy.world_coordinates(obj,co);components=legacy.local_components(obj.data,world)
        dz=np.zeros(len(co));count=0
        for ids in components:
            q=world[ids,:2];center=(q.min(0)+q.max(0))*.5
            if legacy.in_bounds(center[None],bounds)[0]:
                amount=float(shift(center));dz[ids]=amount;count+=abs(amount)>1e-10
        legacy.write_world_z(obj,co,dz);records.append(dict(object=name,moved_complete_bodies=count,shape_preserved=True))
    roots=[]
    for obj in scene.objects:
        if not obj.name.startswith(legacy.PLANT_PREFIXES):continue
        p=np.asarray(obj.matrix_world.translation,float)
        if legacy.in_bounds(p[None,:2],bounds)[0]:
            dz=float(final.height(p[:2])-old.height(p[:2]));m=obj.matrix_world.copy();m.translation.z+=dz;obj.matrix_world=m;roots.append(dict(object=obj.name,z_shift_m=dz))
    return records,roots


def check_audit(audit):
    for key,value in audit.items():
        if ('outside' in key or 'protected' in key) and ('volume' in key or 'displacement' in key) and isinstance(value,(float,int)) and abs(value)>1e-9:
            raise AssertionError('Projection leaks: '+key)


def apply(scene,config,output_directory):
    start=time.monotonic();out=Path(output_directory);ground=scene.objects['Graded shoulder and alluvial plain -1']
    bounds=tuple(config.get('bounds_m',(-6.2,-3.25,-.60,8.20)))
    spec=ContextSpec(bounds_m=bounds,protected_bounds_m=(100.,101.,100.,101.),protected_contact_x_min_m=-3.25,loose_layer_m=.018,retained_deposit_cap_m=.014,flow=FlowConfig(exchange_diameter_m=.15,boundary_band_m=.20,max_erosion_m=.018,max_deposition_m=.018,max_event_erosion_m=.003,rainfall_m=(.020,.030,.025)))
    print('AH_PREPARE',bounds,flush=True)
    prepared=prepare_context_refinement(ground,bounds=bounds,protected_bounds=spec.protected_bounds_m,contact_x=spec.protected_contact_x_min_m,max_edge_m=.07,limits=RefineLimits(max_local_source_triangles=450000,max_added_vertices=240000,max_output_triangles=800000))
    x,y=context_axes(spec);z=sample_triangle_grid(prepared['source_sampler'].height,x,y)
    co=prepared['coordinates'];plan=prepared['plan'];ids=np.arange(len(plan.triangles))
    revision=config.get('foundation_revision','AH')
    if revision=='AT':
        from graded_shoulder_foundation_at import evaluate_mesh_target as evaluate_foundation,FoundationSpec as SelectedFoundationSpec
    elif revision=='AH':evaluate_foundation,SelectedFoundationSpec=evaluate_mesh_target,FoundationSpec
    else:raise ValueError('Unknown authored foundation revision: '+str(revision))
    foundation_delta,foundation_report=evaluate_foundation(co[:,:2],co[:,2],x,y,z,SelectedFoundationSpec())
    foundation_report['revision']=revision
    baseco=co.copy();baseco[:,2]+=foundation_delta
    foundation=Surface(SourceSampler(baseco,plan.triangles,ids,max_triangles=800000,max_bin_entries=3000000))
    foundation_z=sample_triangle_grid(foundation.height,x,y)
    print('AH_FOUNDATION',json.dumps(foundation_report),flush=True)
    history=None;initial_fractions=None
    if config.get('historical_substrate'):
        from substrate_history_ak import substrate_fields,summary as history_summary
        xx,yy=np.meshgrid(x,y);hf=dict(x_m=x,y_m=y,foundation_z_m=foundation_z)
        history=substrate_fields(np.stack((xx,yy),-1),hf)
        # Explicit illustrative 18 mm parent-unit compositions, not measured
        # stratigraphy. Total existing stock per cell is unchanged.
        class_mixtures=np.array([[.40,.34,.26],[.76,.20,.04],[.84,.15,.01]])
        weights=history['unit_weights'];initial_fractions=weights@class_mixtures+(1-weights.sum(-1))[...,None]*np.array(spec.flow.substrate_fractions)
        history_report=history_summary(hf);history_report['class_mixtures_matrix_grit_chips']=class_mixtures.tolist();history_report['chronology']='Pre-existing spatial parent mixture, then same AE storms; no new bed layer added'
        (out/'SUBSTRATE_HISTORY_AK.json').write_text(json.dumps(history_report,indent=2))
    result=solve_context(x,y,foundation_z,spec=spec,initial_class_fractions=initial_fractions)
    print('AH_TRANSPORT',json.dumps(result.receipt),flush=True)
    sediment_delta=sample_displacement(result,co[:,:2]);delta=foundation_delta+sediment_delta
    foundation_audit=audit_context_projection(prepared['plan'],co,foundation_delta,None);sediment_audit=audit_context_projection(prepared['plan'],co,sediment_delta,result);total_audit=audit_context_projection(prepared['plan'],co,delta,None)
    for audit in (foundation_audit,sediment_audit,total_audit):check_audit(audit)
    print('AH_PROJECTION',json.dumps(dict(foundation=foundation_audit,sediment=sediment_audit,total=total_audit)),flush=True)
    new=prepared['mesh'];preserved_normals=_read(new.corner_normals,'vector',3);afterco=co.copy();afterco[:,2]+=delta
    new.vertices.foreach_set('co',afterco.astype('f4').ravel());new.update();normal_report=update_normals(new,prepared['plan'],co,afterco,delta,preserved_normals)
    old=Surface(prepared['source_sampler']);final=Surface(SourceSampler(afterco,plan.triangles,ids,max_triangles=800000,max_bin_entries=3000000))
    movement,roots=move_existing(scene,old,foundation,final,bounds)
    oldmesh=ground.data;ground.data=new
    if oldmesh.users==0:bpy.data.meshes.remove(oldmesh)
    path=out/'AH_FIELDS.npz';payload=dict(x_m=x,y_m=y,old_source_z_m=z,foundation_z_m=foundation_z,sediment_delta_m=result.flow.height_delta_m,retained_deposit_by_class_m=result.flow.retained_deposit_by_class_m,surface_fraction=result.flow.surface_fraction,lag=result.flow.lag_exposure,flow_strength=result.flow.flow_strength)
    if history is not None:
        payload.update(initial_mobile_class_thickness_m=result.flow.initial_mobile_class_thickness_m,remaining_initial_mobile_class_thickness_m=result.flow.remaining_initial_mobile_class_thickness_m,initial_class_fractions=initial_fractions)
        payload.update({'historical_'+k:v for k,v in history.items()})
    np.savez_compressed(path,**payload)
    report=dict(historical_substrate=bool(history is not None),scope='Authored coherent road grading and connected shallow wash, then restrained current-bed-supported sediment weathering',bounds_m=bounds,foundation=foundation_report,transport=result.receipt,refinement=prepared['report'],foundation_projection=foundation_audit,sediment_projection=sediment_audit,total_projection=total_audit,normals=normal_report,moved_bodies=movement,moved_roots=roots,changed_vertices=int(np.count_nonzero(delta)),total_displacement_min_max_m=[float(delta.min()),float(delta.max())],material_sources_modified=False,new_ground_sheets=0,new_particles=0,field_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),elapsed_seconds=time.monotonic()-start,limits='Illustrative terrain construction, not surveyed Victorville or validated hydraulics. Earthwork volume is separate from conservative sediment mass. Existing particles follow all earthwork plus erosion/deposition burial; newly deposited-class population reallocation is not yet included. Visual acceptance separate.')
    del prepared,plan,co,baseco,afterco,delta,old,foundation,final,result,z,preserved_normals;gc.collect()
    print('AH_ASSEMBLED',json.dumps(report),flush=True);return report
