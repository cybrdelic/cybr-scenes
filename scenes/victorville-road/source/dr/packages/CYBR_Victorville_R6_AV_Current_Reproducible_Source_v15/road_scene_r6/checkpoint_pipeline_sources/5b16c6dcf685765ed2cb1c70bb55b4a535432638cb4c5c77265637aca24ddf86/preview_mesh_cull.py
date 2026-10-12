"""Non-saving, conservative expanded-frustum triangle/quad culling for previews.
Coordinates, surviving topology, corner normals and shading attributes are copied.
Off-screen indirect transport may differ; this is never native-scene equivalence.
"""
import bpy
import numpy as np

def apply(scene,job):
    if not job.get('preview_cull_terrain_faces'):return None
    assert job.get('engine')=='CYCLES'
    guard=float(job.get('terrain_cull_margin',.20));assert guard>=.20
    scene.view_layers.update() if hasattr(scene.view_layers,'update') else None
    bpy.context.view_layer.update();cam=scene.camera
    assert cam.data.type=='PERSP'
    frame=cam.data.view_frame(scene=scene)
    left,right=min(v.x/-v.z for v in frame),max(v.x/-v.z for v in frame)
    bottom,top=min(v.y/-v.z for v in frame),max(v.y/-v.z for v in frame)
    dx=right-left;dy=top-bottom;left-=guard*dx;right+=guard*dx;bottom-=guard*dy;top+=guard*dy
    names=('Graded shoulder and alluvial plain -1','Graded shoulder and alluvial plain 1','Gravel lag pockets beside shallow runoff arms','Connected drainage / margin gravel bars')
    reports=[]
    for name in names:
        ob=scene.objects.get(name)
        if ob is None:continue
        assert ob.type=='MESH' and not ob.modifiers,'Static unmodified preview mesh expected'
        old=ob.data;n=len(old.vertices);nf=len(old.polygons);nl=len(old.loops)
        co=np.empty((n,3),np.float32);old.vertices.foreach_get('co',co.ravel())
        matrix=np.asarray(cam.matrix_world.inverted()@ob.matrix_world,dtype=np.float64)
        q=co@matrix[:3,:3].T+matrix[:3,3];depth=-q[:,2]
        lv=np.empty(nl,np.int32);old.loops.foreach_get('vertex_index',lv)
        starts=np.empty(nf,np.int32);counts=np.empty(nf,np.int32);old.polygons.foreach_get('loop_start',starts);old.polygons.foreach_get('loop_total',counts)
        keep=np.ones(nf,bool)
        for outside in (q[:,0]<left*depth,q[:,0]>right*depth,q[:,1]<bottom*depth,q[:,1]>top*depth,depth<=0):
            keep &= np.add.reduceat(outside[lv].astype(np.int32),starts)<counts
        del q,depth
        fi=np.flatnonzero(keep)
        if len(fi)==nf:reports.append({'object':name,'faces_before':nf,'faces_after':nf,'unchanged':True});continue
        if len(fi)==0 and job.get('preview_hide_fully_offscreen_terrain'):
            ob.hide_render=True
            reports.append({'object':name,'faces_before':nf,'faces_after':0,'hidden_render_only':True,'geometry_preserved_in_memory':True,'reason':'Every face outside the expanded view frustum; explicit preview-only option'})
            del co,lv,starts,counts,fi
            continue
        assert len(fi)>0,'Do not erase entire source object with this adapter'
        fc=counts[fi];newstarts=np.r_[0,np.cumsum(fc[:-1])].astype(np.int32)
        li=np.repeat(starts[fi]-newstarts,fc)+np.arange(fc.sum(),dtype=np.int32)
        vi,newlv=np.unique(lv[li],return_inverse=True);newlv=newlv.astype(np.int32)
        mesh=bpy.data.meshes.new(old.name+' / bounded preview')
        mesh.vertices.add(len(vi));mesh.vertices.foreach_set('co',co[vi].ravel())
        mesh.loops.add(len(li));mesh.loops.foreach_set('vertex_index',newlv)
        mesh.polygons.add(len(fi));mesh.polygons.foreach_set('loop_start',newstarts);mesh.polygons.foreach_set('loop_total',fc)
        for mat in old.materials:mesh.materials.append(mat)
        for prop,dtype in (('material_index',np.int32),('use_smooth',bool)):
            a=np.empty(nf,dtype);old.polygons.foreach_get(prop,a);mesh.polygons.foreach_set(prop,a[fi])
        mesh.update(calc_edges=True)
        selectors={'POINT':vi,'FACE':fi,'CORNER':li}
        specs={'FLOAT':('value',np.float32,1),'INT':('value',np.int32,1),'BOOLEAN':('value',bool,1),'FLOAT_VECTOR':('vector',np.float32,3),'FLOAT2':('vector',np.float32,2),'FLOAT_COLOR':('color',np.float32,4),'BYTE_COLOR':('color',np.float32,4)}
        copied=[]
        for attr in old.attributes:
            if attr.name=='position' or attr.name.startswith('.') or attr.domain not in selectors:continue
            if attr.data_type not in specs:raise ValueError('Unsupported shading attribute '+attr.name+' '+attr.data_type)
            prop,dtype,width=specs[attr.data_type];a=np.empty((len(attr.data),width),dtype)
            attr.data.foreach_get(prop,a.ravel());b=a[selectors[attr.domain]]
            target=mesh.attributes.get(attr.name) or mesh.attributes.new(attr.name,attr.data_type,attr.domain)
            target.data.foreach_set(prop,b.ravel());copied.append([attr.name,attr.domain,attr.data_type])
        normals=np.empty((nl,3),np.float32);old.corner_normals.foreach_get('vector',normals.ravel())
        mesh.normals_split_custom_set(normals[li])
        check=np.empty((len(vi),3),np.float32);mesh.vertices.foreach_get('co',check.ravel());assert np.array_equal(check,co[vi])
        ob.data=mesh
        reports.append({'object':name,'vertices_before':n,'vertices_after':len(vi),'faces_before':nf,'faces_after':len(fi),'corner_attributes':copied,'coordinates_exact':True,'corner_normals_copied':True})
        if old.users==0:bpy.data.meshes.remove(old)
        del normals,co,lv,starts,counts,fi,fc,li,vi,newlv,check
    return {'expanded_camera_margin':guard,'objects':reports,'scope':'Preview-only conservative offscreen-face omission. Surviving vertices, faces, materials, named shading attributes and corner normals are retained. Offscreen indirect transport may differ. Full source unchanged.'}

def asphalt_lod(scene,job):
    if 'asphalt_preview_grid_stride' not in job:return None
    step=job['asphalt_preview_grid_stride'];assert step==2,'Only2x bounded native-grid preview LOD qualified'
    obs=[ob for ob in scene.objects if ob.name.startswith('Original asphalt native tile ')]
    meshes={ob.data.name:ob.data for ob in obs};records=[]
    for name,old in meshes.items():
        assert len(old.vertices)==513*513 and len(old.polygons)==2*512*512
        assert all(a.name=='position' or a.name.startswith('.') for a in old.attributes), 'Unexpected native tile shading attributes'
        co=np.empty((513*513,3),np.float32);old.vertices.foreach_get('co',co.ravel());g=co.reshape(513,513,3);v=g[::step,::step].reshape(-1,3);n=257
        q=(np.arange(n-1)[:,None]*n+np.arange(n-1)[None,:]).ravel()
        tri=np.concatenate((np.column_stack((q,q+1,q+n+1)),np.column_stack((q,q+n+1,q+n))),axis=0).astype(np.int32)
        mesh=bpy.data.meshes.new(name+' / stride2 preview');mesh.vertices.add(len(v));mesh.vertices.foreach_set('co',v.ravel());mesh.loops.add(tri.size);mesh.loops.foreach_set('vertex_index',tri.ravel());mesh.polygons.add(len(tri));mesh.polygons.foreach_set('loop_start',np.arange(len(tri),dtype=np.int32)*3);mesh.polygons.foreach_set('loop_total',np.full(len(tri),3,np.int32));mesh.polygons.foreach_set('use_smooth',np.ones(len(tri),bool));mesh.update()
        for mat in old.materials:mesh.materials.append(mat)
        coarse=g[::step,::step,2];t=np.arange(513)/step;i=np.minimum(t.astype(np.int32),255);f=t-i;xx,yy=np.meshgrid(f,f);ii,jj=np.meshgrid(i,i)
        a,b,c,d=coarse[jj,ii],coarse[jj,ii+1],coarse[jj+1,ii+1],coarse[jj+1,ii]
        reconstructed=np.where(xx>=yy,a*(1-xx)+b*(xx-yy)+c*yy,a*(1-yy)+c*xx+d*(yy-xx));error=np.abs(reconstructed-g[:,:,2])
        for ob in obs:
            if ob.data==old:ob.data=mesh
        records.append({'source_template':name,'native_vertices':len(co),'preview_vertices':len(v),'native_pitch_m':.25/512,'preview_pitch_m':.25/256,'maximum_local_height_error_m':float(error.max()),'mean_local_height_error_m':float(error.mean()),'source_boundary_zero_height_preserved':bool(np.max(np.abs(g[[0,-1],:,2]))==0)})
        if old.users==0:bpy.data.meshes.remove(old)
    bpy.context.view_layer.update()
    # Return Python interpolation temporaries before Cycles allocates its BVH.
    import gc;gc.collect()
    return {'stride':step,'templates':records,'scope':'In-memory context-preview LOD only. Subsamples original metric native-grid vertices without height amplification. Shared templates, affine transforms and material nodes retained. This changes inter-vertex relief approximation; full source is unchanged.'}
