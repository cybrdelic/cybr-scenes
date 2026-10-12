"""Bounded, in-memory replacement of the actual coarse left road edge.

No scene open/save, render, environment mutation, or subprocess is performed.
The Blender entry point is ``prepare_edge_strip``. It returns an unlinked new
mesh and a copied road material; the caller decides whether to assign them.
The pure numerical functions import without Blender. Actual Blender loop
triangles, rather than an assumed old rectangular grid, define all sampling.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib
import numpy as np

ROAD = 'Crowned asphalt crust / longitudinal rise'
BASE_NORMAL = 'relief_original_broad_normal'
HEIGHT_SHA256 = '9c6ebba3a109088842a73434cea02069aa3a5a98e1b871a3f7b7b5e246de0c83'
TILE_M = .25
HEIGHT_SCALE_M = .004


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def smoothstep(a, b, x):
    t = np.clip((np.asarray(x)-a)/(b-a), 0, 1)
    return t*t*(3-2*t)


def sample_original_height(g, xy):
    """Exact originalheight=(GeometryHeight[::-1]-.5)*.004, phase XY/.25."""
    p = np.mod(np.asarray(xy, dtype=np.float64)/TILE_M, 1)*(len(g)-1)
    ij = np.floor(p).astype(np.int32); f = p-ij
    ix, iy = ij.T; fx, fy = f.T; up = g[::-1]
    h = ((up[iy,ix]*(1-fx)+up[iy,ix+1]*fx)*(1-fy)
         +(up[iy+1,ix]*(1-fx)+up[iy+1,ix+1]*fx)*fy)
    return (h-.5)*HEIGHT_SCALE_M


def load_height(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _require(digest == HEIGHT_SHA256, 'GeometryHeight is not the pinned original source')
    g = np.load(path, allow_pickle=False)
    _require(g.shape == (513,513) and np.isfinite(g).all(), 'Unsupported native height array')
    _require(np.array_equal(g[0],g[-1]) and np.array_equal(g[:,0],g[:,-1]), 'Height wrap is not exact')
    return g


def _area(p):
    # Translate before the shoelace sum: absolute world coordinates otherwise
    # cancel badly on the retained near-coincident source rows.
    p=np.asarray(p,dtype=np.float64);p=p-p[0]
    return float(np.sum(p[:,0]*np.roll(p[:,1],-1)-p[:,1]*np.roll(p[:,0],-1)))


def split_halfplane(poly, axis, edge):
    """Split XY + source barycentrics without approximating the cut location."""
    low=[]; high=[]
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        ia,ib=a[axis] <= edge,b[axis] <= edge
        (low if ia else high).append(a)
        if ia != ib:
            q=a+(edge-a[axis])/(b[axis]-a[axis])*(b-a);q[axis]=edge
            low.append(q);high.append(q)
    return (np.asarray(low,dtype=float).reshape(-1,5),np.asarray(high,dtype=float).reshape(-1,5))


def subtract_rectangle(triangle_xy, bounds):
    """Exact retained convex pieces, payload = original-triangle barycentrics.

    All four cut lines split every piece. New original-edge vertices still
    need propagation to retained neighbors (done by clip_source below).
    """
    a,b,c,d=bounds;pieces=[np.column_stack((triangle_xy,np.eye(3)))]
    for axis,edge in ((0,a),(0,b),(1,c),(1,d)):
        pieces=[p for old in pieces for p in split_halfplane(old,axis,edge)
                if len(p)>=3 and abs(_area(p[:,:2]))>1e-16]
    return [p for p in pieces if not (a < p[:,0].mean() < b and c < p[:,1].mean() < d)]


class TriangleSampler:
    """Bounded exact barycentric sampler of actual, potentially mixed topology.

    ``triangles`` are vertex IDs from Mesh.loop_triangles, already limited to
    the requested source neighborhood. No extrapolation or nearest fallback.
    """
    def __init__(self, coordinates, triangles, cell=.025, max_bucket_entries=300000):
        self.co=np.asarray(coordinates);self.triangles=np.asarray(triangles,dtype=np.int32)
        _require(0<len(self.triangles)<=50000,'Source neighborhood exceeds 50,000 triangles')
        self.tri=self.co[self.triangles].astype(np.float64)
        self.cell=float(cell);self.bins={};entries=0
        self.a=self.tri[:,0,:2];self.v1=self.tri[:,1,:2]-self.a;self.v2=self.tri[:,2,:2]-self.a
        self.det=self.v1[:,0]*self.v2[:,1]-self.v1[:,1]*self.v2[:,0]
        _require(np.all(np.abs(self.det)>1e-16),'Source has degenerate XY triangles')
        lo=np.floor(self.tri[:,:,:2].min(axis=1)/cell).astype(int)
        hi=np.floor(self.tri[:,:,:2].max(axis=1)/cell).astype(int)
        # Include boundary bins on both sides of an exactly aligned source edge.
        lo=np.floor((self.tri[:,:,:2].min(axis=1)-1e-9)/cell).astype(int)
        for i,(l,h) in enumerate(zip(lo,hi)):
            entries+=int(np.prod(h-l+1))
            _require(entries<=max_bucket_entries,'Triangle-bin cap exceeded; shrink the source neighborhood')
            for x in range(l[0],h[0]+1):
                for y in range(l[1],h[1]+1):self.bins.setdefault((x,y),[]).append(i)
        self.bins={k:np.asarray(v,dtype=np.int32) for k,v in self.bins.items()}

    def weights(self, xy):
        p=np.asarray(xy,dtype=np.float64).reshape(-1,2)
        _require(np.isfinite(p).all(),'Nonfinite source query')
        keys,inverse=np.unique(np.floor(p/self.cell).astype(np.int32),axis=0,return_inverse=True)
        order=np.argsort(inverse,kind='stable');cuts=np.r_[0,np.cumsum(np.bincount(inverse,minlength=len(keys)))]
        chosen=np.full(len(p),-1,dtype=np.int32);weights=np.empty((len(p),3))
        for k,key in enumerate(keys):
            candidates=self.bins.get(tuple(key))
            _require(candidates is not None,'Source query is outside bounded source support')
            for s in range(cuts[k],cuts[k+1],2048):
                rows=order[s:min(cuts[k+1],s+2048)]
                _require(len(rows)*len(candidates)<=2000000,'Source query batch exceeds allocation cap')
                d=p[rows,None,:]-self.a[candidates]
                u=(d[:,:,0]*self.v2[candidates,1]-d[:,:,1]*self.v2[candidates,0])/self.det[candidates]
                v=(self.v1[candidates,0]*d[:,:,1]-self.v1[candidates,1]*d[:,:,0])/self.det[candidates]
                score=np.minimum(np.minimum(u,v),1-u-v)
                col=score.argmax(axis=1);best=score[np.arange(len(rows)),col]
                _require(np.all(best>=-2e-7),'Point outside original asphalt; refusing extrapolation')
                chosen[rows]=candidates[col]
                w=np.column_stack((1-u[np.arange(len(rows)),col]-v[np.arange(len(rows)),col],u[np.arange(len(rows)),col],v[np.arange(len(rows)),col]))
                # Do not clamp: barycentrics describe the actual query location.
                weights[rows]=w
        return chosen,weights

    def sample(self, values, xy, discrete=False):
        t,w=self.weights(xy);return interpolate(values,self.triangles[t],w,discrete)

    def left_edge(self, y):
        """Actual leftmost triangle-union boundary, no copied analytic edge."""
        y=np.asarray(y,dtype=float);flat=y.ravel();out=np.empty(len(flat))
        ymin=self.tri[:,:,1].min(axis=1);ymax=self.tri[:,:,1].max(axis=1)
        for k,yy in enumerate(flat):
            t=self.tri[(ymin<=yy+1e-10)&(ymax>=yy-1e-10)]
            _require(len(t)>0,'Missing source longitudinal support')
            xs=[]
            for j in range(3):
                a,b=t[:,j],t[:,(j+1)%3];dy=b[:,1]-a[:,1]
                normal=np.abs(dy)>1e-14
                f=np.divide(yy-a[:,1],dy,out=np.zeros(len(t)),where=normal)
                ok=normal&(f>=-1e-9)&(f<=1+1e-9)
                if np.any(ok):xs.append(a[ok,0]+f[ok]*(b[ok,0]-a[ok,0]))
                same=(~normal)&(np.abs(a[:,1]-yy)<1e-9)
                if np.any(same):xs.extend((a[same,0],b[same,0]))
            _require(bool(xs),'Source edge intersection is empty')
            out[k]=min(float(np.min(v)) for v in xs)
        return out.reshape(y.shape)


def interpolate(values, ids, weights, discrete=False):
    values=np.asarray(values)
    if discrete:return values[ids[np.arange(len(ids)),np.argmax(weights,axis=1)]]
    return np.einsum('ni,ni...->n...',weights,values[ids])


def zipper(a,b,ta,tb):
    """Conforming join between ordered cut/fine boundaries; same direction."""
    a=list(a);b=list(b);i=j=0;out=[]
    while i<len(a)-1 or j<len(b)-1:
        if i<len(a)-1 and (j==len(b)-1 or ta[i+1]<=tb[j+1]):out.append((a[i],a[i+1],b[j]));i+=1
        else:out.append((a[i],b[j+1],b[j]));j+=1
    return np.asarray(out,dtype=np.int32)


@dataclass
class ClipPlan:
    keep_polygons: np.ndarray
    additions: np.ndarray
    addition_triangle: np.ndarray
    addition_weights: np.ndarray
    triangles: np.ndarray
    triangle_source: np.ndarray
    corner_weights: np.ndarray
    boundary: tuple
    bounds: tuple


def clip_source(co, triangles, triangle_polygons, polygon_count, bounds):
    """Subtract a rectangle and propagate all source-edge cuts exactly.

    All arrays use actual source tessellation. Returns untouched polygon IDs
    verbatim plus changed triangles and their per-corner source provenance.
    ``triangles`` must include the full original mesh tessellation here.
    """
    co=np.asarray(co);triangles=np.asarray(triangles,dtype=np.int32);tp=np.asarray(triangle_polygons)
    _require(len(triangles)<=1500000,'Global source tessellation cap exceeded')
    a,b,c,d=bounds
    p=co[triangles,:2];lo=p.min(axis=1);hi=p.max(axis=1)
    intersects=(hi[:,0]>a+1e-11)&(lo[:,0]<b-1e-11)&(hi[:,1]>c+1e-11)&(lo[:,1]<d-1e-11)
    touched=np.unique(tp[intersects]);_require(0<len(touched)<=20000,'No cut or too many source polygons')
    mask=np.isin(tp,touched);active=np.flatnonzero(mask)
    _require(len(active)<=40000,'Bounded clip exceeds 40,000 triangles')
    newco=[];newt=[];neww=[];lookup={};splits={};pieces={}
    def vertex(t,w,xy):
        exact=np.flatnonzero(np.abs(w-1)<1e-10)
        if len(exact)==1:return int(triangles[t,exact[0]])
        key=tuple(np.round(xy,11))
        if key not in lookup:
            coord=w@co[triangles[t]];coord[:2]=xy
            lookup[key]=len(co)+len(newco);newco.append(coord);newt.append(t);neww.append(w.copy())
        vi=lookup[key]
        nz=np.flatnonzero(np.abs(w)>1e-9)
        if len(nz)==2:
            edge=tuple(sorted(int(v) for v in triangles[t,nz]));splits.setdefault(edge,set()).add(vi)
        return vi
    for t in active:
        polys=subtract_rectangle(p[t],bounds);out=[]
        for poly in polys:
            ring=[vertex(t,q[2:],q[:2]) for q in poly]
            out.append((ring,poly[:,2:]))
        pieces[t]=out
    # Only one-ring neighbors can inherit source-edge splits. Full topology is
    # scanned as arrays; no full-scene Python edge dictionary is constructed.
    neighbors=np.zeros(len(triangles),dtype=bool)
    if splits:
        edgekeys=np.asarray(list(splits),dtype=np.int64)
        radix=int(len(co))+1;wanted=np.sort(edgekeys[:,0]*radix+edgekeys[:,1])
        for j in range(3):
            ee=np.sort(triangles[:,[j,(j+1)%3]],axis=1).astype(np.int64);key=ee[:,0]*radix+ee[:,1]
            pos=np.searchsorted(wanted,key);valid=pos<len(wanted);found=np.zeros(len(key),bool);found[valid]=wanted[pos[valid]]==key[valid];neighbors|=found
    all_touched=np.unique(np.r_[touched,tp[neighbors]])
    for t in np.flatnonzero(np.isin(tp,all_touched)&~mask):pieces[t]=[(list(map(int,triangles[t])),np.eye(3))]
    def coord(i):return co[i] if i<len(co) else newco[i-len(co)]
    outtri=[];outsrc=[];outweights=[]
    for t,polys in pieces.items():
        ids=triangles[t];xyz=co[ids]
        for ring,weights in polys:
            expanded=[];ew=[]
            for j,(va,vb) in enumerate(zip(ring,ring[1:]+ring[:1])):
                wa,wb=weights[j],weights[(j+1)%len(ring)];expanded.append(va);ew.append(wa)
                zero=np.flatnonzero((np.abs(wa)<1e-9)&(np.abs(wb)<1e-9))
                if len(zero)==1:
                    edge=tuple(sorted(int(v) for v in ids[[k for k in range(3) if k!=zero[0]]]))
                    pa,pb=coord(va)[:2],coord(vb)[:2];delta=pb-pa;den=float(delta@delta)
                    if den>1e-22:
                        extra=[]
                        for vi in splits.get(edge,()):
                            s=float((coord(vi)[:2]-pa)@delta/den)
                            if 1e-9<s<1-1e-9:extra.append((s,vi))
                        for s,vi in sorted(extra):expanded.append(vi);ew.append((1-s)*wa+s*wb)
            # A center fan respects collinear boundary subdivisions exactly.
            if len(expanded)==3:
                faces=[tuple(expanded)];ws=[np.asarray(ew)]
            else:
                w=np.asarray(ew).mean(axis=0);xy=w@xyz[:,:2];ci=vertex(t,w,xy)
                faces=[(ci,expanded[j],expanded[(j+1)%len(expanded)]) for j in range(len(expanded))]
                ws=[np.asarray((w,ew[j],ew[(j+1)%len(expanded)])) for j in range(len(expanded))]
            for f,w in zip(faces,ws):
                area=_area(np.asarray([coord(i)[:2] for i in f]))
                if abs(area)<1e-13:continue
                if area<0:f=f[::-1];w=w[::-1]
                outtri.append(f);outsrc.append(t);outweights.append(w)
    ct=np.asarray(outtri,dtype=np.int32).reshape(-1,3)
    _require(len(ct)>0,'Clipping left no finite retained boundary')
    allco=np.concatenate((co,np.asarray(newco).reshape(-1,3)))
    # Retained cut boundary is contained wholly in changed triangles.
    keep=np.setdiff1d(np.arange(polygon_count,dtype=np.int32),all_touched)
    retained_original=triangles[np.isin(tp,keep)]
    edge_faces=np.concatenate((ct,retained_original))
    # The retained scene has nearly coincident Y rows at arange joins. Their
    # zero-footprint triangles render no surface but would falsely add a third
    # edge use. Exclude them from this surface-boundary certificate only;
    # untouched original topology is still retained in the output mesh.
    ep0=allco[edge_faces,:2]
    twice_area=(ep0[:,1,0]-ep0[:,0,0])*(ep0[:,2,1]-ep0[:,0,1])-(ep0[:,1,1]-ep0[:,0,1])*(ep0[:,2,0]-ep0[:,0,0])
    edge_faces=edge_faces[np.abs(twice_area)>1e-13]
    edges=np.concatenate([edge_faces[:,[i,(i+1)%3]] for i in range(3)])
    ep=allco[edges,:2];near=np.zeros(len(edges),bool)
    for axis,value in ((0,b),(1,c),(1,d)):near|=np.all(np.abs(ep[:,:,axis]-value)<2e-9,axis=1)
    near&=np.all((ep[:,:,0]>=a-2e-9)&(ep[:,:,0]<=b+2e-9)&(ep[:,:,1]>=c-2e-9)&(ep[:,:,1]<=d+2e-9),axis=1)
    unique,uses=np.unique(np.sort(edges[near],axis=1),axis=0,return_counts=True)
    cut=unique[uses==1];cutids=np.unique(cut);boundaries=[]
    for axis,value,sortaxis in ((1,c,0),(0,b,1),(1,d,0)):
        ids=cutids[np.abs(allco[cutids,axis]-value)<2e-9];ids=ids[np.argsort(allco[ids,sortaxis])]
        _require(len(ids)>=2,'Clip failed to produce an exact three-sided join')
        actual=set(map(tuple,np.sort(cut,axis=1)));expected=[tuple(sorted((int(u),int(v)))) for u,v in zip(ids[:-1],ids[1:])]
        _require(all(e in actual for e in expected),'Cut boundary contains an unpropagated T-junction')
        boundaries.append(ids)
    keep=np.setdiff1d(np.arange(polygon_count,dtype=np.int32),all_touched)
    return ClipPlan(keep,np.asarray(newco).reshape(-1,3),np.asarray(newt,dtype=np.int32),np.asarray(neww).reshape(-1,3),ct,np.asarray(outsrc,dtype=np.int32),np.asarray(outweights).reshape(-1,3,3),tuple(boundaries),tuple(bounds))


@dataclass
class StripPlan:
    coordinates: np.ndarray
    triangles: np.ndarray
    source_triangles: np.ndarray
    source_weights: np.ndarray
    is_fine: np.ndarray
    old_edge_y: np.ndarray
    old_edge_x: np.ndarray
    new_edge_x: np.ndarray
    report: dict


def build_strip(source, source_global_ids, clip, co, height, x_edge,
                spacing_m=.001, collar_m=.002, fade_m=.008, max_vertices=500000):
    """Fine top surface plus exact three-sided sparse-to-dense joins.

    The outer side is deliberately open for the caller's crust wall / soil
    support. Its chip recession comes from x_edge, never procedural macro noise.
    Source XY is metrically sampled, independently of the changing mesh lattice.
    """
    a,b,c,d=clip.bounds
    _require(.00048<=spacing_m<=.00101,'Only native-to-1mm metric spacing is supported')
    _require(.001<=collar_m<=.004 and collar_m<fade_m<=.02,'Use narrow 1–4mm collar and <=20mm fade')
    yy=np.linspace(c+collar_m,d-collar_m,int(np.ceil((d-c-2*collar_m)/spacing_m))+1)
    old=source.left_edge(yy);desired=np.asarray(x_edge(yy),dtype=float)
    _require(desired.shape==yy.shape and np.isfinite(desired).all(),'x_edge(y) must return finite same-shape X values')
    _require(np.all(desired>=old-2e-7),'x_edge expands beyond the old physical asphalt footprint')
    _require(np.max(desired-old)<=.025,'Micro-ravel exceeds bounded 25mm recession cap')
    envelope=smoothstep(0,fade_m,yy-c)*smoothstep(0,fade_m,d-yy)
    edge=old+np.maximum(desired-old,0)*envelope
    right=b-collar_m
    _require(np.all(right-edge>=.02),'New edge approaches the inner join within 20mm')
    cols=int(np.ceil(np.max(right-edge)/spacing_m))+1
    _require(len(yy)*cols<=max_vertices,'Fine strip exceeds vertex cap; reduce extent, never enlarge grain scale')
    fraction=np.linspace(0,1,cols)
    xx=edge[:,None]*(1-fraction)+right*fraction
    xy=np.column_stack((xx.ravel(),np.repeat(yy,cols)))
    local,w=source.weights(xy);global_t=np.asarray(source_global_ids)[local]
    broad=interpolate(source.co,source.triangles[local],w)
    displacement=sample_original_height(height,xy)
    weight=(smoothstep(collar_m,fade_m,b-xy[:,0])*
            smoothstep(collar_m,fade_m,xy[:,1]-c)*smoothstep(collar_m,fade_m,d-xy[:,1]))
    fine=broad.copy();fine[:,:2]=xy;fine[:,2]+=displacement*weight
    offset=len(co)+len(clip.additions);grid=np.arange(offset,offset+len(fine),dtype=np.int32).reshape(len(yy),cols)
    q=grid[:-1,:-1].ravel();tris=np.concatenate((np.column_stack((q,q+1,q+cols+1)),np.column_stack((q,q+cols+1,q+cols))))
    allco=np.concatenate((co,clip.additions,fine))
    joins=[]
    for outer,inner,axis in ((clip.boundary[0],grid[0],0),(clip.boundary[1],grid[:,-1],1),(clip.boundary[2],grid[-1],0)):
        ta=allco[outer,axis];tb=allco[inner,axis]
        ta=(ta-ta[0])/(ta[-1]-ta[0]);tb=(tb-tb[0])/(tb[-1]-tb[0])
        join=zipper(outer,inner,ta,tb);joins.append(join)
    join=np.concatenate(joins);points=allco[join,:2]
    area=(points[:,1,0]-points[:,0,0])*(points[:,2,1]-points[:,0,1])-(points[:,1,1]-points[:,0,1])*(points[:,2,0]-points[:,0,0])
    _require(np.all(np.abs(area)>1e-15),'Degenerate exact join triangle')
    join[area<0]=join[area<0,::-1]
    # Closed cut/fine seams must have edge usage exactly two. Only the new
    # outer physical edge may be open in this top-surface replacement.
    output=np.concatenate((tris,join));ef=np.concatenate((clip.triangles,join))
    fine_seams=np.concatenate([np.column_stack((ids[:-1],ids[1:])) for ids in (grid[0],grid[:,-1],grid[-1])])
    edges=np.concatenate([ef[:,[i,(i+1)%3]] for i in range(3)]+[fine_seams])
    keys,counts=np.unique(np.sort(edges,axis=1),axis=0,return_counts=True)
    countmap={tuple(e):int(n) for e,n in zip(keys,counts) if e[0]>=offset or e[1]>=offset}
    for ids in (grid[0],grid[:,-1],grid[-1]):
        _require(all(countmap.get(tuple(sorted((int(u),int(v)))))==2 for u,v in zip(ids[:-1],ids[1:])), 'Fine/core join is nonconforming')
    test=np.r_[grid[0],grid[:,-1],grid[-1]]-offset
    _require(np.max(np.abs(fine[test,2]-broad[test,2]))<1e-12,'Relief must be exactly zero on fine join boundaries')
    query_y=np.r_[c,yy,d];oldx=source.left_edge(query_y);newx=np.r_[oldx[0],edge,oldx[-1]]
    report=dict(fine_vertices=len(fine),fine_triangles=len(tris),join_triangles=len(join),
        fine_shape=[len(yy),cols],max_grid_spacing_m=spacing_m,collar_m=collar_m,fade_m=fade_m,
        tile_m=TILE_M,height_scale_m=HEIGHT_SCALE_M,height_phase_origin=[0,0],
        max_actual_displacement_m=float(np.max(np.abs(displacement*weight))),
        max_inward_ravel_m=float(np.max(newx-oldx)),source_sampling='Actual old loop triangles; no grid assumption or extrapolation',
        inner_join_x=b,end_join_y=[c,d],old_edge_from='Actual original triangle-union boundary',
        old_asphalt_beneath_strip=False,source_height_sha256=HEIGHT_SHA256)
    return StripPlan(fine,output,global_t,w,np.r_[np.ones(len(tris),bool),np.zeros(len(join),bool)],query_y,oldx,newx,report)


# Supported Blender attribute types. Unknown schemas are rejected before any
# material/mesh data-block is created, rather than silently dropping data.
ATTRIBUTE_TYPES={
 'FLOAT':('value',1,np.float32,False), 'FLOAT_VECTOR':('vector',3,np.float32,False),
 'FLOAT2':('vector',2,np.float32,False), 'FLOAT_COLOR':('color',4,np.float32,False),
 'BYTE_COLOR':('color',4,np.float32,False), 'INT':('value',1,np.int32,True),
 'BOOLEAN':('value',1,bool,True), 'INT8':('value',1,np.int8,True),
}
TOPOLOGY_ATTRIBUTES={'position','.corner_vert','.corner_edge','.edge_verts','.custom_normal'}


def _read(collection, property_name, size=1, dtype=np.float32):
    result=np.empty((len(collection),size),dtype=dtype);collection.foreach_get(property_name,result.ravel())
    return result if size>1 else result[:,0]


def _attributes(mesh):
    result={}
    for a in mesh.attributes:
        if a.name in TOPOLOGY_ATTRIBUTES:continue
        _require(a.data_type in ATTRIBUTE_TYPES and a.domain in {'POINT','CORNER','FACE','EDGE'},f'Unsupported attribute {a.name}: {a.domain}/{a.data_type}')
        prop,size,dtype,discrete=ATTRIBUTE_TYPES[a.data_type]
        if a.domain=='EDGE':
            _require(a.data_type=='BOOLEAN' and a.name in {'.select_edge','.hide_edge','sharp_edge','uv_seam'},f'Unsupported EDGE field {a.name}; refusing loss')
        result[a.name]=(a.domain,a.data_type,prop,discrete,_read(a.data,prop,size,dtype))
    return result


def _clone_material(original):
    _require(original and original.use_nodes,'Road material must be node-based')
    expected={'BaseColor.png':'34b00d3b699e64aad064c95aac78c9bdbddd18384175e6549bd182c2275314af',
              'Roughness.png':'c97210fce888fe17d062c0e58f3691b10f28b93b41c7738413b14970d55cc90e',
              'Normal_Object_RGB16.png':'98eddd45b4a84a3a5c4873ad22f25dddd5caeac628e910aa412f9f4e292cb3dc'}
    for filename,digest in expected.items():
        node=original.node_tree.nodes.get('Approved original asphalt / '+filename)
        _require(node is not None and node.image is not None and node.image.packed_file is not None,'Missing pinned material bitmap '+filename)
        _require(hashlib.sha256(node.image.packed_file.data).hexdigest()==digest,'Intrinsic bitmap changed: '+filename)
        _require(node.extension=='REPEAT' and node.interpolation=='Linear','Intrinsic sampling changed')
        links=node.inputs['Vector'].links
        _require(len(links)==1,'Intrinsic vector input is ambiguous')
        scale=links[0].from_node
        _require(scale.bl_idname=='ShaderNodeVectorMath' and scale.operation=='SCALE' and not scale.inputs['Scale'].is_linked and abs(scale.inputs['Scale'].default_value-4)<1e-9,'Intrinsic metric scale is not 0.25m')
    copy=original.copy();copy.name=original.name+' / bounded original-grain edge AA'
    n,l=copy.node_tree.nodes,copy.node_tree.links
    existing=[a for a in n if a.bl_idname=='ShaderNodeAttribute' and a.attribute_name==BASE_NORMAL]
    attr=existing[0] if existing else n.new('ShaderNodeAttribute');attr.attribute_name=BASE_NORMAL
    attr.name='Captured broad road datum; full native normal already contains grain slopes'
    rewired=0
    for node in list(n):
        if node.bl_idname=='ShaderNodeNewGeometry':
            for link in list(node.outputs['Normal'].links):l.new(attr.outputs['Vector'],link.to_socket);rewired+=1
    _require(rewired>0 or any(a.outputs['Vector'].is_linked for a in existing),'Unknown original normal contract')
    copy['metric_edge_normal_contract']='Original full-metric normal map plus captured original broad datum once; intrinsic maps unchanged'
    return copy


def prepare_edge_strip(road, height_path, x_edge=None, *, boundary_builder=None,
                       inner_x=-3.07, y_bounds=(0.,2.), spacing_m=.001,
                       collar_m=.002, fade_m=.008, max_vertices=500000):
    """Prepare an unlinked Blender mesh; never assign, open, save or render.

    Prefer ``boundary_builder(old_left, y_bounds)`` returning either a callable
    or an object exposing ``x_edge(y)``. old_left samples the actual road edge.
    Example: lambda old, bounds: field.project(old, bounds, side=-1).

    Returned dict: mesh, material, report, boundary_profile, old_edge_y,
    old_edge_x, new_edge_x, old_edge_xyz, new_edge_xyz, source_sampler,
    source_point_attributes and source_attribute_schema. Sample source Z with
    source_sampler.sample(source_sampler.co[:,2], xy); other POINT fields use
    source_sampler.sample(source_point_attributes[name], xy). Assign ``road.data = result['mesh']`` only when the
    caller has finished soil/wall integration. All other objects are untouched.
    """
    import bpy
    _require(road and road.type=='MESH' and road.name==ROAD,'Need the actual named coarse road object')
    _require(not road.modifiers and road.data.shape_keys is None and len(road.vertex_groups)==0,'Modifiers, shape keys and vertex groups are unsupported')
    _require(np.allclose(np.asarray(road.matrix_world),np.eye(4),atol=1e-9,rtol=0),'Road must retain identity transform')
    _require((x_edge is None)!=(boundary_builder is None),'Provide x_edge or boundary_builder, not both')
    _require(-3.12<=inner_x<=-3.060001 and tuple(y_bounds)==(0.,2.),'Only the bounded y=0..2 edge outside the -3.04 native collar is supported')
    old=road.data
    _require(old.animation_data is None,'Animated mesh data is unsupported')
    _require(len(old.vertices)<=1000000 and len(old.loops)<=5000000,'Source mesh cap exceeded')
    attrs=_attributes(old);co=_read(old.vertices,'co',3)
    old.calc_loop_triangles();tri=_read(old.loop_triangles,'vertices',3,np.int32);tloops=_read(old.loop_triangles,'loops',3,np.int32);tp=_read(old.loop_triangles,'polygon_index',1,np.int32)
    starts=_read(old.polygons,'loop_start',1,np.int32);sizes=_read(old.polygons,'loop_total',1,np.int32);lv=_read(old.loops,'vertex_index',1,np.int32)
    _require(np.all((sizes==3)|(sizes==4)),'Only the current mixed triangles/quads are supported')
    smooth=_read(old.polygons,'use_smooth',1,bool);mats=_read(old.polygons,'material_index',1,np.int32)
    _require(len(old.materials)>0,'Missing road material slots')
    loopnormal=_read(old.corner_normals,'vector',3)
    broad=attrs[BASE_NORMAL][4] if BASE_NORMAL in attrs else _read(old.vertices,'normal',3)
    _require(np.isfinite(loopnormal).all() and np.isfinite(broad).all(),'Source normals contain nonfinite values')
    height=load_height(height_path)
    c,d=map(float,y_bounds);b=float(np.float32(inner_x))
    # Snap a cut already within 0.1 micrometre of an existing row to that exact
    # stored coordinate. This prevents sliver rows from source float32 storage.
    for value,name in ((c,'c'),(d,'d')):
        nearest=float(co[np.argmin(np.abs(co[:,1]-value)),1])
        if abs(nearest-value)<1e-7:
            if name=='c':c=nearest
            else:d=nearest
    p=co[tri,:2];lo=p.min(axis=1);hi=p.max(axis=1)
    near=(lo[:,0]<b+.015)&(hi[:,0]>-3.5)&(lo[:,1]<d+.06)&(hi[:,1]>c-.06)
    area=(p[:,1,0]-p[:,0,0])*(p[:,2,1]-p[:,0,1])-(p[:,1,1]-p[:,0,1])*(p[:,2,0]-p[:,0,0])
    near &= np.abs(area)>1e-13
    global_ids=np.flatnonzero(near);source=TriangleSampler(co,tri[near])
    probe=source.left_edge(np.linspace(c,d,257));a=float(np.min(probe)-.01)
    _require(-3.5<a<b and np.max(b-probe)<.35,'Unexpected road edge extent')
    profile=boundary_builder(source.left_edge,(c,d)) if boundary_builder is not None else None
    callback=(profile.x_edge if hasattr(profile,'x_edge') else profile) if boundary_builder is not None else x_edge
    _require(callable(callback),'Boundary builder must return x_edge callable or profile')
    clip=clip_source(co,tri,tp,len(old.polygons),(a,b,c,d))
    strip=build_strip(source,global_ids,clip,co,height,callback,spacing_m,collar_m,fade_m,max_vertices)
    extra=np.concatenate((clip.additions,strip.coordinates))
    et=np.r_[clip.addition_triangle,strip.source_triangles];ew=np.concatenate((clip.addition_weights,strip.source_weights));eids=tri[et]
    allco=np.concatenate((co,extra));ct=clip.triangles;st=strip.triangles
    centers=allco[st,:2].mean(axis=1);local,cw=source.weights(centers);stripsource=global_ids[local]
    stripmat=np.unique(mats[tp[stripsource]])
    _require(len(stripmat)==1,'Replacement crosses material-slot boundary; unsupported')
    material_index=int(stripmat[0]);_require(material_index<len(old.materials),'Invalid original material slot')
    # Everything risky/unsupported above is checked before data-block creation.
    material=_clone_material(old.materials[material_index]);new=None
    try:
        keep=clip.keep_polygons;counts=np.r_[sizes[keep],np.full(len(ct)+len(st),3,dtype=np.int32)]
        keepmask=np.zeros(len(sizes),bool);keepmask[keep]=True
        keptloops=np.flatnonzero(np.repeat(keepmask,sizes)).astype(np.int32)
        flat=np.r_[lv[keptloops],ct.ravel(),st.ravel()]
        new=bpy.data.meshes.new(old.name+' / exact bounded original-grain edge AA')
        new.vertices.add(len(allco));new.vertices.foreach_set('co',allco.ravel());new.loops.add(len(flat));new.loops.foreach_set('vertex_index',flat)
        new.polygons.add(len(counts));new.polygons.foreach_set('loop_start',np.r_[0,np.cumsum(counts[:-1])].astype(np.int32));new.polygons.foreach_set('loop_total',counts)
        new.polygons.foreach_set('use_smooth',np.r_[smooth[keep],smooth[tp[clip.triangle_source]],np.ones(len(st),bool)])
        for slot in old.materials:new.materials.append(slot)
        new.materials.append(material);new.polygons.foreach_set('material_index',np.r_[mats[keep],mats[tp[clip.triangle_source]],np.full(len(st),len(old.materials),np.int32)])
        # Each original corner normal is preserved; interpolated clipped normals
        # and dense normals represent the pre-displacement broad road surface.
        clipnorm=np.einsum('nki,nij->nkj',clip.corner_weights,loopnormal[tloops[clip.triangle_source]])
        en=interpolate(broad,eids,ew);allnormal=np.concatenate((broad,en));stripnorm=allnormal[st].reshape(-1,3)
        normals=np.concatenate((loopnormal[keptloops],clipnorm.reshape(-1,3),stripnorm))
        for name,(domain,dtype,prop,discrete,values) in attrs.items():
            if domain=='EDGE' or name=='material_index':continue
            if domain=='POINT':output=np.concatenate((values,interpolate(values,eids,ew,discrete)))
            elif domain=='FACE':output=np.concatenate((values[keep],values[tp[clip.triangle_source]],values[tp[stripsource]]))
            else:
                sourcevalues=values[tloops[clip.triangle_source]]
                if discrete:
                    weights=clip.corner_weights;cc=sourcevalues[np.arange(len(weights))[:,None],np.argmax(weights,axis=2)]
                else:cc=np.einsum('nki,ni...->nk...',clip.corner_weights,sourcevalues)
                # New strip CORNER attributes are sampled at each fine/old
                # vertex from the actual source triangle, not face centroids.
                # Original boundary vertices may be used with multiple source
                # corner values; resolve them on actual strip triangle corners.
                sx=allco[st,:2].reshape(-1,2);sl,sw=source.weights(sx);sv=interpolate(values,tloops[global_ids[sl]],sw,discrete)
                output=np.concatenate((values[keptloops],cc.reshape((-1,)+values.shape[1:]),sv))
            attribute=new.attributes.get(name) or new.attributes.new(name,dtype,domain);attribute.data.foreach_set(prop,np.asarray(output).ravel())
        if BASE_NORMAL not in attrs:
            attribute=new.attributes.new(BASE_NORMAL,'FLOAT_VECTOR','POINT');attribute.data.foreach_set('vector',allnormal.ravel())
        new.update(calc_edges=True)
        _require(not new.validate(verbose=True,clean_customdata=False),'Blender repaired the new mesh; rejecting candidate')
        normals[len(keptloops):]/=np.maximum(np.linalg.norm(normals[len(keptloops):],axis=1,keepdims=True),1e-20)
        _require(np.all(np.linalg.norm(normals,axis=1)>.9),'Invalid source loop normals')
        new.normals_split_custom_set(normals)
        # Boolean edge metadata is exact on every retained original edge;
        # generated interior/fine edges have the original false default.
        if any(spec[0]=='EDGE' for spec in attrs.values()):
            oldedges=_read(old.edges,'vertices',2,np.int32);newedges=_read(new.edges,'vertices',2,np.int32)
            radix=int(len(allco))+1;oe=np.sort(oldedges,axis=1).astype(np.int64);ne=np.sort(newedges,axis=1).astype(np.int64)
            keys=oe[:,0]*radix+oe[:,1];order=np.argsort(keys);keys=keys[order];nk=ne[:,0]*radix+ne[:,1];pos=np.searchsorted(keys,nk);valid=pos<len(keys);found=np.zeros(len(nk),bool);found[valid]=keys[pos[valid]]==nk[valid]
            # New pieces of an old edge inherit its boolean fields too. A source
            # triangle diagonal is not an old mesh edge and is left at the default.
            vertex_edge=np.full((len(allco),2),-1,dtype=np.int32)
            for k,(t,w) in enumerate(zip(clip.addition_triangle,clip.addition_weights)):
                zero=np.flatnonzero(np.abs(w)<1e-9)
                if len(zero)==1:vertex_edge[len(co)+k]=np.sort(tri[t,[j for j in range(3) if j!=zero[0]]])
            inherited=np.full(len(newedges),-1,dtype=np.int32)
            for k in np.flatnonzero(~found):
                u,v=map(int,newedges[k]);eu,ev=vertex_edge[u],vertex_edge[v];edge=None
                if eu[0]>=0 and ev[0]>=0 and np.array_equal(eu,ev):edge=eu
                elif eu[0]>=0 and v in eu:edge=eu
                elif ev[0]>=0 and u in ev:edge=ev
                if edge is not None:
                    key=int(edge[0])*radix+int(edge[1]);j=int(np.searchsorted(keys,key))
                    if j<len(keys) and keys[j]==key:inherited[k]=order[j]
            for name,(domain,dtype,prop,discrete,values) in attrs.items():
                if domain!='EDGE':continue
                output=np.zeros(len(newedges),dtype=values.dtype);output[found]=values[order[pos[found]]]
                valid_inherited=inherited>=0;output[valid_inherited]=values[inherited[valid_inherited]]
                attribute=new.attributes.get(name) or new.attributes.new(name,dtype,domain);attribute.data.foreach_set(prop,output)
        for key in old.keys():new[key]=old[key]
        if len(old.uv_layers):
            new.uv_layers.active_index=old.uv_layers.active_index
            for layer in old.uv_layers:
                if layer.name in new.uv_layers:new.uv_layers[layer.name].active_render=layer.active_render
        if len(old.color_attributes):
            new.color_attributes.active_color_name=old.color_attributes.active_color_name
            new.color_attributes.default_color_name=old.color_attributes.default_color_name
        # No original coordinates or untouched polygon corner sequence changed.
        _require(np.array_equal(_read(new.vertices,'co',3)[:len(co)],co),'An original vertex moved')
        _require(np.array_equal(_read(new.loops,'vertex_index',1,np.int32)[:len(keptloops)],lv[keptloops]),'Untouched polygon topology changed')
        report=dict(strip.report,source_vertices=len(co),source_polygons=len(old.polygons),kept_original_polygons=len(keep),clipped_retained_triangles=len(ct),new_mesh_vertices=len(allco),new_mesh_polygons=len(counts),copied_material=material.name,attributes_preserved=list(attrs),source_normals_preserved=True,scene_assigned=False,rendered=False,saved=False,unreferenced_source_vertices_retained=True)
        oldxy=np.column_stack((strip.old_edge_x,strip.old_edge_y))
        oldxyz=np.column_stack((oldxy,source.sample(co[:,2],oldxy)))
        rows,columns=strip.report['fine_shape'];newxyz=np.concatenate((oldxyz[:1],strip.coordinates.reshape(rows,columns,3)[:,0],oldxyz[-1:])).astype(np.float32)
        return dict(mesh=new,material=material,report=report,boundary_profile=profile,old_edge_y=strip.old_edge_y,old_edge_x=strip.old_edge_x,new_edge_x=strip.new_edge_x,old_edge_xyz=oldxyz,new_edge_xyz=newxyz,source_sampler=source,source_point_attributes={name:spec[4] for name,spec in attrs.items() if spec[0]=='POINT'},source_attribute_schema={name:spec[:4] for name,spec in attrs.items() if spec[0]=='POINT'})
    except Exception:
        if new is not None:bpy.data.meshes.remove(new)
        bpy.data.materials.remove(material)
        raise
