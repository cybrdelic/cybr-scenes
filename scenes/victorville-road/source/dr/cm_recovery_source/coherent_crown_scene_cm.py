"""CM2: replace woody meshes on frozen CL transforms; prove support before cull.
Recovered from the earlier authored adapter. No root reposition or terrain change.
"""
from pathlib import Path
import json,hashlib,gc
import numpy as np,bpy
import coherent_shrub_cm as bank
from context_mesh_refine_ab import _read,intersecting_triangles
from sample_final_surface_an import PartialSurfaceSampler

def apply(scene,cfg,out):
 assert cfg['revision']==1
 path=Path(cfg['layout']);assert hashlib.sha256(path.read_bytes()).hexdigest()==cfg['layout_sha256'];j=json.loads(path.read_text())
 palette=[bpy.data.materials[n]for n in j['original_palette']]
 coll=bpy.data.collections.new('CM coherent multistem prototypes');scene.collection.children.link(coll);protos={};stats={}
 for k in (1,2,3):
  m=bank.geometry(k,26101020+104729*k);stats[str(k)]=m.cm_stats
  protos[k]=m.object('CM coherent '+bank.SPECS[k].name,coll,palette,{'family':'coherent_shrub_cm','nominal_height_m':bank.SPECS[k].height,**m.cm_stats});del m
 before={};changed=[];roots=[]
 for p in j['placements']:
  ob=scene.objects[p['name']];mw=np.asarray(ob.matrix_world,dtype=np.float32);assert np.array_equal(mw,np.asarray(j['matrices'][ob.name],dtype=np.float32));before[ob.name]=mw.copy()
  k=p['architecture']
  if k==0:continue
  ob.data=protos[k].data;changed.append(ob.name)
  q=_read(ob.data.vertices,'co',3);q=q[(q[:,2]<.026)&(np.linalg.norm(q[:,:2],axis=1)<.14)];assert len(q)>0 and np.isfinite(q).all()
  if len(q)>100:q=q[np.linspace(0,len(q)-1,100,dtype=int)]
  roots.append((ob.name,q@mw[:3,:3].T+mw[:3,3]))
 for n,mw in before.items():assert np.array_equal(np.asarray(scene.objects[n].matrix_world,dtype=np.float32),mw)
 contacts=[]
 for sign in (-1,1):
  ob=scene.objects['Graded shoulder and alluvial plain '+str(sign)];co=_read(ob.data.vertices,'co',3);mw=np.asarray(ob.matrix_world);co=co@mw[:3,:3].T+mw[:3,3];ob.data.calc_loop_triangles();tri=_read(ob.data.loop_triangles,'vertices',3,np.int32)
  for name,q in roots:
   if np.sign(q[:,0].mean())!=sign:continue
   bounds=(q[:,0].min()-.05,q[:,0].max()+.05,q[:,1].min()-.05,q[:,1].max()+.05);ix=intersecting_triangles(co,tri,bounds)
   assert len(ix)>0,('No current terrain under fixed root before culling',name,bounds)
   t=tri[ix];u,iv=np.unique(t,return_inverse=True);sampler=PartialSurfaceSampler(co[u],iv.reshape(-1,3),cell_m=.3,max_triangles=650000,max_bin_entries=2800000,max_query_products=180000)
   z=sampler.height(q[:,:2]);assert np.isfinite(z).all();d=q[:,2]-z;contacts.append({'name':name,'basal_sample_count':len(q),'clearance_min_m':float(d.min()),'clearance_max_m':float(d.max())});del sampler
  del co,tri;gc.collect()
 assert len(contacts)==len(changed)>0
 assert all(r['clearance_min_m']<-.0005 for r in contacts),contacts
 report={'revision':'CM2 pre-cull support witnesses','changed_instances':changed,'changed_count':len(changed),'exact_world_matrices_preserved':True,'low_crown_unchanged':True,'ground_road_mountains_daylight_unchanged':True,'original_material_slot_names':j['original_palette'],'original_leaf_budgets_preserved':list(bank.LEAF_BUDGET),'source_sha256':hashlib.sha256(Path(bank.__file__).read_bytes()).hexdigest(),'prototype_stats':stats,'contact_evaluation_stage':'Complete current terrain after CE/CI, before preview camera culling; no missing-support root is skipped','basal_contact_witnesses':contacts,'limits':'Authored branching, not measured botany. Sparse basal samples witness support, not full woody-body collision. Exact frozen root transforms and terrain stay unchanged.'}
 (Path(out)/'COHERENT_CROWN_CM.json').write_text(json.dumps(report,indent=2)+'\n');print('COHERENT_CROWN_CM',json.dumps({k:v for k,v in report.items()if k not in ['changed_instances','basal_contact_witnesses']}),flush=True);return report
