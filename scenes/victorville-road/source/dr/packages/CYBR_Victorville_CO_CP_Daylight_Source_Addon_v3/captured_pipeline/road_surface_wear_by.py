"""Coherent scene-only road maintenance response beneath existing paint and dust.
Original material datablocks/images, world-scale aggregate, surface topology and
contact geometry are retained. All new work is staged on material copies. This
is an authored weathering/maintenance scenario, not calibrated pavement aging.
"""
from pathlib import Path
import bpy,hashlib,json,math,time
from road_wear_field_by import PATCHES,REPAIR_TRANSITION_M,TRACK_CENTRES_M,TRACK_CORE_HALF_WIDTH_M,TRACK_SHOULDER_HALF_WIDTH_M,BINDER_REFERENCE_LINEAR,AGE_ROUGHNESS,POLISH_ROUGHNESS_REDUCTION

def graph_hash(m):
 rows=[]
 for q in m.node_tree.nodes:
  values=[]
  for s in q.inputs:
   if not hasattr(s,'default_value'):values.append(None);continue
   v=s.default_value
   if not isinstance(v,(str,int,float,bool)):v=list(v)
   values.append(v)
  rows.append([q.name,q.bl_idname,getattr(q,'operation',None),getattr(q,'blend_type',None),getattr(getattr(q,'image',None),'name',None),getattr(q,'attribute_name',None),values])
 links=sorted((l.from_node.name,l.from_socket.identifier,l.to_node.name,l.to_socket.identifier) for l in m.node_tree.links)
 return hashlib.sha256(json.dumps([rows,links],sort_keys=True).encode()).hexdigest()

class Nodes:
 def __init__(self,tree):self.n=tree.nodes;self.l=tree.links
 def val(self,q,i,v):
  if hasattr(v,'node'):self.l.new(v,q.inputs[i])
  else:q.inputs[i].default_value=v
 def new(self,kind,label):
  q=self.n.new(kind);q.name='BY / '+label;q.label=label;return q
 def math(self,op,a,b=0,label=None):
  q=self.new('ShaderNodeMath',label or op);q.operation=op;self.val(q,0,a);self.val(q,1,b);return q.outputs[0]
 def smooth(self,v,a,b,label):
  q=self.new('ShaderNodeMapRange',label);q.clamp=True;q.interpolation_type='SMOOTHSTEP';self.val(q,0,v);q.inputs['From Min'].default_value=a;q.inputs['From Max'].default_value=b;q.inputs['To Min'].default_value=0;q.inputs['To Max'].default_value=1;return q.outputs[0]
 def mix(self,a,b,f,label):
  q=self.new('ShaderNodeMixRGB',label);self.val(q,0,f);self.val(q,1,a);self.val(q,2,b);return q.outputs[0]
 def reroute(self,old,new,links):
  for link in links:self.l.new(new,link.to_socket)

def history_group():
 ng=bpy.data.node_groups.new('BY metric maintenance history / metre coordinates','ShaderNodeTree')
 for name,ty,io in [('Position','NodeSocketVector','INPUT'),('Crown','NodeSocketFloat','INPUT'),('Traffic','NodeSocketFloat','OUTPUT'),('Repair','NodeSocketFloat','OUTPUT'),('Age','NodeSocketFloat','OUTPUT')]:ng.interface.new_socket(name=name,in_out=io,socket_type=ty)
 a=Nodes(ng);gi=a.new('NodeGroupInput','world position and original aggregate');go=a.new('NodeGroupOutput','shared history fields');sep=a.new('ShaderNodeSeparateXYZ','world XY');a.l.new(gi.outputs['Position'],sep.inputs[0]);x,y=sep.outputs['X'],sep.outputs['Y'];m=a.math
 drift=m('ADD',m('MULTIPLY',.055,m('SINE',m('ADD',m('MULTIPLY',y,.061),.4))),m('MULTIPLY',.019,m('SINE',m('ADD',m('MULTIPLY',y,.147),1.6))))
 ax=m('SUBTRACT',m('ABSOLUTE',x),drift);d=m('MINIMUM',m('ABSOLUTE',m('SUBTRACT',ax,TRACK_CENTRES_M[0])),m('ABSOLUTE',m('SUBTRACT',ax,TRACK_CENTRES_M[1])))
 traffic=m('SUBTRACT',1,a.smooth(d,TRACK_CORE_HALF_WIDTH_M,TRACK_SHOULDER_HALF_WIDTH_M,'physical tyre corridors'))
 repair=0
 for k,poly in enumerate(PATCHES):
  ds=[]
  for p,q in zip(poly,poly[1:]+poly[:1]):
   dx,dy=q[0]-p[0],q[1]-p[1];length=math.hypot(dx,dy)
   ds.append(m('DIVIDE',m('SUBTRACT',m('MULTIPLY',dx,m('SUBTRACT',y,p[1])),m('MULTIPLY',dy,m('SUBTRACT',x,p[0]))),length))
  inset=ds[0]
  for q in ds[1:]:inset=m('MINIMUM',inset,q)
  inset=m('ADD',inset,m('MULTIPLY',.0012,m('SUBTRACT',gi.outputs['Crown'],.5)))
  repair=m('MAXIMUM',repair,a.smooth(inset,-REPAIR_TRANSITION_M,REPAIR_TRANSITION_M,'flush repair boundary '+str(k)))
 age=m('MULTIPLY',m('SUBTRACT',.60,m('MULTIPLY',.30,traffic)),m('SUBTRACT',1,repair))
 for name,value in [('Traffic',traffic),('Repair',repair),('Age',age)]:a.l.new(value,go.inputs[name])
 return ng

def modify(old,group,paint_only=False):
 assert not old.get('BY_applied'),'Cannot apply twice'
 before=graph_hash(old);ma=old.copy();ma.name=old.name[:43]+' / BY maintenance';a=Nodes(ma.node_tree);n=a.n;l=a.l;m=a.math
 try:
  heights=[q for q in n if q.bl_idname=='ShaderNodeTexImage' and q.image and q.image.name=='Original metric aggregate / shelter height']
  assert heights,'Missing actual asphalt height hook'
  height=heights[0].outputs['Color'];crown=a.smooth(height,.47,.58,'native aggregate crown exposure')
  geo=a.new('ShaderNodeNewGeometry','actual same-surface world coordinate');hist=a.new('ShaderNodeGroup','shared metric history');hist.node_tree=group;l.new(geo.outputs['Position'],hist.inputs['Position']);l.new(crown,hist.inputs['Crown'])
  traffic,repair,age=[hist.outputs[q] for q in ('Traffic','Repair','Age')]
  records=[]
  if not paint_only:
   color=[q for q in n if q.bl_idname=='ShaderNodeTexImage' and q.image and q.image.name=='BaseColor.png'];rough=[q for q in n if q.bl_idname=='ShaderNodeTexImage' and q.image and q.image.name=='Roughness.png'];assert len(color)==len(rough)==1,'Ambiguous original asphalt hooks'
   base=color[0].outputs['Color'];base_links=list(base.links);rr=rough[0].outputs['Color'];rough_links=list(rr.links)
   lum=a.new('ShaderNodeRGBToBW','original mineral luminance');l.new(base,lum.inputs[0]);binder=m('MULTIPLY',m('SUBTRACT',1,a.smooth(lum.outputs[0],.015,.038,'dark source binder fraction')),m('SUBTRACT',1,m('MULTIPLY',.5,crown)))
   oxidized=a.mix(base,(*BINDER_REFERENCE_LINEAR,1),m('MULTIPLY',binder,age),'aged binder beneath original dust')
   fresh=a.mix(oxidized,base,repair,'flush repair retains original fresh aggregate recipe');a.reroute(base,fresh,base_links)
   # Aggregate-only polish: inherited normals/height remain unchanged. New
   # roughness is a bounded authored state, not an inferred normal variance.
   agedrough=a.mix(rr,(AGE_ROUGHNESS,)*3+(1,),m('MULTIPLY',binder,age),'binder aging roughness')
   polished=m('MAXIMUM',.38,m('SUBTRACT',agedrough,m('MULTIPLY',POLISH_ROUGHNESS_REDUCTION,m('MULTIPLY',traffic,m('SUBTRACT',1,binder)))))
   a.reroute(rr,polished,rough_links);records.extend(['original BaseColor output beneath existing coating','original roughness output beneath existing coating'])
  # Crown-contact losses and repair erase exactly the same old stripe on the
  # same shared road surface. Existing crisp loss and rectangle bounds survive.
  retain=m('MULTIPLY',m('SUBTRACT',1,repair),m('SUBTRACT',1,m('MULTIPLY',.58,crown)))
  paint_mix=[]
  if paint_only:
   bs=[q for q in n if q.bl_idname=='ShaderNodeBsdfPrincipled'];assert len(bs)==1 and bs[0].inputs['Alpha'].is_linked
   alpha=bs[0].inputs['Alpha'];oldalpha=alpha.links[0].from_socket;l.new(m('MULTIPLY',oldalpha,retain),alpha);paint_mix.append(bs[0].name)
  else:
   for q in list(n):
    if q.bl_idname=='ShaderNodeMixShader' and ('Complete road or op' in q.name or 'Complete road or opaque' in q.label):
     assert q.inputs[0].is_linked;factor=q.inputs[0].links[0].from_socket;l.new(m('MULTIPLY',factor,retain),q.inputs[0]);paint_mix.append(q.name)
  assert graph_hash(old)==before,'Source material changed'
  ma['BY_applied']=True
  return ma,dict(original_material=old.name,copy=ma.name,original_graph_sha256=before,source_preserved=True,paint_only=paint_only,paint_hooks=paint_mix,substrate_hooks=records,original_height_image=heights[0].image.name,original_geometry_and_normal_nodes_unchanged=True,new_nodes=len(n)-len(old.node_tree.nodes))
 except Exception:
  bpy.data.materials.remove(ma);raise

def apply(scene,config,out):
 assert config=={'revision':1},'Explicit BY revision1 required';assert not scene.get('BY_road_wear_applied'),'Duplicate BY pass'
 start=time.monotonic();group=history_group();copies={};rows=[];assignments=[]
 targets=[o for o in scene.objects if o.type=='MESH' and (o.name=='Crowned asphalt crust / longitudinal rise' or o.name.startswith('Original asphalt native tile ') or o.name.startswith('Worn marking following road profile'))]
 assert targets,'Current road objects missing'
 # Stage every needed material first; assign only after all contracts passed.
 for ob in targets:
  for i,old in enumerate(ob.data.materials):
   if old is None:continue
   if old.as_pointer() not in copies:
    paint_only=not any(q.bl_idname=='ShaderNodeTexImage' and q.image and q.image.name=='BaseColor.png' for q in old.node_tree.nodes)
    ma,row=modify(old,group,paint_only);copies[old.as_pointer()]=ma;rows.append(row)
   assignments.append((ob.data,i,copies[old.as_pointer()]))
 for mesh,i,ma in assignments:mesh.materials[i]=ma
 scene['BY_road_wear_applied']=True
 report=dict(revision=1,materials=rows,affected_objects=len(targets),patch_polygons_m=PATCHES,repair_transition_m=REPAIR_TRANSITION_M,aggregate_boundary_excursion_max_m=.0006,traffic_centres_m=TRACK_CENTRES_M,traffic_half_widths_m=[TRACK_CORE_HALF_WIDTH_M,TRACK_SHOULDER_HALF_WIDTH_M],age_binder_reference_linear=BINDER_REFERENCE_LINEAR,polish_roughness_reduction=POLISH_ROUGHNESS_REDUCTION,paint_crown_loss_max_fraction=.58,geometry_changed=False,source_images_changed=False,additional_image_buffers=0,terrain_materials_changed=False,elapsed_seconds=time.monotonic()-start,assumptions='Authored representative maintenance/traffic exposure, not measured Victorville or calibrated pavement deterioration. Flush repairs use the original aggregate geometry with a fresh binder response; no excavation/compaction simulation. Paint losses are fractional metric crown-contact coverage, native filtering may average them at distance.',reference='FHWA-HRT-13-092, asphalt distress definitions: aggregate polishing, binder/aggregate loss and patches; source qualitative only.')
 out=Path(out);out.mkdir(parents=True,exist_ok=True);(out/'ROAD_SURFACE_WEAR_BY.json').write_text(json.dumps(report,indent=2)+'\n');return report
