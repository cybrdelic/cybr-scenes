"""AR exact source-triangle fracture preparation; no scene assignment or rendering.

Prepare AFTER AH/AC/AL/AI and BEFORE continuous_contact_aq. The returned mesh
is unlinked. It is deliberately NOT an apply(scene) hook: all visible asphalt
owners, a replacement physical section, and AC's vacated soil footprint must be
integrated before assignment. AQ's Z-only contact pass cannot fill an XY gap.

Actual boundary geometry is cut, never pushed. Retained source facets, texture
phase, materials, POINT/FACE/CORNER fields and custom normals have explicit
barycentric provenance. The finite approved-relief crown footprints set the
fine break, with no new noise mask or lateral wavelength. A measured upper
concave envelope removes inherited short-wave scallops by inward loss only.
This envelope is an authored repair, not a calibrated erosion simulation.
"""
from dataclasses import dataclass
import numpy as np
from metric_edge_strip_aa import _read, _attributes, interpolate, ATTRIBUTE_TYPES, TOPOLOGY_ATTRIBUTES
from edge_ravel_field_aa import EdgeRavelField, PINNED_GEOMETRY_SHA256


def require(ok, message):
    if not ok:
        raise ValueError(message)


@dataclass(frozen=True)
class FractureSpec:
    y_min_m: float = -.12
    y_max_m: float = 15.12
    max_envelope_loss_m: float = .080
    max_total_loss_m: float = .095
    max_additions: int = 160000
    max_triangles: int = 240000
    max_source_triangles: int = 1200000
    extra_buffer_cap_mib: float = 190.

    def validate(self):
        require(self.y_min_m < 0 and self.y_max_m > 15, 'Visible y=0..15 requires exterior collars')
        require(self.y_max_m-self.y_min_m <= 16, 'Bounded visible interval only')
        require(0 < self.max_envelope_loss_m <= .080 and self.max_total_loss_m <= .095,
                'Measured inward envelope exceeds permitted repair width')
        require(self.max_additions <= 160000 and self.max_triangles <= 240000 and
                self.extra_buffer_cap_mib <= 190, 'AR allocation limits exceeded')
        return self


@dataclass
class Boundary:
    y: np.ndarray
    x: np.ndarray
    old_y: np.ndarray
    old_x: np.ndarray
    report: dict

    def x_edge(self, y):
        return np.interp(y, self.y, self.x)


def upper_envelope(y, x):
    """Least concave polygonal majorant; removes scallops, adds no wavelength."""
    y,x=np.asarray(y,float),np.asarray(x,float)
    require(len(y)>=2 and np.all(np.diff(y)>0), 'Ordered actual boundary required')
    hull=[]
    for i in range(len(y)):
        while len(hull)>1:
            a,b=hull[-2:]
            if (x[b]-x[a])*(y[i]-y[b]) > (x[i]-x[b])*(y[b]-y[a]):
                break
            hull.pop()
        hull.append(i)
    h=np.asarray(hull)
    return np.interp(y,y[h],x[h]),h


def actual_left_boundary(co, triangles, spec=None):
    """Actual topological rim only, not the old generator's edge equation."""
    spec=(spec or FractureSpec()).validate();co=np.asarray(co);tri=np.asarray(triangles)
    chunks=[]
    for first in range(0,len(tri),16384):
        t=tri[first:first+16384];p=co[t,:2]
        area=np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0])
        keep=(p[:,:,0].min(1)<-3.04)&(p[:,:,1].max(1)>=spec.y_min_m-.2)&(p[:,:,1].min(1)<=spec.y_max_m+.2)&(abs(area)>1e-13)
        chunks.append(t[keep])
    t=np.concatenate(chunks);require(len(t)>0,'Missing actual road rim')
    e=np.sort(np.concatenate([t[:,[j,(j+1)%3]] for j in range(3)]),axis=1)
    edges,uses=np.unique(e,axis=0,return_counts=True);edges=edges[uses==1]
    p=co[edges,:2];p=p[np.all(p[:,:,0]<-3.04,axis=1)]
    require(len(p)>1,'No exposed left boundary')
    yy=np.unique(np.concatenate((np.array([spec.y_min_m,spec.y_max_m],dtype=np.float64),p[:,:,1].astype(np.float64).ravel())))
    yy=yy[(yy>=spec.y_min_m)&(yy<=spec.y_max_m)];xx=[]
    for y in yy:
        a,b=p[:,0],p[:,1];dy=b[:,1]-a[:,1]
        ok=(abs(dy)>1e-12)&(y>=np.minimum(a[:,1],b[:,1])-1e-9)&(y<=np.maximum(a[:,1],b[:,1])+1e-9)
        require(np.any(ok),'Actual left rim is longitudinally incomplete')
        xx.append(float(np.min(a[ok,0]+(y-a[ok,1])/dy[ok]*(b[ok,0]-a[ok,0]))))
    return yy,np.asarray(xx)


def build_boundary(old_y, old_x, height_path, spec=None):
    spec=(spec or FractureSpec()).validate();y=np.asarray(old_y,float);x=np.asarray(old_x,float)
    require(y[0]<=spec.y_min_m and y[-1]>=spec.y_max_m,'Actual rim must cover exterior collars')
    envelope,h=upper_envelope(y,x)
    require(np.max(envelope-x)<=spec.max_envelope_loss_m,'Inherited scallops need a wider repair than authorized AR cap')
    base=lambda q:np.interp(q,y,envelope)
    field=EdgeRavelField(height_path)
    pieces=[];receipts=[]
    cuts=np.linspace(spec.y_min_m,spec.y_max_m,6)
    for a,b in zip(cuts[:-1],cuts[1:]):
        # Overlap exceeds the finite crown-cluster neighbor reach (12 mm).
        lo=max(spec.y_min_m,a-.04);hi=min(spec.y_max_m,b+.04)
        profile=field.project(base,(lo,hi),side=-1)
        q=np.unique(np.r_[a,b,y[(y>a)&(y<b)],profile.y[(profile.y>a)&(profile.y<b)]])
        pieces.append(np.c_[q,profile.x_edge(q)]);receipts.append(profile.receipt)
    p=np.concatenate(pieces);q,idx=np.unique(p[:,0],return_index=True);v=p[idx,1]
    # Collars end outside the promised visible interval. No visible end fade.
    w=np.minimum(np.clip((q-spec.y_min_m)/(-spec.y_min_m),0,1),np.clip((spec.y_max_m-q)/(spec.y_max_m-15),0,1))
    old=np.interp(q,y,x);v=old+w*(v-old)
    # Preserve all genuine slope changes; only exact collinear runs disappear.
    slope=np.diff(v)/np.diff(q);keep=np.r_[True,abs(np.diff(slope))>1e-9,True]
    q,v=q[keep],v[keep]
    require(np.all(v>=np.interp(q,y,x)-1e-10),'AR must be inward-only')
    require(np.max(v-np.interp(q,y,x))<=spec.max_total_loss_m,'Total bounded loss exceeded')
    return Boundary(q,v,y,x,dict(source_sha256=PINNED_GEOMETRY_SHA256,world_tile_m=.25,phase_origin_m=[0,0],
        visible_y_m=[0,15],envelope_hull_vertices=int(len(h)),boundary_vertices=int(len(q)),
        maximum_envelope_loss_m=float(np.max(envelope-x)),maximum_total_loss_m=float(np.max(v-np.interp(q,y,x))),
        crown_instances_removed=sum(r['missing_crown_instances'] for r in receipts),
        macro_policy='Measured least concave majorant: inward removal of inherited scallops, no invented lateral waves',
        fine_policy='Finite approved-relief crown loss at original world positions; approximate footprint labels',
        source_relief_modified=False,material_modified=False,geometry_subset_only=True,
        integration_requires=['Clip every intersecting asphalt owner','Close new section from actual top rim','Extend AC soil through vacated XY footprint','Run AQ exact overlap and final film source coverage audits']))


def _clip(poly, value):
    """Clip barycentric-payload polygon by an arbitrary linear signed distance."""
    if not len(poly):return poly
    d=value(poly);out=[]
    for a,b,da,db in zip(poly,np.roll(poly,-1,axis=0),d,np.roll(d,-1)):
        ina,inb=da>=-1e-12,db>=-1e-12
        if ina:out.append(a)
        if ina!=inb:out.append(a+da/(da-db)*(b-a))
    return np.asarray(out,float).reshape(-1,5)


@dataclass
class CutPlan:
    keep_polygons: np.ndarray
    additions: np.ndarray
    addition_triangle: np.ndarray
    addition_weights: np.ndarray
    triangles: np.ndarray
    triangle_source: np.ndarray
    corner_weights: np.ndarray
    report: dict


def clip_actual_triangles(co, triangles, triangle_polygons, polygon_count, boundary, spec=None):
    """Exact graph clipping with propagated original-edge subdivisions.

    Works on vertical section triangles too: degeneracy is tested in XYZ.
    Source vertex identities never move. Entire unchanged polygons are retained.
    Every generated facet lies in one actual source triangle, so crossing,
    relief resampling and material mixing are excluded by construction.
    """
    spec=(spec or FractureSpec()).validate();co=np.asarray(co);tri=np.asarray(triangles,np.int32);tp=np.asarray(triangle_polygons,np.int32)
    require(len(tri)<=spec.max_source_triangles and tri.shape[1:]==(3,), 'Source tessellation cap exceeded')
    require(np.isfinite(co).all() and len(tp)==len(tri),'Finite actual provenance required')
    by,bx=boundary.y,boundary.x;loy,hiy=by[[0,-1]];maxx=float(bx.max())
    active=[]
    levels=[bx]
    while (1 << len(levels)) <= len(bx):
        step=1 << (len(levels)-1);v=levels[-1]
        levels.append(np.maximum(v[:-step],v[step:]))
    for start in range(0,len(tri),16384):
        p=co[tri[start:start+16384],:2]
        y0,y1=p[:,:,1].min(1),p[:,:,1].max(1)
        a=np.searchsorted(by,y0,side='left');b=np.searchsorted(by,y1,side='right');n=b-a
        local=np.maximum(boundary.x_edge(y0),boundary.x_edge(y1))
        for k,level in enumerate(levels):
            rows=np.flatnonzero((n>0)&(np.floor(np.log2(np.maximum(n,1))).astype(int)==k))
            if len(rows):local[rows]=np.maximum(local[rows],np.maximum(level[a[rows]],level[b[rows]-(1<<k)]))
        m=(p[:,:,0].min(1)<local)&(y1>loy)&(y0<hiy)
        active.extend((start+np.flatnonzero(m)).tolist())
    parents=np.unique(tp[active]);active=np.flatnonzero(np.isin(tp,parents))
    require(len(active)<=160000,'Affected source neighborhood cap exceeded')
    # Fixed numerical storage; dictionaries refer to IDs, never duplicate XYZ arrays.
    adds=np.empty((spec.max_additions,3));at=np.empty(spec.max_additions,np.int32);aw=np.empty((spec.max_additions,3))
    faces=np.empty((spec.max_triangles,3),np.int32);ft=np.empty(spec.max_triangles,np.int32);fw=np.empty((spec.max_triangles,3,3))
    lookup={};splits={};rings={};n=0;nf=0
    def vertex(t,w):
        nonlocal n
        one=np.flatnonzero(abs(w-1)<1e-12)
        if len(one):return int(tri[t,one[0]])
        xyz=w@co[tri[t]];zero=np.flatnonzero(abs(w)<1e-12)
        pos=int(np.searchsorted(by,xyz[1]));candidates=[i for i in (pos-1,pos) if 0<=i<len(by)]
        knot=min(candidates,key=lambda i:abs(by[i]-xyz[1])) if candidates else None
        at_knot=knot is not None and abs(by[knot]-xyz[1])<1e-11
        if len(zero)==1:
            edge=tuple(sorted(map(int,tri[t,[j for j in range(3) if j!=zero[0]]])))
            # Same source edge and exact world XYZ, never weld unrelated shells.
            # A shared source edge has at most one cut per profile segment.
            # Canonical topological cut IDs avoid decimal-rounding ties.
            key=('e',*edge,'k',knot) if at_knot else ('e',*edge,'s',int(np.clip(pos-1,0,len(by)-2)))
        else:
            edge=None
            on_profile=abs(xyz[0]-boundary.x_edge(xyz[1]))<1e-11
            key=('p',int(t),knot) if at_knot and on_profile else ('t',int(t),*np.round(w,12))
        if key not in lookup:
            require(n<spec.max_additions,'AR vertex cap exceeded')
            lookup[key]=len(co)+n;adds[n]=xyz;at[n]=t;aw[n]=w;n+=1
        vi=lookup[key]
        if edge is not None:splits.setdefault(edge,set()).add(vi)
        return vi
    for t in active:
        xyz=co[tri[t]];p=np.c_[xyz[:,:2],np.eye(3)];y0,y1=xyz[:,1].min(),xyz[:,1].max()
        cuts=np.r_[y0,by[(by>y0+1e-12)&(by<y1-1e-12)],y1]
        polys=[]
        if y1-y0<1e-12:
            if loy<y0<hiy:polys=[_clip(p,lambda a:a[:,0]-boundary.x_edge(y0))]
            else:polys=[p]
        else:
            for a,b in zip(cuts[:-1],cuts[1:]):
                q=_clip(_clip(p,lambda p:p[:,1]-a),lambda p:b-p[:,1])
                if not len(q):continue
                if b>loy and a<hiy:
                    xa,xb=boundary.x_edge([a,b]);s=(xb-xa)/(b-a)
                    q=_clip(q,lambda p:p[:,0]-(xa+s*(p[:,1]-a)))
                if len(q)>=3:polys.append(q)
        rings[int(t)]=[(list(vertex(t,w) for w in p[:,2:]),p[:,2:].copy()) for p in polys if len(p)>=3]
    # Propagate to all triangles of every neighboring polygon, without a global
    # Python scene-edge graph. Interior source diagonals are included too.
    neighbors=np.zeros(len(tri),bool)
    if splits:
        radix=len(co)+1;ee=np.asarray(list(splits),np.int64);wanted=np.sort(ee[:,0]*radix+ee[:,1])
        for j in range(3):
            for start in range(0,len(tri),32768):
                e=np.sort(tri[start:start+32768,[j,(j+1)%3]],axis=1).astype(np.int64);key=e[:,0]*radix+e[:,1]
                pos=np.searchsorted(wanted,key);ok=pos<len(wanted);match=np.zeros(len(key),bool);match[ok]=wanted[pos[ok]]==key[ok];neighbors[start:start+len(key)]|=match
    changed=np.unique(np.r_[parents,tp[neighbors]])
    for t in np.flatnonzero(np.isin(tp,changed)):
        if int(t) not in rings:rings[int(t)]=[(list(map(int,tri[t])),np.eye(3))]
    def xyz(i):return co[i] if i<len(co) else adds[i-len(co)]
    for t,polys in rings.items():
        for ring,weights in polys:
            ids=[];ws=[]
            for j,(a,b) in enumerate(zip(ring,ring[1:]+ring[:1])):
                wa,wb=weights[j],weights[(j+1)%len(ring)];ids.append(a);ws.append(wa)
                zero=np.flatnonzero((abs(wa)<1e-9)&(abs(wb)<1e-9))
                if len(zero)==1:
                    edge=tuple(sorted(map(int,tri[t,[k for k in range(3) if k!=zero[0]]])))
                    pa,pb=np.asarray(xyz(a),float),np.asarray(xyz(b),float);d=pb-pa;den=float(d@d);extra=[]
                    if den>1e-24:
                        for v in splits.get(edge,()):
                            u=float((xyz(v)-pa)@d/den)
                            if 1e-9<u<1-1e-9:extra.append((u,v))
                    for u,v in sorted(extra):ids.append(v);ws.append((1-u)*wa+u*wb)
            # Convex clipped pieces, centre fan honors every collinear edge split.
            if len(ids)==3:fan=[(ids,np.asarray(ws))]
            else:
                w=np.mean(ws,axis=0);c=vertex(t,w);fan=[([c,ids[j],ids[(j+1)%len(ids)]],np.asarray([w,ws[j],ws[(j+1)%len(ids)]])) for j in range(len(ids))]
            for f,w in fan:
                p=np.asarray([xyz(v) for v in f])
                if np.linalg.norm(np.cross(p[1]-p[0],p[2]-p[0]))<1e-14:continue
                require(nf<spec.max_triangles,'AR triangle cap exceeded')
                faces[nf]=f;ft[nf]=t;fw[nf]=w;nf+=1
    keep=np.setdiff1d(np.arange(polygon_count,dtype=np.int32),changed)
    return CutPlan(keep,adds[:n].copy(),at[:n].copy(),aw[:n].copy(),faces[:nf].copy(),ft[:nf].copy(),fw[:nf].copy(),
        dict(changed_polygons=int(len(changed)),retained_polygons=int(len(keep)),added_vertices=n,new_triangles=nf,
             source_edge_splits=len(splits),original_vertices_moved=0,exact_source_facets=True,
             boundary_report=boundary.report,scene_assigned=False,contact_complete=False))


def inherit_edge_metadata(old,new,source_triangles,plan,attribute_schema):
    """Retained edges and every subdivided original edge keep exact booleans.

    A newly exposed fracture edge or new triangle interior is not a renamed
    original edge. It receives the source schema's false creation default;
    explicit custom corner normals are installed afterward.
    """
    names=[name for name,meta in attribute_schema.items() if meta[0]=='EDGE']
    if not names:return dict(fields=[],split_edges_inherited=0)
    oe=_read(old.edges,'vertices',2,np.int32);ne=_read(new.edges,'vertices',2,np.int32)
    radix=len(new.vertices)+1
    so=np.sort(oe,axis=1).astype(np.int64);keys=so[:,0]*radix+so[:,1];del so
    order=np.argsort(keys);keys=keys[order]
    sn=np.sort(ne,axis=1).astype(np.int64);nk=sn[:,0]*radix+sn[:,1];del sn
    pos=np.searchsorted(keys,nk);found=pos<len(keys);rows=np.flatnonzero(found);found[rows]=keys[pos[rows]]==nk[rows]
    mapping=np.full(len(ne),-1,np.int32);mapping[found]=order[pos[found]]
    # Only generated vertices need a source-edge record, avoiding another
    # scene-size Python adjacency dictionary.
    vertex_edge=np.full((len(plan.additions),2),-1,np.int32)
    for i,(t,w) in enumerate(zip(plan.addition_triangle,plan.addition_weights)):
        zero=np.flatnonzero(abs(w)<1e-9)
        if len(zero)==1:vertex_edge[i]=np.sort(source_triangles[t,[k for k in range(3) if k!=zero[0]]])
    original=len(old.vertices);inherited=0
    for k in np.flatnonzero(~found):
        u,v=map(int,ne[k]);eu=vertex_edge[u-original] if u>=original else None;ev=vertex_edge[v-original] if v>=original else None;edge=None
        if eu is not None and ev is not None and eu[0]>=0 and np.array_equal(eu,ev):edge=eu
        elif eu is not None and eu[0]>=0 and v in eu:edge=eu
        elif ev is not None and ev[0]>=0 and u in ev:edge=ev
        if edge is not None:
            key=int(edge[0])*radix+int(edge[1]);j=int(np.searchsorted(keys,key))
            if j<len(keys) and keys[j]==key:mapping[k]=order[j];inherited+=1
    good=mapping>=0
    for name in names:
        domain,kind,prop,discrete,size,dtype=attribute_schema[name]
        source=_read(old.attributes[name].data,prop,size,dtype);out=np.zeros(len(ne),dtype=dtype);out[good]=source[mapping[good]]
        a=new.attributes.get(name) or new.attributes.new(name,kind,'EDGE');a.data.foreach_set(prop,out)
    return dict(fields=names,retained_source_edges=int(found.sum()),split_edges_inherited=inherited,new_edges_with_creation_default=int((~good).sum()))


def prepare_object(obj, boundary, spec=None):
    """Unlinked Blender owner mesh with original per-material identity.

    Calls only after the parent has selected an actual asphalt owner. No scene
    mutation, world-X translation, material copies, normal regeneration, saves
    or render. Caller must integrate ALL owners/contact before assigning.
    """
    import bpy
    spec=(spec or FractureSpec()).validate();old=obj.data
    require(not obj.modifiers and old.shape_keys is None and not obj.vertex_groups,'Raw mesh owner required')
    require(np.allclose(np.asarray(obj.matrix_world),np.eye(4),atol=1e-9),'World-identity owner required; tile instances need explicit world transform adapter')
    require(not old.animation_data,'Animated source unsupported')
    old.calc_loop_triangles()
    estimate=(len(old.vertices)*16+len(old.loops)*8+len(old.loop_triangles)*28+spec.max_additions*100+spec.max_triangles*140)/1024**2
    require(estimate<spec.extra_buffer_cap_mib,'AR numerical preflight exceeds 190 MiB; reduce owner scope, never silently drop data')
    attrs={}
    for a in old.attributes:
        if a.name in TOPOLOGY_ATTRIBUTES:continue
        require(a.data_type in ATTRIBUTE_TYPES and a.domain in {'POINT','CORNER','FACE','EDGE'},'Unsupported source attribute '+a.name)
        prop,size,dtype,discrete=ATTRIBUTE_TYPES[a.data_type]
        if a.domain=='EDGE':
            require(a.data_type=='BOOLEAN' and a.name in {'.select_edge','.hide_edge','sharp_edge','uv_seam'},'Unsupported EDGE field '+a.name)
        attrs[a.name]=(a.domain,a.data_type,prop,discrete,size,dtype)
    co=_read(old.vertices,'co',3);tri=_read(old.loop_triangles,'vertices',3,np.int32);tp=_read(old.loop_triangles,'polygon_index',1,np.int32);tl=_read(old.loop_triangles,'loops',3,np.int32)
    plan=clip_actual_triangles(co,tri,tp,len(old.polygons),boundary,spec)
    starts=_read(old.polygons,'loop_start',1,np.int32);sizes=_read(old.polygons,'loop_total',1,np.int32);lv=_read(old.loops,'vertex_index',1,np.int32)
    keep=plan.keep_polygons;km=np.zeros(len(sizes),bool);km[keep]=True;kl=np.flatnonzero(np.repeat(km,sizes)).astype(np.int32);del km
    counts=np.r_[sizes[keep],np.full(len(plan.triangles),3,np.int32)];flat=np.r_[lv[kl],plan.triangles.ravel()];allco=np.r_[co,plan.additions]
    new=bpy.data.meshes.new(old.name+' / exact fracture AR')
    try:
        new.vertices.add(len(allco));new.vertices.foreach_set('co',allco.ravel());new.loops.add(len(flat));new.loops.foreach_set('vertex_index',flat);new.polygons.add(len(counts));new.polygons.foreach_set('loop_start',(np.r_[0,np.cumsum(counts[:-1])].astype(np.int32) if len(counts) else np.empty(0,np.int32)));new.polygons.foreach_set('loop_total',counts)
        del starts,sizes,lv,flat,allco,co,counts
        for m in old.materials:new.materials.append(m)
        for prop,dtype in [('material_index',np.int32),('use_smooth',bool)]:
            v=_read(old.polygons,prop,1,dtype);new.polygons.foreach_set(prop,np.r_[v[keep],v[tp[plan.triangle_source]]])
        for name,(domain,dtype,prop,discrete,size,npdtype) in attrs.items():
            if domain=='EDGE' or name=='material_index':continue
            v=_read(old.attributes[name].data,prop,size,npdtype)
            if domain=='POINT':out=np.r_[v,interpolate(v,tri[plan.addition_triangle],plan.addition_weights,discrete)]
            elif domain=='FACE':out=np.r_[v[keep],v[tp[plan.triangle_source]]]
            else:
                src=v[tl[plan.triangle_source]];w=plan.corner_weights
                outnew=src[np.arange(len(w))[:,None],w.argmax(2)] if discrete else np.einsum('nki,ni...->nk...',w,src)
                out=np.concatenate([v[kl],outnew.reshape((-1,)+v.shape[1:])])
            a=new.attributes.get(name) or new.attributes.new(name,dtype,domain);a.data.foreach_set(prop,np.asarray(out).ravel());del v,out
        new.update(calc_edges=True)
        edge_report=inherit_edge_metadata(old,new,tri,plan,attrs)
        normals=_read(old.corner_normals,'vector',3);n=np.einsum('nki,nij->nkj',plan.corner_weights,normals[tl[plan.triangle_source]]).reshape(-1,3);n/=np.maximum(np.linalg.norm(n,axis=1,keepdims=True),1e-20)
        final_normals=np.empty((len(kl)+len(n),3),np.float32)
        for first in range(0,len(kl),32768):
            last=min(first+32768,len(kl));final_normals[first:last]=normals[kl[first:last]]
        final_normals[len(kl):]=n;del normals,n,tri,tp,tl,kl
        new.update(calc_edges=True);require(not new.validate(clean_customdata=False),'Blender repaired the candidate; reject')
        if len(final_normals):new.normals_split_custom_set(final_normals)
        del final_normals
        for key in old.keys():new[key]=old[key]
        if len(old.uv_layers):
            new.uv_layers.active_index=old.uv_layers.active_index
            for layer in old.uv_layers:
                if layer.name in new.uv_layers:new.uv_layers[layer.name].active_render=layer.active_render
        if len(old.color_attributes):
            new.color_attributes.active_color_name=old.color_attributes.active_color_name
            new.color_attributes.default_color_name=old.color_attributes.default_color_name
        return dict(mesh=new,report=dict(plan.report,estimated_added_buffer_mib=estimate,materials_reused_verbatim=True,edge_metadata=edge_report,fully_clipped_owner=len(new.polygons)==0),plan=plan)
    except Exception:
        bpy.data.meshes.remove(new);raise
