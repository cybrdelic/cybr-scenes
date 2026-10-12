"""Reusable authored tapered stem sections and physically curved leaf laminae.

All dimensions are metres. Consumes the existing scene owner's attached axes
and leaf calls; does not own plant placement, lighting or a species claim.
No change to the retained leaf budget or material slots is required.
"""
import math
from mathutils import Vector
UP=Vector((0,0,1))

def refined_tube(mesh,points,radii,material,sides=5,phase=0.):
 """Variable asymmetric cambial flutes and metric shallow bark fissures."""
 if len(points)<2:return
 radius=max(radii)
 if not hasattr(mesh,'flow_axes'):mesh.flow_axes=[]
 mesh.flow_axes.append((points,radii))
 # Fine twigs keep their low-cost authored construction. Larger stems receive
 # enough circumference and axial samples for genuine millimetre bark form.
 rings=[];rs=[];distances=[];length=0.
 for j,(a,b) in enumerate(zip(points,points[1:])):
  seg=(b-a).length;count=max(1,min(12,math.ceil(seg/.006)))
  for k in range(count):
   t=k/count;rings.append(a.lerp(b,t));rs.append(radii[j]*(1-t)+radii[j+1]*t);distances.append(length+seg*t)
  length+=seg
 rings.append(points[-1]);rs.append(radii[-1]);distances.append(length)
 sides=max(sides,24 if radius>.008 else 16)
 # Parallel transported frame avoids independent per-ring spiralling.
 tangents=[(rings[min(i+1,len(rings)-1)]-rings[max(0,i-1)]).normalized() for i in range(len(rings))]
 reference=Vector((.317,.719,.618));side=tangents[0].cross(reference).normalized();frames=[]
 for tangent in tangents:
  side=(side-tangent*side.dot(tangent)).normalized();frames.append((side,tangent.cross(side).normalized()))
 seed=points[0].dot(Vector((193.7,71.3,417.9)))+material*13.9;offset=len(mesh.vertices)
 for j,(p,r,d,(side,other)) in enumerate(zip(rings,rs,distances,frames)):
  t=d/max(length,1e-8)
  for k in range(sides):
   angle=math.tau*k/sides+phase
   # Broad unequal lobes from eccentric growth, separate from fine bark seams.
   flute=.035*math.sin(3*angle+.9*d+seed)+.025*math.sin(5*angle-6*d+1.7*seed)+.012*math.sin(9*angle+15*d+.2*seed)
   seam=max(0.,math.cos(11*angle+6*d+seed))**12
   weather=math.sin(31*d+2*angle+seed)*math.sin(71*d-3*angle-.7*seed)
   bark_depth=min(.00055,r*.055)*seam*(.6+.4*math.sin(17*d+seed)**2)
   growth=r*(1+flute)+min(.00023,r*.03)*weather-bark_depth
   # Asymmetric base/buttress form comes from the retained axis taper, not an
   # oversized uniform skirt or an added subterranean cylinder.
   mesh.vertices.append(tuple(p+growth*(math.cos(angle)*side+math.sin(angle)*other)))
 mesh.face(tuple(offset+k for k in reversed(range(sides))),material)
 for j in range(len(rings)-1):
  a=offset+j*sides;b=a+sides
  for k in range(sides):mesh.face((a+k,a+(k+1)%sides,b+(k+1)%sides,b+k),material,True)
 mesh.face(tuple(offset+(len(rings)-1)*sides+k for k in range(sides)),material);mesh.branch_count+=1

def curved_leaf(mesh,base,direction,normal,length,width,curl,material):
 """Small variable lamina, curved through length and width, same metric bounds."""
 axis=direction.normalized();side=normal.cross(axis)
 if side.length_squared<1e-9:side=UP.cross(axis)
 if side.length_squared<1e-9:side=Vector((1,0,0))
 side.normalize();up=axis.cross(side).normalized();offset=len(mesh.vertices)
 seed=base.dot(Vector((717.1,431.7,287.3)));skew=.09*math.sin(seed);twist=.35*math.sin(seed*1.7);cup=.22+.10*math.sin(seed*.9)
 # Seven longitudinal rings with narrow endpoints keep the original almond
 # footprint but remove the repeated flat eight-triangle diamond silhouette.
 for j in range(7):
  u=j/6;shape=math.sin(math.pi*u)**.82;shape=max(.018,shape);middle=length*(curl*u*u+.08*math.sin(math.pi*u)*math.sin(seed));bend=width*skew*math.sin(math.pi*u)
  for v in (-1,0,1):
   across=.5*width*shape*v*(1+skew*v);height=middle+width*shape*(cup*v*v+.075*(1-v*v))+across*twist*(u-.35)
   mesh.vertices.append(tuple(base+axis*(length*u)+side*(across+bend)+up*height))
 for j in range(6):
  a=offset+3*j;b=a+3
  for k in range(2):
   mesh.face((a+k,a+k+1,b+k+1),material,True);mesh.face((a+k,b+k+1,b+k),material,True)
 mesh.leaf_count+=1

def geometry_from_owner(owner,kind,seed):
 """Wrap the existing CM scene recipe without copying its branch/leaf recipe."""
 Base=owner.base._Mesh;original_skeleton=owner.skeleton
 class Refined(Base):
  def __init__(self):
   super().__init__();self.coarse_wood=Base()
  def tube(self,points,radii,material,sides=5,phase=0.):
   if max(radii)>.0032:refined_tube(self.coarse_wood,points,radii,material,sides,phase)
   else:super().tube(points,radii,material,sides,phase)
  def leaf(self,*args):curved_leaf(self,*args)
  def object(self,*args):
   ob=super().object(*args)
   ob.data.attributes.new('dv_wood_flow_m','FLOAT_VECTOR','POINT').data.foreach_set('vector',self.flow_m.ravel())
   ob.data.attributes.new('dv_wood_flow_valid','FLOAT','POINT').data.foreach_set('value',self.flow_valid)
   return ob
 def skeleton(k,s):
  axes=original_skeleton(k,s);root=[a for a in axes if a.parent<0];centre=sum((a.points[0] for a in root),Vector())/len(root)
  for index,a in enumerate(axes):
   if a.parent<0:
    original=list(a.points);base=original[0];top=original[-1];radial=base-centre;radial.z=0
    tangent=Vector((math.cos(index*2.1+.5),math.sin(index*2.1+.5),0));n=len(a.points)
    for j,p in enumerate(original):
     t=j/(n-1);bend=tangent*(.009*math.sin(math.pi*t)*(1-.35*t));a.points[j]=p+radial*(.12*(1-t)**2)+bend*.45
     a.points[j].z=base.z+(p.z-base.z)*.45
    # Root sectors have visibly unequal taper rather than straight equal tubes.
    a.radii=[r*.64*(1+.12*(1-j/(n-1))**3-.04*math.sin(math.pi*j/(n-1))) for j,r in enumerate(a.radii)]
   else:
    parent=axes[a.parent];target,_=owner.base._sample(parent.points,a.attachment);delta=target-a.points[0];n=len(a.points)
    a.points=[p+delta*(1-j/(n-1))**1.4 for j,p in enumerate(a.points)]
    if a.order==1:a.radii=[r*.78 for r in a.radii]
  skeleton.root_sites=[(tuple(a.points[0]),tuple((a.points[1]-a.points[0]).normalized()),a.radii[0]) for a in axes if a.parent<0]
  return axes
 try:
  owner.base._Mesh=Refined;owner.skeleton=skeleton;mesh=owner.geometry(kind,seed);mesh.dv_root_sites=skeleton.root_sites
 finally:owner.base._Mesh=Base;owner.skeleton=original_skeleton
 fuse_coarse_wood(mesh)
 mesh.cm_stats.update({'geometry_candidate':'DV2 low connected forks, fused coarse wood and curved laminae','leaf_budget_unchanged':mesh.leaf_count==owner.LEAF_BUDGET[kind],'metric_bark_max_nominal_depth_m':.00055,'placement_authority_unchanged':True,'limits':'Authored scene morphology, not measured botany or growth mechanics. Coarse wood is voxel-fused; fine branch tubes retain overlapping axis attachments.'})
 return mesh


def fuse_coarse_wood(mesh,voxel_m=.0006):
 """Fuse actual coarse branch volume before rejoining fine twigs and leaves."""
 import bpy,numpy as np
 wood=mesh.coarse_wood;assert wood.vertices and set(wood.material_indices)=={0}
 data=bpy.data.meshes.new('DV temporary coarse branch union');data.from_pydata(wood.vertices,[],wood.faces);data.update();ob=bpy.data.objects.new('DV temporary union',data);bpy.context.scene.collection.objects.link(ob)
 for obj in bpy.context.selected_objects:obj.select_set(False)
 ob.select_set(True);bpy.context.view_layer.objects.active=ob
 modifier=ob.modifiers.new('Metric coarse wood union','REMESH');modifier.mode='VOXEL';modifier.voxel_size=voxel_m;modifier.use_smooth_shade=True
 bpy.ops.object.modifier_apply(modifier=modifier.name)
 out=ob.data
 # Closed voxel union and explicit basal components rule out floating coarse
 # branch ends before any scene integration. Three separate root crowns are
 # allowed, but every retained coarse component must reach the basal datum.
 edge_ids=np.empty(len(out.loops),'i4');out.loops.foreach_get('edge_index',edge_ids);degree=np.bincount(edge_ids,minlength=len(out.edges));assert np.all(degree==2)
 edges=np.empty((len(out.edges),2),'i4');out.edges.foreach_get('vertices',edges.ravel());parents=list(range(len(out.vertices)))
 def find(i):
  while parents[i]!=i:parents[i]=parents[parents[i]];i=parents[i]
  return i
 for a,b in edges:
  a=find(int(a));b=find(int(b))
  if a!=b:parents[max(a,b)]=min(a,b)
 labels=np.fromiter((find(i) for i in range(len(parents))),dtype='i4',count=len(parents))
 vertices=np.array([tuple(v.co) for v in out.vertices]);groups=[]
 for label in np.unique(labels):
  part=vertices[labels==label];low=part[:,2].min();assert low<.012,('Floating coarse wood component',float(low))
  basal=part[part[:,2]<low+.0015];groups.append(basal)
 assert 1<=len(groups)<=3
 mesh.cm_stats['fused_wood_closed_two_manifold']=True;mesh.cm_stats['fused_wood_components']=len(groups);mesh.cm_stats['every_coarse_component_reaches_basal_datum']=True
 basal_caps=[]
 for centre,tangent,radius in mesh.dv_root_sites:
  delta=vertices-np.array(centre);tangent=np.array(tangent);along=delta@tangent;radial=delta-along[:,None]*tangent;take=(abs(along)<.0018)&(np.linalg.norm(radial,axis=1)<radius*1.35);cap=vertices[take];assert len(cap)>10;basal_caps.append(cap)
 mesh.dv_basal_groups=basal_caps;mesh.cm_stats['authored_basal_caps_checked']=len(basal_caps)
 offset=len(mesh.vertices);mesh.flow_m=np.concatenate((np.zeros((offset,3),'f4'),flow_coordinates(vertices,wood.flow_axes)));mesh.flow_valid=np.concatenate((np.zeros(offset,'f4'),np.ones(len(vertices),'f4')));mesh.vertices.extend(tuple(v) for v in vertices)
 for face in out.polygons:mesh.face(tuple(offset+i for i in face.vertices),0,True)
 mesh.branch_count+=wood.branch_count;mesh.cm_stats['coarse_wood_union_voxel_m']=voxel_m;mesh.cm_stats['fused_coarse_vertices']=len(out.vertices);mesh.cm_stats['fused_coarse_polygons']=len(out.polygons)
 bpy.data.objects.remove(ob,do_unlink=True)
 if out.users==0:bpy.data.meshes.remove(out)
 if data!=out and data.users==0:bpy.data.meshes.remove(data)


def flow_coordinates(vertices,axes):
 import numpy as np
 best=np.full(len(vertices),np.inf);result=np.zeros_like(vertices);ref=np.array((.317,.719,.618))
 for points,radii in axes:
  distance=0.
  for j in range(len(points)-1):
   a=np.array(points[j]);b=np.array(points[j+1]);delta=b-a;length=np.linalg.norm(delta);tangent=delta/length;side=np.cross(tangent,ref);side/=np.linalg.norm(side);other=np.cross(tangent,side)
   t=np.clip((vertices-a)@delta/(length*length),0,1);centre=a+t[:,None]*delta;radial=vertices-centre;radius=radii[j]*(1-t)+radii[j+1]*t;error=abs(np.linalg.norm(radial,axis=1)-radius);take=error<best
   result[take,0]=radial[take]@side;result[take,1]=radial[take]@other;result[take,2]=distance+t[take]*length;best[take]=error[take];distance+=length
 return result.astype('f4')
