"""Persist full Z-shear for shared native tiles through an identity parent.

Object.matrix_world assignment is NOT a durable shear representation: Blender
reconstructs a basis from location/rotation/scale. matrix_parent_inverse is a
full affine matrix and survives evaluation and file reload. Neither geometry
nor materials are edited here. Caller owns saving/reloading and rendering.
"""
from __future__ import annotations
import numpy as np
import bpy
from mathutils import Matrix
from tiled_relief_math import tile_matrix

PREFIX='Original asphalt native tile '
PARENT='Native relief affine datum / identity parent'


def tile_objects(scene,bounds):
    xmin,xmax,ymin,ymax=bounds
    nx,ny=round((xmax-xmin)/.25),round((ymax-ymin)/.25)
    wanted={(i,j):f'{PREFIX}{i:02d} {j:02d}' for j in range(ny) for i in range(nx)}
    observed={ob.name:ob for ob in scene.objects if ob.name.startswith(PREFIX)}
    if set(observed)!=set(wanted.values()):raise ValueError('Saved native tile grid differs from requested bounds')
    objects={key:observed[name] for key,name in wanted.items()}
    for ob in objects.values():
        if ob.type!='MESH' or len(ob.data.vertices)!=513*513 or ob.modifiers or ob.data.shape_keys or ob.constraints:
            raise ValueError('Native tile topology or object stack changed')
    return objects


def install_affine_parent(scene,bounds):
    objects=tile_objects(scene,bounds)
    if scene.objects.get(PARENT):raise ValueError('Affine parent already exists; do not repair twice')
    if any(ob.parent for ob in objects.values()):raise ValueError('Expected the original unparented tiles')
    parent=bpy.data.objects.new(PARENT,None);scene.collection.objects.link(parent)
    parent.matrix_world=Matrix.Identity(4)
    parent.empty_display_type='PLAIN_AXES';parent.empty_display_size=.05
    parent['contract']='Identity world datum; full per-tile affine transform is stored in matrix_parent_inverse'
    xmin,_,ymin,_=bounds
    for (i,j),ob in objects.items():
        transform=Matrix(tile_matrix(xmin+i*.25,ymin+j*.25))
        ob.parent=parent
        ob.matrix_basis=Matrix.Identity(4)
        ob.matrix_parent_inverse=transform
        ob['affine_transform_contract']='parent_world(identity) @ full_affine_parent_inverse @ basis(identity)'
    bpy.context.view_layer.update()
    return validate_affine_tiles(scene,bounds,require_parent=True)


def validate_affine_tiles(scene,bounds,require_parent=True):
    """Read actual evaluated matrices and ALL native boundary samples."""
    objects=tile_objects(scene,bounds)
    bpy.context.view_layer.update();depsgraph=bpy.context.evaluated_depsgraph_get()
    parent=scene.objects.get(PARENT)
    if require_parent and (not parent or not np.array_equal(np.asarray(parent.matrix_world),np.eye(4))):
        raise ValueError('Missing or moved affine identity parent')
    xmin,_,ymin,_=bounds;transforms={};matrix_error=0.;normal_error=0.;cache={}
    for key,ob in objects.items():
        i,j=key
        if require_parent and (ob.parent!=parent or not np.array_equal(np.asarray(ob.matrix_basis),np.eye(4))):
            raise ValueError('Tile parent/basis no longer represents the exact affine contract')
        expected=tile_matrix(xmin+i*.25,ymin+j*.25)
        actual=np.asarray(ob.evaluated_get(depsgraph).matrix_world,dtype=np.float64)
        transforms[key]=actual;matrix_error=max(matrix_error,float(np.max(abs(actual-expected))))
        n=np.linalg.inv(actual[:3,:3]).T@np.array([0.,0.,1.]);n/=np.linalg.norm(n)
        wanted=np.array([-expected[2,0],-expected[2,1],1.]);wanted/=np.linalg.norm(wanted)
        normal_error=max(normal_error,float(np.max(abs(n-wanted))))
        if ob.data.name not in cache:
            co=np.empty((len(ob.data.vertices),3),dtype=np.float32);ob.data.vertices.foreach_get('co',co.ravel())
            cache[ob.data.name]=co.reshape(513,513,3)
    seam=np.zeros(3);pairs=0
    for (i,j),a in objects.items():
        for di,dj in ((1,0),(0,1)):
            key=(i+di,j+dj)
            if key not in objects:continue
            b=objects[key];va,vb=cache[a.data.name],cache[b.data.name]
            aa,bb=(va[:,-1],vb[:,0]) if di else (va[-1],vb[0])
            ma,mb=transforms[i,j],transforms[key]
            aw=aa@ma[:3,:3].T+ma[:3,3];bw=bb@mb[:3,:3].T+mb[:3,3]
            seam=np.maximum(seam,np.max(abs(aw-bw),axis=0));pairs+=1
    if matrix_error>2e-7 or normal_error>2e-7 or max(seam)>5e-7:
        raise ValueError(f'Evaluated affine gate failed: matrix {matrix_error}; normal {normal_error}; seam {seam}')
    return dict(tile_count=len(objects),shared_templates=len(cache),evaluated_max_matrix_error=matrix_error,
                evaluated_max_broad_normal_component_error=normal_error,evaluated_max_seam_xyz_m=seam.tolist(),
                checked_adjacent_pairs=pairs,boundary_samples_per_pair=513,
                transform_storage='identity parent, full matrix_parent_inverse, identity matrix_basis',
                geometry_changed=False,materials_changed=False)
