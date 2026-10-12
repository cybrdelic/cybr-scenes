"""Restore retained roof tags without assigning unsourced neighbourhood colours.

Direct roof-colour tags change only the roof finish. Nested UCSB/OSM roof-shape
tags transfer only after the independent footprint-overlap audit passes.
"""
from pathlib import Path
import sys,json,struct,hashlib,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
import shapely
from shapely.ops import split
from scipy.optimize import lsq_linear
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import DEM,polygons,metres
from cybr_ucsb.geometry import triangulate_polygon,optical_atlas
from cybr_light import Scene
from cybr_light.runtime import read_pfm
from cybr_terrain.materials import write_pfm
from iv_mesh_parts import Parts
out=r/'evidence/full-iv-sourced-roofs';out.mkdir(exist_ok=True);base=r/'evidence/full-iv-roofs';features=json.loads((base/'normalized.geojson').read_text())['features'];features={f['id']:f for f in features if f['properties']['category']=='building'}
layout=json.loads((base/'glb-part-layout.json').read_text());parts_by_name={p['part']:p['component'] for b in layout.values() for p in b['parts']};audit=json.loads((r/'evidence/full-iv-roof-provenance/NESTED_ROOF_MATCH_AUDIT.json').read_text());accepted={x['target_id']:x for x in audit['rows'] if x['accepted']}
special=set()
for folder,receipt in [('full-iv-house-component','COMPONENT_RECEIPT.json'),('full-iv-pardall','PARDALL_RECEIPT.json')]:special.update(json.loads((r/'evidence'/folder/receipt).read_text())['replace_sector_components'])
facades=json.loads((r/'evidence/full-iv-facades/FACADE_RECEIPT.json').read_text());facade_kind={x['source_id']:x['type'] for x in facades['buildings']};wall_material={k:facades['material_offset']+i*2+1 for i,k in enumerate(['house','apartment','commercial','institution','unspecified'])}
water=json.loads((r/'evidence/full-iv-coastal-water/WATER_RECEIPT.json').read_text());offset=water['material_offset']+water['material_count'];s=Scene();s.materials=offset
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.array(day['native_basis_to_linear_rgb']);white=M@np.ones(3);inverse=np.linalg.inv(M)
def native(rgb):return np.asarray(rgb)*white@inverse.T
atlas=optical_atlas('roof-membrane',(.29,.28,.25),.84,.00055,out/'textures',256);assert np.array_equal(atlas.albedo,read_pfm(base/'textures/roof-membrane_color.pfm'))
height_path=out/'textures/retained_roof_height_metres.pfm';write_pfm(height_path,np.repeat(atlas.height[:,:,None],3,axis=2));variation=atlas.albedo/np.array([.29,.28,.25]);palette={};palette_records={}
def roof_material(tag):
 if not tag:return 5
 key=str(tag).strip().lower()
 if key in palette:return palette[key]
 names={'white':'#ffffff','grey':'#808080','gray':'#808080','silver':'#c0c0c0','brown':'#805b40','red':'#a64b37','black':'#242424'};value=names.get(key,key)
 if not (len(value)==7 and value.startswith('#')):raise ValueError('Unrecognized sourced roof colour '+key)
 rgb=np.array([int(value[j:j+2],16)/255 for j in [1,3,5]]);linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
 # A colour tag is not a calibrated reflectance. Limit the brightest authored
 # diffuse finish to .78 while preserving hue and procedural field correlation.
 target=linear*min(1,.78/max(float(linear.max()),1e-8));scalar=variation.mean(axis=2);fit=lsq_linear(M/white[:,None],target,bounds=(0,.95/float(scalar.max())),tol=1e-12);assert fit.success;controls=scalar[...,None]*fit.x;assert controls.min()>=0 and controls.max()<=1;matched=(M@fit.x)/white
 path=out/'textures'/('roof_colour_'+hashlib.sha256(key.encode()).hexdigest()[:10]+'.pfm');write_pfm(path,controls.astype('f4'))
 a=s.material('plastic',(1,1,1),.84,ior=1.5,texture=path);s.emit('roughness_texture',a,json.dumps(str(atlas.roughness_pfm.resolve())),1,1,1);b=s.material('bumpmap',texture=height_path);s.emit('nested',b,a,-1,.5);s.emit('metric_bump',b);palette[key]=b;palette_records[key]={'native_material':b,'source_colour_tag':tag,'sRGB_interpretation':value,'authored_target_linear_rgb':target.tolist(),'bounded_native_controls':fit.x.tolist(),'matched_linear_rgb':matched.tolist(),'max_gamut_fit_error_linear_rgb':float(np.max(abs(matched-target))),'source_is_measured_reflectance':False};return b
direct={};copy_objects={};replacements=[];records=[]
for id_,f in features.items():
 props=f['properties']['source_properties'];colour=props.get('roof:colour',props.get('roof:color'))
 if not colour:continue
 stem=id_.replace(':','_')+'_';roof_objects=[ob for name,ob in parts_by_name.items() if name.startswith(stem) and (name.endswith('_roof') or '_roof_tagged_' in name)]
 if not roof_objects or any(ob in special for ob in roof_objects):continue
 material=roof_material(colour);direct[id_]=roof_objects
 for ob in roof_objects:copy_objects[ob]=(id_,material)
 replacements.extend(roof_objects);records.append({'source_id':id_,'operation':'Retained roof geometry with sourced colour and existing correlated surface fields','source_colour':colour,'source_roof_material':props.get('roof:material'),'old_components':roof_objects})
parts=Parts(out/'roofs.clm',9000000);dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')]);buffers={};positions={};before_digest=hashlib.sha256();after_digest=hashlib.sha256();flat_roof_objects={};copied_new_objects=set()
for id_,row in accepted.items():
 stem=id_.replace(':','_')+'_';obs=[ob for name,ob in parts_by_name.items() if name.startswith(stem) and name.endswith('_roof')]
 assert obs and not any(ob in special for ob in obs)
 for ob in obs:flat_roof_objects[ob]=id_
with (base/'sector.clm').open('rb') as stream:
 magic,total,packets=struct.unpack('<4sQI',stream.read(16));assert magic==b'CLM1'
 for _ in range(packets):
  nv,nt=struct.unpack('<HH',stream.read(4));v=np.frombuffer(stream.read(nv*44),'<f4').reshape(nv,11);t=np.frombuffer(stream.read(nt*11),dtype)
  for ob in np.intersect1d(np.unique(t['object']),list(copy_objects.keys())+list(flat_roof_objects.keys())):
   mask=t['object']==ob;q=v[t['indices'][mask]]
   if ob in flat_roof_objects:positions.setdefault(int(ob),[]).append(q[:,:,:3].copy())
   if ob in copy_objects:buffers.setdefault(int(ob),[]).append(q.copy())
 assert not stream.read(1)
copied_triangles=0
for ob,chunks in buffers.items():
 id_,material=copy_objects[ob];q=np.concatenate(chunks);vv=q[:,:,:3].reshape(-1,3);before_digest.update(vv.astype('<f4').tobytes());raw=np.zeros((len(q),36),'<f4');raw[:,:9]=q[:,:,:3].reshape(-1,9);raw[:,9:18]=q[:,:,3:6].reshape(-1,9);raw[:,18]=material;raw[:,19]=parts.object;uv=q[:,:,:2].astype(float)/1.25;uv-=np.floor(uv[:,:1,:]);raw[:,20:26]=uv.reshape(-1,6);raw[:,26:35]=q[:,:,8:11].reshape(-1,9);parts.writer.add(raw);parts.parts.append({'object':parts.object,'name':id_.replace(':','_')+'_retained_roof_'+str(ob),'source':id_,'estimated':'Retained serialized roof positions and normals; sourced colour; metric scalar-height transport','triangles':len(q)});copied_new_objects.add(parts.object);parts.object+=1;copied_triangles+=len(q)
sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);dem=DEM(r/'data/full-iv-20261011/dem.tif',sector.frame);restored=[]
for id_,row in accepted.items():
 f=features[id_];props=f['properties']['source_properties'];tags=row['retained_roof_tags'];kind=row['roof_shape'];polyall=shapely.geometry.shape(f['geometry']);material=roof_material(tags.get('roof:colour',tags.get('roof:color')));old=[ob for ob,source in flat_roof_objects.items() if source==id_];replacements.extend(old)
 assert not props['height_method'].startswith('explicit'), 'A supplied total height requires a separate wall/eave reconstruction.'
 for index,poly in enumerate(polygons(polyall)):
  if poly.area<2:continue
  rect=np.asarray(poly.minimum_rotated_rectangle.exterior.coords)[:4,:2];edges=np.roll(rect,-1,axis=0)-rect;u=edges[np.argmax(np.linalg.norm(edges,axis=1))];u/=np.linalg.norm(u);v=np.array([-u[1],u[0]])
  if tags.get('roof:orientation')=='across':u,v=v,-u
  center=rect.mean(0);hu=max(abs((rect-center)@u));hv=max(abs((rect-center)@v));rise=metres(tags.get('roof:height')) or min(3.2,max(.65,hv*.38));xy,unused=triangulate_polygon(poly);datum=float(np.median(dem.sample(xy[:,0],xy[:,1]))+props['height_m'])
  # Confirm the reconstructed base datum against the retained serialized roof.
  candidates=[np.concatenate(positions[ob]) for ob in old if ob in positions];allq=np.concatenate(candidates).reshape(-1,3);near=shapely.intersects_xy(poly.buffer(.001),allq[:,0],allq[:,1]);assert near.any();stored_datum=float(np.median(allq[near,2]));assert abs(stored_datum-datum)<.001;datum=stored_datum
  def z(p):
   a=(p-center)@u;b=(p-center)@v;h=1-abs(b)/hv if kind=='gabled' else np.minimum(hu-abs(a),hv-abs(b))/hv
   return datum+rise*np.clip(h,0,1)
  span=max(hu,hv)*4+4
  def line(origin,direction):return shapely.LineString([origin-direction*span,origin+direction*span])
  cuts=[line(center,u)]
  if kind=='hipped':
   cuts.append(line(center,v))
   for su in [-1,1]:
    for sv in [-1,1]:
     corner=center+u*hu*su+v*hv*sv;ridge=center+u*(hu-hv)*su;delta=ridge-corner;cuts.append(line(corner,delta/np.linalg.norm(delta)))
  pieces=[poly]
  for cutter in cuts:pieces=[q for p in pieces for q in split(p,cutter).geoms if q.area>1e-8]
  projected=0.
  for j,p in enumerate(pieces):
   xy,ff=triangulate_polygon(p);projected+=p.area;parts.mesh(id_.replace(':','_')+f'_restored_roof_{index}_{j}',np.c_[xy,z(xy)],ff,material,id_,'Nested roof shape accepted after independent footprint audit; pitch/ridge orientation partly estimated',uv_period=1.,drop_zero_projected_area=True)
  assert abs(projected-poly.area)<1e-5
  wall=wall_material.get(facade_kind.get(id_),3)
  for ringindex,ring in enumerate([poly.exterior,*poly.interiors]):
   q=np.asarray(ring.coords)[:,:2]
   for j,(a,b) in enumerate(zip(q[:-1],q[1:])):
    sample=np.vstack([a,b]);da,db=(sample-center)@v
    if kind=='gabled' and da*db<0:sample=np.vstack([a,a+(b-a)*(-da/(db-da)),b])
    for k,(aa,bb) in enumerate(zip(sample[:-1],sample[1:])):
     top=z(np.vstack([aa,bb]));vv=np.array([[*aa,datum],[*bb,datum],[*bb,top[1]],[*aa,top[0]]]);length=np.linalg.norm(bb-aa);uv=np.array([[0,datum],[length,datum],[length,top[1]],[0,top[0]]])/1.25;parts.mesh(id_.replace(':','_')+f'_gable_fill_{index}_{ringindex}_{j}_{k}',vv,[[0,1,2],[0,2,3]],wall,id_,'Estimated roof-following end wall above retained floor-count wall height',uv=uv)
  restored.append({'source_id':id_,'matched_osm_id':row['source_id'],'shape_tag':kind,'source_overlap_fraction':row['source_overlap_fraction'],'target_overlap_fraction':row['target_overlap_fraction'],'source_colour':tags.get('roof:colour'),'source_material':tags.get('roof:material'),'roof_rise_m':rise,'rise_basis':'roof:height tag' if tags.get('roof:height') else 'Estimated0.38 slope with0.65–3.2m rise bound','eave_z_from_retained_geometry_m':datum,'projected_footprint_m2':poly.area,'roof_projected_area_m2':projected,'floor_count_wall_height_m':props['height_m']})
report=parts.close();s.save(out/'materials.cys');assert len(replacements)==len(set(replacements))
with (out/'roofs.clm').open('rb') as stream:
 magic,total,packets=struct.unpack('<4sQI',stream.read(16));assert magic==b'CLM1'
 for _ in range(packets):
  nv,nt=struct.unpack('<HH',stream.read(4));v=np.frombuffer(stream.read(nv*44),'<f4').reshape(nv,11);t=np.frombuffer(stream.read(nt*11),dtype);mask=np.isin(t['object'],list(copied_new_objects))
  if np.any(mask):after_digest.update(v[t['indices'][mask],:3].astype('<f4').tobytes())
 assert not stream.read(1)
assert before_digest.digest()==after_digest.digest(),'Serialized recoloured roof positions changed.'
report.update(material_offset=offset,material_count=s.materials-offset,replace_sector_components=replacements,direct_coloured_buildings=len(direct),copied_roof_triangles=copied_triangles,copied_position_sha256=before_digest.hexdigest(),copied_positions_unchanged=before_digest.digest()==after_digest.digest(),direct_colour_records=records,restored_nested_roofs=restored,palette=palette_records,surface_contract='The retained original CYBR roof optical field is regenerated exactly, with linked color variation, roughness and full scalar physical height. Colour tags supply visual targets, decoded once from authored sRGB. Bright diffuse targets are capped at0.78 and local fields at0.95; neither is measured local reflectance. Metric height replaces the old tangent-normal approximation on recoloured roofs.',limits='Source tags do not establish current measured reflectance or exact roof construction. A colour called silver is not assumed to prove metal. Nested shape transfers require at least90% overlap of both footprints. Existing floor-count wall heights remain; missing pitch, ridge topology and end-wall finish remain authored estimates. No untagged roof types or colours assigned; individual reference components preserved.')
(out/'SOURCED_ROOFS_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print('SOURCED_ROOFS',json.dumps({'triangles':report['triangles'],'direct_colour_buildings':len(direct),'nested_roof_components':len(restored),'replaced_base_components':len(replacements)}),flush=True)
