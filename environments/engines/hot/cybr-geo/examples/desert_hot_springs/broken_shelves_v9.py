"""Disconnected porous carbonate outcrops extracted from an authored 3-D field.

These are solid isosurfaces, not texture decals, image layers, or mineral-growth
simulation. Only selected shore arcs carry raised shelf geometry.
"""
from __future__ import annotations
import numpy as np
from skimage.measure import marching_cubes
from build_scene_v4 import noise,fbm,mesh_normals,join

def build_broken_shelves(pools,poolq,debug_path=None):
    vertices=[];faces=[];tiles=0;offset=0;seam_ids={};welded=0;nonedge_seam_vertices=0
    for index,(cx,cy,rx,ry,level,depth) in enumerate(pools):
        step=.006;tile=step*256
        lo=np.floor(np.array([cx-rx*1.45,cy-ry*1.45])/tile)*tile
        hi=np.ceil(np.array([cx+rx*1.45,cy+ry*1.45])/tile)*tile
        zz=level+np.arange(-4,37)*step
        for x0 in np.arange(lo[0],hi[0]-.01,tile):
            for y0 in np.arange(lo[1],hi[1]-.01,tile):
                xs=x0+np.arange(257)*step;ys=y0+np.arange(257)*step
                xx,yy=np.meshgrid(xs,ys,indexing='ij')
                q=poolq(xx,yy,index);d=(q-1)*rx
                if d.min()>.5 or d.max()<-.30:continue
                theta=np.arctan2((yy-cy)/ry,(xx-cx)/rx)
                support=np.full_like(d,-1e6)
                for center,width in [(-2.43,.30),(-1.51,.22),(.39,.27),(2.31,.25)]:
                    angle=np.arctan2(np.sin(theta-center-.14*index),np.cos(theta-center-.14*index))
                    support=np.maximum(support,1-(angle/width)**4)
                if support.max()<-.2:continue
                lower=-.015-.028*noise(xx*3.3,yy*3.7)
                upper=.23+.11*noise(xx*2.8+3,yy*3.1)
                radial=np.maximum(lower-d,d-upper)
                center=level+.044+.006*fbm(xx*3.1,yy*3.9,4)
                thick=.028+.005*noise(xx*8.3,yy*8.1)
                X=xx[:,:,None];Y=yy[:,:,None];Z=zz[None,None,:]
                field=np.maximum(np.abs(Z-center[:,:,None])-thick[:,:,None],radial[:,:,None]*.37)
                field=np.maximum(field,-support[:,:,None]*.080)
                field+=.004*noise(X*21.3,Y*22.6,Z*27.1)
                field+=.002*noise(X*67.1,Y*61.2,Z*64.9)
                # Real cavities and thin bridges, rather than painted dark dots.
                field+=.024*np.maximum(noise(X*44.2+23,Y*43.7-16,Z*47.1+4)-.12,0)**1.2
                # Through-cracks interrupt long arcs instead of creating a raised collar.
                field=np.maximum(field,(-.08-noise(X*5.3+13,Y*5.7-7))*.055)
                if field.min()>=0 or field.max()<=0:continue
                # Extract in integer voxel coordinates, so shared vertices can
                # be welded by lattice EDGE ID rather than spatial rounding.
                # Rounding all positions merged nearby opposite pore surfaces
                # and made the earlier candidate nonmanifold.
                local,f,_,_=marching_cubes(np.asarray(field,dtype=np.float32),0,gradient_direction='ascent',allow_degenerate=False)
                local=local.astype(np.float64)
                ids=np.arange(len(local),dtype=np.int64)+offset
                on_seam=(local[:,0]==0)|(local[:,0]==256)|(local[:,1]==0)|(local[:,1]==256)
                ox=int(round(x0/step));oy=int(round(y0/step))
                for vi in np.flatnonzero(on_seam):
                    point=local[vi]
                    fractional=np.abs(point-np.rint(point))>1e-6
                    count=int(fractional.sum())
                    if count==0:
                        cell=np.rint(point).astype(np.int64);axis=3
                    elif count==1:
                        axis=int(np.argmax(fractional));cell=np.rint(point).astype(np.int64)
                        cell[axis]=int(np.floor(point[axis]))
                    else:
                        # Lewiner cell-interior vertices are not edge vertices.
                        # They normally cannot be on a tile boundary; never
                        # merge them with a nearby edge merely by tolerance.
                        nonedge_seam_vertices+=1
                        continue
                    key=(index,int(cell[0]+ox),int(cell[1]+oy),int(cell[2]),axis)
                    previous=seam_ids.get(key)
                    if previous is not None:ids[vi]=previous;welded+=1
                    else:seam_ids[key]=int(ids[vi])
                world=local*step+np.array([x0,y0,zz[0]])
                vertices.append(world);faces.append(ids[f]);offset+=len(local);tiles+=1
    if not vertices:raise RuntimeError('The carbonate field produced no geometry')
    import trimesh
    v=np.concatenate(vertices);f=np.concatenate(faces)
    used,inverse=np.unique(f,return_inverse=True);v=v[used];f=inverse.reshape(-1,3)
    mesh=trimesh.Trimesh(v,f,process=False)
    mesh.update_faces(mesh.unique_faces())
    mesh.update_faces(mesh.nondegenerate_faces(height=1e-12))
    mesh.remove_unreferenced_vertices()
    if mesh.volume<0:mesh.faces=mesh.faces[:,::-1]
    v=np.asarray(mesh.vertices);f=np.asarray(mesh.faces);n=mesh_normals(v,f)
    topology={'watertight':bool(mesh.is_watertight),'winding_consistent':bool(mesh.is_winding_consistent),'signed_volume_m3':float(mesh.volume)}
    if debug_path is not None:np.savez_compressed(debug_path,vertices=v,faces=f)
    if not topology['watertight'] or not topology['winding_consistent']:raise RuntimeError('Porous shelf topology: '+str(topology))
    return v,f,n,{'field_tiles':tiles,'lattice_spacing_m':.006,'placement':'Selected disconnected shoreline arcs','tile_weld':'Shared voxel-edge identities, not distance rounding','shared_boundary_vertices_welded':welded,'nonedge_boundary_vertices':nonedge_seam_vertices,'mineral_growth_simulated':False,**topology}
