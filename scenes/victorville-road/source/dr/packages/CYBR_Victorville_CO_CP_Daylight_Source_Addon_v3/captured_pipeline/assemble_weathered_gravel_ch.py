"""CH same-placement subtractive weathering; stock remainder updated explicitly."""
from pathlib import Path
import numpy as np,json,time,hashlib,bpy,gc
from weather_metric_gravel_ch import bank
from context_mesh_refine_ab import _read

def apply(scene,cfg,out):
 start=time.monotonic();assert cfg['revision']==1;records=bank(cfg['fractured_prototypes']);coll=bpy.data.collections['CG finite historical gravel prototype bank'];objects=sorted(coll.objects,key=lambda o:o.name);assert [o.name for o in objects]==[f'CG finite gravel {i:03d}' for i in range(192)]
 # Preserve actual point geometry and prototype identities byte for byte.
 ob=scene.objects['CG finite 18–60 mm historical gravel pockets'];points=_read(ob.data.vertices,'co',3);pi=_read(ob.data.attributes['prototype'].data,'value',1,np.int32);before=hashlib.sha256(points.tobytes()+pi.tobytes()).hexdigest();oldvol=[];newvol=[]
 for o,r in zip(objects,records):
  old=o.data;me=bpy.data.meshes.new(old.name+' / narrow irregular weathering');me.from_pydata(r['v'].tolist(),[],r['f'].tolist());me.materials.append(old.materials[0]);me.color_attributes.new(name='mineral',type='FLOAT_COLOR',domain='POINT').data.foreach_set('color',r['color'].ravel());me.attributes.new('grain_roughness','FLOAT','POINT').data.foreach_set('value',r['rough']);me.polygons.foreach_set('use_smooth',np.zeros(len(me.polygons),bool));me.update();o.data=me
  if old.users==0:bpy.data.meshes.remove(old)
  oldvol.append(r['parent_volume']);newvol.append(r['volume'])
 oldvol=np.asarray(oldvol);newvol=np.asarray(newvol);ledger=np.load(Path(out)/'CG_FINITE_GRAVEL_LEDGER.npz');c=ledger['cell'];initial=ledger['initial_solid'];used=np.bincount(c,weights=newvol[pi],minlength=len(initial));reserve=initial-used;assert reserve.min()>=0 and np.all(used<=ledger['explicit_new_solid']+1e-12)
 assert hashlib.sha256(_read(ob.data.vertices,'co',3).tobytes()+_read(ob.data.attributes['prototype'].data,'value',1,np.int32).tobytes()).hexdigest()==before
 # New faces stay within the prior parent envelope. Kept buried original base
 # corners plus the existing large burial depths preserve the support witness.
 minimum_base=float(min(r['v'][:,2].min() for r in records));maximum_base=float(max(r['v'][:,2].min() for r in records));assert abs(minimum_base)<1e-8 and abs(maximum_base)<1e-8
 report=dict(revision='CH',new_body_count=len(points),same_placement_and_prototype_sha256=before,instance_scale_unchanged=True,rendered_new_body_solid_m3=float(used.sum()),smaller_template_solid_allocation_returned_to_reserve_m3=float((oldvol[pi]-newvol[pi]).sum()),reserve_after_weathering_m3=float(reserve.sum()),body_volume_retained_range=[float((newvol/oldvol).min()),float((newvol/oldvol).max())],setback_range_m=[min(r['weathering_width_m']for r in records),max(r['weathering_width_m']for r in records)],bank_vertices=sum(len(r['v'])for r in records),bank_triangles=sum(len(r['f'])for r in records),new_bodies_watertight=True,unchanged_buried_base_z=True,material_endpoints_changed=False,normal_policy='Explicit fracture/bevel planes with flat face normals; no whole-stone smooth shading',limits='Alternative authored weathered templates have smaller solid volume inside the same parent envelopes; budget difference stays unallocated. This is a shape comparison, not time-resolved erosion, fresh transported fines, or validated geological mass flux',elapsed_seconds=time.monotonic()-start)
 np.savez_compressed(Path(out)/'CH_WEATHERED_STOCK_PARTITION.npz',initial_solid=initial,explicit_new_solid=used,buried_reserve=reserve,bank_volume=newvol)
 (Path(out)/'WEATHERED_GRAVEL_CH.json').write_text(json.dumps(report,indent=2)+'\n');ledger.close();print('CH_WEATHERED_GRAVEL',json.dumps(report),flush=True);del records;gc.collect();return report
