"""AR in-memory physical edge integration, before the mandatory AQ support pass.

Caller runs this once after AH/AC/AL/AI and before continuous_contact_aq,
assemble_road_margin_aq and current_contact_film_aq. No save/load/render occurs.
Original materials, bitmap sources and world texture coordinates are untouched.
An error invalidates this disposable candidate scene; do not publish it.
"""
from pathlib import Path
import gc,json,time
import numpy as np
from fractured_boundary_ar import (FractureSpec,actual_left_boundary,build_boundary,
    prepare_object,require,_read,ATTRIBUTE_TYPES,TOPOLOGY_ATTRIBUTES,Boundary,upper_envelope)

ROAD='Crowned asphalt crust / longitudinal rise'
GROUND='Graded shoulder and alluvial plain -1'
SECTION='AC supported pavement section'
WALL='Broken exposed asphalt edge -1'
PARTICLES='AC anchored subsurface aggregate'


def world_box(obj):
    p=np.asarray(obj.bound_box,float);m=np.asarray(obj.matrix_world,float)
    return p@m[:3,:3].T+m[:3,3]


def overlaps_repair(obj,boundary):
    p=world_box(obj);lo=p.min(0);hi=p.max(0)
    if hi[1]<boundary.y[0] or lo[1]>boundary.y[-1]:return False
    y=np.r_[max(lo[1],boundary.y[0]),min(hi[1],boundary.y[-1]),boundary.y[(boundary.y>=lo[1])&(boundary.y<=hi[1])]]
    return lo[0]<boundary.x_edge(y).max()+1e-5 and hi[0]>boundary.old_x.min()-.02


def preflight_owners(scene,boundary):
    """Native templates are shared and immutable; prove that none enters loss."""
    tiles=[];markings=[];dust=[]
    for ob in scene.objects:
        if ob.type!='MESH':continue
        if ob.name.startswith('Original asphalt native tile '):
            if overlaps_repair(ob,boundary):
                raise ValueError('Native asphalt tile overlaps AR loss; exact instance clipping required before proceeding: '+ob.name)
            tiles.append(ob.name)
        elif ('marking' in ob.name.lower() or 'paint' in ob.name.lower()) and not ob.hide_render:
            require(not overlaps_repair(ob,boundary),'AR repair reaches actual marking: '+ob.name)
            markings.append(ob.name)
        elif ob.name.startswith('Wind and grading dust deposit') and not ob.hide_render and overlaps_repair(ob,boundary):dust.append(ob)
    return dict(native_tiles_tested=len(tiles),native_tile_loss_overlap_count=0,markings_tested=markings),dust


class ActualRoadHeights:
    """Small exact source slabs; preserves existing microrelief, no new height."""
    def __init__(self,road):
        road.data.calc_loop_triangles();self.co=_read(road.data.vertices,'co',3)
        self.tri=_read(road.data.loop_triangles,'vertices',3,np.int32)
    def __call__(self,xy):
        from continuous_contact_aq import road_slab
        q=np.asarray(xy,float).reshape(-1,2);z=np.empty(len(q))
        # 0.1 m slabs keep the dense AC patch under the existing sampler cap.
        keys=np.floor(q[:,1]/.1).astype(int)
        for key in np.unique(keys):
            ids=np.flatnonzero(keys==key);lo,hi=key*.1,(key+1)*.1
            road=road_slab(self.co,self.tri,lo,hi,float(q[ids,0].max())+.008)
            z[ids]=road.sample(road.co[:,2],q[ids])
        return z


def append_ground_bridge(old,plan):
    """Exact append through one final-size buffer per attribute, never two.

    Numerical buffer estimate excludes Blender-native source/candidate storage;
    caller's locked process RSS guard also covers the temporary native clone.
    """
    import bpy
    nv,nl,nf=len(old.vertices),len(old.loops),len(old.polygons)
    av=np.asarray(plan.additions);faces=np.asarray(plan.triangles,np.int32)
    final_sizes={'POINT':nv+len(av),'CORNER':nl+3*len(faces),'FACE':nf+len(faces)}
    max_buffer=max((nv+len(av))*12,(nl+3*len(faces))*12,(nf+len(faces))*4)
    schema=[]
    for a in old.attributes:
        if a.name in TOPOLOGY_ATTRIBUTES:continue
        require(a.data_type in ATTRIBUTE_TYPES and a.domain in {'POINT','CORNER','FACE','EDGE'},'Unsupported ground field '+a.name)
        prop,size,dtype,discrete=ATTRIBUTE_TYPES[a.data_type]
        if a.domain!='EDGE':max_buffer=max(max_buffer,final_sizes[a.domain]*size*np.dtype(dtype).itemsize)
        schema.append((a.name,a.domain,a.data_type,prop,size,dtype,discrete))
    extra=sum(getattr(plan,k).nbytes for k in ('additions','triangles','addition_source_vertex_pairs','addition_weights','triangle_source','corner_source_vertex_pairs','corner_weights','corner_source_triangles'))
    estimate=(max_buffer+extra+24*1024**2)/1024**2
    require(estimate<190,'Ground one-buffer append estimate exceeds 190 MiB')
    old.calc_loop_triangles()
    used=np.unique(np.r_[plan.triangle_source,plan.corner_source_triangles.ravel()])
    ts=[old.loop_triangles[int(i)] for i in used]
    tri=np.asarray([t.vertices[:] for t in ts],np.int32);tl=np.asarray([t.loops[:] for t in ts],np.int32);tp=np.asarray([t.polygon_index for t in ts],np.int32);del ts
    parents=tp[np.searchsorted(used,plan.triangle_source)]
    cs=np.searchsorted(used,plan.corner_source_triangles);cp=plan.corner_source_vertex_pairs;cw=plan.corner_weights
    corner_ids=np.empty(cp.shape,np.int32)
    for k in range(2):
        matches=tri[cs]==cp[:,:,k,None]
        require(np.all(matches.any(2)),'Bridge corner source is not on actual supplying triangle')
        corner_ids[:,:,k]=np.take_along_axis(tl[cs],matches.argmax(2)[:,:,None],2)[:,:,0]
    # Only local source/target facets are needed to transport original normal
    # detail into the new bank geometry; no global normal or XYZ duplicate.
    ids=np.unique(tri);xyz=np.asarray([old.vertices[int(i)].co[:] for i in ids],float)
    source_corner_xyz=xyz[np.searchsorted(ids,tri)][cs]
    ids=np.unique(faces);xyz=np.asarray([old.vertices[int(i)].co[:] if i<nv else av[int(i)-nv] for i in ids],float)
    target_face_xyz=xyz[np.searchsorted(ids,faces)]
    del tri,tl,tp,cs,used,ids,xyz
    new=old.copy();new.name=old.name+' / AR actual rim support extension'
    try:
        out=np.empty((nv+len(av),3),np.float32);old.vertices.foreach_get('co',out[:nv].ravel());out[nv:]=av
        new.vertices.add(len(av));new.vertices.foreach_set('co',out.ravel());del out
        out=np.empty(nl+faces.size,np.int32);old.loops.foreach_get('vertex_index',out[:nl]);out[nl:]=faces.ravel();new.loops.add(faces.size);new.loops.foreach_set('vertex_index',out);del out
        new.polygons.add(len(faces))
        for prop,tail in [('loop_start',nl+np.arange(len(faces),dtype=np.int32)*3),('loop_total',np.full(len(faces),3,np.int32))]:
            out=np.empty(nf+len(faces),np.int32);old.polygons.foreach_get(prop,out[:nf]);out[nf:]=tail;new.polygons.foreach_set(prop,out);del out
        for prop,dtype in [('material_index',np.int32),('use_smooth',bool)]:
            out=np.empty(nf+len(faces),dtype);old.polygons.foreach_get(prop,out[:nf]);out[nf:]=out[parents];new.polygons.foreach_set(prop,out);del out
        pairs=plan.addition_source_vertex_pairs;weights=plan.addition_weights
        old_sizes={'POINT':nv,'CORNER':nl,'FACE':nf}
        for name,domain,kind,prop,size,dtype,discrete in schema:
            if domain=='EDGE' or name=='material_index':continue
            count=old_sizes[domain];shape=(final_sizes[domain],size) if size>1 else (final_sizes[domain],)
            out=np.empty(shape,dtype);old.attributes[name].data.foreach_get(prop,out[:count].ravel())
            if domain=='POINT':
                out[count:]=out[pairs[np.arange(len(pairs)),weights.argmax(1)]] if discrete else np.einsum('ni,ni...->n...',weights,out[pairs])
            elif domain=='FACE':out[count:]=out[parents]
            else:
                src=out[corner_ids]
                tail=src[np.arange(len(src))[:,None],np.arange(3)[None,:],cw.argmax(2)] if discrete else np.einsum('nki,nki...->nk...',cw,src)
                out[count:]=tail.reshape((-1,)+out.shape[1:]);del src,tail
            new.attributes[name].data.foreach_set(prop,out.ravel());del out
        new.update(calc_edges=True);require(not new.validate(clean_customdata=False),'Blender repaired appended ground')
        normals=np.empty((nl+3*len(faces),3),np.float32)
        # One full buffer; old detailed source normals go directly to their
        # exact prefix and the new tail receives source-provenance transport.
        old.corner_normals.foreach_get('vector',normals[:nl].ravel())
        detail=np.einsum('nki,nkij->nkj',cw,normals[corner_ids])
        from soil_rim_bridge_ar import transport_corner_normals
        normals[nl:]=transport_corner_normals(detail,source_corner_xyz,target_face_xyz).reshape(-1,3)
        new.normals_split_custom_set(normals);del normals,detail,corner_ids
        plan.report['new_corner_normals']='Exact source-corner interpolation plus shortest-arc source-facet to bridge-facet rotation; AQ transports final bank change'
        return new,dict(plan.report,estimated_peak_numeric_buffer_mib=estimate,native_blender_clone_included_in_process_RSS_guard=True)
    except Exception:
        bpy.data.meshes.remove(new);raise


def new_section(old,boundary,top):
    """Same 24/38 mm AC stratigraphy, newly seated on exact clipped top rim."""
    import bpy
    y,x=boundary.y,boundary.x;z=np.asarray(top)
    depth=np.array([0.,.024,.038]);v=np.empty((len(y),3,3))
    # 0.6 mm outward batter gives finite actual XY section ownership. It stays
    # buried below the source-ground bridge except at inherited exposure.
    v[:,:,0]=x[:,None]-.0006*depth[None,:]/.038;v[:,:,1]=y[:,None];v[:,:,2]=z[:,None]-depth
    q=np.arange(len(y)-1,dtype=np.int32)*3;faces=[];layers=[]
    for j in range(2):
        faces.extend([np.c_[q+j,q+3+j,q+4+j],np.c_[q+j,q+4+j,q+1+j]])
        layers.extend([np.full(len(q),j,np.int32),np.full(len(q),j,np.int32)])
    faces=np.concatenate(faces);layers=np.concatenate(layers)
    mesh=bpy.data.meshes.new('AR fractured supported pavement section')
    mesh.vertices.add(v.size//3);mesh.vertices.foreach_set('co',v.ravel());mesh.loops.add(faces.size);mesh.loops.foreach_set('vertex_index',faces.ravel());mesh.polygons.add(len(faces));mesh.polygons.foreach_set('loop_start',np.arange(len(faces),dtype=np.int32)*3);mesh.polygons.foreach_set('loop_total',np.full(len(faces),3,np.int32))
    for m in old.materials:mesh.materials.append(m)
    share=_read(old.attributes['asphalt_share'].data,'value');tint=_read(old.attributes['macro_tint'].data,'color',4)
    s=np.tile([float(share.max()),float(share.max()),float(share.min())],len(y));colors=np.tile(np.stack([tint[np.argmax(share)],tint[np.argmax(share)],tint[np.argmin(share)]]),(len(y),1))
    for name,dtype,domain,prop,val in [('asphalt_share','FLOAT','POINT','value',s),('macro_tint','FLOAT_COLOR','POINT','color',colors),('ac_section_layer','INT','FACE','value',layers)]:
        a=mesh.attributes.new(name,dtype,domain);a.data.foreach_set(prop,np.asarray(val).ravel())
    mesh.update(calc_edges=True);require(not mesh.validate(clean_customdata=False),'New physical section is invalid')
    return mesh,dict(top_vertices=len(y),triangles=len(faces),surface_course_m=.024,section_m=.038,source_materials=[m.name for m in old.materials],new_materials=0,top_matches_actual_source=True)


def write_failure_fixture(directory,ground_co,ground_tri,road_source,boundary,support,error):
    """Small exact actual-source replay on a failed guard, never a full scene."""
    import shutil
    from context_mesh_refine_ab import intersecting_triangles
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    require(shutil.disk_usage(directory).free>160*1024**2,'Insufficient reserve for bounded AR diagnostic')
    bounds=(float(min(boundary.old_x.min(),support.x.min()))-.12,-2.94,float(boundary.y[0])-.30,float(boundary.y[-1])+.30)
    arrays={};size=0
    for name,co,tri in [('ground',ground_co,ground_tri),('road',road_source.co,road_source.tri)]:
        ids=intersecting_triangles(co,tri,bounds);local=tri[ids];used,iv=np.unique(local,return_inverse=True)
        arrays[name+'_co']=co[used].copy();arrays[name+'_triangles']=iv.reshape(-1,3).astype(np.int32)
        arrays[name+'_source_vertex_ids']=used.astype(np.int32);arrays[name+'_source_triangle_ids']=ids.astype(np.int32)
    arrays.update(boundary_y=boundary.y,boundary_x=boundary.x,old_boundary_y=boundary.old_y,old_boundary_x=boundary.old_x,support_y=support.y,support_x=support.x)
    size=sum(v.nbytes for v in arrays.values());require(size<48*1024**2,'AR diagnostic exceeds48MiB source-array cap')
    dest=directory/'AR_FAILURE_SOURCE.npz';np.savez_compressed(dest,**arrays)
    report=dict(error_type=type(error).__name__,message=str(error),bounds_xy_m=list(bounds),source_array_bytes=size,npz=str(dest),
                arrays={k:list(v.shape) for k,v in arrays.items()},topology=getattr(error,'diagnostics',None),
                provenance='Actual pre-AR mesh subset with explicit original vertex/triangle IDs; no coordinate welding, source edits, smoothing or synthetic support')
    (directory/'AR_FAILURE_TOPOLOGY.json').write_text(json.dumps(report,indent=2))
    print('AR_FAILURE_SOURCE_CAPTURED',json.dumps({k:report[k] for k in ('message','source_array_bytes','npz')}),flush=True)
    return report


def apply(scene,config=None,output_directory=None):
    """Complete AR owner/soil/section geometry; caller MUST run existing AQ next."""
    import bpy
    from soil_rim_bridge_ar import plan_soil_bridge,BridgeSpec
    config=config or {};spec=(config.get('spec') or FractureSpec()).validate();started=time.monotonic()
    road=scene.objects[ROAD];ground=scene.objects[GROUND];section=scene.objects[SECTION]
    require(not road.get('ar_fractured_boundary_applied',False),'AR must start from fresh pre-AQ source')
    for ob in (road,ground,section):
        require(not ob.modifiers and np.allclose(np.asarray(ob.matrix_world),np.eye(4),atol=1e-9),'Actual identity-matrix owners required')
    height_path=config.get('height_path')
    require(height_path,'AR requires the explicitly pinned original GeometryHeight path')
    print('AR_STAGE actual_source_boundary',flush=True)
    source=ActualRoadHeights(road);y,x=actual_left_boundary(source.co,source.tri,spec);boundary=build_boundary(y,x,height_path,spec)
    print('AR_STAGE ownership_preflight',flush=True)
    owners,dust=preflight_owners(scene,boundary)
    top=source(np.c_[boundary.x,boundary.y])
    ground.data.calc_loop_triangles();gc0=_read(ground.data.vertices,'co',3);gt=_read(ground.data.loop_triangles,'vertices',3,np.int32)
    # Soil is a continuous bank beneath the fine asphalt fracture, not a copy
    # of each aggregate notch. A conservative support majorant covers every
    # removed cell while keeping AQ's actual 360k-triangle audit bound intact.
    sx,sh=upper_envelope(boundary.y,boundary.x)
    sy=np.unique(np.r_[np.linspace(boundary.y[0],boundary.y[-1],int(np.ceil((boundary.y[-1]-boundary.y[0])/.025))+1),boundary.y[sh]])
    support=Boundary(sy,np.interp(sy,boundary.y,sx),boundary.old_y,boundary.old_x,{})
    require(np.all(np.interp(boundary.y,support.y,support.x)>=boundary.x-1e-10),'Soil support majorant misses an actual fracture knot')
    require(float(support.x.max())+.004<=-3.04-1e-6,'Soil support extends outside AQ exact audit domain')
    print('AR_STAGE actual_soil_rim',flush=True)
    try:
        bridge=plan_soil_bridge(gc0,gt,support,source,spec=BridgeSpec(rim_search_width_m=.10))
    except ValueError as error:
        if output_directory:write_failure_fixture(output_directory,gc0,gt,source,boundary,support,error)
        raise
    from context_mesh_refine_ab import intersecting_triangles
    old_local=len(intersecting_triangles(gc0,gt,(-4.05,-2.94,-.45,15.75)))
    require(old_local+len(bridge.triangles)<=360000,'AR bridge would exceed existing AQ local triangle cap')
    bridge.report['AQ_local_triangle_bound_after']=old_local+len(bridge.triangles)
    bridge.report['support_contour']='Conservative continuous 25 mm bank support majorant, beneath full grain-scale asphalt boundary'
    del gc0,gt;gc.collect()
    # Finish geometric support planning before changing any owner. No AQ or film
    # result from the old footprint may be reused after this point.
    section_mesh=None;section_report=None
    gc.collect()
    edits=[];old_meshes=[]
    try:
        # Sequential preparations bound peak memory. Original meshes are kept as
        # rollback references, not copies; successful cleanup releases orphans.
        for ob in [road]+[scene.objects[n] for n in (WALL,PARTICLES) if n in scene.objects]+dust:
            if ob is not road and not overlaps_repair(ob,boundary):continue
            print('AR_STAGE clip_owner',ob.name,flush=True)
            result=prepare_object(ob,boundary,spec)
            if ob is road:
                additions=result['plan'].additions;onrim=(abs(additions[:,0]-boundary.x_edge(additions[:,1]))<1e-8)&(additions[:,1]>=boundary.y[0])&(additions[:,1]<=boundary.y[-1])
                ry=np.unique(np.r_[boundary.y,additions[onrim,1]]);rx=boundary.x_edge(ry)
                # Source-triangle crossings are real relief knots, not optional
                # decimation: carry every one into the replacement section.
                rb=Boundary(ry,rx,boundary.old_y,boundary.old_x,boundary.report)
                section_mesh,section_report=new_section(section.data,rb,source(np.c_[rx,ry]))
                del source;gc.collect()
            old=ob.data;ob.data=result['mesh'];old_meshes.append((ob,old));edits.append(dict(object=ob.name,**result['report']));del result;gc.collect()
        print('AR_STAGE append_ground_bridge',len(bridge.additions),len(bridge.triangles),flush=True)
        gm,bridge_report=append_ground_bridge(ground.data,bridge);old_meshes.append((ground,ground.data));ground.data=gm;del bridge;gc.collect()
        old_meshes.append((section,section.data));section.data=section_mesh
        road['ar_fractured_boundary_applied']=True
        report=dict(boundary=boundary.report,owners=owners,owner_edits=edits,ground_bridge=bridge_report,section=section_report,
                    elapsed_seconds=time.monotonic()-started,scene_assigned=True,contact_audit_pending=True,
                    mandatory_next_hooks=['continuous_contact_aq','assemble_road_margin_aq','current_contact_film_aq'],
                    old_film_inventory_reusable=False,original_source_materials_and_world_phase_unchanged=True,
                    geometry_counts_after={ob.name:dict(vertices=len(ob.data.vertices),polygons=len(ob.data.polygons),loops=len(ob.data.loops)) for ob in (road,ground,section)},
                    limits=['Measured inward envelope is authored edge repair, not sediment mass or site reconstruction','Full AQ overlap and final-surface coverage audits must pass before any render or acceptance'])
        for ob,old in old_meshes:
            if old.users==0:bpy.data.meshes.remove(old)
        if output_directory:Path(output_directory,'FRACTURED_BOUNDARY_AR.json').write_text(json.dumps(report,indent=2))
        print('FRACTURED_BOUNDARY_AR',report,flush=True);return report
    except Exception:
        for ob,old in reversed(old_meshes):
            candidate=ob.data;ob.data=old
            if candidate.users==0:bpy.data.meshes.remove(candidate)
        if section_mesh is not None and section_mesh.users==0:bpy.data.meshes.remove(section_mesh)
        raise
