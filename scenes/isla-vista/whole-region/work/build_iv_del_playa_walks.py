"""Restore source-aligned sidewalk continuity across local service driveways.

A bounded105m interval; common terrain triangles, closed construction edges.
Width, curb/apron rise and panel dimensions are explicit estimates. Native
terrain, main carriageways, mapped buildings and all-IV coverage remain.
"""
from pathlib import Path
import sys,json,numpy as np,hashlib,re
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
import shapely
from shapely.geometry import shape,box,Point
from shapely.ops import unary_union
from scipy.ndimage import gaussian_filter
from cybr_ucsb.geometry import triangulate_polygon
from iv_mesh_parts import Parts
out=r/'evidence/full-iv-del-playa-walks';out.mkdir(exist_ok=True);base=r/'evidence/full-iv-roofs';features=json.loads((base/'normalized.geojson').read_text())['features'];byid={f['id']:f for f in features};roi=box(270,-420,375,-320);path_ids=['osm:way:553000025','osm:way:587045863'];lines=[shape(byid[i]['geometry']).intersection(roi) for i in path_ids];walks=unary_union([p.buffer(.9,cap_style='flat',join_style='round') for p in lines]);drivers=[];major=[];buildings=[]
for f in features:
 p=f['properties'];g=shape(f['geometry'])
 if not roi.buffer(8).intersects(g):continue
 if p['category']=='building':buildings.append(g)
 if p['category']=='road':
  props=p['source_properties'];kind=props.get('highway');width=4 if kind=='service' else 7 if kind in {'residential','unclassified'} else 6
  try:width=float(props.get('width',width))
  except (TypeError,ValueError):pass
  if props.get('service')=='driveway':drivers.append((f['id'],g.buffer(width/2,cap_style='flat',join_style='round')))
  else:major.append(g.buffer(width/2,cap_style='flat',join_style='round'))
road=unary_union([g for _,g in drivers]);walks=walks.difference(unary_union(major)).difference(unary_union(buildings));lost=walks.intersection(road);state=np.load(base/'measured-terrain-state.npz');meta=json.loads(str(state['metadata']));n=meta['config']['grid'];extent=meta['config']['extent'];dx=extent/(n-1);z=state['foundation']+state['thickness'].sum(axis=0);rng=np.random.default_rng(meta['config']['seed']+19);fields=[]
for sigma in [.75,2.2,6]:a=gaussian_filter(rng.normal(size=(n,n)),sigma);a/=max(a.std(),1e-9);fields.append(a)
rough,medium,coarse=fields;amp=min(max(meta['layers'][0]['grain_scale']*.30,.008),dx*.20);display=z+(.54*rough+.30*medium+.16*coarse-.14*np.maximum(rough,0)**2)*amp
axis=np.linspace(-extent/2,extent/2,n)
def terrain(p):
 p=np.asarray(p);q=np.clip((p+extent/2)/dx,0,n-1-1e-9);ix=np.floor(q[:,0]).astype(int);iy=np.floor(q[:,1]).astype(int);tx=q[:,0]-ix;ty=q[:,1]-iy;a=display[iy,ix];b=display[iy,ix+1];c=display[iy+1,ix+1];d=display[iy+1,ix];return np.where(ty<=tx,(1-tx)*a+(tx-ty)*b+ty*c,(1-ty)*a+tx*c+(ty-tx)*d)
def offset(p):
 dist=shapely.distance(shapely.points(p),road);t=np.clip(dist/1.2,0,1);rise=.045+.100*t*t*(3-2*t)
 #Five millimetres above the retained path at the bounded end transitions.
 end=np.minimum(np.asarray(p)[:,0]-270,375-np.asarray(p)[:,0]);blend=np.clip(end/1.5,0,1);old=.023+.122*t*t*(3-2*t);return old*(1-blend)+rise*blend
#Panel joints are authored construction detail, not mapped/as-built features.
joint_polys=[]
for line in lines:
 for distance in np.arange(1.5,line.length,1.5):
  a=np.array(line.interpolate(distance).coords[0]);t=np.array(line.interpolate(min(line.length,distance+.02)).coords[0])-np.array(line.interpolate(max(0,distance-.02)).coords[0]);t/=np.linalg.norm(t);v=np.array([-t[1],t[0]]);joint_polys.append(shapely.LineString([a-v,a+v]).buffer(.003,cap_style='flat'))
joints=unary_union(joint_polys).intersection(walks);reference_line=lines[0];tangent=np.asarray(reference_line.interpolate(reference_line.length).coords[0])-np.asarray(reference_line.interpolate(0).coords[0]);tangent/=np.linalg.norm(tangent);across=np.array([-tangent[1],tangent[0]])
def top_uv(v):return np.c_[v[:,:2]@across,v[:,:2]@tangent]/1.25
surfaces=[('walk',walks.difference(joints),186,0.),('joint',joints,185,-.004)];parts=Parts(out/'walks.clm',13000000);areas=[];b=walks.bounds;lo=np.floor((np.array(b[:2])+extent/2)/dx).astype(int)-1;hi=np.ceil((np.array(b[2:])+extent/2)/dx).astype(int)+1
for name,area,mat,recess in surfaces:
 chunks=[];totalarea=0.
 for iy in range(max(0,lo[1]),min(n-1,hi[1])):
  for ix in range(max(0,lo[0]),min(n-1,hi[0])):
   q=np.array([[axis[ix],axis[iy]],[axis[ix+1],axis[iy]],[axis[ix+1],axis[iy+1]],[axis[ix],axis[iy+1]]])
   for ids in [[0,1,2],[0,2,3]]:
    clipped=shapely.Polygon(q[ids]).intersection(area)
    for p in (clipped.geoms if hasattr(clipped,'geoms') else [clipped]):
     if p.geom_type!='Polygon' or p.area<1e-8:continue
     xy,f=triangulate_polygon(p,max_edge=.75);vv=np.c_[xy,terrain(xy)+offset(xy)+recess];chunks.append(vv[f]);totalarea+=p.area
 tris=np.concatenate(chunks);v=tris.reshape(-1,3);parts.mesh(name+'_shared_TIN',v,np.arange(len(v)).reshape(-1,3),mat,','.join(path_ids),'Mapped alignments and retained1.8m estimated width; apron and panel dimensions authored',uv=top_uv(v),uv_period=.256,drop_zero_projected_area=True);areas.append({'name':name,'area_m2':area.area,'triangulated_xy_area_m2':totalarea});assert abs(totalarea-area.area)<1e-5
#Close outside edges into common terrain. Panels share this outer slab body.
v=[];f=[];uv=[];arc=0.
for p in (walks.geoms if hasattr(walks,'geoms') else [walks]):
 if p.geom_type!='Polygon':continue
 for ring in [p.exterior,*p.interiors]:
  xy=np.asarray(shapely.segmentize(shapely.LineString(ring.coords),.5).coords);bottom=terrain(xy)-.04;top=terrain(xy)+offset(xy)
  for k in range(len(xy)-1):
   length=np.linalg.norm(xy[k+1]-xy[k]);j=len(v);v.extend([[*xy[k],bottom[k]],[*xy[k+1],bottom[k+1]],[*xy[k+1],top[k+1]],[*xy[k],top[k]]]);f.extend([[j,j+1,j+2],[j,j+2,j+3]]);uv.extend([[arc/1.25,bottom[k]/1.25],[(arc+length)/1.25,bottom[k+1]/1.25],[(arc+length)/1.25,top[k+1]/1.25],[arc/1.25,top[k]/1.25]]);arc+=length
parts.mesh('closed_construction_edges',v,f,185,','.join(path_ids),'Slab body terminates40mm below common terrain; profile is estimated',uv=uv,uv_period=.256)
report=parts.close();source_material=r/'evidence/full-iv-street-materials/materials.cys';lines=[]
for line in source_material.read_text().splitlines():
 if line.startswith('#'):continue
 line=re.sub(r'"([^"]+)"',lambda m:json.dumps(str((source_material.parent/m[1]).resolve())),line);tokens=line.split()
 if tokens[0] in {'texture','roughness_texture','nested','metric_bump'}:tokens[1]=str(int(tokens[1])+113)
 if tokens[0]=='nested':tokens[2]=str(int(tokens[2])+113)
 lines.append(' '.join(tokens))
(out/'materials.cys').write_text('\n'.join(lines)+'\n');report.update(material_offset=185,material_count=2,source_sidewalk_ids=path_ids,source_driveway_ids=[i for i,_ in drivers],bounded_xy=[270,-420,375,-320],retained_estimated_walk_width_m=1.8,brush_U_world_direction=across.tolist(),longitudinal_V_world_direction=tangent.tolist(),walk_area_m2=walks.area,restored_driveway_crossing_area_m2=lost.area,original_priority_error='Road category combined main streets and service driveways and removed sidewalk at every driveway crossing.',construction={'ordinary_slab_rise_m':.145,'driveway_apron_rise_m':.045,'transition_length_m':1.2,'boundary_fade_m':1.5,'body_bottom_below_common_terrain_m':.04,'joint_pitch_m':1.5,'joint_width_m':.006,'joint_recess_m':.004},top_area_checks=areas,terrain_state_sha256=hashlib.sha256((base/'measured-terrain-state.npz').read_bytes()).hexdigest(),material_basis='Existing original merged CYBR MATERIALS31_concrete_brushed recipe, retained0.32m physical tile and full metre-valued relief; material IDs shifted only.',limits='Bounded authored sidewalk construction, not survey or accessibility/design compliance. Source alignments/width estimates preserved. Underlying old paving remains enclosed beneath this slab; this is not terrain replacement or a floating plane.')
(out/'WALKS_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'triangles':report['triangles'],'parts':len(report['parts']),'walk_area_m2':walks.area,'restored_crossing_area_m2':lost.area}),flush=True)
