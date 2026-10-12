"""AS sparse outer-shoulder rock tier. In-memory candidate, after AQ margin.
New metric solids and shared meshes; intrinsic R5D/asphalt inputs unchanged.
Placement is authored historical sorting, not transported sediment inventory.
"""
import gc,math,time,hashlib
import numpy as np
import bpy
from metric_margin_fragments_as import build_fragment,audit_fragment
from assemble_road_margin_aq import terrain_sampler,surface_fields
from approved_density_lod import CameraProjection,PackingIndex

def material():
    m=bpy.data.materials.new('AS new metric rock / shared regional mineral palette');m.use_nodes=True;n=m.node_tree.nodes;l=m.node_tree.links;b=n.get('Principled BSDF');b.inputs['Specular IOR Level'].default_value=.28
    g=n.new('ShaderNodeNewGeometry');a=n.new('ShaderNodeAttribute');a.attribute_name='mineral';r=n.new('ShaderNodeAttribute');r.attribute_name='grain_roughness'
    noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=680;noise.inputs['Detail'].default_value=3;noise.inputs['Roughness'].default_value=.73;l.new(g.outputs['Position'],noise.inputs['Vector'])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].position=.21;ramp.color_ramp.elements[0].color=(.65,.68,.73,1);ramp.color_ramp.elements[1].position=.78;ramp.color_ramp.elements[1].color=(1.15,1.10,1.02,1);l.new(noise.outputs['Fac'],ramp.inputs[0]);mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1;l.new(a.outputs['Color'],mix.inputs[1]);l.new(ramp.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],b.inputs['Base Color'])
    rough=n.new('ShaderNodeMapRange');rough.inputs['From Min'].default_value=0;rough.inputs['From Max'].default_value=1;rough.inputs['To Min'].default_value=-.04;rough.inputs['To Max'].default_value=.05;l.new(noise.outputs['Fac'],rough.inputs['Value']);add=n.new('ShaderNodeMath');add.operation='ADD';l.new(r.outputs['Fac'],add.inputs[0]);l.new(rough.outputs['Result'],add.inputs[1]);l.new(add.outputs[0],b.inputs['Roughness'])
    micro=n.new('ShaderNodeTexNoise');micro.inputs['Scale'].default_value=3100;micro.inputs['Detail'].default_value=2;l.new(g.outputs['Position'],micro.inputs['Vector']);bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000085;bump.inputs['Strength'].default_value=.65;l.new(micro.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],b.inputs['Normal'])
    # Mineral inclusions affect sub-mm face relief and roughness together, while
    # actual fracture planes/edge weathering remain mesh geometry with flat normals.
    bump2=n.new('ShaderNodeBump');bump2.inputs['Distance'].default_value=.00025;bump2.inputs['Strength'].default_value=.5;l.new(noise.outputs['Fac'],bump2.inputs['Height']);l.new(bump.outputs['Normal'],bump2.inputs['Normal']);l.new(bump2.outputs['Normal'],b.inputs['Normal']);return m

def apply(scene,config,out):
    start=time.monotonic();rng=np.random.default_rng(2610100910);ground=scene.objects['Graded shoulder and alluvial plain -1'];sampler,source_co=terrain_sampler(ground);del source_co;gc.collect();projection=CameraProjection(scene,int(config.get('projection_width',1000)),int(config.get('projection_height',667)))
    if 'camera_location' in config:projection=projection.with_pose(config['camera_location'],config['camera_target'],config.get('lens',scene.camera.data.lens))
    revision=config.get('geometry_revision','AS')
    if revision=='AS':builder,auditor=build_fragment,audit_fragment
    elif revision=='fractured_candidate':
        from metric_margin_fragments_as_fractured_candidate import build_fragment as builder,audit_fragment as auditor
    else:raise ValueError('Unknown AS geometry revision')
    other_views=config.get('additional_views',[])
    assert len(other_views)<=1,'One additional cache view is supported'
    projections=[projection]+[CameraProjection(scene,int(v['width']),int(v['height'])).with_pose(v['camera_location'],v['camera_target'],v['lens']) for v in other_views]
    bank=[builder(i) for i in range(40)];meta=[auditor(f) for f in bank];mat=material();meshes=[]
    for i,f in enumerate(bank):
        me=bpy.data.meshes.new(f'AS actual metric fragment {i:03d}');me.from_pydata(f.vertices.tolist(),[],f.faces.tolist());me.materials.append(mat);c=me.color_attributes.new(name='mineral',type='FLOAT_COLOR',domain='POINT');c.data.foreach_set('color',f.color.astype('f4').ravel());r=me.attributes.new('grain_roughness','FLOAT','POINT');r.data.foreach_set('value',f.roughness.astype('f4'));me.polygons.foreach_set('use_smooth',np.zeros(len(me.polygons),bool));me.update();meshes.append(me)
    # Worked inner fines are excluded continuously by their actual historical
    # graded fraction. Wider margins get sparse small groups, not a rock carpet.
    xy=np.c_[rng.uniform(-10.8,-3.85,9000),rng.uniform(-.2,72,9000)];z,v=surface_fields(sampler,xy);ids=rng.integers(0,len(bank),len(xy));diam=np.array([max(m['dimensions_m'][:2]) for m in meta]);height=np.array([m['dimensions_m'][2] for m in meta]);rad=np.array([np.linalg.norm(f.vertices[:,:2],axis=1).max() for f in bank]);positions=np.c_[xy,np.nan_to_num(z)];visible=projection.visible(positions+np.array([0,0,.08]),margin=60);q=projection.area_vectors(positions);pixels=diam[ids]*np.sqrt(np.linalg.norm(q,axis=1))
    for other in projections[1:]:
        visible|=other.visible(positions+np.array([0,0,.08]),margin=60)
        pixels=np.maximum(pixels,diam[ids]*np.sqrt(np.linalg.norm(other.area_vectors(positions),axis=1)))
    probability=(.006+.13*v['coarse']**1.5)*(1-v['graded'])**1.7*(1-.78*v['receiving']);good=np.isfinite(z)&(rng.random(len(xy))<probability)
    # Largest bodies are deliberately rarer, and finite packing prevents a
    # repeated intersecting pile. This is no statistical site-calibration claim.
    good &= (rng.random(len(xy))<np.clip(.09/diam[ids],.25,1))
    yaw_all=rng.uniform(0,math.tau,len(xy));selected=[];packing=PackingIndex(float(rad.max()*1.6))
    for j in np.flatnonzero(good):
        if packing.clear(xy[j],rad[ids[j]]*1.6):packing.add(xy[j],rad[ids[j]]*1.6);selected.append(int(j))
    global_selected_count=len(selected);selected=[j for j in selected if visible[j] and pixels[j]>.7]
    entries=[]
    for j in selected:
        k=int(ids[j]);f=bank[k];yaw=float(yaw_all[j]);cs,sn=math.cos(yaw),math.sin(yaw);bottom=f.vertices[np.argmin(f.vertices[:,2])];botxy=xy[j]+np.array([bottom[0]*cs-bottom[1]*sn,bottom[0]*sn+bottom[1]*cs]);support=float(sampler.height(botxy[None])[0]);embed=float(height[k]*(.28+.38*v['fines'][j]));oz=min(float(z[j]-embed),support-.00005)
        ob=bpy.data.objects.new('AS sparse outer fragment / actual metric dimensions',meshes[k]);scene.collection.objects.link(ob);ob.location=(*xy[j],oz);ob.rotation_euler[2]=yaw;ob.scale=(1,1,1);entries.append({'bank_index':k,'xyz_m':list(ob.location),'yaw_rad':yaw,'nominal_diameter_m':float(diam[k]),'embedment_m':embed,'coarse':float(v['coarse'][j]),'graded':float(v['graded'][j]),'source_minimum_vertex_below_soil_m':support-oz})
    uv,depth=projection.project(np.array([e['xyz_m'] for e in entries]).reshape(-1,3))
    for e,pixel in zip(entries,uv):e['pixel_xy']=pixel.tolist()
    report={'scope':'New original sparse outer-margin centimetre/decimetre tier, not rescaled approved particles','instances':len(entries),'allocation_projection_resolution':[projection.width,projection.height],'allocation_uses_requested_view':('camera_location' in config),'camera_independent_packed_candidates':global_selected_count,'camera_changes_geometry_placements':False,'near_y_under_8m_instances':sum(e['xyz_m'][1]<8 for e in entries),'projected_expected_span_px':[float(pixels[j]) for j in selected],'bank':meta,'placements':entries,'approved_materials_modified':False,'existing_grains_scaled':False,'camera_geometry_lighting_modified':False,'terrain_modified':False,'roughness_and_microrelief_linked_to_mineral_field':True,'weathering_geometry':'Physical 0.55–1.8mm narrow edge truncation; face normals remain planar','limitations':['Authored rock size/mineral distribution guided by regional visual observation, not measured Victorville data','Lowest-vertex soil contact only; no rigid-body dynamics or exact embedded volume','New coarse fragment material uses original R5D palette values but is a distinct scale-specific procedural material','Actual wider and near render gate required before delivery'],'elapsed_seconds':time.monotonic()-start}
    report['geometry_revision']=revision;report['allocation_view_count']=len(projections)
    report['placement_comparison_scope']='Each morphology bank is repacked with its actual radius; exact unchanged placement is not claimed across different geometry revisions'
    if revision=='fractured_candidate':report['weathering_geometry']='Asymmetric multi-plane mass with true 0.55–1.8 mm edge setbacks and 2–3 finite corner spalls; flat face normals'
    del sampler,bank;gc.collect();return report
