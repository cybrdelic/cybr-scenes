"""Bounded scene-scale thin-film deposition over pavement and existing paint.
Regional observation-led shader prototype, not a new micro-material recipe.
The thickness label is a surface-film interpretation, not explicit film geometry.
"""
import bpy,json,hashlib,sys,numpy as np
from pathlib import Path
R=Path(__file__).resolve().parents[1];src=R/'preview/road_r6_o.blend';out=R/'preview/road_r6_r2_dust.blend'
if '--' in sys.argv:
 argv=sys.argv[sys.argv.index('--')+1:]
 if argv:src=Path(argv[0]).resolve()
 if len(argv)>1:out=Path(argv[1]).resolve()
bpy.ops.wm.open_mainfile(filepath=str(src));s=bpy.context.scene
# Dry fines colour is the linear-light mean of the unchanged R5D BaseColor,
# not a replacement of that grain map. The original asphalt remains beneath it.
DUST=(.308221809,.255643471,.183828350,1)
patches=[(.65,.62,.47,.82),(2.9,1.0,.36,.70),(6.8,.65,.41,.75),(12.4,1.7,.28,.64),(23.5,1.2,.43,.77),(37.0,1.8,.25,.62),(58.0,2.7,.36,.68),(88.0,3.2,.40,.74)]
# Height-derived retention is linked to the same immutable asphalt source.
height_path=R.parent/'discrete_grains_r5/asphalt/native4096/GeometryHeight.npy'
grid=np.load(height_path,allow_pickle=False)[::-1].astype('f4')
im=bpy.data.images.new('Original metric aggregate / shelter height',width=513,height=513,float_buffer=True,alpha=False);im.colorspace_settings.name='Non-Color';rgba=np.ones((513,513,4),dtype='f4');rgba[...,:3]=grid[...,None];im.pixels.foreach_set(rgba.ravel());im.pack()
records=[]
def apply(m,bs):
 n=m.node_tree.nodes;l=m.node_tree.links
 def link(q,i,v):l.new(v,q.inputs[i]) if hasattr(v,'node') else setattr(q.inputs[i],'default_value',v)
 def math(op,a,b=0):q=n.new('ShaderNodeMath');q.operation=op;q.label='Shoulder-fed thin fines';link(q,0,a);link(q,1,b);return q.outputs[0]
 def mix(a,b,f):q=n.new('ShaderNodeMixRGB');link(q,0,f);link(q,1,a);link(q,2,b);return q.outputs[0]
 g=n.new('ShaderNodeNewGeometry');xyz=n.new('ShaderNodeSeparateXYZ');l.new(g.outputs['Position'],xyz.inputs[0]);x=xyz.outputs['X'];y=xyz.outputs['Y'];ax=math('ABSOLUTE',x)
 # Unequal sides; repeat no single left/right mask.
 yy=math('ADD',y,math('MULTIPLY',math('GREATER_THAN',x,0),17.3))
 v=n.new('ShaderNodeCombineXYZ');l.new(yy,v.inputs['Y'])
 no=n.new('ShaderNodeTexNoise');no.inputs['Scale'].default_value=7.3;no.inputs['Detail'].default_value=2;l.new(v.outputs[0],no.inputs[0]);edge=math('SUBTRACT',3.2,ax)
 # Two resolved lateral scales make deposit contacts irregular in both XY axes.
 edge_noise=n.new('ShaderNodeTexNoise');edge_noise.inputs['Scale'].default_value=31;edge_noise.inputs['Detail'].default_value=2;l.new(g.outputs['Position'],edge_noise.inputs[0])
 edge_broad=n.new('ShaderNodeTexNoise');edge_broad.inputs['Scale'].default_value=8.2;edge_broad.inputs['Detail'].default_value=2;l.new(g.outputs['Position'],edge_broad.inputs[0])
 edge=math('ADD',edge,math('ADD',math('MULTIPLY',math('SUBTRACT',edge_noise.outputs['Fac'],.5),.055),math('MULTIPLY',math('SUBTRACT',edge_broad.outputs['Fac'],.5),.060)))
 coat=0
 for cy,half,width,strength in patches:
  longitudinal=math('MAXIMUM',0,math('SUBTRACT',1,math('DIVIDE',math('ABSOLUTE',math('SUBTRACT',yy,cy)),half)))
  reach=math('MULTIPLY',width,math('POWER',longitudinal,.65));reach=math('MULTIPLY',reach,math('ADD',.75,math('MULTIPLY',no.outputs['Fac'],.25)))
  mr=n.new('ShaderNodeMapRange');mr.clamp=True;mr.interpolation_type='SMOOTHERSTEP';l.new(math('SUBTRACT',reach,edge),mr.inputs['Value']);mr.inputs['From Min'].default_value=-.017;mr.inputs['From Max'].default_value=.025;mr.inputs['To Min'].default_value=0;mr.inputs['To Max'].default_value=strength
  local=math('MULTIPLY',mr.outputs[0],math('GREATER_THAN',longitudinal,.015));coat=math('MAXIMUM',coat,local)
 # Shelter factor from original metric aggregate height, rather than unrelated
 # noise. Shader texel-center mapping matches the retained 513-node field.
 scale=n.new('ShaderNodeVectorMath');scale.operation='SCALE';scale.inputs['Scale'].default_value=4;l.new(g.outputs['Position'],scale.inputs[0]);fract=n.new('ShaderNodeVectorMath');fract.operation='FRACTION';l.new(scale.outputs[0],fract.inputs[0]);uv=n.new('ShaderNodeVectorMath');uv.operation='SCALE';uv.inputs['Scale'].default_value=512/513;l.new(fract.outputs[0],uv.inputs[0]);offset=n.new('ShaderNodeVectorMath');offset.operation='ADD';offset.inputs[1].default_value=(.5/513,.5/513,0);l.new(uv.outputs[0],offset.inputs[0]);tex=n.new('ShaderNodeTexImage');tex.image=im;tex.interpolation='Linear';tex.extension='REPEAT';l.new(offset.outputs[0],tex.inputs[0]);ret=n.new('ShaderNodeMapRange');ret.clamp=True;ret.interpolation_type='SMOOTHERSTEP';ret.inputs['From Min'].default_value=.42;ret.inputs['From Max'].default_value=.68;ret.inputs['To Min'].default_value=1.18;ret.inputs['To Max'].default_value=.36;l.new(tex.outputs['Color'],ret.inputs[0]);coat=math('MINIMUM',.94,math('MULTIPLY',coat,ret.outputs[0]))
 # Small broken contacts plus variable film opacity; no uniform opaque band.
 fine=n.new('ShaderNodeTexNoise');fine.inputs['Scale'].default_value=310;fine.inputs['Detail'].default_value=2;l.new(g.outputs['Position'],fine.inputs[0]);coat=math('MULTIPLY',coat,math('ADD',.70,math('MULTIPLY',fine.outputs['Fac'],.30)))
 bc=bs.inputs['Base Color'];orig=bc.links[0].from_socket if bc.links else tuple(bc.default_value);l.new(mix(orig,DUST,coat),bc)
 rough=bs.inputs['Roughness'];orig_r=rough.links[0].from_socket if rough.links else rough.default_value;l.new(math('ADD',math('MULTIPLY',orig_r,math('SUBTRACT',1,coat)),math('MULTIPLY',coat,.94)),rough)
 # A sub-mm film attenuates, rather than enlarges, the exposed aggregate slope.
 if bs.inputs['Normal'].links:
  orig_n=bs.inputs['Normal'].links[0].from_socket;fac=math('MULTIPLY',coat,.18);norm=n.new('ShaderNodeVectorMath');norm.operation='NORMALIZE';l.new(mix(orig_n,g.outputs['Normal'],fac),norm.inputs[0]);l.new(norm.outputs[0],bs.inputs['Normal'])
 m['deposition_surface_film']='Shoulder-fed 40–180 micrometre visual interpretation; no explicit raised sheet';m['deposition_color_source']='Unchanged R5D BaseColor linear mean';records.append(m.name)
road=s.objects['Crowned asphalt crust / longitudinal rise'];original=road.data.materials[0];m=original.copy();m.name=original.name+' / coupled shoulder-fines prototype';road.data.materials[0]=m;apply(m,m.node_tree.nodes['Linked dry dielectric'])
# Copy each paint material only once; same world-space deposition field on all
# its sheets. No geometry or opaque/transparent ownership changed in this pass.
copies={}
for ob in s.objects:
 if not ob.name.startswith('Worn marking following road profile'):continue
 for i,old in enumerate(ob.data.materials):
  if old.name not in copies:
   ma=old.copy();ma.name=old.name+' / shoulder-fed fines';apply(ma,ma.node_tree.nodes['Principled BSDF']);copies[old.name]=ma
  ob.data.materials[i]=copies[old.name]
s['scene_version']='R6 R2 height-linked dust-film appearance prototype over immutable O geometry';bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(out),compress=True)
rec={'source_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),'scene_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'materials':records,'patches_y_half_length_width_opacity':patches,'mean_dust_color_linear':DUST,'geometry_changed':False,'dust_retention':'Original GeometryHeight low-pocket support, correct flipped row phase and texel-center mapping','height_source_sha256':hashlib.sha256(height_path.read_bytes()).hexdigest(),'limitation':'Thin-film appearance prototype only; paint still uses the retained source sheets until the separate shared-surface relief pass is integrated.','reference_record':'road_surface_reference_observations.json'};(R/'receipts/shoulder_dust_r2.json').write_text(json.dumps(rec,indent=2));print('DUST_PROTOTYPE_READY',rec,flush=True)
