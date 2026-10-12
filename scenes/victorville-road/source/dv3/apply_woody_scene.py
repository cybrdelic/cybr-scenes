"""DV plant-only adapter after admitted DU5 soil, with strict basal witnesses."""
from pathlib import Path
import bpy,numpy as np,json,hashlib,gc
from woody_form import geometry_from_owner
from wood_surface import install
import coherent_shrub_cm as owner
from context_mesh_refine_ab import intersecting_triangles
from sample_final_surface_an import PartialSurfaceSampler

def read(sequence,name,width=1,dtype='f4'):
 a=np.empty((len(sequence),width),dtype) if width>1 else np.empty(len(sequence),dtype);sequence.foreach_get(name,a.ravel());return a

def digest_mesh(ob):return hashlib.sha256(read(ob.data.vertices,'co',3).tobytes()).hexdigest()

def contact(scene,targets,groups):
 reports=[]
 for sign in (-1,1):
  relevant=[o for o in targets if np.sign(o.matrix_world.translation.x)==sign]
  if not relevant:continue
  ground=scene.objects['Graded shoulder and alluvial plain '+str(sign)];co=read(ground.data.vertices,'co',3);matrix=np.array(ground.matrix_world);co=co@matrix[:3,:3].T+matrix[:3,3];ground.data.calc_loop_triangles();tri=read(ground.data.loop_triangles,'vertices',3,'i4')
  for ob in relevant:
   matrix=np.array(ob.matrix_world);parts=[q@matrix[:3,:3].T+matrix[:3,3] for q in groups];q=np.concatenate(parts);bounds=(q[:,0].min()-.03,q[:,0].max()+.03,q[:,1].min()-.03,q[:,1].max()+.03);ix=intersecting_triangles(co,tri,bounds);local=tri[ix];u,ids=np.unique(local,return_inverse=True)
   sampler=PartialSurfaceSampler(co[u],ids.reshape(-1,3),cell_m=.04,max_triangles=400000,max_bin_entries=1000000,max_query_products=120000)
   for i,part in enumerate(parts):
    heights=sampler.height(part[:,:2]);assert np.isfinite(heights).all(),('Missing current substrate at basal root',ob.name,i)
    clearance=part[:,2]-heights;row={'object':ob.name,'coarse_component':i,'basal_samples':len(part),'clearance_min_m':float(clearance.min()),'clearance_max_m':float(clearance.max()),'all_basal_samples_below_substrate':bool(clearance.max()<-.0002)};reports.append(row)
   del sampler;gc.collect()
  del co,tri;gc.collect()
 return reports

def apply(scene,cfg,out):
 assert cfg['kind']==3 and cfg['revision']==3
 unchanged={o.name:np.array(o.matrix_world).copy() for o in scene.objects};kind=cfg['kind'];targets=[o for o in scene.objects if o.type=='MESH' and o.name.startswith('CK pocket / '+owner.SPECS[kind].name)];assert len(targets)==12
 protected=['Graded shoulder and alluvial plain -1','Graded shoulder and alluvial plain 1','True approved R5D near-camera grain geometry','U approved R5D density / projected chip and grit supplement','CZ current-view original sand instances','AP graded margin / exact metric lag instances','CG finite 18–60 mm historical gravel pockets']
 before={n:digest_mesh(scene.objects[n]) for n in protected};matrices={o.name:np.array(o.matrix_world).tolist() for o in targets};old=targets[0].data;assert all(o.data==old for o in targets);palette=list(old.materials);assert len(palette)==14
 mesh=geometry_from_owner(owner,kind,26101020+104729*kind);assert mesh.leaf_count==owner.LEAF_BUDGET[kind]
 support=contact(scene,targets,mesh.dv_basal_groups)
 report={'candidate':'DV3 plant-only native crop','prototype_stats':mesh.cm_stats,'target_instances':list(matrices),'instance_matrices':matrices,'root_support':support,'soil_and_five_grain_banks_before':before,'no_clast_candidate_installed':True,'new_mineral_stock_m3':0.}
 Path(out,'DV_ROOT_PREFLIGHT.json').write_text(json.dumps(report,indent=2)+'\n')
 assert all(r['all_basal_samples_below_substrate'] for r in support), 'A basal component is not continuously supported; stop before rendering'
 collection=bpy.data.collections.new('DV shared drought-thinned morphology');scene.collection.children.link(collection);prototype=mesh.object('DV shared '+owner.SPECS[kind].name,collection,palette,{'family':'DV woody form','nominal_height_m':owner.SPECS[kind].height,**mesh.cm_stats});bark=palette[0].copy();bark.name='DV original procedural bark / '+palette[0].name;prototype.data.materials[0]=bark;report['bark']=install(bark,cfg)
 for ob in targets:ob.data=prototype.data
 after={n:digest_mesh(scene.objects[n]) for n in protected};assert before==after
 assert all(np.array_equal(np.array(scene.objects[n].matrix_world),m) for n,m in unchanged.items())
 report.update({'soil_and_five_grain_banks_byte_exact':True,'all_existing_object_matrices_byte_exact':True,'shared_prototype_users':prototype.data.users,'current_terrain_root_support_passed':True,'source_sha256':{n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ['apply_woody_scene.py','woody_form.py','wood_surface.py']},'limits':['Only the drought-thinned existing prototype changes; other species remain unchanged.','Coarse wood is closed/fused; fine tube attachments are inherited geometric overlaps.','Basal lowest-surface samples are checked on current substrate; this is not a full soil/root/grain collision simulation.']})
 Path(out,'DV_GEOMETRY.json').write_text(json.dumps(report,indent=2)+'\n');print('DV_GEOMETRY_PASS',json.dumps({'instances':len(targets),'coarse_components':len(mesh.dv_basal_groups),'root_witnesses':len(support),'vertices':len(mesh.vertices)}),flush=True)
 return report
