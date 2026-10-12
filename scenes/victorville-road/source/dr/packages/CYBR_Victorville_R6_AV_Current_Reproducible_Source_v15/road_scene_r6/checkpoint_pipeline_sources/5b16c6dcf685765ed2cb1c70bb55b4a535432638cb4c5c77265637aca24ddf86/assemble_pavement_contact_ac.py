"""Bounded actual contact proof, in memory over immutable Z. Never saves a scene."""
import gc,json,hashlib
from dataclasses import replace
from pathlib import Path
import numpy as np
import bpy
from edge_ravel_field_aa import EdgeRavelField
from metric_edge_strip_aa import prepare_edge_strip
from assemble_raveled_edge_aa import trim_old_wall
from pavement_contact_ac import ContactSpec,boundary_builder,prepare_contact
import prepare_physical_lenses as legacy

class OldSurface:
    def __init__(self,p):self.p=p
    def height(self,xy):
        q=np.asarray(xy);return self.p.sample(self.p.co[:,2],q.reshape(-1,2)).reshape(q.shape[:-1])
class NewSurface:
    def __init__(self,p):self.p=p
    def height(self,xy):
        q=np.asarray(xy);return self.p.height(q.reshape(-1,2)).reshape(q.shape[:-1])

def move_origins(ob,contact):
    co=legacy.read_coordinates(ob.data);world=legacy.world_coordinates(ob,co);xy=world[:,:2]
    a,b,c,d=contact['ground_plan'].bounds;band=(xy[:,0]>a)&(xy[:,0]<b)&(xy[:,1]>c)&(xy[:,1]<d)
    old=contact['ground_plan'].old_sampler;new=contact['ground_plan'].sampler
    oldright=old.right_edge(xy[:,1]);newright=new.right_edge(xy[:,1])
    supported=band&(xy[:,0]<=oldright-1e-9)&(xy[:,0]<=newright-1e-9)
    revealed=band&(xy[:,0]>oldright-1e-9)&(xy[:,0]<=newright-1e-9)
    shift=np.zeros(len(co))
    if supported.any():shift[supported]=legacy.loose_shift(contact['ground_delta'](xy[supported]))
    # Some immutable origin populations extend beneath the old pavement. Only
    # those newly exposed by inward ravel receive the actual new soil datum.
    if revealed.any():shift[revealed]=new.height(xy[revealed])-world[revealed,2]
    newco=legacy.write_world_z(ob,co,shift)
    assert np.array_equal(newco[shift==0],co[shift==0])
    return dict(object=ob.name,moved_origins=int(np.count_nonzero(shift)),previously_supported=int(supported.sum()),newly_revealed_soil_origins=int(revealed.sum()),still_under_pavement_unchanged=int((band&~supported&~revealed).sum()),shift_min_max_m=[float(shift.min()),float(shift.max())],prototype_geometry_identity_and_scale_unchanged=True)

def move_retained(scene,contact):
    records=[move_origins(scene.objects[n],contact) for n in (legacy.ORIGINS,'U approved R5D density / projected chip and grit supplement')]
    plan=contact['ground_plan'];a,b,c,d=plan.bounds
    legacy.EDIT_BOUNDS=plan.bounds;legacy.PATCH_BOUNDS=(a-.065,b+.065,c-.065,d+.065);legacy.in_bounds.__defaults__=(plan.bounds,0.)
    for name in legacy.RIGID:
        ob=scene.objects[name];co=legacy.read_coordinates(ob.data);world=legacy.world_coordinates(ob,co);components=legacy.local_components(ob.data,world);shifts=np.zeros(len(co));moved=revealed=0
        for component in components:
            v=world[component];center=(v[:,:2].min(0)+v[:,:2].max(0))*.5
            if not legacy.in_bounds(center[None,:])[0]:continue
            oldright=float(plan.old_sampler.right_edge(center[1]));newright=float(plan.sampler.right_edge(center[1]));shift=0.
            if center[0]<=min(oldright,newright)-1e-9:shift=float(legacy.loose_shift(plan.ground_delta(center)))
            elif oldright-1e-9<center[0]<=newright-1e-9:
                radius=float(np.linalg.norm(v[:,:2]-center,axis=1).max());shift=float(plan.sampler.height(center[None,:])[0]-np.mean(v[:,2])-.2*radius);revealed+=1
            if abs(shift)>1e-10:shifts[component]=shift;moved+=1
        if np.any(shifts):legacy.write_world_z(ob,co,shifts)
        records.append(dict(object=name,moved_rigid_bodies=moved,newly_revealed_bodies=revealed,prototype_shape_unchanged=True))
    roots=[]
    for ob in scene.objects:
        if not ob.name.startswith(legacy.PLANT_PREFIXES):continue
        p=np.asarray(ob.matrix_world.translation,float)
        if legacy.in_bounds(p[None,:2])[0] and p[0]<=min(float(plan.old_sampler.right_edge(p[1])),float(plan.sampler.right_edge(p[1])))-1e-9:
            dz=float(plan.ground_delta(p[:2]));m=ob.matrix_world.copy();m.translation.z+=dz;ob.matrix_world=m;roots.append(dict(object=ob.name,delta_m=dz))
    return records,roots

def apply(scene,config):
    height=Path(config['height_path']);spec=ContactSpec(sectors=()) if config.get('runoff_support_fields') else ContactSpec();road=scene.objects['Crowned asphalt crust / longitudinal rise'];ground=scene.objects['Graded shoulder and alluvial plain -1']
    field=EdgeRavelField(height)
    strip=prepare_edge_strip(road,height,boundary_builder=boundary_builder(field,spec))
    support_report=None
    if config.get('runoff_support_fields'):
        from runoff_edge_support_ai import build_edge_support
        f=dict(np.load(config['runoff_support_fields']))
        profile=build_edge_support(f['x_m'],f['y_m'],f['foundation_z_m'],f['sediment_delta_m'],f['retained_deposit_by_class_m'],f['flow_strength'],strip['old_edge_xyz'])
        spec=replace(spec,support_profile=profile);support_report=profile.report;del f
    contact=prepare_contact(scene,strip,spec=spec)
    movement,roots=move_retained(scene,contact)
    wall=trim_old_wall(scene,spec.bounds_y_m)
    old=ground.data;ground.data=contact['ground_mesh']
    if old.users==0:bpy.data.meshes.remove(old)
    old=road.data;road.data=strip['mesh']
    if old.users==0:bpy.data.meshes.remove(old)
    for key,name in [('wall_mesh','AC supported pavement section'),('particle_mesh','AC anchored subsurface aggregate')]:
        ob=bpy.data.objects.new(name,contact[key]);scene.collection.objects.link(ob)
    report=dict(runoff_support=support_report,strip=strip['report'],contact=contact['report'],old_wall=wall,moved_existing=movement,moved_roots=roots,source_height_sha256=hashlib.sha256(height.read_bytes()).hexdigest(),scene_assigned=True,scope='Actual supported cross-section diagnostic; original material recipe and metric grain scale retained',limits=('Short bank-grade continuation crosses the unsimulated protected collar; it is a geometric interpretation, not an edge deposition ledger. A shallow continuous lip may remain.' if support_report else 'Intermittent erosion sectors and subsurface course thickness are authored regional interpretations, not a surveyed Victorville road.')+' Crop inspection is required; surface support uses exact center contact, full footprint auditing is separate.')
    del field,strip,contact;gc.collect();print('AC_ASSEMBLED',json.dumps(report),flush=True);return report
