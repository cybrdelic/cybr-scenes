"""Bounded landscape-only derivative of the pinned native asphalt grid adapter."""
import bpy,numpy as np
def asphalt_lod(scene,job):
    if 'asphalt_context_grid_stride' not in job:return None
    step=job['asphalt_context_grid_stride'];assert step==4,'Only explicit4x context-only native-grid approximation supported'
    obs=[ob for ob in scene.objects if ob.name.startswith('Original asphalt native tile ')]
    meshes={ob.data.name:ob.data for ob in obs};records=[]
    for name,old in meshes.items():
        assert len(old.vertices)==513*513 and len(old.polygons)==2*512*512
        assert all(a.name=='position' or a.name.startswith('.') for a in old.attributes), 'Unexpected native tile shading attributes'
        co=np.empty((513*513,3),np.float32);old.vertices.foreach_get('co',co.ravel());g=co.reshape(513,513,3);v=g[::step,::step].reshape(-1,3);n=129
        q=(np.arange(n-1)[:,None]*n+np.arange(n-1)[None,:]).ravel()
        tri=np.concatenate((np.column_stack((q,q+1,q+n+1)),np.column_stack((q,q+n+1,q+n))),axis=0).astype(np.int32)
        mesh=bpy.data.meshes.new(name+' / stride4 context preview');mesh.vertices.add(len(v));mesh.vertices.foreach_set('co',v.ravel());mesh.loops.add(tri.size);mesh.loops.foreach_set('vertex_index',tri.ravel());mesh.polygons.add(len(tri));mesh.polygons.foreach_set('loop_start',np.arange(len(tri),dtype=np.int32)*3);mesh.polygons.foreach_set('loop_total',np.full(len(tri),3,np.int32));mesh.polygons.foreach_set('use_smooth',np.ones(len(tri),bool));mesh.update()
        for mat in old.materials:mesh.materials.append(mat)
        coarse=g[::step,::step,2];t=np.arange(513)/step;i=np.minimum(t.astype(np.int32),127);f=t-i;xx,yy=np.meshgrid(f,f);ii,jj=np.meshgrid(i,i)
        a,b,c,d=coarse[jj,ii],coarse[jj,ii+1],coarse[jj+1,ii+1],coarse[jj+1,ii]
        reconstructed=np.where(xx>=yy,a*(1-xx)+b*(xx-yy)+c*yy,a*(1-yy)+c*xx+d*(yy-xx));error=np.abs(reconstructed-g[:,:,2])
        assert float(error.max())<.001,'Context approximation exceeds1mm height bound'
        for ob in obs:
            if ob.data==old:ob.data=mesh
        records.append({'source_template':name,'native_vertices':len(co),'preview_vertices':len(v),'native_pitch_m':.25/512,'preview_pitch_m':.25/128,'maximum_local_height_error_m':float(error.max()),'mean_local_height_error_m':float(error.mean()),'source_boundary_zero_height_preserved':bool(np.max(np.abs(g[[0,-1],:,2]))==0)})
        if old.users==0:bpy.data.meshes.remove(old)
    bpy.context.view_layer.update()
    # Return Python interpolation temporaries before Cycles allocates its BVH.
    import gc;gc.collect()
    return {'stride':step,'templates':records,'scope':'In-memory stride4 landscape-context approximation only; matched baseline and candidate require identical settings. Not a native texture-detail proof. Subsamples original metric native-grid vertices without height amplification. Shared templates, affine transforms and material nodes retained. This changes inter-vertex relief approximation; full source is unchanged.'}
