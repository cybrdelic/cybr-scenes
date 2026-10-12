"""Let the retained finite surface inventory own optics in its qualified domain.
Historical AP coverage remains the parent response outside that domain. This
changes representation ordering only; no sediment, colors or relief are added.
"""
from pathlib import Path
import json,hashlib,time
import numpy as np
from fine_coating_az import graph_stamp
GROUND='Graded shoulder and alluvial plain -1'
FIELD_SHA='cb13eb9f9422741f113d244f249e6b70cece71596934df63643a59412483dac3'

def sample_domain(xy,f):
 x,y=f['x_m'],f['y_m'];p=np.asarray(xy,float);q=np.zeros(len(p));inside=(p[:,0]>=x[0])&(p[:,0]<=x[-1])&(p[:,1]>=y[0])&(p[:,1]<=y[-1]);v=p[inside]
 if len(v):
  u=(v[:,0]-x[0])/(x[1]-x[0]);w=(v[:,1]-y[0])/(y[1]-y[0]);i=np.minimum(np.floor(u).astype(int),len(x)-2);j=np.minimum(np.floor(w).astype(int),len(y)-2);a=u-i;b=w-j;z=f['historical_domain_strength'];q[inside]=(1-b)*((1-a)*z[j,i]+a*z[j,i+1])+b*((1-a)*z[j+1,i]+a*z[j+1,i+1])
 assert np.isfinite(q).all() and q.min()>=-1e-6 and q.max()<=1+1e-6;return np.clip(q,0,1)

def apply(scene,cfg,out):
 import bpy
 assert cfg['revision']==1;path=Path(cfg['fields']);assert hashlib.sha256(path.read_bytes()).hexdigest()==FIELD_SHA
 o=scene.objects[GROUND];me=o.data;assert me.users==1 and not o.modifiers and np.array_equal(np.asarray(o.matrix_world),np.eye(4));assert not me.attributes.get('cc_finite_surface_authority')
 co=np.empty((len(me.vertices),3),'f4');me.vertices.foreach_get('co',co.ravel());before_co=hashlib.sha256(co.tobytes()).hexdigest();f=np.load(path,allow_pickle=False);d=sample_domain(co[:,:2],f).astype('f4');old=me.materials[0];assert old.get('bw_historical_fine_area') and not old.get('cc_surface_authority')
 n=old.node_tree.nodes;mix=n['BW / two source closures area mixture'];bounded=n['BW / bounded existing area'];assert mix.inputs[0].links[0].from_socket==bounded.outputs['Result'];assert mix.inputs[1].links[0].from_node.name=='Linked dry dielectric' and mix.inputs[2].links[0].from_node.name=='BW / original fine-only dielectric'
 oldstamp=graph_stamp(old);m=old.copy();m.name='CC finite inventory owns current shoulder surface';names={q.name for q in m.node_tree.nodes};allowed={(mix.name,mix.inputs[0].identifier)};protected=graph_stamp(m,names,allowed);n,l=m.node_tree.nodes,m.node_tree.links
 a=n.new('ShaderNodeAttribute');a.name='CC / retained finite-domain authority';a.attribute_name='cc_finite_surface_authority';inv=n.new('ShaderNodeMath');inv.name='CC / parent coverage outside finite domain';inv.operation='SUBTRACT';inv.inputs[0].default_value=1.;l.new(a.outputs['Fac'],inv.inputs[1]);mul=n.new('ShaderNodeMath');mul.name='CC / remove duplicate historical overcoat';mul.operation='MULTIPLY';l.new(n['BW / bounded existing area'].outputs['Result'],mul.inputs[0]);l.new(inv.outputs[0],mul.inputs[1]);l.new(mul.outputs[0],n[mix.name].inputs[0])
 assert graph_stamp(m,names,allowed)==protected and graph_stamp(old)==oldstamp
 attr=me.attributes.new('cc_finite_surface_authority','FLOAT','POINT');attr.data.foreach_set('value',d);m['cc_surface_authority']=True;me.materials[0]=m
 check=np.empty_like(co);me.vertices.foreach_get('co',check.ravel());assert np.array_equal(check,co)
 # Summaries are vertex diagnostics, explicitly not projected/physical area.
 def read(name):
  v=np.empty(len(me.vertices),'f4');me.attributes[name].data.foreach_get('value',v);return v
 ap=read('ap_fines');film=read('ai_fine_coat');lag=read('ai_coarse_lag');conflict=(d>.999)&(ap>.85)&(film<.01);interior=d>.999
 report=dict(revision='CC',fields_sha256=FIELD_SHA,domain_bounds_m=[float(f['x_m'][0]),float(f['x_m'][-1]),float(f['y_m'][0]),float(f['y_m'][-1])],domain_boundary_feather_m=.12,source_material=old.name,source_graph_sha256=oldstamp,protected_graph_unchanged=True,new_factor='clamp(ap_fines) * (1 - sampled historical_domain_strength)',finite_event_closure='Existing AZ/AI closure retains surviving prior skin, retained fine class, lag, historical matrix and compaction.',vertices=len(d),interior_vertices=int(interior.sum()),conflicting_high_ap_exhausted_skin_vertices=int(conflict.sum()),conflict_mean_lag=float(lag[conflict].mean()) if conflict.any() else 0,old_extra_fine_factor_mean_interior=float(ap[interior].mean()),new_extra_fine_factor_mean_interior=float((ap*(1-d))[interior].mean()),authority_minmax=[float(d.min()),float(d.max())],geometry_sha256=before_co,geometry_changed=False,existing_fields_changed=False,sediment_inventory_changed=False,particle_geometry_or_placement_changed=False,source_images_changed=False,lighting_changed=False,source_saved=False,limitations='Authored domain boundary and nonvalidated finite-layer optical proxies remain. This resolves duplicate top-layer authority; it does not validate erosion physics or add missing coarse substrate geometry.')
 (Path(out)/'HISTORICAL_SURFACE_AUTHORITY_CC.json').write_text(json.dumps(report,indent=2)+'\n');f.close();return report
