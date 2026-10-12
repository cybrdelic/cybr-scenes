"""Attach finite-stock surface visibility and existing R5D particle exposure.
Runs after AH earthwork and pavement contact. No scene save or new particles.
"""
from pathlib import Path
import gc,hashlib,time
import numpy as np
import bpy
import approved_density_lod as lod
from context_mesh_refine_ab import _read,intersecting_triangles,SourceSampler
from visible_shoulder_flow_ad import sample_field
from sediment_surface_ai import surface_fields,retained_grain_lift,summary,SurfaceSpec
from transported_grain_exposure import allocate_transported_grains,ExposureConfig

GROUND='Graded shoulder and alluvial plain -1'

def shader(ground,history=False):
    old=ground.data.materials[0];m=old.copy();m.name='AI runoff-sorted surface / approved intrinsic R5D retained';ground.data.materials[0]=m
    n=m.node_tree.nodes;l=m.node_tree.links;bs=n['Linked dry dielectric'];base=bs.inputs['Base Color'].links[0].from_socket;rough=bs.inputs['Roughness'].links[0].from_socket;normal=bs.inputs['Normal'].links[0].from_socket
    def value(q,k,v):l.new(v,q.inputs[k]) if hasattr(v,'node') else setattr(q.inputs[k],'default_value',v)
    def mix(a,b,t):q=n.new('ShaderNodeMixRGB');value(q,0,t);value(q,1,a);value(q,2,b);return q.outputs[0]
    def math(op,a,b):q=n.new('ShaderNodeMath');q.operation=op;value(q,0,a);value(q,1,b);return q.outputs[0]
    def attr(name):q=n.new('ShaderNodeAttribute');q.attribute_name=name;return q.outputs['Fac']
    lag=attr('ai_coarse_lag');film=attr('ai_fine_coat')
    # Coarse-rich lag exposes the less powder-coated approved mineral composite.
    # This is a bounded scene optical response, not a modification of the recipe.
    mul=n.new('ShaderNodeMixRGB');mul.blend_type='MULTIPLY';value(mul,0,1.);value(mul,1,base);mul.inputs[2].default_value=(.72,.76,.82,1.)
    color=mix(base,mul.outputs[0],lag)
    matrix=attr('ak_historical_matrix');compact=attr('ak_historical_compaction')
    if history:color=mix(color,(.29535648,.24439612,.17515583,1),math('MULTIPLY',matrix,.40))
    # Exact linear mean of pinned R5D compacted_microbed color, not a photo sample.
    color=mix(color,(.29535648,.24439612,.17515583,1),math('MULTIPLY',film,.85));l.new(color,bs.inputs['Base Color'])
    response=mix(math('MINIMUM',.98,math('ADD',rough,math('MULTIPLY',lag,.055))),(.84,.84,.84,1),film)
    if history:response=math('SUBTRACT',response,math('MULTIPLY',compact,.035))
    l.new(response,bs.inputs['Roughness'])
    # A thin fine coat fills sub-mm voids while retaining actual broad geometry.
    # Existing full metric R5D normal is attenuated only where actual fines remain.
    geo=n['World surface geometry'];atten=math('MULTIPLY',film,.68)
    if history:atten=math('MAXIMUM',atten,math('MULTIPLY',math('MULTIPLY',matrix,compact),.25))
    vn=mix(normal,geo.outputs['Normal'],atten);norm=n.new('ShaderNodeVectorMath');norm.operation='NORMALIZE';l.new(vn,norm.inputs[0]);l.new(norm.outputs[0],bs.inputs['Normal'])
    return dict(original_material=old.name,scene_material=m.name,approved_input_nodes_copied=True,recipe_images_unchanged=True,layer='Bounded thin retained fine coat and uncoated coarse-lag response',fine_color_linear_source='Pinned approved compacted microbed mean RGB',fine_roughness=.84)

def apply(scene,config,out):
    spec=SurfaceSpec(include_net_eroded_retained=bool(config.get('include_net_eroded_retained',False)),include_substrate_history=bool(config.get('include_substrate_history',False)))
    started=time.monotonic();path=Path(out)/'AH_FIELDS.npz';f=dict(np.load(path));x,y=f['x_m'],f['y_m'];bounds=(float(x[0]),float(x[-1]),float(y[0]),float(y[-1]));ground=scene.objects[GROUND]
    co=_read(ground.data.vertices,'co',3);xy=co[:,:2];v=surface_fields(xy,f,spec)
    for name,key in [('ai_coarse_lag','lag'),('ai_fine_coat','fine_coat'),('ak_historical_matrix','historical_matrix'),('ak_historical_compaction','historical_compaction')]:
        a=ground.data.attributes.new(name,'FLOAT','POINT');a.data.foreach_set('value',v[key].astype('f4'))
    shader_report=shader(ground,spec.include_substrate_history);del v
    ground.data.calc_loop_triangles();tri=_read(ground.data.loop_triangles,'vertices',3,np.int32)
    ids=intersecting_triangles(co,tri,(bounds[0]-.02,bounds[1]+.02,bounds[2]-.02,bounds[3]+.02));local=tri[ids];used,inv=np.unique(local,return_inverse=True);localco=co[used].copy();localtri=inv.reshape(-1,3)
    del co,tri,ids,local,used,inv;gc.collect()
    sampler=SourceSampler(localco,localtri,np.arange(len(localtri)),max_triangles=850000,max_bin_entries=3200000)
    records,_,_=lod._bank(scene.objects[lod.ORIGINS]);minimum=np.array([a['vertices'][:,2].min() for a in records]);maximum=np.array([a['vertices'][:,2].max() for a in records]);diam=np.array([a['diameter'] for a in records]);foot=np.array([a['footprint_area'] for a in records]);cls=np.array([2 if a['band']=='chips' else 1 for a in records]);volume=[]
    prototype_sha=hashlib.sha256()
    for rec in records:
        me=bpy.data.objects[rec['name']].data;me.calc_loop_triangles();t=_read(me.loop_triangles,'vertices',3,np.int32);p=rec['vertices'];tv=p[t];vol=abs(float(np.einsum('ij,ij->i',tv[:,0],np.cross(tv[:,1],tv[:,2])).sum()/6));volume.append(vol);prototype_sha.update(p.tobytes());prototype_sha.update(t.tobytes())
    reports=[]
    for name in (lod.ORIGINS,lod.OUTPUT):
        ob=scene.objects[name];p=lod._co(ob.data);assert np.allclose(np.asarray(ob.matrix_world),np.eye(4));pi=_read(ob.data.attributes['prototype'].data,'value',1,np.int32);yaw=_read(ob.data.attributes['yaw'].data,'vector',3)
        inside=(p[:,0]>bounds[0]+.008)&(p[:,0]<bounds[1]-.008)&(p[:,1]>bounds[2]+.008)&(p[:,1]<bounds[3]-.008);rows=np.flatnonzero(inside);q=p[rows].copy();pr=pi[rows];sv=surface_fields(q[:,:2],f,spec);lift=retained_grain_lift(sv,minimum[pr],spec);final=lod._height(sampler,q[:,:2]);new=q.copy();embedding=sv['historical_matrix']*diam[pr]*.30 if spec.include_substrate_history else 0.;new[:,2]+=lift-embedding
        # Prove one actual lowest prototype vertex remains embedded for every
        # moved origin; full body intersections/settling are not solved.
        bot=np.array([r['vertices'][np.argmin(r['vertices'][:,2])] for r in records])[pr].copy();ang=yaw[rows,2];c,s=np.cos(ang),np.sin(ang);bx=bot[:,0]*c-bot[:,1]*s;by=bot[:,0]*s+bot[:,1]*c
        bxy=q[:,:2]+np.c_[bx,by];bz=lod._height(sampler,bxy);cap=bz-bot[:,2]-.00002;new[:,2]=np.minimum(new[:,2],cap if spec.include_substrate_history else np.maximum(q[:,2],cap))
        allocation=None
        if name==lod.OUTPUT:
            a=allocate_transported_grains(xy_m=q[:,:2],flow_class=cls[pr],solid_volume_m3=np.asarray(volume)[pr],diameter_m=diam[pr],footprint_area_m2=foot[pr],local_z_bounds_m=np.c_[minimum,maximum][pr],final_surface_m=final,x_m=x,y_m=y,retained_deposit_by_class_m=f['retained_deposit_by_class_m'],net_deposit_m=f['sediment_delta_m'],local_net_deposit_m=sv['net_m'],config=ExposureConfig(availability_mode='surviving_deposit_stock' if spec.include_net_eroded_retained else 'net_positive_only'))
            chosen=a.transported;new[chosen,2]=np.minimum(final[chosen]-a.extra_embedment_m[chosen],cap[chosen]);allocation=a.receipt
        dz=new[:,2]-q[:,2];p[rows,2]=new[:,2];ob.data.vertices.foreach_set('co',p.ravel());ob.data.update()
        changed=np.abs(dz)>1e-9;contact=new[:,2]+bot[:,2]-bz
        if np.any(contact[changed]>.000021):raise AssertionError('AI moved a lowest grain vertex above its actual supporting triangle')
        reports.append(dict(object=name,eligible=len(rows),moved_origins=int(changed.sum()),raised=int((dz>1e-9).sum()),lowered=int((dz < -1e-9).sum()),shift_range_m=[float(dz.min(initial=0)),float(dz.max(initial=0))],lowest_vertex_contact_max_m=float(contact[changed].max()) if changed.any() else None,transported=allocation))
        del p,q,new,pi,yaw,sv,final,bot,bxy,bz,cap,lift
    report=dict(scope='Finite-stock surface representation after actual graded geometry/contact',fields=summary(f,x,y,spec),shader=shader_report,particle_changes=reports,prototype_geometry_hash=prototype_sha.hexdigest(),new_particles=0,world_xy_changed=False,particle_identity_materials_scale_unchanged=True,terrain_geometry_changed=False,field_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),elapsed_seconds=time.monotonic()-started,limits='Lag retention and thin-film optical response are bounded illustrative mappings. Real grains remain exact size/shape; contact proof is a lowest-vertex check, not full rigid-body packing. No optical/physical/site validation claim.')
    del sampler,localco,localtri,records,f;gc.collect();print('AI_SEDIMENT_ASSEMBLED',report,flush=True);return report
