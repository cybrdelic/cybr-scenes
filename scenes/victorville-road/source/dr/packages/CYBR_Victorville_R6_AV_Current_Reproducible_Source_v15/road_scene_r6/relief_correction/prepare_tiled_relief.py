#!/usr/bin/env python3
"""UNRENDERED optional shared-tile asphalt candidate. Never calls a render.

Cloud/CPU only. Source scene and material assets are immutable. New artifacts
must stay beside this script. The original interior specimen is not modified.
"""
from __future__ import annotations
import os
for key in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[key]='2'
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import numpy as np
import bpy
from mathutils import Matrix
sys.path.insert(0,str(Path(__file__).resolve().parent))
from prepare_interior_relief import (coordinates,attributes,verify_source_grid,
                                    verify_packed_shader,sha256,patch_material,BASE_NORMAL,ROAD)
from relief_math import HEIGHT_SHA256,HEIGHT_SCALE_M,TILE_M,zipper,footprint_weight
from tiled_relief_math import SourceGrid,road_height,tile_matrix,tile_template,bilinear_raster,subtract_rectangle
from paint_shader_adapter import attach_shared_surface_paint

REFERENCE_Z='relief_original_left_paint_z'
ROOT=Path(__file__).resolve().parent


def graph_signature(material):
    result=[]
    for n in material.node_tree.nodes:
        values=[]
        for i in n.inputs:
            if hasattr(i,'default_value'):
                v=i.default_value
                values.append((i.identifier,list(v) if hasattr(v,'__len__') and not isinstance(v,str) else v))
        result.append((n.name,n.bl_idname,values,getattr(getattr(n,'image',None),'name',None)))
    links=[(a.from_node.name,a.from_socket.identifier,a.to_node.name,a.to_socket.identifier) for a in material.node_tree.links]
    return hashlib.sha256(json.dumps([result,links],sort_keys=True).encode()).hexdigest()


def shader_node(material,kind,name):
    n=material.node_tree.nodes.new(kind);n.name=name;return n


def make_reference_position(material,z_socket):
    n=material.node_tree.nodes;l=material.node_tree.links
    geom=shader_node(material,'ShaderNodeNewGeometry','Actual world position for shared paint bounds')
    sep=shader_node(material,'ShaderNodeSeparateXYZ','Shared paint XY');l.new(geom.outputs['Position'],sep.inputs[0])
    combine=shader_node(material,'ShaderNodeCombineXYZ','Original paint reference position')
    l.new(sep.outputs['X'],combine.inputs['X']);l.new(sep.outputs['Y'],combine.inputs['Y']);l.new(z_socket,combine.inputs['Z'])
    return combine.outputs[0]


def build_tile_material(original,image,table_bounds,paint_material,paint_bounds):
    material=original.copy();material.name=original.name+' / shared metric tiles'
    n=material.node_tree.nodes;l=material.node_tree.links
    geom=shader_node(material,'ShaderNodeNewGeometry','Tile world XY data lookup')
    sub=shader_node(material,'ShaderNodeVectorMath','Scene field origin');sub.operation='SUBTRACT'
    xmin,xmax,ymin,ymax=table_bounds;sub.inputs[1].default_value=(xmin,ymin,0);l.new(geom.outputs['Position'],sub.inputs[0])
    scale=shader_node(material,'ShaderNodeVectorMath','Scene field UV, not material scale');scale.operation='MULTIPLY'
    scale.inputs[1].default_value=(1/(xmax-xmin),1/(ymax-ymin),0);l.new(sub.outputs[0],scale.inputs[0])
    tex=shader_node(material,'ShaderNodeTexImage','Original POINT fields / packed float scene lookup')
    tex.image=image;tex.extension='EXTEND';tex.interpolation='Linear';tex.projection='FLAT';l.new(scale.outputs[0],tex.inputs['Vector'])
    split=shader_node(material,'ShaderNodeSeparateColor','Tint, edge inset, deposit depth');split.mode='RGB';l.new(tex.outputs['Color'],split.inputs[0])
    tint=shader_node(material,'ShaderNodeCombineColor','Original scalar-equal RGB tint');tint.mode='RGB'
    for socket in tint.inputs[:3]:l.new(split.outputs[0],socket)
    one=shader_node(material,'ShaderNodeValue','Original road ownership is one');one.outputs[0].default_value=1
    replacements={'asphalt_share':one.outputs[0],'macro_tint':tint.outputs[0],
                  'road_edge_inset_m':split.outputs[1],'road_deposit_depth_m':split.outputs[2]}
    counts={}
    for node in list(n):
        if node.bl_idname=='ShaderNodeAttribute' and node.attribute_name in replacements:
            source=replacements[node.attribute_name]
            for output in node.outputs:
                for link in list(output.links):
                    # The actual source uses Color for tint and Fac otherwise.
                    allowed='Color' if node.attribute_name=='macro_tint' else 'Fac'
                    if output.name!=allowed:raise ValueError('Unexpected source attribute socket '+node.attribute_name+'/'+output.name)
                    l.new(source,link.to_socket);counts[node.attribute_name]=counts.get(node.attribute_name,0)+1
    if set(counts)!=set(replacements):raise ValueError('Not all original POINT fields were routed to the lookup')
    broad=shader_node(material,'ShaderNodeVectorTransform','Broad plane normal, excluding native relief')
    broad.vector_type='NORMAL';broad.convert_from='OBJECT';broad.convert_to='WORLD';broad.inputs[0].default_value=(0,0,1)
    replaced=0
    for node in list(n):
        if node.bl_idname=='ShaderNodeNewGeometry':
            for link in list(node.outputs['Normal'].links):l.new(broad.outputs[0],link.to_socket);replaced+=1
    if replaced<1:raise ValueError('Missing original broad normal chain')
    position=make_reference_position(material,tex.outputs['Alpha'])
    info=attach_shared_surface_paint(material,paint_material,paint_bounds,position,broad.outputs[0],label='Original left white stripe on actual road')
    material['lookup_contract']='RGBA32F: scalar macro tint, edge inset m, deposit depth m, original paint reference Z m'
    return material,counts,replaced


def pack_float_table(data,path):
    """Save 32-bit float EXR, verify exact values after reload, then pack it."""
    h,w,_=data.shape
    raw=bpy.data.images.new('Original road POINT lookup staging',width=w,height=h,alpha=True,float_buffer=True)
    raw.colorspace_settings.name='Non-Color';raw.alpha_mode='CHANNEL_PACKED';raw.pixels.foreach_set(np.asarray(data,dtype=np.float32).ravel());raw.update()
    io=bpy.data.scenes.new('Float scene-field I/O only; no render')
    io.render.image_settings.file_format='OPEN_EXR';io.render.image_settings.color_mode='RGBA';io.render.image_settings.color_depth='32';io.render.image_settings.exr_codec='ZIP'
    io.view_settings.view_transform='Raw';io.view_settings.look='None';io.view_settings.exposure=0;io.view_settings.gamma=1
    # save_render writes this existing pixel buffer; it does not render a scene.
    raw.save_render(str(path),scene=io)
    bpy.data.scenes.remove(io);bpy.data.images.remove(raw)
    if path.read_bytes()[:4]!=b'v/1\x01':raise ValueError('Scene lookup was not written as EXR')
    image=bpy.data.images.load(str(path),check_existing=False);image.colorspace_settings.name='Non-Color';image.alpha_mode='CHANNEL_PACKED'
    back=np.empty(data.size,dtype=np.float32);image.pixels.foreach_get(back)
    error=float(np.max(np.abs(back.reshape(data.shape)-data)))
    if error>2e-7:raise ValueError(f'Float scene lookup changed during EXR round trip: {error}')
    image.pack();image.name='Original source POINT fields / immutable scene lookup'
    return image,error


def data_table(source,paint_source,attrs,bounds,spacing):
    xmin,xmax,ymin,ymax=bounds
    requested=(xmin,xmax,ymin,ymax)
    # Data pixels are centers, aligned to the original 30mm near Y lattice.
    # With 2mm spacing, every original row lands on a pixel center rather than
    # being rounded by Linear filtering across two derivative segments.
    xfirst=np.floor(xmin/spacing)*spacing;xlast=np.ceil(xmax/spacing)*spacing
    anchor=float(source.ys[0]);yfirst=anchor+np.floor((ymin-anchor)/spacing)*spacing;ylast=anchor+np.ceil((ymax-anchor)/spacing)*spacing
    w=int(round((xlast-xfirst)/spacing))+1;h=int(round((ylast-yfirst)/spacing))+1
    xmin,xmax,ymin,ymax=xfirst-spacing/2,xlast+spacing/2,yfirst-spacing/2,ylast+spacing/2
    bounds=(xmin,xmax,ymin,ymax)
    if h*w>14000000:raise ValueError('Scene lookup exceeds bounded 14 MP cap')
    macro=attrs['macro_tint'][3]
    if np.max(np.abs(macro[:,:3]-macro[:,:1]))>1e-7:raise ValueError('Source macro tint is no longer scalar-equal RGB')
    if np.max(np.abs(attrs['asphalt_share'][3]-1))>1e-7:raise ValueError('Source road ownership changed')
    values=np.column_stack((macro[:,0],attrs['road_edge_inset_m'][3],attrs['road_deposit_depth_m'][3]))
    data=np.empty((h,w,4),dtype=np.float32)
    xs=xmin+(np.arange(w)+.5)*(xmax-xmin)/w
    for a in range(0,h,128):
        b=min(h,a+128);ys=ymin+(np.arange(a,b)+.5)*(ymax-ymin)/h
        x,y=np.meshgrid(xs,ys);xy=np.column_stack((x.ravel(),y.ravel()))
        data[a:b,:,:3]=source.sample(values,xy).reshape(b-a,w,3)
        data[a:b,:,3]=paint_source.sample(paint_source.co[:,2],xy,extrapolate_x=True).reshape(b-a,w)
    rng=np.random.default_rng(20261010)
    # Include random queries plus concentrated source-cell/threshold crossings.
    xy=rng.uniform([xmin+spacing,ymin+spacing],[xmax-spacing,ymax-spacing],(160000,2))
    exact=np.column_stack((source.sample(values,xy),paint_source.sample(paint_source.co[:,2],xy,extrapolate_x=True)))
    approx=bilinear_raster(data,xy,bounds)
    error=np.abs(approx-exact)
    def coverage(a):
        t=np.clip((a[:,2]-a[:,1]+.003)/.008,0,1)
        return t*t*t*(t*(t*6-15)+10)*(a[:,2]>.0005)
    coating_error=float(np.max(np.abs(coverage(approx)-coverage(exact))))
    maxima=error.max(axis=0)
    if np.any(maxima>np.array([.003,.0001,.0001,.00002])) or coating_error>.035:
        raise ValueError('Lookup interpolation exceeds field/coverage error budget: '+str(maxima)+'; coverage '+str(coating_error))
    report=dict(resolution=[w,h],bounds=list(bounds),source_row_center_alignment=True,pixel_step_m=[(xmax-xmin)/w,(ymax-ymin)/h],channels=['scalar macro_tint','road_edge_inset_m','road_deposit_depth_m','original left-paint reference Z'],
                validation_samples=len(xy),max_abs_error=maxima.tolist(),p99_abs_error=np.percentile(error,99,axis=0).tolist(),mean_abs_error=error.mean(axis=0).tolist(),max_deposit_coverage_error=coating_error,
                qualification='Bounded raster approximation to original triangle interpolation; sample checks are not a proof over every point')
    return data,report


def make_triangle_mesh(name,co,tri,material):
    mesh=bpy.data.meshes.new(name);mesh.vertices.add(len(co));mesh.vertices.foreach_set('co',np.asarray(co,dtype=np.float32).ravel())
    mesh.loops.add(tri.size);mesh.loops.foreach_set('vertex_index',np.asarray(tri,dtype=np.int32).ravel());mesh.polygons.add(len(tri))
    mesh.polygons.foreach_set('loop_start',np.arange(len(tri),dtype=np.int32)*3);mesh.polygons.foreach_set('loop_total',np.full(len(tri),3,dtype=np.int32));mesh.polygons.foreach_set('use_smooth',np.ones(len(tri),dtype=bool))
    mesh.update();mesh.materials.append(material)
    if mesh.validate(verbose=True):raise ValueError('Blender repaired a tile template')
    return mesh


def create_tiles(scene,height,bounds,fade,material):
    xmin,xmax,ymin,ymax=bounds;nx=round((xmax-xmin)/TILE_M);ny=round((ymax-ymin)/TILE_M)
    meshes={};objects={};bank=[]
    for j in range(ny):
        for i in range(nx):
            flags=(i==0,i==nx-1,j==0,j==ny-1)
            if flags not in meshes:
                co,tri=tile_template(height,flags,fade)
                name='Original asphalt native relief template '+''.join(str(int(v)) for v in flags)
                meshes[flags]=make_triangle_mesh(name,co,tri,material);bank.append(dict(flags=list(flags),vertices=len(co),triangles=len(tri)))
            ob=bpy.data.objects.new(f'Original asphalt native tile {i:02d} {j:02d}',meshes[flags]);scene.collection.objects.link(ob)
            ob.matrix_world=Matrix(tile_matrix(xmin+i*TILE_M,ymin+j*TILE_M));objects[i,j]=ob
    # Complete outer edge at native spacing, each corner present on two sides.
    sides=[]
    for side in ('bottom','right','top','left'):
        chunks=[]
        count=nx if side in ('bottom','top') else ny
        for k in range(count):
            if side=='bottom':i,j=k,0;local=np.column_stack((np.linspace(0,TILE_M,513),np.zeros(513),np.zeros(513)))
            elif side=='top':i,j=k,ny-1;local=np.column_stack((np.linspace(0,TILE_M,513),np.full(513,TILE_M),np.zeros(513)))
            elif side=='left':i,j=0,k;local=np.column_stack((np.zeros(513),np.linspace(0,TILE_M,513),np.zeros(513)))
            else:i,j=nx-1,k;local=np.column_stack((np.full(513,TILE_M),np.linspace(0,TILE_M,513),np.zeros(513)))
            matrix=np.asarray(objects[i,j].matrix_world,dtype=np.float64)
            world=local@matrix[:3,:3].T+matrix[:3,3]
            chunks.append(world if k==count-1 else world[:-1])
        sides.append(np.concatenate(chunks))
    # Edge-aligned world XY is exact in this binary 0.25 m lattice. Z transforms
    # are float32 in Blender; quantify sharing rather than claiming a weld.
    max_seam=0.
    for j in range(ny):
        for i in range(nx):
            for di,dj in ((1,0),(0,1)):
                if (i+di,j+dj) not in objects:continue
                a,b=objects[i,j],objects[i+di,j+dj]
                va=coordinates(a.data).reshape(513,513,3);vb=coordinates(b.data).reshape(513,513,3)
                aa=va[:,-1] if di else va[-1];bb=vb[:,0] if di else vb[0]
                ma,mb=np.asarray(a.matrix_world,dtype=float),np.asarray(b.matrix_world,dtype=float)
                aw=aa@ma[:3,:3].T+ma[:3,3];bw=bb@mb[:3,:3].T+mb[:3,3]
                max_seam=max(max_seam,float(np.max(np.abs(aw-bw))))
    if max_seam>5e-7:raise ValueError(f'Tile boundary mismatch {max_seam} m')
    return sides,dict(tile_count=len(objects),template_count=len(meshes),template_bank=bank,max_adjacent_coordinate_mismatch_m=max_seam)


def clip_base_and_collar(old,co,faces,diagonal,source,attrs,normal,paint_reference,bounds,outer,inner_sides,material):
    """Exact rectangle subtraction of source triangles; a real, nonoverlap hole."""
    xmin,xmax,ymin,ymax=outer
    points=co[faces,:2];lo=points.min(axis=1);hi=points.max(axis=1)
    outside=(hi[:,0]<xmin-1e-9)|(lo[:,0]>xmax+1e-9)|(hi[:,1]<ymin-1e-9)|(lo[:,1]>ymax+1e-9)
    inside=(lo[:,0]>xmin+1e-9)&(hi[:,0]<xmax-1e-9)&(lo[:,1]>ymin+1e-9)&(hi[:,1]<ymax-1e-9)
    crossing=np.flatnonzero(~outside&~inside)
    verts=[p for p in co.astype(float)]
    key=lambda p:(round(float(p[0]),9),round(float(p[1]),9))
    lookup={key(p):i for i,p in enumerate(co)}
    new_tri=[];edge_splits={}
    for index in crossing:
        f=faces[index];ac=diagonal.ravel()[index]
        for cols in (((0,1,2),(0,2,3)) if ac else ((0,1,3),(1,2,3))):
            ids=f[list(cols)];triangle=co[ids]
            for poly in subtract_rectangle(triangle[:,:2],outer):
                ring=[]
                for p in poly:
                    coord=p[2:]@triangle;coord[:2]=p[:2];k=key(coord)
                    if k not in lookup:lookup[k]=len(verts);verts.append(coord)
                    point_id=lookup[k]
                    nz=np.flatnonzero(np.abs(p[2:])>1e-10)
                    if len(nz)==2:
                        edge=tuple(sorted(int(ids[v]) for v in nz));edge_splits.setdefault(edge,set()).add(point_id)
                    if not ring or ring[-1]!=point_id:ring.append(point_id)
                if len(ring)>1 and ring[0]==ring[-1]:ring.pop()
                for q in range(1,len(ring)-1):
                    idx=(ring[0],ring[q],ring[q+1]);v=np.asarray([verts[a][:2] for a in idx]);area=np.cross(v[1]-v[0],v[2]-v[0])
                    if abs(area)>1e-15:new_tri.append(idx if area>0 else idx[::-1])
    # A cut line can extend onto a source edge just outside the rectangle.
    # Propagate those vertices into the adjacent retained face; do not leave
    # a source-triangle T junction merely because that face itself is outside.
    for index in np.flatnonzero(outside):
        f=faces[index]
        if not any(tuple(sorted((int(f[k]),int(f[(k+1)%4])))) in edge_splits for k in range(4)):continue
        outside[index]=False
        for cols in (((0,1,2),(0,2,3)) if diagonal.ravel()[index] else ((0,1,3),(1,2,3))):
            ids=f[list(cols)];ring=[]
            for k in range(3):
                ia,ib=int(ids[k]),int(ids[(k+1)%3]);ring.append(ia)
                extra=edge_splits.get(tuple(sorted((ia,ib))),set())-{ia,ib}
                if extra:
                    direction=co[ib,:2]-co[ia,:2]
                    ring.extend(sorted(extra,key=lambda a:float(np.dot(np.asarray(verts[a])[:2]-co[ia,:2],direction))))
            if len(ring)==3:new_tri.append(tuple(ring));continue
            center=co[ids].astype(float).mean(axis=0);k=key(center)
            if k not in lookup:lookup[k]=len(verts);verts.append(center)
            ci=lookup[k]
            for ia,ib in zip(ring,ring[1:]+ring[:1]):new_tri.append((ci,ia,ib))
    v=np.asarray(verts)
    # Use actual single-use cut edges, never unused old vertices that merely
    # happen to lie near the new rectangle. This prevents collar T junctions.
    kept=faces[outside];ct=np.asarray(new_tri,dtype=np.int32)
    edges=np.concatenate([kept[:,[i,(i+1)%4]] for i in range(4)]+[ct[:,[i,(i+1)%3]] for i in range(3)])
    ev=v[edges,:2];near=np.zeros(len(edges),dtype=bool)
    for axis,value in ((0,xmin),(0,xmax),(1,ymin),(1,ymax)):
        near|=np.all(np.abs(ev[:,:,axis]-value)<1.1e-9,axis=1)
    near&=np.all((ev[:,:,0]>=xmin-1.1e-9)&(ev[:,:,0]<=xmax+1.1e-9)&(ev[:,:,1]>=ymin-1.1e-9)&(ev[:,:,1]<=ymax+1.1e-9),axis=1)
    unique,usage=np.unique(np.sort(edges[near],axis=1),axis=0,return_counts=True)
    cut=unique[usage==1];cut_ids,degree=np.unique(cut,return_counts=True)
    if not len(cut) or not np.all(degree==2):raise ValueError('Source clipping did not create one conforming cut loop')
    boundary=[]
    for axis,value,sortaxis in ((1,ymin,0),(0,xmax,1),(1,ymax,0),(0,xmin,1)):
        ids=cut_ids[np.abs(v[cut_ids,axis]-value)<1.1e-9];ids=ids[np.argsort(v[ids,sortaxis])]
        if len(ids)<2:raise ValueError('Rectangle clipping did not expose a complete outer boundary')
        boundary.append(ids)
    for side,outer_ids in zip(inner_sides,boundary):
        inner_ids=[]
        for p in side:
            k=key(p)
            if k not in lookup:lookup[k]=len(verts);verts.append(p)
            inner_ids.append(lookup[k])
        triangles=zipper(outer_ids,inner_ids)
        for tri in triangles:
            v=np.asarray([verts[i][:2] for i in tri]);area=np.cross(v[1]-v[0],v[2]-v[0])
            if abs(area)<1e-15:raise ValueError('Degenerate collar face')
            new_tri.append(tri if area>0 else tri[::-1])
    allco=np.asarray(verts,dtype=np.float32);qfaces=faces[outside];tri=np.asarray(new_tri,dtype=np.int32)
    used=np.unique(np.r_[qfaces.ravel(),tri.ravel()]);remap=np.full(len(allco),-1,dtype=np.int32);remap[used]=np.arange(len(used))
    flat=np.r_[remap[qfaces].ravel(),remap[tri].ravel()];counts=np.r_[np.full(len(qfaces),4,dtype=np.int32),np.full(len(tri),3,dtype=np.int32)]
    new=bpy.data.meshes.new(old.name+' / clipped original base and exact collar');new.vertices.add(len(used));new.vertices.foreach_set('co',allco[used].ravel())
    new.loops.add(len(flat));new.loops.foreach_set('vertex_index',flat);new.polygons.add(len(counts));new.polygons.foreach_set('loop_start',np.r_[0,np.cumsum(counts[:-1])].astype(np.int32));new.polygons.foreach_set('loop_total',counts);new.polygons.foreach_set('use_smooth',np.ones(len(counts),dtype=bool))
    additions=allco[len(co):,:2]
    field_specs=dict(attrs);field_specs[BASE_NORMAL]=('FLOAT_VECTOR','vector',False,normal);field_specs[REFERENCE_Z]=('FLOAT','value',False,paint_reference)
    ids,weights=source.weights(additions)
    for name,(dtype,prop,discrete,values) in field_specs.items():
        if discrete:extra=values[ids[np.arange(len(ids)),np.argmax(weights,axis=1)]]
        else:extra=np.einsum('ni,ni...->n...',weights,np.asarray(values)[ids])
        output=np.concatenate((values,extra))[used];a=new.attributes.new(name,dtype,'POINT');a.data.foreach_set(prop,output.ravel())
    new.update();new.materials.append(material)
    if new.validate(verbose=True):raise ValueError('Blender repaired clipped base/collar')
    ny,nx=source.ny,source.nx
    perimeter=np.unique(np.r_[np.arange(nx),np.arange((ny-1)*nx,ny*nx),np.arange(0,ny*nx,nx),np.arange(nx-1,ny*nx,nx)])
    if not np.array_equal(coordinates(new)[remap[perimeter]],co[perimeter]):raise ValueError('Original physical road perimeter moved')
    # A centroid inside the tile area means an accidental lower plane/collar.
    centers=allco[tri,:2].mean(axis=1);a,b,c,d=bounds
    if np.any((centers[:,0]>a+1e-7)&(centers[:,0]<b-1e-7)&(centers[:,1]>c+1e-7)&(centers[:,1]<d-1e-7)):
        raise ValueError('Base/collar overlaps tile footprint')
    return new,dict(base_vertices=len(used),source_faces_kept=int(outside.sum()),source_faces_removed=int(inside.sum()),source_faces_clipped=len(crossing),new_clip_and_collar_triangles=len(tri),physical_perimeter_vertices_unchanged=len(perimeter),base_beneath_tile_footprint=False)


def choose_extent(scene,bounds,collar):
    xmin,xmax,ymin,ymax=bounds;changes=[]
    for ob in scene.objects:
        if not ob.name.startswith('Sparse narrow transverse pavement fissure') or ob.type!='MESH':continue
        p=coordinates(ob.data);matrix=np.asarray(ob.matrix_world);p=p@matrix[:3,:3].T+matrix[:3,3]
        lo,hi=p[:,:2].min(axis=0),p[:,:2].max(axis=0)
        if hi[0]<xmin-collar or lo[0]>xmax+collar or hi[1]<ymin-collar or lo[1]>ymax+collar:continue
        limit=np.floor((lo[1]-collar-1e-5)/TILE_M)*TILE_M
        ymax=min(ymax,float(limit));changes.append(dict(fissure=ob.name,min_y=float(lo[1]),new_max_y=ymax))
    if ymax-ymin<.5:raise ValueError('Too little safe painted-road extent before the first fissure')
    return (xmin,xmax,ymin,ymax),changes


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--height',type=Path,required=True)
    p.add_argument('--bounds',type=float,nargs=4,default=(-3,-.25,0,2));p.add_argument('--lookup-mm',type=float,default=2);p.add_argument('--edge-fade-mm',type=float,default=125);p.add_argument('--collar-mm',type=float,default=40)
    args=p.parse_args(argv);source_path=args.source.resolve();output=args.output.resolve();height_path=args.height.resolve()
    if output.parent!=ROOT or output.exists() or output==source_path or output.suffix!='.blend':raise ValueError('Use a new .blend output beside this script')
    receipt=output.with_suffix('.receipt.json');table_path=output.with_suffix('.fields.exr')
    if receipt.exists() or table_path.exists():raise ValueError('Output sidecar already exists; use a fresh output stem')
    xmin,xmax,ymin,ymax=args.bounds
    if not (-3<=xmin<xmax<=-.25 and 0<=ymin<ymax<=4 and xmax-xmin>=.5):raise ValueError('Only the bounded near left lane, outside the center crown, is supported')
    if any(abs(v/TILE_M-round(v/TILE_M))>1e-8 for v in args.bounds):raise ValueError('Tile bounds must align with original world 0.25 m phase')
    if not (.5<=args.lookup_mm<=2 and 20<=args.edge_fade_mm<=125 and 20<=args.collar_mm<=60):raise ValueError('Unsupported raster/fade/collar limits')
    if sha256(height_path)!=HEIGHT_SHA256:raise ValueError('Not the pinned original dense asphalt geometry')
    height=np.load(height_path,allow_pickle=False)
    if height.shape!=(513,513) or not np.array_equal(height[0],height[-1]) or not np.array_equal(height[:,0],height[:,-1]):raise ValueError('Original periodic geometry endpoints are not bit-identical')
    source_hash=sha256(source_path);bpy.ops.wm.open_mainfile(filepath=str(source_path));scene=bpy.context.scene
    scene.render.threads_mode='FIXED';scene.render.threads=2
    road=scene.objects.get(ROAD)
    if not road or road.modifiers or road.data.shape_keys or not np.allclose(np.asarray(road.matrix_world),np.eye(4),atol=1e-9,rtol=0):raise ValueError('Need the identity-transformed original unmodified road')
    old=road.data;co=coordinates(old);faces,diagonal=verify_source_grid(old,co);attrs=attributes(old);src=SourceGrid(co,diagonal)
    if len(old.materials)!=1:raise ValueError('Original road material topology changed')
    original_material=old.materials[0];packed=verify_packed_shader(original_material);source_material_signature=graph_signature(original_material)
    if not {'asphalt_share','macro_tint','road_edge_inset_m','road_deposit_depth_m'}.issubset(attrs):raise ValueError('Use fixed-contact I or later')
    bounds,fissures=choose_extent(scene,tuple(args.bounds),args.collar_mm/1000)
    a,b,c,d=bounds;collar=args.collar_mm/1000
    # Mesh storage is float32. Use one exactly shared representable cut plane,
    # avoiding zero-area slivers when a cut nearly coincides with a source row.
    outer=tuple(float(np.float32(v)) for v in (a-collar,b+collar,c-collar,d+collar))
    # Validate the copied broad profile against actual source vertices near band.
    check=(co[:,0]>=outer[0]-.1)&(co[:,0]<=outer[1]+.1)&(co[:,1]>=outer[2]-.1)&(co[:,1]<=outer[3]+.1)
    profile_error=float(np.max(np.abs(co[check,2]-road_height(co[check,0],co[check,1]))))
    if profile_error>2e-7:raise ValueError('Source road broad profile no longer matches the verified tile profile')
    # Protect the original asphalt contact edge, not merely the nominal 3.2m width.
    yprobe=np.linspace(outer[2],outer[3],1025);j=np.searchsorted(src.ys,yprobe,side='right')-1;t=(yprobe-src.ys[j])/(src.ys[j+1]-src.ys[j])
    left=src.grid[j,0,0]*(1-t)+src.grid[j+1,0,0]*t
    if np.min(outer[0]-left)<.10:raise ValueError('Tile collar approaches within 0.10m of fixed shoulder contact')
    paints=[]
    for ob in scene.objects:
        if ob.type=='MESH' and ob.name.startswith('Worn marking following road profile'):
            xyz=coordinates(ob.data);lo,hi=xyz[:,:2].min(axis=0),xyz[:,:2].max(axis=0)
            if hi[0]>a and lo[0]<b:
                if not (a<lo[0]<hi[0]<b):raise ValueError('Tile X limits cut through a stripe')
                paints.append((ob,xyz,(float(lo[0]),float(hi[0]),float(lo[1]),float(hi[1]))))
    if len(paints)!=1:raise ValueError('This candidate requires exactly the left white stripe')
    paint,paint_co,paint_bounds=paints[0]
    if paint.modifiers or not np.allclose(np.asarray(paint.matrix_world),np.eye(4),atol=1e-9,rtol=0) or len(paint.data.materials)!=1:raise ValueError('Unexpected source paint geometry/material')
    _,paint_diagonal=verify_source_grid(paint.data,paint_co);paint_src=SourceGrid(paint_co,paint_diagonal)
    if not np.array_equal(src.ys,paint_src.ys):raise ValueError('Original paint and road Y rows differ')
    paint_material=paint.data.materials[0];paint_signature=graph_signature(paint_material)
    # Table covers the entire native band and collar; this does not alter maps.
    data,lookup_report=data_table(src,paint_src,attrs,outer,args.lookup_mm/1000)
    image,roundtrip=pack_float_table(data,table_path);del data
    tile_material,field_links,normal_links=build_tile_material(original_material,image,lookup_report['bounds'],paint_material,paint_bounds)
    base_material,base_normal_links=patch_material(original_material)
    az=shader_node(base_material,'ShaderNodeAttribute','Original paint reference Z');az.attribute_name=REFERENCE_Z
    bn=shader_node(base_material,'ShaderNodeAttribute','Original broad road normal for paint');bn.attribute_name=BASE_NORMAL
    ref=make_reference_position(base_material,az.outputs['Fac'])
    attach_shared_surface_paint(base_material,paint_material,paint_bounds,ref,bn.outputs['Vector'],label='Retained left stripe, shared road datum')
    normal=np.empty((len(co),3),dtype=np.float32);old.vertices.foreach_get('normal',normal.ravel())
    reference=paint_src.sample(paint_co[:,2],co[:,:2],extrapolate_x=True).astype(np.float32)
    # Measure the small reference-field interpolation error of the coarse base.
    rng=np.random.default_rng(2317);qxy=np.column_stack((rng.uniform(paint_bounds[0],paint_bounds[1],50000),rng.uniform(src.ys[0],src.ys[-1],50000)))
    paint_reference_error=float(np.max(np.abs(src.sample(reference,qxy)-paint_src.sample(paint_co[:,2],qxy))))
    if paint_reference_error>3e-6:raise ValueError(f'Shared paint reference interpolation exceeds 3 micrometres: {paint_reference_error:.9g} m')
    sides,tile_report=create_tiles(scene,height,bounds,args.edge_fade_mm/1000,tile_material)
    new,base_report=clip_base_and_collar(old,co,faces,diagonal,src,attrs,normal,reference,bounds,outer,sides,base_material)
    old.use_fake_user=True;road.data=new
    paint.hide_render=True;paint.hide_viewport=True;paint['retained_shared_surface_source']=True
    if graph_signature(original_material)!=source_material_signature or graph_signature(paint_material)!=paint_signature:raise ValueError('An original shared material changed')
    # Quantify source-field versus corner-plane approximation without claiming a
    # continuous analytic bound. Fixed 1mm tests over every actual tile.
    plane_error=0.
    for y in np.arange(c,d,TILE_M):
        for x in np.arange(a,b,TILE_M):
            u=np.linspace(0,TILE_M,251);m=tile_matrix(x,y)
            ex=road_height(x+u,y)-(m[2,3]+m[2,0]*u);ey=road_height(x,y+u)-(m[2,3]+m[2,1]*u)
            plane_error=max(plane_error,float(max(abs(ex.min()+ey.min()),abs(ex.max()+ey.max()))))
    scene['optional_asphalt_relief']='UNRENDERED shared metric-tile left-lane candidate; not accepted'
    bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(output),compress=True)
    if sha256(source_path)!=source_hash or sha256(height_path)!=HEIGHT_SHA256:raise ValueError('Immutable input changed')
    report=dict(status='UNRENDERED_CANDIDATE',source_scene=str(source_path),source_scene_sha256=source_hash,output_scene=str(output),output_scene_sha256=sha256(output),original_height_sha256=HEIGHT_SHA256,
                verified_original_packed_hashes=packed,requested_bounds=list(args.bounds),effective_bounds=list(bounds),outer_cut_bounds=list(outer),fissure_extent_reductions=fissures,
                tile_m=TILE_M,height_scale_m=HEIGHT_SCALE_M,geometry_grid=512,geometry_spacing_m=TILE_M/512,edge_fade_m=args.edge_fade_mm/1000,collar_m=collar,
                lookup=lookup_report,lookup_exr=str(table_path),lookup_exr_sha256=sha256(table_path),lookup_roundtrip_max_error=roundtrip,
                source_profile_vertex_error_m=profile_error,corner_plane_sampled_max_error_m=plane_error,paint_reference_base_sampled_max_error_m=paint_reference_error,
                converted_paint=paint.name,paint_bounds=list(paint_bounds),paint_original_retained_hidden=True,other_stripes_unchanged=True,
                paint_contract='Existing opaque paint BSDF mixed using exact strip mask times original crisp alpha; both share the actual road datum. Original +0.6mm paint geometry height is removed.',
                normal_contract='Full original world-XY normal plus broad plane/captured original normal once; OBJECT paint normal transform replaced with equivalent raw world-aligned decode',
                original_road_material_signature=source_material_signature,original_paint_material_signature=paint_signature,source_materials_unchanged=True,ground_geometry_unchanged=True,
                attribute_lookup_links=field_links,tile_broad_normal_links=normal_links,base_broad_normal_links=base_normal_links,render_run=False,threads=2,
                limits=['No renderer execution or appearance acceptance', 'Float lookup is a measured approximation to original POINT interpolation',
                        'Broad tile profile approximates original smooth grade; shared instances are not welded',
                        'Fixed near-field envelope, not dynamically retargeted after camera changes',
                        'Only the left white stripe is converted; no new paint dust/wear is authored',
                        'Actual renderer instance sharing, normal transform and resource limits require validation'])
    report.update(tile_report);report.update(base_report);receipt.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':
    main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
