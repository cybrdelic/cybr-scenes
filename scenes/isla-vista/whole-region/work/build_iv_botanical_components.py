"""Recover mapped palm families and replace nearby solid crowns with branches/leaves.

Taxonomy/positions remain source data. Leaf dimensions, architecture and absent
heights are authored estimates; no species identification is inferred from a
generic OSM tree point. Detailed broadleaf geometry is limited to the Pardall
reference corridor, an explicit spatial detail tier, not dynamic streaming.
"""
from pathlib import Path
import sys,json,numpy as np,hashlib
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
from cybr_light import Scene
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import DEM,metres
from iv_mesh_parts import Parts,leaf_mesh
coarse_far='--coarse-far' in sys.argv
dense_crown='--dense-crown' in sys.argv
out=r/('evidence/full-iv-botanical-dense' if dense_crown else 'evidence/full-iv-botanical-tiered' if coarse_far else 'evidence/full-iv-botanical');out.mkdir(exist_ok=True)
base=r/'evidence/full-iv-roofs';features=json.loads((base/'normalized.geojson').read_text())['features'];layout=json.loads((base/'glb-part-layout.json').read_text());partmap={p['part']:p['component'] for b in layout.values() for p in b['parts']}
sector=Sector(longitude=-119.8614,latitude=34.413,extent=2600);dem=DEM(r/'data/full-iv-20261011/dem.tif',sector.frame)
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.array(day['native_basis_to_linear_rgb']);white=M@np.ones(3);inv=np.linalg.inv(M)
def col(rgb):return np.maximum(0,(np.array(rgb)*white)@inv.T)
house_count=sum(x.startswith('material ') for x in (r/'evidence/full-iv-house-component/materials.cys').read_text().splitlines())
s=Scene();s.materials=20+house_count;offset=s.materials
trunk=s.material('plastic',col((.095,.075,.052)),.88,ior=1.43)
leaf_r=s.material('plastic',col((.045,.097,.022)),.59,ior=1.44);leaf_t=s.material('difftrans',col((.055,.13,.016)),1)
leaf=s.material('blendbsdf');s.emit('nested',leaf,leaf_r,leaf_t,.18)
dry=s.material('plastic',col((.16,.125,.065)),.88,ior=1.44)
parts=Parts(out/'botanical.clm',2000000);replacements=[];counts={'mapped_palms':0,'detailed_generic_canopies':0};records=[]
palms={'Syagrus','Phoenix','Washingtonia','Howea','Butia','Chamaerops','Archontophoenix'}
for feature in features:
 if feature['geometry']['type']!='Point' or feature['properties']['category'] not in {'tree','vegetation'}:continue
 stem=feature['id'].replace(':','_');old=[partmap[n] for n in [stem+'_trunk',stem+'_crown',stem+'_fronds'] if n in partmap]
 if not old:continue
 props=feature['properties']['source_properties'];xy=np.array(feature['geometry']['coordinates']);family=str(props.get('taxon:family','')).strip();genus=str(props.get('genus','')).strip();is_palm=family in {'Arecaceae','Arecacea'} or genus in palms
 near=np.linalg.norm(xy-np.array([483,15]))<120
 if not is_palm and not near:continue
 seed=int.from_bytes(hashlib.sha256(feature['id'].encode()).digest()[:8],'little');rng=np.random.default_rng(seed)
 supplied=metres(props.get('height'));height=supplied or (11 if is_palm else 7.5)*rng.uniform(.8,1.15);z=float(dem.sample(*xy));origin=np.r_[xy,z];source=feature['id']
 estimate='Mapped position and taxonomy; botanical dimensions, branches and leaf construction estimated'
 replacements.extend(old);records.append({'source_id':source,'source_family':family,'source_genus':genus,'representation':'estimated palm architecture' if is_palm else 'estimated generic broadleaf architecture','height_m':height,'height_source':'height tag' if supplied else 'authored estimate','replaced_objects':old})
 if is_palm:
  counts['mapped_palms']+=1;radius=height*.024
  for k in range(6):
   a=origin+np.array([.10*np.sin(k*.33),.07*np.sin(k*.26),height*.90*k/6]);b=origin+np.array([.10*np.sin((k+1)*.33),.07*np.sin((k+1)*.26),height*.90*(k+1)/6]);parts.tube(stem+f'_stem{k}',a,b,radius*(1-.25*k/6),radius*(1-.25*(k+1)/6),trunk,source,estimate,10)
  crown=origin+np.array([.09,.07,height*.9]);lc=[];la=[];ll=[];lw=[]
  detailed=near or not coarse_far
  for j in range(22 if detailed else 14):
   angle=j*2.39996323+rng.uniform(-.10,.10);axis=np.array([np.cos(angle),np.sin(angle),0]);side=np.array([-axis[1],axis[0],0]);reach=height*rng.uniform(.24,.32);lift=rng.uniform(.5,1.3)
   def frond(t):return crown+axis*reach*t+np.array([0,0,lift*np.sin(np.pi*t)-reach*.65*t*t])
   p0=frond(0)
   for k,t in enumerate(np.linspace(.16,1,7 if detailed else 4)):
    p1=frond(t);parts.tube(stem+f'_rachis{j}_{k}',p0,p1,.025*(1-t)+.003,.023*(1-t)+.002,trunk,source,estimate,4);p0=p1
   for t in np.linspace(.12,.94,16 if detailed else 12):
    center=frond(t);span=(.18+.78*np.sin(np.pi*t))*min(1.3,reach/2.5)
    for sign in [-1,1]:
     direction=side*sign*.92-axis*.25+np.array([0,0,-.24-.38*t]);direction/=np.linalg.norm(direction);lc.append(center+direction*span*.43);la.append(direction);ll.append(span);lw.append(.045+.025*np.sin(np.pi*t))
  vv,ff=leaf_mesh(lc,la,ll,lw,folded=detailed);parts.mesh(stem+'_palm_leaflets',vv,ff,leaf,source,estimate)
 else:
  counts['detailed_generic_canopies']+=1;radius=height*.27;crown=origin+np.array([0,0,height*.66]);parts.tube(stem+'_stem',origin,origin+[0,0,height*.55],max(.10,height*.018),.055,trunk,source,estimate,10)
  lc=[];la=[];ll=[];lw=[]
  for branch in range(21):
   zz=-.80+1.60*(branch+.5)/21;angle=branch*2.39996323;direction=np.array([np.cos(angle)*np.sqrt(1-zz*zz),np.sin(angle)*np.sqrt(1-zz*zz),zz]);center=crown+direction*np.array([radius*.72,radius*.72,height*.23]);root=origin+[0,0,height*(.32+.18*rng.random())];parts.tube(stem+f'_branch{branch}',root,center,.045,.012,trunk,source,estimate,6)
   for shoot in range(20 if dense_crown else 10):
    delta=rng.normal(size=3);delta/=np.linalg.norm(delta);tip=center+delta*rng.uniform(.35,.78);parts.tube(stem+f'_shoot{branch}_{shoot}',center,tip,.009,.002,trunk,source,estimate,3)
    direction=(tip-center)/np.linalg.norm(tip-center);side=np.cross(direction,[0,0,1.]);side/=max(np.linalg.norm(side),1e-8)
    for t in np.linspace(.12,1,12):
     for sign in [-1,1]:
      a=side*sign*.75+direction*.30+np.array([0,0,rng.uniform(-.35,.35)]);a/=np.linalg.norm(a);length=rng.uniform(.09,.16);lc.append(center+(tip-center)*t+a*length*.36);la.append(a);ll.append(length);lw.append(length*rng.uniform(.38,.52))
  rolls=rng.uniform(-1.35,1.35,len(lc)) if dense_crown else None
  vv,ff=leaf_mesh(lc,la,ll,lw,folded=not dense_crown,rolls=rolls);parts.mesh(stem+'_foliage_leaves',vv,ff,leaf,source,estimate)
 if sum(counts.values())%100==0:print('BOTANICAL',sum(counts.values()),parts.writer.triangles,flush=True)
report=parts.close();s.save(out/'materials.cys');report.update(counts=counts,material_offset=offset,material_count=s.materials-offset,replace_sector_components=sorted(replacements),features=records,coarse_distant_palms=coarse_far,detail_tier_radius_m=120,detail_tier_center=[483,15],limits='Palm family tags had been ignored by the old genus-only branch. Family recovers palms, not an exact species. OSM Arecacea spelling is normalized explicitly. Generic near-corridor broadleaf crown geometry is estimated. Distant generic crowns remain the preserved massing tier. Distant palm leaflets use lower geometric detail. This is a fixed geographic detail tier, not dynamic screen-error LOD or streaming. No scans, photo maps, billboards or fluid/vegetation simulation.',source_feature_snapshot_sha256=hashlib.sha256((base/'normalized.geojson').read_bytes()).hexdigest())
report['near_broadleaf_detail']={'dense_crown':dense_crown,'shoots_per_branch':20 if dense_crown else 10,'leaf_representation':'two-triangle blade with varied roll' if dense_crown else 'four-triangle shallow folded blade','roll_radians':[-1.35,1.35] if dense_crown else [0,0]}
(out/'BOTANICAL_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print('DONE',json.dumps({'counts':counts,'triangles':report['triangles'],'replaced_objects':len(replacements)}),flush=True)
