"""Bounded conforming refinement of the existing AB shoulder, never a new sheet.

Pure NumPy planning imports without Blender. ``prepare_context_refinement``
returns an unassigned mesh; it never opens/saves a scene, renders, or moves a
vertex. Read actual Mesh.loop_triangles, not an assumed rectangular lattice.

Integration::

    prepared = prepare_context_refinement(ground)
    z = sample_triangle_grid(prepared['source_sampler'].height, x, y)
    result = solve_context(x, y, z)
    co = prepared['coordinates']  # original surface, BEFORE any displacement
    dz = sample_displacement(result, co[:, :2])
    audit = audit_context_projection(prepared['plan'], co, dz, result)
    # Inspect audit, especially leakage / projection error. No mass fix-up.
    co[:, 2] += dz
    prepared['mesh'].vertices.foreach_set('co', co.astype('float32').ravel())
    # Caller owns mesh assignment and normal/shader policy after displacement.

Float fields interpolate barycentrically. Discrete fields use the highest-
weight source vertex/corner, ties resolved by the lowest original ID. Original
vertices and untouched polygon corner sequences are retained. Split edge data
inherits its original edge; newly created triangle interiors have zero edge
metadata. Unrecognized attribute schemas fail rather than silently drop data.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

TERRAIN = 'Graded shoulder and alluvial plain -1'
DEFAULT_BOUNDS = (-10., -3.2, 0., 40.)
DEFAULT_PROTECTED = (-6.25, -3.15, -.7, 8.35)
TOPOLOGY_ATTRIBUTES = {'position', '.corner_vert', '.corner_edge', '.edge_verts', '.custom_normal'}
ATTRIBUTE_TYPES = {
    'FLOAT': ('value', 1, np.float32, False),
    'FLOAT_VECTOR': ('vector', 3, np.float32, False),
    'FLOAT2': ('vector', 2, np.float32, False),
    'FLOAT_COLOR': ('color', 4, np.float32, False),
    'BYTE_COLOR': ('color', 4, np.float32, False),
    'INT': ('value', 1, np.int32, True),
    'INT8': ('value', 1, np.int8, True),
    'BOOLEAN': ('value', 1, bool, True),
}


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _bounds(b):
    b = np.asarray(b, dtype=float)
    _require(b.shape == (4,) and np.isfinite(b).all() and b[0] < b[1] and b[2] < b[3],
             'Bounds must be finite (xmin, xmax, ymin, ymax)')
    return tuple(map(float, b))


def _keys(edges, radix):
    a = np.asarray(edges, dtype=np.int64)
    return np.minimum(a[..., 0], a[..., 1]) * radix + np.maximum(a[..., 0], a[..., 1])


def _match(sorted_keys, queries):
    pos = np.searchsorted(sorted_keys, queries)
    valid = pos < len(sorted_keys)
    found = np.zeros(queries.shape, bool)
    found[valid] = sorted_keys[pos[valid]] == queries[valid]
    return pos, found


def _box_intersects(lo, hi, bounds):
    a, b, c, d = bounds
    return (hi[:, 0] >= a) & (lo[:, 0] <= b) & (hi[:, 1] >= c) & (lo[:, 1] <= d)


def intersecting_triangles(co, triangles, bounds, batch_size=32768):
    """Conservative bounded AABB scan. Does not build a full-mesh point tensor."""
    bounds = _bounds(bounds)
    out = []
    for start in range(0, len(triangles), batch_size):
        q = co[triangles[start:start+batch_size], :2]
        out.append(start + np.flatnonzero(_box_intersects(q.min(1), q.max(1), bounds)))
    return np.concatenate(out).astype(np.int32) if out else np.empty(0, np.int32)


def interpolate(values, ids, weights, discrete=False):
    values = np.asarray(values); ids = np.asarray(ids); weights = np.asarray(weights)
    if discrete:
        best = weights == weights.max(axis=-1, keepdims=True)
        choice = np.where(best, ids, np.iinfo(np.int64).max).argmin(axis=-1)
        return values[np.take_along_axis(ids, choice[..., None], axis=-1)[..., 0]]
    return _weighted(values[ids], weights)


def _weighted(values, weights):
    tail = values.ndim - weights.ndim
    return np.sum(values * weights.reshape(weights.shape + (1,)*tail), axis=weights.ndim-1)


@dataclass(frozen=True)
class RefineLimits:
    max_source_vertices: int = 1_600_000
    max_source_triangles: int = 3_000_000
    max_local_source_triangles: int = 160_000
    max_added_vertices: int = 240_000
    max_output_triangles: int = 600_000
    max_rounds: int = 12
    scan_batch_size: int = 32768


@dataclass
class RefinePlan:
    original_vertex_count: int
    keep_polygons: np.ndarray
    replaced_polygons: np.ndarray
    local_source_triangle_ids: np.ndarray
    source_triangles: np.ndarray
    source_triangle_polygons: np.ndarray
    additions: np.ndarray
    addition_triangle: np.ndarray
    addition_weights: np.ndarray
    addition_source_edges: np.ndarray
    triangles: np.ndarray
    triangle_source: np.ndarray
    corner_weights: np.ndarray
    refine_source_mask: np.ndarray
    bounds: tuple
    protected_bounds: tuple | None
    contact_x: float | None
    report: dict

    def coordinates(self, original):
        _require(len(original) == self.original_vertex_count, 'Wrong original vertex array')
        return np.concatenate((original, self.additions))

    def point_values(self, original, discrete=False):
        ids = self.source_triangles[self.addition_triangle]
        return np.concatenate((original, interpolate(original, ids, self.addition_weights, discrete)))

    def corner_values(self, original, source_triangle_loops, discrete=False):
        """Only replacement corners. Caller prepends unchanged original loops."""
        ids = np.asarray(source_triangle_loops)[self.triangle_source]
        expanded = np.broadcast_to(ids[:, None, :], self.corner_weights.shape)
        return interpolate(original, expanded, self.corner_weights, discrete)


def plan_refinement(co, triangles, triangle_polygons, polygon_count, *,
                    bounds=DEFAULT_BOUNDS, protected_bounds=DEFAULT_PROTECTED,
                    contact_x=-3.45, max_edge_m=.07, protection_edge_m=.05,
                    limits=None):
    """Selective red/green midpoint refinement with shared-edge propagation.

    Triangle IDs in all provenance arrays are GLOBAL original loop-triangle IDs.
    Input arrays are never changed. All original vertices remain a stable prefix.
    Entire affected parents are replaced by their actual tessellation. Only
    selected parent triangles request splits; their one-ring parents inherit
    matching edge splits. Those neighbors do not request unrelated refinement.
    Thus conformity never propagates arbitrarily across the 1.2M-polygon mesh.
    The near protected-interface band uses <=5cm edges. Exact protected-surface
    preservation also needs a pre-transport zero-inventory guard of at least
    (one model grid cell + protection_edge_m), or an exact boundary-aligned mesh.
    A one-cell guard alone protects points, not triangles. Always run the audit.
    Other moving areas use <=7cm.
    """
    limits = limits or RefineLimits(); bounds = _bounds(bounds)
    protected_bounds = None if protected_bounds is None else _bounds(protected_bounds)
    co = np.asarray(co); triangles = np.asarray(triangles); tp = np.asarray(triangle_polygons)
    _require(co.ndim == 2 and co.shape[1] == 3 and np.isfinite(co).all(), 'Finite coordinates(N,3) required')
    _require(triangles.ndim == 2 and triangles.shape[1] == 3 and np.issubdtype(triangles.dtype, np.integer), 'Integer original loop triangles(M,3) required')
    _require(tp.shape == (len(triangles),) and np.issubdtype(tp.dtype, np.integer), 'Original triangle parent IDs required')
    _require(len(co) <= limits.max_source_vertices and len(triangles) <= limits.max_source_triangles, 'Global source cap exceeded')
    _require(len(triangles) and triangles.min() >= 0 and triangles.max() < len(co), 'Invalid source vertex IDs')
    _require(tp.min() >= 0 and tp.max() < polygon_count, 'Invalid source parent IDs')
    _require(.02 <= protection_edge_m <= max_edge_m <= .075, 'Use 2–7.5cm bounded edge thresholds')
    _require(contact_x is None or np.isfinite(contact_x), 'Contact X must be finite')
    for value in vars(limits).values():
        _require(isinstance(value, int) and value > 0, 'Allocation limits must be positive integers')
    # Filter protected dense source triangles while scanning, before allocating
    # local point tensors or enforcing the LOCAL refinement cap. A protected
    # near patch may contain far more triangles than the active distant domain.
    candidate_parts=[];rectangle_count=0;active_count=0
    for first in range(0,len(triangles),limits.scan_batch_size):
        ids=triangles[first:first+limits.scan_batch_size]
        q=co[ids,:2];lo=q.min(1);hi=q.max(1)
        active=_box_intersects(lo,hi,bounds);rectangle_count+=int(active.sum())
        active &= 2.*_triangle_area(q)>1e-13
        if protected_bounds is not None:
            a,b,c,d=protected_bounds
            active &= ~((lo[:,0]>=a)&(hi[:,0]<=b)&(lo[:,1]>=c)&(hi[:,1]<=d))
        if contact_x is not None:
            active &= lo[:,0]<contact_x
        rows=first+np.flatnonzero(active);active_count+=len(rows)
        _require(active_count<=limits.max_local_source_triangles,'Active source rectangle exceeds local triangle cap')
        candidate_parts.append(rows)
    candidate=np.concatenate(candidate_parts).astype(np.int32)
    selected_parents = np.unique(tp[candidate])
    _require(len(selected_parents), 'No source triangles in active flow support')
    seed_ids = np.flatnonzero(np.isin(tp, selected_parents)).astype(np.int32)
    _require(len(seed_ids) <= limits.max_local_source_triangles, 'Seed parent tessellation exceeds local cap')
    radix = len(co) + limits.max_added_vertices + 1
    wanted = np.unique(_keys(triangles[seed_ids][:, [[0,1],[1,2],[2,0]]], radix))
    adjacent_parents = []
    for start in range(0, len(triangles), limits.scan_batch_size):
        t = triangles[start:start+limits.scan_batch_size]
        _, found = _match(wanted, _keys(t[:, [[0,1],[1,2],[2,0]]], radix))
        adjacent_parents.append(tp[start:start+len(t)][found.any(1)])
    replaced = np.unique(np.concatenate(adjacent_parents)).astype(np.int32)
    local = np.flatnonzero(np.isin(tp, replaced)).astype(np.int32)
    _require(len(local) <= limits.max_local_source_triangles, 'Conforming one-ring exceeds local source cap')
    refine_source = np.isin(tp[local], selected_parents)
    src = local.copy(); faces = triangles[local].astype(np.int32, copy=True)
    weights = np.broadcast_to(np.eye(3), (len(faces),3,3)).copy()
    target_by_source = np.full(len(local), max_edge_m)
    p = co[triangles[local], :2]; ll = p.min(1); hh = p.max(1)
    interface = np.zeros(len(local), bool)
    if protected_bounds is not None:
        a,b,c,d=protected_bounds
        interface |= _box_intersects(ll, hh, (a-max_edge_m,b+max_edge_m,c-max_edge_m,d+max_edge_m))
    if contact_x is not None:
        interface |= hh[:,0] >= contact_x-max_edge_m
    target_by_source[interface] = protection_edge_m
    # Capacity-backed arrays avoid repeated copies of the 1.2M original vertices.
    additions = np.empty((limits.max_added_vertices,3), np.float64)
    add_source = np.empty(limits.max_added_vertices, np.int32)
    add_weights = np.empty((limits.max_added_vertices,3), np.float64)
    count = 0; rounds = 0
    def coords(ids):
        out = np.empty(ids.shape + (3,), np.float64); old = ids < len(co)
        out[old] = co[ids[old]]; out[~old] = additions[ids[~old]-len(co)]
        return out
    # Each template indexes (a,b,c,m_ab,m_bc,m_ca) and preserves orientation.
    templates = {
        0: ((0,1,2),), 1: ((0,3,2),(3,1,2)),
        2: ((1,4,0),(4,2,0)), 4: ((2,5,1),(5,0,1)),
        3: ((1,4,3),(0,3,2),(3,4,2)),
        6: ((2,5,4),(1,4,0),(4,5,0)),
        5: ((0,3,5),(2,5,1),(5,3,1)),
        7: ((0,3,5),(3,1,4),(5,4,2),(3,4,5)),
    }
    while True:
        local_index = np.searchsorted(local, src)
        xyz = coords(faces)
        lengths = np.linalg.norm(xyz[:, [1,2,0]]-xyz[:, [0,1,2]], axis=2)
        marking = refine_source[local_index,None] & (lengths > target_by_source[local_index,None]*(1+1e-12))
        if not marking.any():
            break
        _require(rounds < limits.max_rounds, 'Refinement round cap exceeded')
        edge_keys = _keys(faces[:, [[0,1],[1,2],[2,0]]], radix)
        marked_rows, marked_edges = np.nonzero(marking)
        split_keys, first = np.unique(edge_keys[marking], return_index=True)
        n = len(split_keys)
        _require(count+n <= limits.max_added_vertices, 'Added-vertex cap exceeded; do not silently coarsen')
        rr, ee = marked_rows[first], marked_edges[first]
        ww = (weights[rr,ee]+weights[rr,(ee+1)%3])*.5
        tt = src[rr]
        additions[count:count+n] = interpolate(co, triangles[tt], ww)
        add_source[count:count+n] = tt; add_weights[count:count+n] = ww
        pos, split = _match(split_keys, edge_keys)
        midpoint = np.where(split, len(co)+count+pos, -1).astype(np.int32)
        mask = split @ np.array([1,2,4], dtype=np.int8)
        output_count = int(sum(np.count_nonzero(mask == k)*len(t) for k,t in templates.items()))
        _require(output_count <= limits.max_output_triangles, 'Replacement-triangle cap exceeded')
        nf = np.empty((output_count,3),np.int32); ns = np.empty(output_count,np.int32)
        nw = np.empty((output_count,3,3),np.float64); offset = 0
        for k, template in templates.items():
            rows = np.flatnonzero(mask == k)
            if not len(rows):
                continue
            v = np.concatenate((faces[rows],midpoint[rows]),axis=1)
            w = np.concatenate((weights[rows],(weights[rows]+weights[rows][:,[1,2,0]])*.5),axis=1)
            template = np.asarray(template); total = len(rows)*len(template)
            nf[offset:offset+total] = v[:,template].reshape(-1,3)
            nw[offset:offset+total] = w[:,template].reshape(-1,3,3)
            ns[offset:offset+total] = np.repeat(src[rows],len(template))
            offset += total
        faces,src,weights = nf,ns,nw
        count += n; rounds += 1
    # Near-coincident source rows may produce zero-footprint children. They
    # carry no renderable height surface; omit only changed child faces, never
    # merge positions or alter untouched original polygons.
    nondegenerate = 2.*_triangle_area(coords(faces)[...,:2]) > 1e-13
    omitted_children = int((~nondegenerate).sum())
    faces=faces[nondegenerate]; src=src[nondegenerate]; weights=weights[nondegenerate]
    lengths=lengths[nondegenerate]
    additions=additions[:count].copy(); add_source=add_source[:count].copy(); add_weights=add_weights[:count].copy()
    source_edges = np.full((count,2),-1,np.int32)
    zeros = np.abs(add_weights) < 1e-13; boundary = zeros.sum(1) == 1
    for j in range(3):
        hit = boundary & zeros[:,j]
        source_edges[hit] = np.sort(triangles[add_source[hit]][:,[k for k in range(3) if k != j]],axis=1)
    # Connectivity certificate: every split-original-edge incident triangle was
    # captured by the exact global one-ring scan, and each round split ALL uses.
    original_area = _triangle_area(co[triangles[local],:2]).sum()
    output_area = _triangle_area(coords(faces)[...,:2]).sum()
    _require(abs(original_area-output_area) <= 1e-9*max(1.,original_area), 'Refinement changed source projected area')
    local_index=np.searchsorted(local,src)
    peak=float(lengths[refine_source[local_index]].max()) if refine_source[local_index].any() else 0.
    keep=np.setdiff1d(np.arange(polygon_count,dtype=np.int32),replaced)
    report=dict(source_vertices=len(co),source_triangles=len(triangles),source_polygons=int(polygon_count),
        source_rectangle_triangles=rectangle_count,active_rectangle_triangles=active_count,
        excluded_protected_or_degenerate_rectangle_triangles=rectangle_count-active_count,
        local_source_triangles=len(local),selected_source_triangles=int(refine_source.sum()),
        replaced_polygons=len(replaced),kept_original_polygons=len(keep),added_vertices=count,
        replacement_triangles=len(faces),omitted_zero_footprint_children=omitted_children,refinement_rounds=rounds,max_active_edge_m=peak,
        edge_limit_m=max_edge_m,protected_interface_edge_limit_m=protection_edge_m,
        required_extra_pretransport_inventory_guard_m=protection_edge_m,
        original_projected_area_m2=float(original_area),refined_projected_area_m2=float(output_area),
        bounds_m=list(bounds),original_vertices_bitwise_preserved=True,
        original_triangle_barycentric_additions=True,shared_edge_midpoints=True,
        neighbor_policy='Original-edge one-ring parent closure; only selected sources request splits',
        limits=vars(limits).copy(),rendered=False,saved=False,scene_assigned=False)
    plan=RefinePlan(len(co),keep,replaced,local,triangles,tp,additions,add_source,add_weights,
        source_edges,faces,src,weights,refine_source,bounds,protected_bounds,contact_x,report)
    report['conformity_certificate']=certify_refinement(plan,co)
    return plan


def _triangle_area(q):
    q=np.asarray(q,dtype=np.float64)
    a=q[:,1]-q[:,0]; b=q[:,2]-q[:,0]
    return .5*np.abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])


class SourceSampler:
    """Compact-bin, exact original-triangle XY sampler; no nearest fallback.

    Accepts only the bounded source rectangle plus a caller-selected collar.
    Ambiguous overlapping XY layers are not combined: use separate ground and
    road samplers and an explicit topmost policy where the ground ends.
    """
    def __init__(self, co, triangles, triangle_ids, cell_m=.20,
                 max_triangles=160_000, max_bin_entries=1_500_000):
        self.co=np.asarray(co); self.source_triangles=np.asarray(triangles)
        ids=np.asarray(triangle_ids,dtype=np.int32)
        _require(0 < len(ids) <= max_triangles and cell_m > 0, 'Bounded nonempty sampler required')
        q=self.co[self.source_triangles[ids],:2].astype(float)
        a=q[:,0]; u=q[:,1]-a; v=q[:,2]-a
        det=u[:,0]*v[:,1]-u[:,1]*v[:,0]
        good=np.abs(det)>1e-13
        self.omitted_degenerate_triangles=int((~good).sum())
        self.triangle_ids=ids[good]; self.triangles=self.source_triangles[self.triangle_ids]
        self.a=a[good]; self.u=u[good]; self.v=v[good]; self.det=det[good]
        _require(len(self.triangle_ids)>0, 'Sampler has no nondegenerate XY support')
        q=q[good]; self.cell=float(cell_m)
        lo=np.floor((q.min(1)-1e-9)/self.cell).astype(np.int32)
        hi=np.floor((q.max(1)+1e-9)/self.cell).astype(np.int32)
        entries=int(np.prod(hi-lo+1,axis=1).sum())
        _require(entries <= max_bin_entries,'Sampler bin-entry cap exceeded')
        self.origin=lo.min(0); shape=hi.max(0)-self.origin+1
        self.shape=shape; keys=np.empty(entries,np.int64); values=np.empty(entries,np.int32); at=0
        for i,(l,h) in enumerate(zip(lo,hi)):
            xx,yy=np.meshgrid(np.arange(l[0],h[0]+1),np.arange(l[1],h[1]+1))
            n=xx.size; keys[at:at+n]=(yy.ravel()-self.origin[1])*shape[0]+xx.ravel()-self.origin[0]
            values[at:at+n]=i; at+=n
        order=np.argsort(keys,kind='stable'); self.keys=keys[order]; self.entries=values[order]

    def weights(self,xy,batch_size=1024,max_products=1_000_000):
        p=np.asarray(xy,dtype=float)
        _require(p.ndim==2 and p.shape[1]==2 and np.isfinite(p).all(), 'Finite points(N,2) required')
        bins=np.floor(p/self.cell).astype(np.int64)-self.origin
        _require(np.all(bins>=0) and np.all(bins<self.shape), 'Source query outside bounded support')
        k=bins[:,1]*self.shape[0]+bins[:,0]
        unique,inverse=np.unique(k,return_inverse=True); order=np.argsort(inverse,kind='stable')
        cuts=np.r_[0,np.cumsum(np.bincount(inverse,minlength=len(unique)))]
        chosen=np.empty(len(p),np.int32); weights=np.empty((len(p),3))
        for group,key in enumerate(unique):
            start=np.searchsorted(self.keys,key,side='left'); end=np.searchsorted(self.keys,key,side='right')
            cand=self.entries[start:end]; _require(len(cand)>0,'Source query has a coverage gap')
            step=min(batch_size,max_products//len(cand)); _require(step>0,'Sampler query-product cap exceeded')
            for first in range(cuts[group],cuts[group+1],step):
                rows=order[first:min(first+step,cuts[group+1])]; d=p[rows,None,:]-self.a[cand]
                u=(d[:,:,0]*self.v[cand,1]-d[:,:,1]*self.v[cand,0])/self.det[cand]
                v=(self.u[cand,0]*d[:,:,1]-self.u[cand,1]*d[:,:,0])/self.det[cand]
                score=np.minimum(np.minimum(u,v),1-u-v); best=score.argmax(1); r=np.arange(len(rows))
                _require(np.all(score[r,best]>=-2e-7),'Point is outside actual source triangles; no extrapolation')
                chosen[rows]=self.triangle_ids[cand[best]]
                weights[rows]=np.column_stack((1-u[r,best]-v[r,best],u[r,best],v[r,best]))
        return chosen,weights

    def sample(self,values,xy,discrete=False):
        ids,w=self.weights(xy)
        return interpolate(values,self.source_triangles[ids],w,discrete)

    def height(self,xy):
        return self.sample(self.co[:,2],xy)


def edge_attribute_sources(original_edges, output_edges, plan):
    """Return old-edge ID for retained/split edges, -1 for generated interiors."""
    old=np.asarray(original_edges); new=np.asarray(output_edges); radix=plan.original_vertex_count+len(plan.additions)+1
    keys=_keys(old,radix); order=np.argsort(keys); keys=keys[order]
    pos,found=_match(keys,_keys(new,radix)); source=np.full(len(new),-1,np.int32); source[found]=order[pos[found]]
    root=np.full((plan.original_vertex_count+len(plan.additions),2),-1,np.int32)
    root[plan.original_vertex_count:]=plan.addition_source_edges
    u,v=new.T; a,b=root[u],root[v]; candidate=np.full_like(new,-1)
    same=(a[:,0]>=0)&np.all(a==b,axis=1); candidate[same]=a[same]
    left=(a[:,0]>=0)&((a[:,0]==v)|(a[:,1]==v)); candidate[left]=a[left]
    right=(b[:,0]>=0)&((b[:,0]==u)|(b[:,1]==u)); candidate[right]=b[right]
    take=(~found)&(candidate[:,0]>=0); rows=np.flatnonzero(take)
    pos,found=_match(keys,_keys(candidate[take],radix)); source[rows[found]]=order[pos[found]]
    return source



def certify_refinement(plan, original):
    """Bounded topology certificate, excluding zero-footprint source triangles.

    Every output interior edge must have two uses. Every one-use edge must be
    a segment of an ORIGINAL local patch boundary edge; segment lengths must
    cover that original edge exactly. This catches missing propagation and
    holes without constructing a full 2.4M-triangle scene edge dictionary.
    """
    source=plan.source_triangles[plan.local_source_triangle_ids]
    source=source[2.*_triangle_area(np.asarray(original)[source,:2])>1e-13]
    se=np.sort(source[:,[[0,1],[1,2],[2,0]]].reshape(-1,2),axis=1)
    unique,uses=np.unique(se,axis=0,return_counts=True)
    _require(np.all(uses<=2),'Source local surface is nonmanifold after zero-footprint exclusion')
    source_boundary=unique[uses==1]
    oe=np.sort(plan.triangles[:,[[0,1],[1,2],[2,0]]].reshape(-1,2),axis=1)
    unique,uses=np.unique(oe,axis=0,return_counts=True)
    _require(np.all(uses<=2),'Refined local surface has a nonmanifold edge')
    boundary=unique[uses==1]
    inherited=edge_attribute_sources(source_boundary,boundary,plan)
    _require(np.all(inherited>=0),'Unpropagated edge split or unexpected refined-surface hole')
    co=plan.coordinates(original)
    lengths=np.linalg.norm(co[boundary[:,1]]-co[boundary[:,0]],axis=1)
    covered=np.bincount(inherited,weights=lengths,minlength=len(source_boundary))
    original64=np.asarray(original,dtype=float)
    expected=np.linalg.norm(original64[source_boundary[:,1]]-original64[source_boundary[:,0]],axis=1)
    error=float(np.max(np.abs(covered-expected))) if len(expected) else 0.
    _require(error<=1e-10*max(1.,float(expected.max(initial=0.))),'Original patch boundary coverage changed')
    return dict(local_surface_edges=len(unique),interior_edges_have_two_uses=True,
        boundary_segments=len(boundary),all_boundary_segments_have_original_provenance=True,
        maximum_boundary_coverage_error_m=error,zero_footprint_xy_cross_threshold_m2=1e-13)

def _clip_payload(poly,bounds):
    for axis,value,above in ((0,bounds[0],True),(0,bounds[1],False),(1,bounds[2],True),(1,bounds[3],False)):
        out=[]
        for a,b in zip(poly,np.roll(poly,-1,axis=0)):
            ia=a[axis]>=value if above else a[axis]<=value
            ib=b[axis]>=value if above else b[axis]<=value
            if ia: out.append(a)
            if ia!=ib:
                t=(value-a[axis])/(b[axis]-a[axis]); q=a+t*(b-a); q[axis]=value; out.append(q)
        poly=np.asarray(out,dtype=float).reshape(-1,3)
        if not len(poly): break
    return poly


def audit_context_projection(plan, coordinates, vertex_delta, result=None, *, batch_size=8192):
    """Audit signed linear-triangle volume, including clipped boundary pieces.

    Unlike an inside-only audit, it reports displaced surface outside the solved
    rectangle and inside protected areas. It never modifies displacements or
    claims mesh mass closure. Includes untouched source triangles intersecting
    the domain, as well as replacement triangles. Unknown overlaps remain the
    caller's responsibility; rectangle area mismatch exposes coverage problems.
    """
    co=np.asarray(coordinates); dz=np.asarray(vertex_delta)
    if result is not None:
        grid_bounds=(result.x_m[0],result.x_m[-1],result.y_m[0],result.y_m[-1])
        _require(np.allclose(grid_bounds,plan.bounds,atol=1e-7,rtol=0),'Solver grid bounds do not match the refinement domain')
    _require(co.shape==(plan.original_vertex_count+len(plan.additions),3) and dz.shape==(len(co),), 'Projection arrays do not match plan')
    _require(np.isfinite(co).all() and np.isfinite(dz).all(),'Projection must be finite')
    keep_source=np.isin(plan.source_triangle_polygons,plan.keep_polygons)
    ids=intersecting_triangles(co,plan.source_triangles,plan.bounds)
    untouched=plan.source_triangles[ids[keep_source[ids]]]
    faces=np.concatenate((plan.triangles,untouched)); bounds=plan.bounds
    area=volume=outside_abs=protected_abs=coarse_area=0.; maxedge=0.
    def clipped_integrals(q,b):
        poly=_clip_payload(q,b)
        if len(poly)<3:return 0.,0.,0.
        tris=np.stack((np.broadcast_to(poly[0],(len(poly)-2,3)),poly[1:-1],poly[2:]),axis=1)
        aa=_triangle_area(tris[:,:,:2]); vv=aa*tris[:,:,2].mean(1)
        return float(aa.sum()),float(vv.sum()),float((aa*np.abs(tris[:,:,2]).mean(1)).sum())
    for first in range(0,len(faces),batch_size):
        t=faces[first:first+batch_size]; xy=co[t,:2]; delta=dz[t]; lo=xy.min(1);hi=xy.max(1)
        aa=_triangle_area(xy); vv=aa*delta.mean(1)
        inside=(lo[:,0]>=bounds[0])&(hi[:,0]<=bounds[1])&(lo[:,1]>=bounds[2])&(hi[:,1]<=bounds[3])
        intersects=_box_intersects(lo,hi,bounds); area+=float(aa[inside].sum()); volume+=float(vv[inside].sum())
        whole_abs=aa*np.abs(delta).mean(1)
        outside_abs+=float(whole_abs[~intersects].sum())
        for row in np.flatnonzero(intersects&~inside):
            payload=np.column_stack((xy[row],delta[row])); a,v,av=clipped_integrals(payload,bounds)
            area+=a;volume+=v;outside_abs+=max(0.,float(whole_abs[row])-av)
        edges=np.linalg.norm(xy[:,[1,2,0]]-xy[:,[0,1,2]],axis=2).max(1)
        moved=np.max(np.abs(delta),axis=1)>1e-12
        if np.any(moved):maxedge=max(maxedge,float(edges[moved].max()))
        coarse_area+=float(aa[moved&(edges>plan.report['edge_limit_m']*(1+1e-6))].sum())
        protected=[]
        if plan.protected_bounds is not None: protected.append(plan.protected_bounds)
        if plan.contact_x is not None: protected.append((plan.contact_x,max(plan.contact_x+1.,float(hi[:,0].max())+1.),float(lo[:,1].min())-1.,float(hi[:,1].max())+1.))
        for b in protected:
            for row in np.flatnonzero(moved&_box_intersects(lo,hi,b)):
                protected_abs+=clipped_integrals(np.column_stack((xy[row],delta[row])),b)[2]
    rectangle=(bounds[1]-bounds[0])*(bounds[3]-bounds[2])
    report=dict(triangle_area_m2=area,rectangle_area_m2=rectangle,area_difference_m2=area-rectangle,
        triangle_signed_volume_m3=volume,outside_domain_absolute_volume_upper_bound_m3=outside_abs,
        protected_absolute_volume_upper_bound_m3=protected_abs,max_moving_triangle_xy_edge_m=maxedge,
        coarse_moving_triangle_area_m2=coarse_area,needs_refinement=coarse_area>1e-10,
        protected_projection_unchanged=protected_abs<=1e-14,boundary_projection_contained=outside_abs<=1e-14,
        note='Exact clipped linear-triangle signed volume; absolute bounds may overcount sign changes/overlapping protected regions; no mass fix-up')
    if result is not None:
        dx=result.x_m[1]-result.x_m[0];dy=result.y_m[1]-result.y_m[0]
        grid=float(np.sum(result.flow.height_delta_m)*dx*dy)
        gross=float(result.flow.receipt['cumulative_erosion_m3']+result.flow.receipt['cumulative_deposition_m3'])
        report.update(solver_signed_volume_m3=grid,projection_volume_error_m3=volume-grid,
            projection_relative_to_gross_exchange=abs(volume-grid)/max(gross,1e-30))
    return report


def _read(collection,property_name,size=1,dtype=np.float32):
    output=np.empty((len(collection),size),dtype=dtype);collection.foreach_get(property_name,output.ravel())
    return output if size>1 else output[:,0]


def prepare_context_refinement(terrain, **options):
    """Prepare an unassigned Blender mesh with original materials/attributes.

    No bpy import until called. No source object mutation, no second terrain,
    no material copy, no save/render. Unsupported data is rejected before new
    mesh creation. Source custom normals are retained/interpolated before any
    flow displacement; callers explicitly own their post-displacement policy.
    """
    import bpy
    _require(terrain and terrain.type=='MESH' and terrain.name==TERRAIN,'Need the actual named left terrain object')
    old=terrain.data
    _require(not terrain.modifiers and old.shape_keys is None and not terrain.vertex_groups,'Modifiers, shape keys and vertex groups are unsupported')
    _require(old.animation_data is None,'Animated mesh data is unsupported')
    _require(np.allclose(np.asarray(terrain.matrix_world),np.eye(4),atol=1e-9,rtol=0),'Terrain must have identity world transform')
    schemas={}
    for attr in old.attributes:
        if attr.name in TOPOLOGY_ATTRIBUTES:continue
        _require(attr.data_type in ATTRIBUTE_TYPES and attr.domain in {'POINT','EDGE','FACE','CORNER'},'Unsupported attribute '+attr.name+': '+attr.domain+'/'+attr.data_type)
        schemas[attr.name]=(attr.domain,attr.data_type,*ATTRIBUTE_TYPES[attr.data_type])
    co=_read(old.vertices,'co',3);old.calc_loop_triangles()
    triangles=_read(old.loop_triangles,'vertices',3,np.int32);tp=_read(old.loop_triangles,'polygon_index',1,np.int32)
    tloops=_read(old.loop_triangles,'loops',3,np.int32)
    sizes=_read(old.polygons,'loop_total',1,np.int32); lv=_read(old.loops,'vertex_index',1,np.int32)
    _require(np.all(sizes>=3),'Invalid source polygon')
    edges=_read(old.edges,'vertices',2,np.int32)
    # All source wire edges would otherwise disappear during topology rebuild.
    use=_read(old.edges,'is_loose',1,bool);_require(not use.any(),'Loose source edges unsupported; refusing loss')
    plan=plan_refinement(co,triangles,tp,len(old.polygons),**options)
    sampler_ids=intersecting_triangles(co,triangles,plan.bounds)
    _require(len(sampler_ids)<=(options.get('limits') or RefineLimits()).max_local_source_triangles,
        'Exact source sampler rectangle exceeds local cap, including protected dense triangles; narrow the model/refinement bounds, e.g. (-10.,-3.50,8.70,40.), rather than coarsen or approximate source Z')
    sampler=SourceSampler(co,triangles,sampler_ids,max_triangles=(options.get('limits') or RefineLimits()).max_local_source_triangles)
    allco=plan.coordinates(co);keep=plan.keep_polygons
    keptmask=np.zeros(len(sizes),bool);keptmask[keep]=True
    keptloops=np.flatnonzero(np.repeat(keptmask,sizes)).astype(np.int32)
    counts=np.r_[sizes[keep],np.full(len(plan.triangles),3,np.int32)]
    flat=np.r_[lv[keptloops],plan.triangles.ravel()]
    parent=np.r_[keep,tp[plan.triangle_source]];new=None
    try:
        new=bpy.data.meshes.new(old.name+' / conforming AB context refinement')
        new.vertices.add(len(allco));new.vertices.foreach_set('co',allco.astype(np.float32).ravel())
        new.loops.add(len(flat));new.loops.foreach_set('vertex_index',flat)
        new.polygons.add(len(counts));new.polygons.foreach_set('loop_start',np.r_[0,np.cumsum(counts[:-1])].astype(np.int32))
        new.polygons.foreach_set('loop_total',counts)
        for slot in old.materials:new.materials.append(slot)
        new.polygons.foreach_set('material_index',_read(old.polygons,'material_index',1,np.int32)[parent])
        new.polygons.foreach_set('use_smooth',_read(old.polygons,'use_smooth',1,bool)[parent])
        new.update(calc_edges=True)
        output_edges=_read(new.edges,'vertices',2,np.int32)
        edge_sources=edge_attribute_sources(edges,output_edges,plan)
        for name,(domain,dtype,prop,width,ndtype,discrete) in schemas.items():
            values=_read(old.attributes[name].data,prop,width,ndtype)
            if domain=='POINT':output=plan.point_values(values,discrete)
            elif domain=='FACE':output=values[parent]
            elif domain=='CORNER':
                changed=plan.corner_values(values,tloops,discrete).reshape((-1,)+values.shape[1:])
                output=np.concatenate((values[keptloops],changed))
            else:
                output=np.zeros((len(output_edges),)+values.shape[1:],dtype=values.dtype)
                valid=edge_sources>=0;output[valid]=values[edge_sources[valid]]
            attr=new.attributes.get(name) or new.attributes.new(name,dtype,domain)
            attr.data.foreach_set(prop,np.asarray(output).ravel())
        normals=_read(old.corner_normals,'vector',3)
        changed=plan.corner_values(normals,tloops).reshape(-1,3)
        lengths=np.linalg.norm(changed,axis=1,keepdims=True)
        _require(np.all(lengths>1e-12),'Source corner normals cancel; refusing synthetic replacement')
        changed/=lengths
        preserved_normals=np.concatenate((normals[keptloops],changed))
        _require(not new.validate(verbose=False,clean_customdata=False),'Blender repaired candidate topology; rejecting it')
        new.normals_split_custom_set(preserved_normals)
        for key in old.keys():new[key]=old[key]
        if len(old.uv_layers):
            new.uv_layers.active_index=old.uv_layers.active_index
            for layer in old.uv_layers:new.uv_layers[layer.name].active_render=layer.active_render
        if len(old.color_attributes):
            new.color_attributes.active_color_name=old.color_attributes.active_color_name
            new.color_attributes.default_color_name=old.color_attributes.default_color_name
        _require(np.array_equal(_read(new.vertices,'co',3)[:len(co)],co),'Original coordinate changed')
        _require(np.array_equal(_read(new.loops,'vertex_index',1,np.int32)[:len(keptloops)],lv[keptloops]),'Untouched polygon corner sequence changed')
        report=dict(plan.report,attribute_names_preserved=list(schemas),material_slots_unchanged=True,
            source_custom_normals_interpolated=True,source_sampler_triangles=len(sampler.triangle_ids),
            sampler_degenerate_triangles_omitted=sampler.omitted_degenerate_triangles,
            blender_float32_storage=True,post_displacement_normals='Caller must choose an explicit shading policy')
        return dict(mesh=new,plan=plan,coordinates=allco,source_sampler=sampler,report=report,
            source_triangle_loops=tloops,source_attribute_schema=schemas)
    except Exception:
        if new is not None:bpy.data.meshes.remove(new)
        raise
