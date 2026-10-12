"""Non-saving, bounded raveled edge assembly for one actual CPU diagnostic."""
from pathlib import Path
import hashlib,json,gc
import numpy as np
import bpy
from edge_ravel_field_aa import EdgeRavelField
from metric_edge_strip_aa import prepare_edge_strip,_read,_attributes,ATTRIBUTE_TYPES

def _mesh(name,co,faces,material):
    me=bpy.data.meshes.new(name);me.from_pydata(co,[],faces);me.materials.append(material);me.update();ob=bpy.data.objects.new(name,me);bpy.context.scene.collection.objects.link(ob);return ob

def trim_old_wall(scene,bounds):
    ob=scene.objects['Broken exposed asphalt edge -1'];old=ob.data
    assert np.allclose(np.asarray(ob.matrix_world),np.eye(4)) and not ob.modifiers
    attrs=_attributes(old);co=_read(old.vertices,'co',3);lv=_read(old.loops,'vertex_index',1,np.int32);starts=_read(old.polygons,'loop_start',1,np.int32);counts=_read(old.polygons,'loop_total',1,np.int32)
    outco=list(co);faces=[];parents=[];extra=[]
    def clip(poly,threshold,below):
        out=[]
        for q,a in enumerate(poly):
            b=poly[(q+1)%len(poly)];ina=a[1]<=threshold if below else a[1]>=threshold;inb=b[1]<=threshold if below else b[1]>=threshold
            if ina:out.append(a)
            if ina!=inb:
                f=(threshold-a[1])/(b[1]-a[1]);out.append(a*(1-f)+b*f)
        return out
    for i,(st,n) in enumerate(zip(starts,counts)):
        ids=lv[st:st+n];ys=co[ids,1]
        if ys.max()<=bounds[0] or ys.min()>=bounds[1]:faces.append(ids.tolist());parents.append(i);continue
        if ys.min()>=bounds[0] and ys.max()<=bounds[1]:continue
        poly=np.c_[co[ids],np.eye(n)]
        for below,t in [(True,bounds[0]),(False,bounds[1])]:
            clipped=clip(poly,t,below)
            if len(clipped)<3:continue
            ring=[]
            for p in clipped:
                k=int(np.argmax(p[3:]));
                if p[3+k]>.999999999:ring.append(int(ids[k]))
                else:ring.append(len(outco));outco.append(p[:3]);extra.append((ids,p[3:]))
            faces.append(ring);parents.append(i)
    new=bpy.data.meshes.new(old.name+' / bounded wall removal AA');new.from_pydata(outco,[],faces)
    for m in old.materials:new.materials.append(m)
    for name,(domain,dtype,prop,discrete,values) in attrs.items():
        if domain=='POINT':
            tails=[values[ids[int(np.argmax(w))]] if discrete else np.tensordot(w,values[ids],axes=(0,0)) for ids,w in extra];data=np.concatenate((values,np.asarray(tails,dtype=values.dtype))) if tails else values
        elif domain=='FACE':data=values[parents]
        elif domain=='EDGE':continue
        else:raise ValueError('Unqualified wall corner attribute '+name)
        a=new.attributes.get(name) or new.attributes.new(name,dtype,domain);a.data.foreach_set(prop,np.asarray(data).ravel())
    mi=_read(old.polygons,'material_index',1,np.int32);sm=_read(old.polygons,'use_smooth',1,bool);new.polygons.foreach_set('material_index',mi[parents]);new.polygons.foreach_set('use_smooth',sm[parents]);new.update();ob.data=new
    if old.users==0:bpy.data.meshes.remove(old)
    return dict(old_faces=len(counts),new_faces=len(faces),range_y_m=list(bounds),partial_faces_clipped=True)

def fill_soil_gap(scene,result):
    ground=scene.objects['Graded shoulder and alluvial plain -1'];old=ground.data;co=_read(old.vertices,'co',3)
    assert np.allclose(np.asarray(ground.matrix_world),np.eye(4))
    # Existing inner boundary is the maximum X vertex of each original Y row.
    near=np.flatnonzero((co[:,0]>-3.5)&(co[:,1]>=-.08)&(co[:,1]<=2.08));order=np.argsort(co[near,1],kind='stable');ids=near[order];ys,starts=np.unique(co[ids,1],return_index=True);groups=np.split(ids,starts[1:]);edgeids=np.array([a[np.argmax(co[a,0])] for a in groups]);edge=co[edgeids]
    y=result['new_edge_xyz'][:,1];top=result['new_edge_xyz'];gx=np.interp(y,edge[:,1],edge[:,0]);gz=np.interp(y,edge[:,1],edge[:,2]);gap=top[:,0]-gx
    # Brown soil fills only newly uncovered open footprints. At the actual
    # asphalt border it stays at least150um below each sampled crown vertex.
    sz=np.where(gap>1e-7,np.minimum(gz,top[:,2]-.00015),gz);verts=np.empty((len(y)*2,3));verts[::2]=np.c_[gx,y,gz];verts[1::2]=np.c_[np.maximum(gx,top[:,0]),y,sz]
    faces=[]
    for i in range(len(y)-1):
        if max(gap[i],gap[i+1])<=1e-7:continue
        q=2*i
        if gap[i]>1e-7:faces.append((q,q+1,q+3))
        if gap[i+1]>1e-7:faces.append((q,q+3,q+2))
    if not faces:return dict(gap_faces=0)
    ob=_mesh('AA existing-soil support in raveled openings',verts,faces,old.materials[0]);attrs=_attributes(old)
    for name,(domain,dtype,prop,discrete,values) in attrs.items():
        if domain!='POINT':continue
        avalues=values[edgeids];flat=avalues.reshape(len(edgeids),-1)
        if discrete:
            index=np.argmin(np.abs(y[:,None]-edge[:,1][None,:]),axis=1);v=avalues[index]
        else:v=np.column_stack([np.interp(y,edge[:,1],flat[:,k]) for k in range(flat.shape[1])]).reshape((len(y),)+avalues.shape[1:])
        a=ob.data.attributes.new(name,dtype,domain);a.data.foreach_set(prop,np.repeat(v,2,axis=0).ravel())
    # The former wall is removed; minute exposed crown sides close onto soil.
    skirt=np.empty_like(verts);skirt[::2]=top;skirt[1::2]=np.c_[top[:,0],y,sz]
    side=_mesh('AA finite exposed crown ends',skirt,[f[::-1] for f in faces],scene.objects['Broken exposed asphalt edge -1'].data.materials[0])
    a=side.data.attributes.new('asphalt_share','FLOAT','POINT');a.data.foreach_set('value',np.ones(len(skirt),np.float32))
    a=side.data.attributes.new('macro_tint','FLOAT_COLOR','POINT');a.data.foreach_set('color',np.tile([.68,.67,.65,1.],(len(skirt),1)).ravel())
    return dict(gap_faces=len(faces),max_gap_width_m=float(np.maximum(gap,0).max()),max_exposed_crown_side_m=float(np.max(top[:,2]-sz)),minimum_soil_crown_clearance_m=.00015,original_ground_vertices_unchanged=True,existing_soil_boundary_interpolated=True)

def apply(scene,config):
    height=Path(config['height_path']);field=EdgeRavelField(height);road=scene.objects['Crowned asphalt crust / longitudinal rise']
    result=prepare_edge_strip(road,height,boundary_builder=lambda old,bounds:field.project(old,bounds,side=-1))
    wall=trim_old_wall(scene,(0.,2.));soil=fill_soil_gap(scene,result);old=road.data;road.data=result['mesh']
    if old.users==0:bpy.data.meshes.remove(old)
    report=dict(strip=result['report'],ravel=result['boundary_profile'].receipt,wall=wall,soil=soil,source_height_sha256=hashlib.sha256(height.read_bytes()).hexdigest(),scope='Bounded in-memory physical edge diagnostic. Approximate original-crown segmentation, exact preserved material maps/stripe. No full scene save.',quality='Actual render inspection required')
    del result;gc.collect();return report
