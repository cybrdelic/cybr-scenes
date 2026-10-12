"""R6 O: continuously eroded granitic ridges with terrain-routed drainage.
Keeps approved near materials, road contact, drainage and camera unchanged.
Ridge joints are granitic fracture structure, not invented sedimentary banding.
"""
import bpy,math,json,hashlib,ast,numpy as np
from pathlib import Path
R=Path(__file__).resolve().parents[1];source=R/'preview/road_r6_l.blend';bpy.ops.wm.open_mainfile(filepath=str(source));s=bpy.context.scene
ns={'np':np};tree=ast.parse((R/'src/build_scene.py').read_text());exec(compile(ast.Module(body=[q for q in tree.body if isinstance(q,ast.FunctionDef) and q.name in {'field','grade'}],type_ignores=[]),'<fields>','exec'),ns);field=ns['field'];grade=ns['grade']
def sm(a,b,x):t=np.clip((np.asarray(x)-a)/(b-a),0,1);return t*t*(3-2*t)
for ob in list(s.objects):
 if ob.name.startswith('Irregular ridge and talus'):bpy.data.objects.remove(ob,do_unlink=True)

def stone_material():
 m=bpy.data.materials.new('Jointed weathered granite and pale talus / atmospheric depth');m.use_nodes=True;n=m.node_tree.nodes;l=m.node_tree.links;n.clear();g=n.new('ShaderNodeNewGeometry');a=n.new('ShaderNodeAttribute');a.attribute_name='ridge_mineral';bs=n.new('ShaderNodeBsdfPrincipled');l.new(a.outputs['Color'],bs.inputs['Base Color']);bs.inputs['Roughness'].default_value=.87;bs.inputs['IOR'].default_value=1.48
 noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=.32;noise.inputs['Detail'].default_value=3;l.new(g.outputs['Position'],noise.inputs[0]);ramp=n.new('ShaderNodeMapRange');ramp.inputs['From Min'].default_value=.12;ramp.inputs['From Max'].default_value=.88;ramp.inputs['To Min'].default_value=.82;ramp.inputs['To Max'].default_value=1.12;l.new(noise.outputs['Fac'],ramp.inputs[0]);mix=n.new('ShaderNodeMixRGB');mix.blend_type='MULTIPLY';mix.inputs[0].default_value=1;l.new(a.outputs['Color'],mix.inputs[1]);l.new(ramp.outputs[0],mix.inputs[2]);l.new(mix.outputs[0],bs.inputs['Base Color'])
 bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.25;bump.inputs['Distance'].default_value=.055;l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
 # Beer–Lambert distance/airlight approximation. No arbitrary large linear fade.
 cam=n.new('ShaderNodeCameraData');mult=n.new('ShaderNodeMath');mult.operation='MULTIPLY';mult.inputs[1].default_value=-.00022;l.new(cam.outputs['View Distance'],mult.inputs[0]);ex=n.new('ShaderNodeMath');ex.operation='EXPONENT';l.new(mult.outputs[0],ex.inputs[0]);sub=n.new('ShaderNodeMath');sub.operation='SUBTRACT';sub.inputs[0].default_value=1;l.new(ex.outputs[0],sub.inputs[1]);air=n.new('ShaderNodeEmission');air.inputs[0].default_value=(.36,.405,.455,1);air.inputs[1].default_value=.65;ms=n.new('ShaderNodeMixShader');l.new(sub.outputs[0],ms.inputs[0]);l.new(bs.outputs[0],ms.inputs[1]);l.new(air.outputs[0],ms.inputs[2]);out=n.new('ShaderNodeOutputMaterial');l.new(ms.outputs[0],out.inputs[0]);return m
mat=stone_material();rng=np.random.default_rng(101031)

def mesh(name,co,faces,col,smooth=True):
 co=np.asarray(co,dtype='f4');assert np.isfinite(co).all();faces=np.asarray(faces,dtype='i4');me=bpy.data.meshes.new(name);me.vertices.add(len(co));me.vertices.foreach_set('co',co.ravel());me.loops.add(faces.size);me.loops.foreach_set('vertex_index',faces.ravel());me.polygons.add(len(faces));me.polygons.foreach_set('loop_start',np.arange(len(faces),dtype='i4')*faces.shape[1]);me.polygons.foreach_set('loop_total',np.full(len(faces),faces.shape[1],dtype='i4'));me.polygons.foreach_set('use_smooth',np.full(len(faces),smooth));me.update();me.materials.append(mat);ca=me.color_attributes.new(name='ridge_mineral',type='FLOAT_COLOR',domain='POINT');ca.data.foreach_set('color',np.asarray(col,dtype='f4').ravel());ob=bpy.data.objects.new(name,me);s.collection.objects.link(ob);return ob
def crest_interp(x,xp,fp):
 xp=np.asarray(xp);fp=np.asarray(fp);h=np.diff(xp);slope=np.diff(fp)/h;m=np.zeros(len(xp))
 for j in range(1,len(xp)-1):
  if slope[j-1]*slope[j]>0:
   w1=2*h[j]+h[j-1];w2=h[j]+2*h[j-1];m[j]=(w1+w2)/(w1/slope[j-1]+w2/slope[j])
 ii=np.clip(np.searchsorted(xp,x)-1,0,len(xp)-2);t=np.clip((x-xp[ii])/h[ii],0,1);v=(2*t**3-3*t*t+1)*fp[ii]+(t**3-2*t*t+t)*h[ii]*m[ii]+(-2*t**3+3*t*t)*fp[ii+1]+(t**3-t*t)*h[ii]*m[ii+1]
 return np.where((x<xp[0])|(x>xp[-1]),0,v)
ridge_records=[]
def drainage(z,step):
 """D8 flow over the current heightfield; strict downhill graph has no cycles."""
 ny,nx=z.shape;ii=np.arange(z.size).reshape(z.shape);dest=ii.copy();steep=np.zeros(z.shape)
 for dy,dx in [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]:
  zz=np.roll(z,(-dy,-dx),(0,1));jj=np.roll(ii,(-dy,-dx),(0,1));sl=(z-zz)/(step*math.hypot(dy,dx));sl[0,:]=sl[-1,:]=sl[:,0]=sl[:,-1]=0;take=sl>steep;steep[take]=sl[take];dest[take]=jj[take]
 area=np.full(z.size,step*step);d=dest.ravel()
 for k in np.argsort(z.ravel())[::-1]:
  if d[k]!=k:area[d[k]]+=area[k]
 return area.reshape(z.shape),steep,dest

def erode(z,bed,step,rock):
 original=z.copy();removed=np.zeros(z.shape)
 # Recompute downslope routing after each bounded incision step. Geological
 # resistance and connected contributing area create a branching network.
 for iteration in range(18):
  area,slope,d=drainage(z,step)
  rate=.038*np.power(np.maximum(area,step*step),.37)*np.power(slope,.85)/(0.70+.65*rock)
  rate=np.minimum(rate,.90)*sm(1,8,z-bed);z=np.maximum(bed,z-rate);removed+=rate
  # Conservative downhill talus relaxation, limited to angles of loose rubble.
  # Exposed rock remains steeper via a local resistance-dependent threshold.
  delta=np.zeros(z.shape)
  for dy,dx in [(0,1),(1,0),(1,1),(1,-1)]:
   other=np.roll(z,(-dy,-dx),(0,1));lim=step*math.hypot(dx,dy)*(.67+.22*rock);move=np.sign(z-other)*np.maximum(np.abs(z-other)-lim,0)*.075
   move[[0,-1],:]=0;move[:,[0,-1]]=0;delta-=move;delta+=np.roll(move,(dy,dx),(0,1))
  z=np.maximum(bed,z+delta)
 area,slope,d=drainage(z,step)
 return z,area,slope,original-z

# Deliberately unequal mountain masses, peaks, saddles and frontal gully systems.
configs=[(-500,745,365,255,124,2.5),(765,1440,540,355,133,3.5),(-905,1970,775,430,182,5.0)]
for idx,(cx,cy,sx,sy,H,step) in enumerate(configs):
 controls=np.array([-1,-.8,-.55,-.18,.13,.48,.74,1]);heights=np.array([[0,.50,.95,.61,.82,.70,.38,0],[0,.40,.78,.63,.96,.82,.48,0],[0,.32,.63,.91,.71,.88,.42,0]][idx])
 cyoff=np.array([0,-.16,.05,.12,-.08,.08,-.12,0])*sy
 # The skeleton sets mass and geological scale; all channels below are routed
 # down the generated surface, rather than painted or cut along fixed lines.
 hx=np.arange(cx-sx*1.10,cx+sx*1.10+step,step);hy=np.arange(cy-sy*1.43,cy+sy*.93+step,step);x,y=np.meshgrid(hx,hy);u=(x-cx)/sx
 crest=crest_interp(u,controls,heights)*H;crest_y=cy+crest_interp(u,controls,cyoff)
 toe=cy-sy*(1.02+.13*field(x,0,90,530+idx));back=cy+sy*.77
 t=np.clip((y-toe)/(crest_y-toe),0,1);behind=np.clip((back-y)/(back-crest_y),0,1)
 profile=np.where(y<=crest_y,t**1.48,behind**1.15);base=crest*profile
 support=sm(0,14,base);wx=x+17*field(x,y,65,811+idx);wy=y+23*field(x,y,82,817+idx)
 resistance=np.clip(.5+.33*field(wx,wy,47,840+idx)+.21*field(wx,wy,16,850+idx),0,1)
 # Resolved geological heterogeneity, not enlarged grain prototypes.
 relief=(12*field(wx,wy,52,870+idx)+5*field(wx+wy*.23,wy,23,880+idx)+1.9*field(wx,wy,9,890+idx))*support
 bed=grade(y)-.04;initial=bed+np.maximum(base+relief,0)
 z,area,slope,cut=erode(initial,bed,step,resistance)
 exposure=sm(.30,.68,slope)*sm(12,35,z-bed)
 # Bedrock hue varies with resistance; talus and connected drainage deposits
 # retain more pale fines. All colour masks derive from this same geometry.
 drainage_mask=sm(150,1800,area)*(1-sm(.33,.65,slope))*sm(1,10,z-bed)
 weather=np.clip(.5+.5*field(wx,wy,36,640+idx),0,1)
 col=np.ones(x.shape+(4,));col[...,:3]=np.array([.31,.265,.205])*(1-exposure[...,None])+np.array([.265,.247,.222])*exposure[...,None]
 col[...,:3]*=(.83+.30*weather)[...,None];col[...,:3]+=drainage_mask[...,None]*np.array([.026,.025,.020])
 co=np.stack((x,y,z),-1).reshape(-1,3);nx=len(hx);q=(np.arange(len(hy)-1)[:,None]*nx+np.arange(nx-1)[None,:]).ravel();faces=np.stack((q,q+1,q+nx+1,q+nx),1)
 mesh('Continuous granite and talus / routed erosion '+str(idx),co,faces,col.reshape(-1,4))
 ridge_records.append({'index':idx,'vertices':len(co),'crest_scale_m':H,'mesh_spacing_m':step,'routing':'D8 recomputed at each of 18 stream-power incision steps','max_incision_m':float(cut.max()),'height_m':float((z-bed).max()),'separate_outcrop_templates':0})
# Larger soil/mineral patterns survive distance averaging. Paired broad swales
# supply thin pale splays and darker lag; no grain enlargement or nearby edits.
for ob in s.objects:
 if not ob.name.startswith('Graded shoulder and alluvial plain'):continue
 me=ob.data;co=np.array([v.co[:] for v in me.vertices],dtype='f8');x,y=co[:,0],co[:,1];g=sm(45,85,y)*sm(9,20,np.abs(x))*(1-sm(900,1350,y));cx=np.where(x<0,-1,1)*(12+.095*np.maximum(y-30,0)+8*field(0,y,85,731));d=np.abs(x-cx);corridor=(1-sm(4,17,d))*(.55+.45*field(x,y,65,732));fan=sm(7,15,d)*(1-sm(20,48,d))*(.5+.5*field(x,y,90,733));ct=np.empty(len(co)*4,dtype='f4');me.color_attributes['macro_tint'].data.foreach_get('color',ct);ct=ct.reshape(-1,4);ct[:,:3]*=1+g[:,None]*(fan[:,None]*np.array([.11,.065,.005])-corridor[:,None]*np.array([.23,.21,.16]));me.color_attributes['macro_tint'].data.foreach_set('color',ct.ravel())
s['scene_version']='R6 O continuous eroded granitic ridges and routed drainage';out=R/'preview/road_r6_o.blend';bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(out),compress=True);receipt={'source_scene_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'scene_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'ridges':ridge_records,'outcrop_vertices':0,'aerial_perspective':'Beer–Lambert distance/airlight surface approximation with extinction .00022 per metre; no volume scattering claim.','near_materials_road_contact_camera_and_daylight':'unchanged from L','references':{'url':'https://www.usgs.gov/media/images/granite-mountains','observed':'Public USGS image viewed in the cloud browser: pale massive granite, steep joints, rounded block shoulders, broken crests and detached blocks below.','limits':'Mojave National Preserve regional analogue, not a verified Victorville or Apple Valley site. No measured dimensions inferred; no horizontal sedimentary strata claimed; no image pixels used.'}};(R/'receipts/rocky_ridges_o.json').write_text(json.dumps(receipt,indent=2));print('ROCKY_RIDGES_READY',receipt,flush=True)
