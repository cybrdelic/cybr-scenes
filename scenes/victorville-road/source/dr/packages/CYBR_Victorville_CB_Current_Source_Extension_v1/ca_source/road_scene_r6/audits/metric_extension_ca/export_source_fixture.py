"""Read only the actual retained AV road and one native tile; no scene mutation/render."""
import bpy,numpy as np,json,hashlib,sys,argparse
from pathlib import Path
def digest(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
R=Path(__file__).resolve().parents[2]
a=argparse.ArgumentParser();a.add_argument('--source',type=Path,default=R/'preview/road_r6_av_integrated_cache.blend');a.add_argument('--output-folder',type=Path,default=Path(__file__).resolve().parent);args=a.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []);out=args.output_folder.resolve();out.mkdir(parents=True,exist_ok=True);assert not (out/'actual_road_fixture.npz').exists(),'Never overwrite an existing extracted fixture'
bpy.ops.wm.read_factory_settings(use_empty=True)
source=args.source.resolve()
with bpy.data.libraries.load(str(source),link=False) as(a,b):
 names=['Crowned asphalt crust / longitudinal rise','Original asphalt native tile 00 00'];assert set(names)<=set(a.objects);b.objects=names
road,tile=b.objects;me=road.data;me.calc_loop_triangles();co=np.empty((len(me.vertices),3),'f4');me.vertices.foreach_get('co',co.ravel());tri=np.empty((len(me.loop_triangles),3),'i4');me.loop_triangles.foreach_get('vertices',tri.ravel());parent=np.empty(len(me.loop_triangles),'i4');me.loop_triangles.foreach_get('polygon_index',parent);loops=np.empty(len(me.loops),'i4');me.loops.foreach_get('vertex_index',loops);starts=np.empty(len(me.polygons),'i4');counts=starts.copy();me.polygons.foreach_get('loop_start',starts);me.polygons.foreach_get('loop_total',counts)
arrays=dict(co=co,tri=tri,triangle_polygon=parent,loops=loops,starts=starts,counts=counts);attrs=[]
for a in me.attributes:
 if a.name=='position' or a.name.startswith('.'):continue
 assert a.domain in ('POINT','EDGE','FACE','CORNER'),('unsupported actual source attribute',a.name,a.domain)
 specs={'FLOAT':('value',1,'f4'),'FLOAT_VECTOR':('vector',3,'f4'),'FLOAT_COLOR':('color',4,'f4'),'BYTE_COLOR':('color',4,'f4'),'INT':('value',1,'i4'),'BOOLEAN':('value',1,'bool')};assert a.data_type in specs
 prop,n,dt=specs[a.data_type];v=np.empty((len(a.data),n),dt);a.data.foreach_get(prop,v.ravel());key='attribute_'+str(len(attrs));arrays[key]=v;attrs.append(dict(name=a.name,type=a.data_type,domain=a.domain,property=prop,key=key))
mat=tile.data.materials[0];nodes=[n for n in mat.node_tree.nodes if n.bl_idname=='ShaderNodeTexImage' and 'POINT' in n.name];assert len(nodes)==1,[(n.name,n.image.name) for n in nodes]
tex=nodes[0];im=tex.image;wh=list(im.size);pixels=np.empty((wh[1],wh[0],4),'f4');im.pixels.foreach_get(pixels.ravel());arrays['lookup']=pixels
scale=tex.inputs['Vector'].links[0].from_node;sub=scale.inputs[0].links[0].from_node;origin=list(sub.inputs[1].default_value);scaling=list(scale.inputs[1].default_value)
np.savez_compressed(out/'actual_road_fixture.npz',**arrays)
record=dict(source_scene_sha256=digest(source),fixture_sha256=digest(out/'actual_road_fixture.npz'),vertices=len(co),polygons=len(counts),triangles=len(tri),attributes=attrs,road_matrix=[list(r) for r in road.matrix_world],native_tile_matrix=[list(r) for r in tile.matrix_world],native_tile_parent_inverse=[list(r) for r in tile.matrix_parent_inverse],native_tile_material=mat.name,lookup_image=im.name,lookup_size=wh,lookup_origin=origin,lookup_scale=scaling,lookup_colorspace=im.colorspace_settings.name,lookup_alpha_mode=im.alpha_mode,rendered=False,source_unchanged=True)
(out/'actual_road_fixture.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
