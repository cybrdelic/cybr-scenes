"""Actual fixed Y mesh surface queries for the bounded loose-film event."""
import numpy as np
import prepare_physical_lenses as u

def partial_height(patch,xy):
    shape=np.shape(xy)[:-1];p=np.asarray(xy,float).reshape(-1,2);answer=np.full(len(p),np.nan)
    keys,inverse=np.unique(np.floor(p/patch.cell).astype(np.int32),axis=0,return_inverse=True)
    for number,key in enumerate(keys):
        rows=np.flatnonzero(inverse==number);indices=patch.bins.get(tuple(key))
        if indices is None:continue
        t=patch.tri[indices];a,b,c=t[:,0],t[:,1],t[:,2];v0,v1=b[:,:2]-a[:,:2],c[:,:2]-a[:,:2];det=v0[:,0]*v1[:,1]-v0[:,1]*v1[:,0]
        q=p[rows,None,:]-a[None,:,:2];s=(q[...,0]*v1[:,1]-q[...,1]*v1[:,0])/det;t=(v0[:,0]*q[...,1]-v0[:,1]*q[...,0])/det
        inside=(s>=-2e-7)&(t>=-2e-7)&(s+t<=1+2e-7);z=a[:,2]+s*(b[:,2]-a[:,2])+t*(c[:,2]-a[:,2]);z[~inside]=-np.inf;best=z.max(axis=1);answer[rows]=np.where(np.isfinite(best),best,np.nan)
    return answer.reshape(shape)

def sample(scene,xy,bounds):
    ground=u.exact_patch(scene.objects[u.GROUND],bounds,260000)
    road=u.exact_patch(scene.objects['Crowned asphalt crust / longitudinal rise'],bounds,260000)
    zg=partial_height(ground,xy);zr=partial_height(road,xy);flat=np.asarray(xy).reshape(-1,2);z=zr.ravel();cache={};tile_queries=0
    for ob in scene.objects:
        if not ob.name.startswith('Original asphalt native tile '):continue
        matrix=np.asarray(ob.matrix_world,float);assert np.max(np.abs(matrix[:2,:2]-np.eye(2)))<1e-7 and np.max(np.abs(matrix[:2,2]))<1e-7
        local=flat-matrix[:2,3];mask=(local[:,0]>=-1e-8)&(local[:,0]<=.25+1e-8)&(local[:,1]>=-1e-8)&(local[:,1]<=.25+1e-8)
        if not np.any(mask):continue
        if ob.data.name not in cache:
            assert len(ob.data.vertices)==513*513 and len(ob.data.polygons)==2*512*512
            cache[ob.data.name]=u.read_coordinates(ob.data).reshape(513,513,3)
        g=cache[ob.data.name];t=np.clip(local[mask]/.25*512,0,512);ij=np.minimum(t.astype(int),511);f=t-ij;i,j=ij[:,0],ij[:,1];fx,fy=f[:,0],f[:,1]
        a,b,c,d=g[j,i,2],g[j,i+1,2],g[j+1,i+1,2],g[j+1,i,2]
        height=np.where(fx>=fy,a*(1-fx)+b*(fx-fy)+c*fy,a*(1-fy)+c*fx+d*(fy-fx))
        worldz=local[mask,0]*matrix[2,0]+local[mask,1]*matrix[2,1]+height*matrix[2,2]+matrix[2,3]
        z[mask]=np.fmax(z[mask],worldz);tile_queries+=int(mask.sum())
    zr=z.reshape(zg.shape);highest=np.fmax(zg,zr);assert np.isfinite(highest).all(),'Actual road/ground surface has unhandled query gaps'
    pavement=np.isfinite(zr)&(~np.isfinite(zg)|(zr>=zg-.00002))
    return highest,pavement,dict(ground_triangles=len(ground.triangles),road_base_triangles=len(road.triangles),native_tile_queries=tile_queries,native_templates_read=len(cache),finite_surface_queries=int(highest.size),surface='Actual Y ground/base loop triangles and exact native tile A-C triangles; topmost contact surface selected',ground_above_road_queries=int(np.sum(np.isfinite(zg)&np.isfinite(zr)&~pavement)))
