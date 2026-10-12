"""DA: same CZ sand bodies/XY/materials, original measured fine-bed relative datum."""
from pathlib import Path
import hashlib,json
import numpy as np

def apply(scene,cfg,out):
 from approved_density_lod import VERIFIED_BANK_IDS
 raw=Path(cfg['datums']).read_bytes();assert hashlib.sha256(raw).hexdigest()==cfg['datums_sha256'];src=json.loads(raw);record={r['source_id']:r for r in src['records']};sand=json.loads(Path(cfg['sand_bank']).read_text());sand_ids=[p['source_id']for p in sand['particles']];rows=[]
 for name,ids in [('CZ current-view original sand instances',sand_ids)]:
  ob=scene.objects[name];me=ob.data;co=np.empty((len(me.vertices),3),'f4');me.vertices.foreach_get('co',co.ravel());pi=np.empty(len(co),'i4');me.attributes['prototype'].data.foreach_get('value',pi);yaw=np.empty((len(co),3),'f4');me.attributes['yaw'].data.foreach_get('vector',yaw.ravel());before=hashlib.sha256(co[:,:2].tobytes()+pi.tobytes()+yaw.tobytes()).hexdigest();offset=np.array([record[k]['bed_reference_offset_m']for k in ids]);assert np.all(offset>=0)and np.max(offset)<.0003
  after=co.copy();after[:,2]=(co[:,2].astype(float)-offset[pi]).astype('f4');me.vertices.foreach_set('co',after.ravel());me.update();assert np.array_equal(after[:,:2],co[:,:2]);error=float(np.max(abs((co[:,2].astype(float)-after[:,2])-offset[pi]),initial=0));assert error<1e-7
  tops=np.array([record[k]['before_top_m']for k in ids]);rows.append(dict(object=name,count=len(co),identity_XY_prototype_yaw_sha256=before,z_shift_um_min_median_max=(np.quantile(offset[pi],[0,.5,1])*1e6).tolist(),maximum_stored_coordinate_error_m=error,reference_plane_fully_buried_instances_before=int(np.sum(tops[pi]<=0)),reference_plane_fully_buried_instances_after=int(np.sum((tops-offset)[pi]<=0)),prototype_geometry_material_scale_unchanged=True))
 rec=dict(revision='DA source-bed datum',objects=rows,original_microbed_sha256=src['microbed_sha256'],datum_source_sha256=cfg['datums_sha256'],terrain_materials_light_camera_unchanged=True,older_chip_grit_and_coarse_geometry_unchanged=True,body_count_volume_and_XY_unchanged=True,limits=['Pointwise original-bed reference-plane correction. The road microbed is still normal-only and this is not exact original footprint occlusion.','Original grain bodies become more embedded; no body enlargement, brightness change, blur or sediment-transport claim.','Source colour/mineral coating remains unchanged. Existing coarse-body shadow issue is unrelated.']);(Path(out)/'SOURCE_RELATIVE_BURIAL_DA.json').write_text(json.dumps(rec,indent=2)+'\n');print('DA_BURIAL',json.dumps(rec),flush=True);return rec
