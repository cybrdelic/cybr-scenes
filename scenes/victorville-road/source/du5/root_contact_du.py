"""Original basal wood flare, integrated with the DU4 irregular soil collar.
Only low main-stem components of existing CK shrubs are shaped. No mineral
geometry or sediment inventory is added. Existing crown/foliage is untouched.
"""
from pathlib import Path
import bpy,numpy as np,json,hashlib
from field_du import smooth

def apply(scene,out):
 rows=[];seen=set()
 for ob in scene.objects:
  if ob.hide_render or not ob.name.startswith('CK pocket /'):continue
  if not(-40<ob.location.x<40 and -6<ob.location.y<125):continue
  identity=ob.data.as_pointer()
  if identity in seen:continue
  seen.add(identity)
  # Component membership comes from authored stem faces, not a guessed cylinder.
  polygons=[p for p in ob.data.polygons if p.material_index==0]
  if not polygons:continue
  parent={v:v for p in polygons for v in p.vertices}
  def find(i):
   while parent[i]!=i:parent[i]=parent[parent[i]];i=parent[i]
   return i
  for p in polygons:
   a=find(p.vertices[0])
   for v in p.vertices[1:]:parent[find(v)]=a
  components={}
  for i in parent:components.setdefault(find(i),[]).append(i)
  co=np.empty((len(ob.data.vertices),3),'f4');ob.data.vertices.foreach_get('co',co.ravel());mw=np.asarray(ob.matrix_world);w=co@mw[:3,:3].T+mw[:3,3];before=w.copy();z0=min(w[i,2]for i in parent);touched=0
  for ids in components.values():
   ix=np.array(ids);part=w[ix];low=float(part[:,2].min());high=float(part[:,2].max())
   if low>z0+.016 or high-low<.055:continue
   bottom=part[part[:,2]<low+.010];center=bottom[:,:2].mean(0);d=part[:,:2]-center;angle=np.arctan2(d[:,1],d[:,0]);gain=.7*(1-smooth(low,low+.075,part[:,2]))**2*(1+.24*np.sin(angle*3+center[0])+.16*np.sin(angle*5-center[1]));w[ix,:2]+=d*gain[:,None];touched+=1
  if not touched:continue
  # Author the shared basal prototype once. Preserve instancing and all exact
  # foliage vertices; copying full crowns would waste BVH memory.
  mesh=ob.data;inv=np.linalg.inv(mw);changed=np.any(w!=before,axis=1);new=co.copy();new[changed]=((w[changed]-mw[:3,3])@inv[:3,:3].T).astype('f4');assert np.array_equal(new[~changed],co[~changed]);mesh.vertices.foreach_set('co',new.ravel());mesh.update()
  rows.append({'prototype':mesh.name,'representative_object':ob.name,'shared_users':mesh.users,'basal_components':touched,'changed_vertices':int(np.count_nonzero(np.any(w!=before,axis=1))),'maximum_radial_change_m':float(np.linalg.norm(w[:,:2]-before[:,:2],axis=1).max()),'source_vertex_sha256':hashlib.sha256(co.tobytes()).hexdigest(),'result_vertex_sha256':hashlib.sha256(new.astype('f4').tobytes()).hexdigest(),'foliage_and_topology_unchanged':True})
 report={'revision':'DU4','plants':rows,'sediment_added_m3':0.,'model':'Authored irregular basal wood flare plus the area-conserved foundation collar. Not measured botany or plant growth simulation.'};Path(out,'DU_ROOT_CONTACT.json').write_text(json.dumps(report,indent=2)+'\n');return report
