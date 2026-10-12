"""Explicit near-street botanical geometry, preserving mapped source positions.

Pinnate architecture on family-only palms is an illustrative assumption. Fan
leaves are used only where the retained genus supports that form. Blade area,
branch architecture and leaf dimensions are authored, not surveyed biomass.
"""
from pathlib import Path
import sys,json,hashlib,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
import shapely
from shapely.ops import substring
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import DEM,metres
from cybr_ucsb.geometry import stable_seed
from iv_mesh_parts import Parts,leaf_mesh
base=r/'evidence/full-iv-roofs';out=r/'evidence/full-iv-near-street-vegetation';out.mkdir(exist_ok=True)
features=json.loads((base/'normalized.geojson').read_text())['features'];by_id={f['id']:f for f in features};layout=json.loads((base/'glb-part-layout.json').read_text());partmap={p['part']:p['component'] for b in layout.values() for p in b['parts']}
prior=json.loads((r/'evidence/full-iv-botanical-dense/BOTANICAL_RECEIPT.json').read_text());prior_features={f['source_id']:f for f in prior['features']};prior_replacements=set(prior['replace_sector_components'])
road=shapely.geometry.shape(by_id['osm:way:50978848']['geometry']);corridor=substring(road,310,610).buffer(42,cap_style='round')
sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);dem=DEM(r/'data/full-iv-20261011/dem.tif',sector.frame)
parts=Parts(out/'vegetation.clm',10000000);records=[];base_skip=[];previous_skip=[]
# Reuse the exact existing native leaf reflection/transmission and bark controls.
trunk=prior['material_offset'];leaf=trunk+3
palms={'Syagrus','Phoenix','Washingtonia','Howea','Butia','Chamaerops','Archontophoenix'};fans={'Washingtonia','Chamaerops'}
leaf_area_total=0.;leaf_count=0;attachment_error=0.;all_positions=[]
def curved_blades(roots,axes,lengths,widths,rolls,bends):
 roots=np.asarray(roots);axes=np.asarray(axes);axes/=np.linalg.norm(axes,axis=1,keepdims=True);up=np.tile([0.,0.,1.],(len(axes),1));up[abs(axes[:,2])>.96]=[1,0,0];side=np.cross(axes,up);side/=np.linalg.norm(side,axis=1,keepdims=True);normal=np.cross(side,axes);side=side*np.cos(rolls)[:,None]+normal*np.sin(rolls)[:,None];normal=np.cross(side,axes)
 t=np.linspace(0,1,5);mid=roots[:,None,:]+axes[:,None,:]*lengths[:,None,None]*t[None,:,None]+normal[:,None,:]*bends[:,None,None]*t[None,:,None]**2
 width=np.maximum(.025,np.sin(np.pi*t)**.72);vv=[]
 for j in range(len(t)):
  ridge=normal*width[j]*widths[:,None]*.13;spread=side*width[j]*widths[:,None]*.5
  vv.extend([mid[:,j]-spread,mid[:,j]+ridge,mid[:,j]+spread])
 v=np.stack(vv,axis=1);local=[]
 for j in range(4):
  a=j*3;b=(j+1)*3;local.extend([[a,a+1,b+1],[a,b+1,b],[a+1,a+2,b+2],[a+1,b+2,b+1]])
 f=(np.asarray(local)[None]+np.arange(len(roots))[:,None,None]*15).reshape(-1,3);v=v.reshape(-1,3)
 global attachment_error
 attachment_error=max(attachment_error,float(np.max(np.linalg.norm(v.reshape(-1,15,3)[:,0:3].mean(1)-roots,axis=1))))
 return v,f

def write_leaves(name,v,f,source,estimate):
 global leaf_area_total,leaf_count
 t=v[f];area=float((np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)*.5).sum());leaf_area_total+=area
 parts.mesh(name,v,f,leaf,source,estimate)
 return area
for feature in features:
 if feature['geometry']['type']!='Point' or feature['properties']['category'] not in {'tree','vegetation'}:continue
 props=feature['properties']['source_properties'];genus=str(props.get('genus','')).strip();family=str(props.get('taxon:family','')).strip();xy=np.asarray(feature['geometry']['coordinates']);near=corridor.covers(shapely.Point(xy));is_palm=family in {'Arecaceae','Arecacea'} or genus in palms
 if not near and genus not in fans:continue
 source=feature['id'];stem=source.replace(':','_');old=[partmap[n] for n in [stem+'_trunk',stem+'_crown',stem+'_fronds'] if n in partmap]
 if not old:continue
 supplied=metres(props.get('height'));rng0=np.random.default_rng(stable_seed(source));baseline_height=supplied or (11 if genus in palms else 14 if genus in {'Pinus','Eucalyptus','Corymbia'} else 7.5)*rng0.uniform(.8,1.15)
 height=prior_features.get(source,{}).get('height_m',baseline_height);rng=np.random.default_rng(int.from_bytes(hashlib.sha256((source+':near-street-v1').encode()).digest()[:8],'little'));origin=np.r_[xy,float(dem.sample(*xy))]
 base_skip.extend(x for x in old if x not in prior_replacements);previous_skip.extend(p['object'] for p in prior['parts'] if p['source']==source)
 estimate='Source point and supplied taxonomy retained; previous height retained. Branches, blade dimensions and leaf area are authored estimates.';start=parts.writer.triangles;area_before=leaf_area_total
 if is_palm:
  radius=height*.024
  for k in range(8):
   a=origin+np.array([.10*np.sin(k*.33),.07*np.sin(k*.26),height*.90*k/8]);b=origin+np.array([.10*np.sin((k+1)*.33),.07*np.sin((k+1)*.26),height*.90*(k+1)/8]);parts.tube(stem+f'_trunk{k}',a,b,radius*(1-.25*k/8),radius*(1-.25*(k+1)/8),trunk,source,estimate,14)
  crown=origin+np.array([.09,.07,height*.9]);root_list=[];axes=[];lengths=[];widths=[];rolls=[];bends=[]
  if genus in fans:
   for j in range(30):
    az=j*2.39996323+rng.uniform(-.12,.12);elev=np.interp((j+.5)/30,[0,1],[1.15,-.75]);radial=np.array([np.cos(az),np.sin(az),0.]);axis=radial*np.cos(elev)+np.array([0,0,np.sin(elev)]);side=np.array([-radial[1],radial[0],0]);normal=np.cross(side,axis)
    petiole=max(.6,min(1.6,height*.12));hub=crown+axis*petiole;parts.tube(stem+f'_petiole{j}',crown,hub,.035,.016,trunk,source,estimate,6);fan_radius=max(.48,min(1.2,height*.095));v=[];f=[];sectors=36;angles=np.linspace(-1.25,1.25,sectors+1)
    # Basally joined fan with split, folded distal lobes. All lobes remain
    # attached to one petiole rather than detached triangular leaf cards.
    for k in range(sectors):
     aa,bb=angles[k:k+2];mm=(aa+bb)/2;startv=len(v)
     def point(angle,t,ridge=0):return hub+(axis*np.cos(angle)+side*np.sin(angle))*fan_radius*t+normal*(.15*fan_radius*t*t+ridge)
     v.extend([hub,point(aa,.48),point(mm,.53,.018),point(bb,.48),point(aa,.95),point(mm,1.0,.022),point(bb,.95)])
     f.extend((np.array([[0,1,2],[0,2,3],[1,4,5],[1,5,2],[2,5,6],[2,6,3]])+startv).tolist())
    v=np.asarray(v);f=np.asarray(f);write_leaves(stem+f'_fan{j}',v,f,source,estimate);leaf_count+=1
   form='Source-genus fan architecture with basally connected folded segments'
  else:
   for j in range(30):
    angle=j*2.39996323+rng.uniform(-.10,.10);axis=np.array([np.cos(angle),np.sin(angle),0]);side=np.array([-axis[1],axis[0],0]);reach=height*rng.uniform(.23,.31);age=(j+.5)/30;lift=np.interp(age,[0,1],[reach*.9,reach*.12]);drop=np.interp(age,[0,1],[reach*.18,reach*.90])
    def frond(t):return crown+axis*reach*t+np.array([0,0,lift*np.sin(np.pi*t*.72)-drop*t*t])
    p0=frond(0)
    for k,t in enumerate(np.linspace(.1,1,10)):
     p1=frond(t);parts.tube(stem+f'_rachis{j}_{k}',p0,p1,.031*(1-t)+.003,.027*(1-t)+.002,trunk,source,estimate,6);p0=p1
    for t in np.linspace(.17,.97,38):
     center=frond(t);span=(.20+.72*np.sin(np.pi*t))*min(1.3,reach/2.5)
     for sign in [-1,1]:
      direction=side*sign*.94-axis*(.12+.2*t)+np.array([0,0,-.12-.30*t]);direction/=np.linalg.norm(direction);root_list.append(center);axes.append(direction);lengths.append(span);widths.append(.035+.025*np.sin(np.pi*t));rolls.append(rng.uniform(-.45,.45));bends.append(-.10*span)
   v,f=curved_blades(root_list,axes,np.array(lengths),np.array(widths),np.array(rolls),np.array(bends));write_leaves(stem+'_pinnate_blades',v,f,source,estimate);leaf_count+=len(root_list);form='Pinnate architecture supported by source genus' if genus in palms else 'Illustrative pinnate architecture; source identifies only palm family'
 else:
  crown=origin+np.array([0,0,height*.66]);radius=height*.27;parts.tube(stem+'_trunk',origin,origin+[0,0,height*.57],max(.10,height*.018),.045,trunk,source,estimate,14);centers=[];axes=[];lengths=[];widths=[]
  for branch in range(24):
   zz=-.75+1.5*(branch+.5)/24;angle=branch*2.39996323;direction=np.array([np.cos(angle)*np.sqrt(1-zz*zz),np.sin(angle)*np.sqrt(1-zz*zz),zz]);center=crown+direction*np.array([radius*.76,radius*.76,height*.21]);root=origin+[0,0,height*(.36+.18*rng.random())];parts.tube(stem+f'_branch{branch}',root,center,.047,.014,trunk,source,estimate,7)
   for shoot in range(16):
    delta=rng.normal(size=3);delta/=np.linalg.norm(delta);tip=center+delta*rng.uniform(.38,.78);parts.tube(stem+f'_shoot{branch}_{shoot}',center,tip,.009,.002,trunk,source,estimate,4);direction=(tip-center)/np.linalg.norm(tip-center);side=np.cross(direction,[0,0,1]);side/=max(np.linalg.norm(side),1e-8)
    for t in np.linspace(.14,1,14):
     for sign in [-1,1]:
      a=side*sign*.77+direction*.3+[0,0,rng.uniform(-.55,.55)];a/=np.linalg.norm(a);length=rng.uniform(.10,.17);anchor=center+(tip-center)*t;petiole=.012;centers.append(anchor+a*(petiole+length*.5));axes.append(a);lengths.append(length);widths.append(length*rng.uniform(.42,.60))
   # Individual shoot axes, not an opaque envelope, support every blade.
  v,f=leaf_mesh(centers,axes,lengths,widths,folded=True,rolls=rng.uniform(-1.45,1.45,len(centers)));write_leaves(stem+'_branch_supported_blades',v,f,source,estimate);leaf_count+=len(centers);form='Estimated generic broadleaf crown; source supplies no species'
 records.append({'source_id':source,'source_xy_m':xy.tolist(),'source_genus':genus,'source_family':family,'height_m':height,'height_retained_from':'previous detailed palm/crown' if source in prior_features else 'previous geographic massing formula','source_height_tag':supplied,'near_del_playa':near,'form':form,'leaf_surface_area_m2':leaf_area_total-area_before,'triangles':parts.writer.triangles-start});all_positions.append(xy)
 print('NEAR_STREET_TREE',source,records[-1]['triangles'],round(records[-1]['leaf_surface_area_m2'],2),flush=True)
report=parts.close();report.update(material_offset=172,material_count=0,replace_sector_components=sorted(set(base_skip)),exclude_prior_botanical_objects=sorted(set(previous_skip)),source_features=records,leaf_surface_area_m2=leaf_area_total,leaf_blade_count=leaf_count,blade_root_centroid_error_m=attachment_error,detail_selection={'road_source_id':'osm:way:50978848','arclength_range_m':[310,610],'corridor_radius_m':42,'additional_sourced_fan_genera':sorted(fans),'dynamic_LOD_or_streaming':False},references=[{'url':'https://ask.ifas.ufl.edu/publication/EP473','basis':'Palm frond canopy, rachis/leaflet attachment and palmate versus pinnate structure.'},{'url':'https://efloras.org/florataxon.aspx?flora_id=1&taxon_id=134783','basis':'Washingtonia costapalmate blade, basally connected folded segments.'}],limits='Author-estimated near-street botanical forms, leaf area, porosity and branch architecture. Source points/taxonomy and prior height estimates retained. Family-only palms remain explicitly illustrative pinnate forms, not an inferred species. No scans, photo textures, opaque crown shells, wind dynamics or measured biomass. No facade changes. Original leaf material remains unchanged for a geometry-only comparison.',normalized_source_sha256=hashlib.sha256((base/'normalized.geojson').read_bytes()).hexdigest())
(out/'materials.cys').write_text('# Uses unchanged prior botanical material controls.\n');(out/'VEGETATION_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print('DONE_NEAR_STREET',json.dumps({'trees':len(records),'triangles':report['triangles'],'leaf_area_m2':leaf_area_total}),flush=True)
