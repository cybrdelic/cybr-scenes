"""Optional source-anchored hedge candidate. Never modifies the baseline scene.

Mapped line/polygon geometry is retained; missing dimensions, leaf area, species
form and pruning state are explicitly authored. Four triangles describe one
folded leaf sheet, without a duplicated reverse side. Native transport handles
the two-sided leaf response. This is new reconstruction, not recovered fixture
code or surveyed planting.
"""
from pathlib import Path
import argparse, hashlib, json, math, re, struct, sys
import numpy as np
R = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(R/'geo-deps'), str(R/'work/cybr-iv-full/src'), str(R/'whole-iv-vendor'), str(R/'work')]
import shapely
from shapely.geometry import shape, Point, LineString, mapping
from shapely.ops import nearest_points
from cybr_ucsb.ingest import metres
from iv_shared_ground import SharedGround
from iv_mesh_parts import Parts, leaf_mesh
from cybr_light import Scene, render

OUT = R/'evidence/mapped-hedges-v1'
BASE = R/'evidence/full-iv-roofs'
FIXTURE = 'osm:way:822177699'
LAI = 2.80
SEED_VERSION = ':mapped-hedges-v1'
SHOOT_DISTRIBUTION = 'lateral-plant-variation-r4'
ENVELOPE_TOLERANCE_M = .0002
ROOT_BURIAL_ALLOWANCE_M = .02  # Authored seating of the 14 mm basal cylinder on sloped ground.

class NativeParts(Parts):
    def mesh(self,name,v,f,*args,**kwargs):
        # Derive face normals from the vertices actually serialized by LIGHT.
        return super().mesh(name,np.asarray(v,dtype='f4').astype(float),f,*args,**kwargs)

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def source():
    return json.loads((BASE/'normalized.geojson').read_text())['features']

def footprint(feature):
    geometry = shape(feature['geometry'])
    tags = feature['properties']['source_properties']
    def dimension(key):
        raw=tags.get(key)
        if raw is None or str(raw).strip()=='':return None
        parsed=metres(raw)
        if parsed is None:
            match=re.fullmatch(r'\s*([0-9]+(?:\.[0-9]+)?)\s*(cm|mm)\s*',str(raw))
            if match:parsed=float(match[1])*(.01 if match[2]=='cm' else .001)
        if parsed is None:raise ValueError('Unparsed source '+key+' tag for '+feature['id']+': '+str(raw))
        return parsed
    height = dimension('height')
    width = dimension('width')
    if height is not None and height <= 0:
        raise ValueError('Non-positive source height: '+feature['id'])
    if width is not None and width <= 0:
        raise ValueError('Non-positive source width: '+feature['id'])
    if geometry.geom_type in {'LineString','MultiLineString'}:
        support = geometry.buffer((width or .8)/2, cap_style='round', join_style='round')
        width_record = {'value_m':width or .8, 'basis':'source width tag' if width else 'authored missing-width estimate'}
    elif geometry.geom_type in {'Polygon','MultiPolygon'}:
        support = geometry
        width_record = {'value_m':None,'basis':'mapped polygon outline; no replacement width'}
    else:
        raise ValueError('Unsupported hedge geometry: '+geometry.geom_type)
    return support, {'height_m':height or 1.2, 'height_basis':'source height tag' if height else 'authored missing-height estimate', 'width':width_record}

def audit():
    OUT.mkdir(exist_ok=True)
    features = source()
    rows = []
    layout=json.loads((BASE/'glb-part-layout.json').read_text())
    base_parts=[p for b in layout.values() for p in b['parts']]
    for f in features:
        if f['properties']['category']!='hedge':continue
        support, dims=footprint(f)
        stem=f['id'].replace(':','_')
        matches=[p['part'] for p in base_parts if p['part'].startswith(stem+'_')]
        osm=f['id'].startswith('osm:')
        rows.append({'source_id':f['id'],'source_geometry_type':f['geometry']['type'], 'source_geometry':f['geometry'] if osm else None, 'source_properties':f['properties']['source_properties'] if osm else None, 'geometry_sha256':hashlib.sha256(json.dumps(f['geometry'],sort_keys=True,separators=(',',':')).encode()).hexdigest(), 'support_area_m2':support.area, 'dimensions':dims,'base_parts':matches,'scope':'candidate OSM' if osm else 'deferred campus polygon; overlap/epoch review required','redistribution':'OSM ODbL with original source notices' if osm else 'Source geometry/attributes withheld from compact public receipt; retain consumer-fetched UCSB input and its original terms'})
    assert len(rows)==203 and sum(x['source_id'].startswith('osm:') for x in rows)==103
    building_rows=[(f['id'],shape(f['geometry'])) for f in features if f['properties']['category']=='building']
    buildings=shapely.union_all([g for _,g in building_rows]);interior=buildings.buffer(-1e-6)
    conflicts=[];osm_support=[];osm_ids=[]
    for f in features:
        if f['properties']['category']!='hedge' or not f['id'].startswith('osm:'):continue
        support,_=footprint(f);osm_support.append(support);osm_ids.append(f['id'])
        overlap=support.intersection(buildings).area
        if overlap>.001:
            mapped=shape(f['geometry']);linear=mapped.geom_type in {'LineString','MultiLineString'}
            length=mapped.intersection(interior).length if linear else None
            classification='mapped line crosses building interior' if linear and length>1e-6 else 'estimated width only; mapped line clear of building interior' if linear else 'mapped polygon overlap'
            conflicts.append({'source_id':f['id'],'classification':classification,'building_overlap_area_m2':overlap,'mapped_line_inside_building_m':length,'intersected_building_source_ids':[sid for sid,b in building_rows if support.intersection(b).area>.001],'disposition':'excluded pending explicit source/dimension review; no clipping or repositioning'})
    pairs=[];tree=shapely.STRtree(osm_support)
    for i,support in enumerate(osm_support):
        for j in tree.query(support,predicate='intersects'):
            if j<=i:continue
            area=support.intersection(osm_support[j]).area
            if area>.001:pairs.append({'source_ids':[osm_ids[i],osm_ids[j]],'overlap_area_m2':area})
    report={'schema':'cybr-mapped-hedge-coverage/1','normalized_source_sha256':digest(BASE/'normalized.geojson'),'total_mapped':len(rows),'osm_lines':sum(x['source_id'].startswith('osm:') and x['source_geometry_type']=='LineString' for x in rows),'osm_polygons':sum(x['source_id'].startswith('osm:') and x['source_geometry_type']=='Polygon' for x in rows),'deferred_campus':sum(x['source_id'].startswith('ucsb:') for x in rows),'existing_base_hedge_parts':sum(len(x['base_parts']) for x in rows),'building_support_conflicts':conflicts,'overlapping_candidate_pairs':pairs,'candidate_support_sum_area_m2':sum(p.area for p in osm_support),'candidate_support_union_area_m2':shapely.union_all(osm_support).area,'rows':rows,'limits':'Coverage audit is not evidence that every candidate was built or integrated. Source geometries and tags remain dated map evidence; botanical form, leaf dimensions, LAI and missing height/width are authored. Positive source-plan conflicts require review; no clipping or moving of source geometry.'}
    excluded={x['source_id'] for x in conflicts}|{sid for x in pairs for sid in x['source_ids']}
    report['excluded_from_preliminary_rollout']=sorted(excluded)
    report['preliminary_conflict_free_source_ids']=sorted(set(osm_ids)-excluded)
    report['preliminary_conflict_free_count']=len(set(osm_ids)-excluded)
    (OUT/'COVERAGE.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'}),flush=True)
    return report

def sample_inside(polygon, count, rng):
    lo=np.array(polygon.bounds[:2]);hi=np.array(polygon.bounds[2:]); chunks=[];left=count
    while left:
        q=rng.uniform(lo,hi,(max(64,min(left*4,200000)),2))
        q=q[shapely.contains_xy(polygon,q[:,0],q[:,1])][:left]
        chunks.append(q);left-=len(q)
    return np.concatenate(chunks)

def sheet_area(v,f):
    t=v[f].astype(float)
    return np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1).sum()*.5

def selection_blockers(coverage,selected):
    chosen=set(selected)
    return {'buildings':[x for x in coverage['building_support_conflicts'] if x['source_id'] in chosen],
            'hedges':[x for x in coverage['overlapping_candidate_pairs'] if set(x['source_ids'])&chosen]}

def require_resolved_support(coverage,selected):
    blockers=selection_blockers(coverage,selected)
    if blockers['buildings'] or blockers['hedges']:
        raise ValueError('Source support conflicts require explicit review before build: '+json.dumps(blockers))

def require_connected_convex_support(support):
    # Straight branches may not bridge holes, concavities or disconnected parts.
    # A future component-routing author must supply and test a separate form.
    if support.geom_type!='Polygon' or support.interiors or support.convex_hull.area-support.area>max(1.,support.area)*1e-10:
        raise ValueError('This bounded form requires a single convex support without holes')

def local_terrain_lipschitz(ground,support):
    if not all(hasattr(ground,x) for x in ['z','dx','extent','n']):
        raise TypeError('Native envelope audit requires the exact SharedGround triangle surface')
    lo=np.floor((np.array(support.bounds[:2])+ground.extent/2)/ground.dx).astype(int)
    hi=np.floor((np.array(support.bounds[2:])+ground.extent/2)/ground.dx).astype(int)
    lo=np.maximum(lo-1,0);hi=np.minimum(hi+1,ground.n-2)
    z=ground.z;ix=np.arange(lo[0],hi[0]+1);iy=np.arange(lo[1],hi[1]+1)
    xx,yy=np.meshgrid(ix,iy);a=z[yy,xx];b=z[yy,xx+1];c=z[yy+1,xx+1];d=z[yy+1,xx]
    # SharedGround's two affine triangles use (a,b,c) and (a,c,d).
    return float(max(np.max(np.hypot(b-a,c-b)),np.max(np.hypot(c-d,d-a)))/ground.dx)

def triangle_envelope_bounds(q,support,ground,height_m,terrain_lipschitz,is_basal_stem):
    # Convex hull of each projected native triangle also handles vertical or
    # degenerate XY projections. This checks surfaces, not only their vertices.
    projected=shapely.convex_hull(shapely.multipoints(q[:,:,:2]))
    if not np.all(shapely.covers(support.buffer(ENVELOPE_TOLERANCE_M),projected)):
        raise ValueError('Native triangle surface escaped source support')
    relative=q[:,:,2]-ground.height(q[:,:,:2].reshape(-1,2)).reshape(-1,3)
    diameter=np.max(np.linalg.norm(q[:,:,:2]-np.roll(q[:,:,:2],1,axis=1),axis=2),axis=1)
    # A conservative continuous-surface certificate, not sparse ground samples:
    # affine triangle z minus the piecewise-affine terrain lies within vertex
    # extrema +/- local terrain Lipschitz constant * horizontal diameter.
    lower=relative.min(axis=1)-terrain_lipschitz*diameter
    upper=relative.max(axis=1)+terrain_lipschitz*diameter
    burial=ROOT_BURIAL_ALLOWANCE_M if is_basal_stem else 0.
    if lower.min() < -burial-ENVELOPE_TOLERANCE_M:
        raise ValueError('Native triangle terrain bound exceeds its burial allowance')
    if upper.max() > height_m+ENVELOPE_TOLERANCE_M:
        raise ValueError('Native triangle height bound exceeds the declared authored height')
    return float(lower.min()),float(upper.max())

def geometry(feature, ground, lai=LAI):
    support,dims=footprint(feature);require_connected_convex_support(support);h=dims['height_m']
    if h<.18:raise ValueError('Source height too small for this authored form; do not override it.')
    inside=support.buffer(-.083)
    if inside.is_empty:raise ValueError('Hedge too narrow for 4–8 cm leaves; requires separate form.')
    rng=np.random.default_rng(int.from_bytes(hashlib.sha256((feature['id']+SEED_VERSION).encode()).digest()[:8],'little'))
    assert 1.0<=lai<=6.0
    target=lai*support.area
    # 12 actual sheets per twig. Expected area only chooses the integer count;
    # final measured one-sided area normalizes dimensions by a small scalar.
    shoots=max(1,math.ceil(target/(12*.00090)))
    roots_xy=sample_inside(inside,max(2,math.ceil(support.area/.50)),rng)
    plant_height_scale=rng.uniform(.88,1.0,len(roots_xy))
    plant_branch_rotation=rng.uniform(-.35,.35,len(roots_xy))
    from scipy.spatial import cKDTree
    tips_xy=sample_inside(inside,shoots,rng)
    root_z=ground.height(roots_xy)
    # Basal stems support lateral primary branches. Their overlapping crowns
    # share nearby volume; the prior full-height parallel stems are removed.
    primary_xy=sample_inside(inside,max(16,len(roots_xy)*10),rng)
    _,root_for_primary=cKDTree(roots_xy).query(primary_xy)
    for k,root_index in enumerate(root_for_primary):
        delta=primary_xy[k]-roots_xy[root_index];angle=plant_branch_rotation[root_index]
        for _ in range(12):
            c,s=np.cos(angle),np.sin(angle);rotated=roots_xy[root_index]+np.array([c*delta[0]-s*delta[1],s*delta[0]+c*delta[1]])
            if inside.covers(Point(rotated)):
                primary_xy[k]=rotated;break
            angle*=.5
    primary_start=np.c_[roots_xy[root_for_primary],root_z[root_for_primary]+h*.17*plant_height_scale[root_for_primary]]
    primary_end=np.c_[primary_xy,ground.height(primary_xy)+rng.uniform(.20,.88,len(primary_xy))*h*plant_height_scale[root_for_primary]]
    _,root_for_tip=cKDTree(roots_xy).query(tips_xy)
    tip_height=rng.uniform(.11,.94,shoots)*h*plant_height_scale[root_for_tip]
    ends=np.c_[tips_xy,ground.height(tips_xy)+tip_height]
    # Choose spatially adjacent branch support in 3D, rather than forcing every
    # leaf cluster onto a vertical rod. Leaves remain in the mapped envelope.
    _,branch_for_shoot=cKDTree(primary_end).query(ends)
    starts=primary_end[branch_for_shoot].copy()
    length=np.linalg.norm(ends-starts,axis=1)
    too_short=length<.06
    # Avoid a zero-length twig by starting farther along its existing parent.
    starts[too_short]=(primary_start[branch_for_shoot[too_short]]+primary_end[branch_for_shoot[too_short]])*.5
    directions=ends-starts;directions/=np.linalg.norm(directions,axis=1)[:,None]
    t=np.tile(np.linspace(.34,1.,6).repeat(2),shoots)
    anchor=np.repeat(starts,12,axis=0)+np.repeat(ends-starts,12,axis=0)*t[:,None]
    dirs=np.repeat(directions,12,axis=0)
    # Alternating coherent pairs follow each actual twig, with a small authored
    # phyllotactic rotation. Orientation is world/branch-based, never camera-facing.
    up=np.tile([0.,0.,1.],(shoots*12,1));up[abs(dirs[:,2])>.97]=[1.,0.,0.]
    side=np.cross(dirs,up);side/=np.linalg.norm(side,axis=1)[:,None];across=np.cross(dirs,side)
    phase=np.repeat(rng.uniform(0,2*np.pi,shoots),12)+np.tile(np.repeat(np.arange(6)*2.39996323,2)+np.tile([0.,np.pi],6),shoots)
    radial=side*np.cos(phase)[:,None]+across*np.sin(phase)[:,None]
    axes=radial*.86+dirs*.30+np.array([0,0,.16])
    axes/=np.linalg.norm(axes,axis=1)[:,None]
    lengths=rng.uniform(.043,.077,shoots*12);widths=lengths*rng.uniform(.43,.53,shoots*12)
    rolls=rng.uniform(-1.0,1.0,shoots*12)
    v,f=leaf_mesh(anchor+axes*lengths[:,None]*.5,axes,lengths,widths,rolls=rolls)
    scale=math.sqrt(target/sheet_area(v,f));lengths*=scale;widths*=scale
    if not (.04<=lengths.min()<=lengths.max()<=.08):raise ValueError('Leaf size normalization exceeded 4–8 cm contract')
    v,f=leaf_mesh(anchor+axes*lengths[:,None]*.5,axes,lengths,widths,rolls=rolls)
    # A single triangle sheet represents both reflection and transmission.
    v=v.astype('f4').astype(float)
    actual=sheet_area(v,f)
    # Preserve exact mapped polygon/estimated buffered-line envelope. Omit no
    # outlying leaf: fail and review instead of silently moving source geometry.
    envelope=support.buffer(.0002)
    if not np.all(shapely.covers(envelope,shapely.points(v[:,:2]))):
        raise ValueError('Leaf escaped support envelope')
    if np.min(v[:,2]-ground.height(v[:,:2]))<-.0002:raise ValueError('Leaves below retained terrain')
    native_roots=np.c_[roots_xy,root_z].astype('f4').astype(float)
    root_error=float(np.max(abs(native_roots[:,2]-ground.height(native_roots[:,:2]))))
    attachment_error=float(np.max(np.linalg.norm(v.reshape(-1,5,3)[:,0]-anchor,axis=1)))
    return v,f,roots_xy,root_z,starts,ends,primary_start,primary_end,{'source_id':feature['id'],'source_geometry':feature['geometry'],'source_properties':feature['properties']['source_properties'],'dimensions':dims,'support_area_m2':support.area,'leaf_count':len(lengths),'leaf_length_m':[float(lengths.min()),float(lengths.max())],'one_sided_leaf_area_m2':actual,'target_one_sided_lai':lai,'actual_one_sided_lai':actual/support.area,'area_counting':'Four triangles per folded single sheet; no reverse-face duplication','shoot_count':shoots,'stem_count':len(roots_xy),'primary_branch_count':len(primary_end),'authored_plant_height_scale_range':[float(plant_height_scale.min()),float(plant_height_scale.max())],'authored_plant_branch_rotation_radians':[float(plant_branch_rotation.min()),float(plant_branch_rotation.max())],'plant_variation':'Per-root deterministic crown height and lateral branch orientation, bounded within source support; no camera-facing or per-frame noise','support_envelope_max_tolerance_m':.0002,'stem_native_axis_base_terrain_error_m':root_error,'leaf_native_attachment_error_m':attachment_error,'unmeasured':'Generic broadleaf hedge; species, pruning state, missing height/width, LAI, blade form, stem/shoot topology and optics are authored.'}

def build(ids,material_offset=20,lai=LAI,folder=None):
    OUT.mkdir(exist_ok=True);coverage=audit();features=source();byid={x['id']:x for x in features}
    selected=[x['source_id'] for x in coverage['rows'] if x['scope']=='candidate OSM'] if ids==['ALL'] else ids
    assert selected and len(set(selected))==len(selected)
    require_resolved_support(coverage,selected)
    for sid in selected:require_connected_convex_support(footprint(byid[sid])[0])
    ground=SharedGround(BASE/'measured-terrain-state.npz')
    path=OUT/(folder or ('whole_osm' if ids==['ALL'] else 'fixture'));path.mkdir(exist_ok=True)
    s=Scene();s.materials=material_offset;day=json.loads((R/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.array(day['native_basis_to_linear_rgb']);white=M@np.ones(3)
    def col(rgb):
        x=np.linalg.solve(M,np.array(rgb)*white);assert x.min()>=0 and x.max()<1;return x
    bark=s.material('plastic',col((.095,.075,.052)),.88,ior=1.43)
    refl=s.material('plastic',col((.045,.097,.022)),.59,ior=1.44)
    trans=s.material('difftrans',col((.055,.13,.016)),1)
    leaf=s.material('blendbsdf');s.emit('nested',leaf,refl,trans,.18)
    parts=NativeParts(path/'hedges.clm',15000000);records=[]
    for sid in selected:
        feature=byid[sid];assert feature['properties']['category']=='hedge' and sid.startswith('osm:')
        v,f,roots,z,starts,ends,primary_start,primary_end,row=geometry(feature,ground,lai);stem=sid.replace(':','_')
        parts.mesh(stem+'_leaves',v,f,leaf,sid,row['unmeasured'])
        # Thin structural twigs and root-supported stems, not an opaque crown.
        for k,(xy,zz) in enumerate(zip(roots,z)):
            parts.tube(stem+f'_stem{k}',np.r_[xy,zz],np.r_[xy,zz+row['dimensions']['height_m']*.17],.014,.008,bark,sid,row['unmeasured'],5)
        for k,(a,b) in enumerate(zip(primary_start,primary_end)):
            parts.tube(stem+f'_lateral{k}',a,b,.006,.0022,bark,sid,row['unmeasured'],4)
        # Aggregate twigs to a single native object per source feature.
        tv=[];tf=[]
        for a,b in zip(starts,ends):
            axis=b-a;axis/=np.linalg.norm(axis);ref=np.array([0.,0,1.]) if abs(axis[2])<.95 else np.array([1.,0,0]);u=np.cross(axis,ref);u/=np.linalg.norm(u);w=np.cross(axis,u);angle=np.arange(3)*2*np.pi/3;ring=np.cos(angle)[:,None]*u+np.sin(angle)[:,None]*w;first=len(tv);tv.extend(a+.0018*ring);tv.extend(b+.0007*ring)
            for j in range(3):k=(j+1)%3;tf.extend([[first+j,first+k,first+3+k],[first+j,first+3+k,first+3+j]])
        parts.mesh(stem+'_twigs',np.asarray(tv,dtype='f4').astype(float),tf,bark,sid,row['unmeasured'])
        records.append(row);print('HEDGE',sid,row['leaf_count'],round(row['actual_one_sided_lai'],6),flush=True)
    report=parts.close();s.save(path/'materials.cys')
    report.update(source_features=records,selected_source_ids=selected,material_offset=material_offset,leaf_material=leaf,bark_material=bark,shoot_distribution=SHOOT_DISTRIBUTION,generator_sha256=digest(Path(__file__)),normalized_source_sha256=digest(BASE/'normalized.geojson'),baseline_glb_sha256=digest(BASE/'sector.glb'),mesh_sha256=digest(path/'hedges.clm'),integration='standalone optional candidate; baseline and dedicated assemblies untouched',coverage_receipt_sha256=digest(OUT/'COVERAGE.json'))
    (path/'BUILD.json').write_text(json.dumps(report,indent=2)+'\n');return path

def verify(folder='fixture'):
    path=OUT/folder;r=json.loads((path/'BUILD.json').read_text());assert digest(path/'hedges.clm')==r['mesh_sha256'];source_byid={x['id']:x for x in source()}
    assert digest(BASE/'normalized.geojson')==r['normalized_source_sha256'] and digest(BASE/'sector.glb')==r['baseline_glb_sha256']
    ground=SharedGround(BASE/'measured-terrain-state.npz');envelopes={};bounds={}
    for row in r['source_features']:
        support,dims=footprint(source_byid[row['source_id']]);require_connected_convex_support(support)
        envelopes[row['source_id']]=(support,dims['height_m'],local_terrain_lipschitz(ground,support))
    objects={p['object']:p for p in r['parts']};areas={sid:0. for sid in r['selected_source_ids']};counts={sid:0 for sid in areas};seen=set();bad=0;worst=0.;worst_direction=0.
    dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')])
    with (path/'hedges.clm').open('rb') as stream:
        magic,total,packets=struct.unpack('<4sQI',stream.read(16));assert magic==b'CLM1' and total==r['triangles']
        for _ in range(packets):
            nv,nt=struct.unpack('<HH',stream.read(4));v=np.frombuffer(stream.read(nv*44),'<f4').reshape(nv,11).astype(float);t=np.frombuffer(stream.read(nt*11),dtype);assert np.isfinite(v).all();q=v[t['indices'],:3];cross=np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]);length=np.linalg.norm(cross,axis=1);bad+=int((length<=1e-12).sum());a=length*.5
            worst=max(worst,float(np.max(abs(np.linalg.norm(v[:,3:6],axis=1)-1))))
            n=cross/length[:,None];saved=v[t['indices'][:,0],3:6];worst_direction=max(worst_direction,float(np.max(1-np.einsum('ij,ij->i',n,saved))))
            for obj in np.unique(t['object']):
                selected=t['object']==obj;row=objects[int(obj)];seen.add(int(obj))
                support,height,gradient=envelopes[row['source']];basal='_stem' in row['name']
                lower,upper=triangle_envelope_bounds(q[selected],support,ground,height,gradient,basal)
                key='basal_stem' if basal else 'leaves' if row['name'].endswith('_leaves') else 'primary_branch' if '_lateral' in row['name'] else 'twig'
                b=bounds.setdefault(key,{'native_triangles_checked':0,'min_certified_relative_height_m':float('inf'),'max_certified_relative_height_m':-float('inf')})
                b['native_triangles_checked']+=int(selected.sum());b['min_certified_relative_height_m']=min(b['min_certified_relative_height_m'],lower);b['max_certified_relative_height_m']=max(b['max_certified_relative_height_m'],upper)
                if np.all(t['material'][selected]==r['leaf_material']):areas[row['source']]+=float(a[selected].sum());counts[row['source']]+=int(selected.sum())
        assert not stream.read(1)
    assert bad==0 and worst<1e-6 and worst_direction<1e-5,(bad,worst,worst_direction)
    assert seen==set(objects) and sum(x['native_triangles_checked'] for x in bounds.values())==total
    for row in r['source_features']:
        sid=row['source_id'];assert row['source_geometry']==source_byid[sid]['geometry'];assert counts[sid]==row['leaf_count']*4
        assert abs(areas[sid]/row['support_area_m2']-row['target_one_sided_lai'])<.0005
        assert abs(areas[sid]-row['one_sided_leaf_area_m2'])<max(.000001,areas[sid]*1e-7)
    report={'passed':True,'source_identity_geometry_checks':len(areas),'triangles':total,'leaf_triangles':sum(counts.values()),'one_sided_leaf_area_m2':sum(areas.values()),'zero_area_triangles':bad,'native_normal_length_max_error':worst,'native_normal_direction_max_error':worst_direction,'mesh_sha256':digest(path/'hedges.clm'),'baseline_glb_unchanged':True,'all_native_triangle_envelope_checks':bounds,'support_tolerance_m':ENVELOPE_TOLERANCE_M,'basal_stem_only_burial_allowance_m':ROOT_BURIAL_ALLOWANCE_M,'burial_basis':'Authored 20 mm root seating allowance for 14 mm radius basal cylinders on sloped terrain; no allowance for branches, twigs or blades. This is not a site root-depth measurement.','terrain_certificate':'Whole triangle support projection; continuous terrain/height bounds using exact SharedGround local affine-gradient Lipschitz maximum. Conservative failures remain failures.','scope':'Serialized single-sheet area, finite geometry and unchanged source identity. No measured biomass, species or photorealism claim.'}
    (path/'VALIDATION.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True);return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['audit','build','verify']);p.add_argument('--source-id',action='append');p.add_argument('--all-osm',action='store_true');p.add_argument('--material-offset',type=int,default=20);p.add_argument('--lai',type=float,default=LAI);p.add_argument('--folder');args=p.parse_args()
    if args.action=='audit':audit()
    elif args.action=='build':build(['ALL'] if args.all_osm else args.source_id or [FIXTURE],args.material_offset,args.lai,args.folder)
    else:verify(args.folder or ('whole_osm' if args.all_osm else 'fixture'))
