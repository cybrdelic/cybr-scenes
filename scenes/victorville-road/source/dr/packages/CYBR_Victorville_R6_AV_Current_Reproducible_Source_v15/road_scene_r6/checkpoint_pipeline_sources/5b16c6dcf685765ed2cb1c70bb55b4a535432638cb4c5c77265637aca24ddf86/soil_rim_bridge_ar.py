"""AR append-only soil bridge from the actual exposed topological ground rim.

Pure NumPy; no Blender import, scene mutation, file I/O, or terrain resampling.
Coordinates are world XYZ. Existing vertices/faces are never moved or replaced.
The caller must copy original material slots and map triangle_source to the
original face; CORNER provenance is explicit for every generated corner.
"""
from dataclasses import dataclass
import json
import numpy as np

GROUND = 'Graded shoulder and alluvial plain -1'


def require(ok, message):
    if not ok:
        raise ValueError(message)


class RimTopologyError(ValueError):
    """Hard topology failure with bounded, JSON-safe exact source evidence."""
    def __init__(self, message, diagnostics):
        self.diagnostics = diagnostics
        encoded = json.dumps(diagnostics,separators=(',',':'),allow_nan=False)
        # Lists already contain at most 100 records. This final cap prevents
        # an unusually verbose source coordinate representation bloating logs.
        while len(encoded.encode('utf-8')) > 100000:
            lists = [v for v in diagnostics.values() if isinstance(v,list) and len(v)>2]
            require(bool(lists), 'Unexpected rim diagnostic size')
            max(lists,key=len).pop()
            diagnostics['output_truncated_to_100kb'] = True
            encoded = json.dumps(diagnostics,separators=(',',':'),allow_nan=False)
        super().__init__(message+'; components='+str(diagnostics.get('component_count','?'))+
                         ', excluded_horizontal_edges='+str(diagnostics.get('excluded_horizontal_or_near_zero_y_edges','?')))


@dataclass(frozen=True)
class BridgeSpec:
    overlap_m: float = .004
    clearance_m: float = .0008
    rim_search_width_m: float = .6
    max_edge_occurrences: int = 650000
    max_additions: int = 30000
    max_exposed_edges: int = 16000
    extra_buffer_cap_mib: float = 60.


@dataclass
class SoilBridgePlan:
    additions: np.ndarray
    triangles: np.ndarray
    addition_source_vertex_pairs: np.ndarray
    addition_weights: np.ndarray
    addition_source_triangles: np.ndarray
    triangle_source: np.ndarray
    corner_source_vertex_pairs: np.ndarray
    corner_weights: np.ndarray
    corner_source_triangles: np.ndarray
    old_rim_vertex_ids: np.ndarray
    old_rim_source_triangles: np.ndarray
    new_rim_vertex_ids: np.ndarray
    report: dict


def _exposed_edges(co, triangles, bounds, spec):
    """Count actual edges globally, selecting edges rather than clipping faces."""
    xmin, ymin, ymax = bounds
    radix = len(co) + 1
    keys, sources = [], []
    count = 0
    for start in range(0, len(triangles), 8192):
        t = triangles[start:start+8192]
        for j in range(3):
            e = t[:, [j, (j+1) % 3]]
            p = co[e]
            keep = ((p[:, :, 0].min(1) >= xmin) &
                    (p[:, :, 1].max(1) >= ymin) &
                    (p[:, :, 1].min(1) <= ymax))
            e = np.sort(e[keep].astype(np.int64), axis=1)
            count += len(e)
            require(count <= spec.max_edge_occurrences,
                    'Actual rim edge allocation cap exceeded; narrow the search width')
            keys.append(e[:, 0]*radix+e[:, 1])
            sources.append(np.flatnonzero(keep).astype(np.int32)+start)
    k = np.concatenate(keys); s = np.concatenate(sources)
    del keys, sources
    require(len(k) > 0, 'Missing actual ground support')
    order = np.argsort(k, kind='stable'); k, s = k[order], s[order]
    first = np.r_[True, k[1:] != k[:-1]]
    last = np.r_[k[:-1] != k[1:], True]
    indices = np.flatnonzero(first & last)
    edge = np.c_[k[indices]//radix, k[indices] % radix].astype(np.int32)
    group_starts = np.flatnonzero(first)
    multiplicity = np.diff(np.r_[group_starts,len(k)])
    extraction = dict(scanned_source_triangles=int(len(triangles)),
        selected_edge_occurrences=int(len(k)),
        selected_unique_edges=int(len(group_starts)),
        actual_exposed_edges=int(len(indices)),
        selected_two_use_edges=int(np.count_nonzero(multiplicity==2)),
        selected_nonmanifold_edges=int(np.count_nonzero(multiplicity>2)),
        search_x_min_m=float(xmin),search_y_bounds_m=[float(ymin),float(ymax)])
    return edge, s[indices], extraction


def actual_right_rim(co, triangles, y_bounds, x_reference, spec=None):
    """Return exact source vertex IDs and adjacent source triangle IDs.

    Every retained edge occurs exactly once in the entire input tessellation.
    Components with branches, horizontal steps, backwards Y, or competing
    rightmost support are rejected rather than joined by synthetic segments.
    """
    spec = spec or BridgeSpec()
    co, tri = np.asarray(co), np.asarray(triangles)
    lo, hi = map(float, y_bounds)
    edges, source, extraction = _exposed_edges(co, tri,
        (float(x_reference)-spec.rim_search_width_m, lo, hi), spec)
    # Orient every candidate upwards. The third vertex must lie on the soil
    # (west) side. Left external rims and downward-facing hole sides drop out.
    p = co[edges]
    swap = p[:, 0, 1] > p[:, 1, 1]
    edges[swap] = edges[swap, ::-1]
    p = co[edges]
    dy = p[:, 1, 1]-p[:, 0, 1]
    third = co[tri[source]].mean(1)
    d = p[:, 1, :2]-p[:, 0, :2]; q = third[:, :2]-p[:, 0, :2]
    cross = d[:, 0]*q[:, 1]-d[:, 1]*q[:, 0]
    keep = (dy > 1e-12) & (cross > 1e-14)
    horizontal = np.flatnonzero(dy <= 1e-12)
    # Capture exact excluded source records before filtering. These arrays are
    # capped independently of the potentially large source mesh.
    horizontal = horizontal[np.argsort(p[horizontal,0,1],kind='stable')]
    excluded_horizontal = [dict(vertex_ids=edges[i].astype(int).tolist(),
        xyz=p[i].astype(float).tolist(),source_triangle_id=int(source[i]),
        delta_y_m=float(dy[i]),oriented_interior_xy_cross=float(cross[i]))
        for i in horizontal[:100]]
    extraction.update(excluded_horizontal_or_near_zero_y_edges=int(len(horizontal)),
        excluded_nonwest_or_degenerate_interior_edges=int(np.count_nonzero(cross<=1e-14)),
        retained_upward_west_interior_edges=int(np.count_nonzero(keep)))
    # Zero-XY source edges are retained as connectivity evidence only. They
    # must never supply normal/attribute interpolation for new positive-area
    # facets, and no existing endpoint is welded or moved.
    zero_xy = np.all(p[:,0,:2] == p[:,1,:2],axis=1)
    zero_pairs = edges[zero_xy]; zero_sources = source[zero_xy]
    zero_parent = {}
    def root(v):
        v=int(v);zero_parent.setdefault(v,v)
        while zero_parent[v] != v:
            zero_parent[v]=zero_parent[zero_parent[v]];v=zero_parent[v]
        return v
    zero_lookup = {}
    for pair,parent in zip(zero_pairs,zero_sources):
        a,b=map(int,pair);zero_parent[root(a)]=root(b)
        zero_lookup[tuple(sorted((a,b)))]=int(parent)
    edges, source = edges[keep], source[keep]
    require(len(edges) <= spec.max_exposed_edges, 'Exposed rim topology allocation cap exceeded')
    require(len(edges) > 0, 'No upward monotone exposed right ground rim')
    adjacency = {}
    for i, (a, b) in enumerate(edges):
        adjacency.setdefault(int(a), []).append(i)
        adjacency.setdefault(int(b), []).append(i)
    require(all(len(v) <= 2 for v in adjacency.values()), 'Ambiguous branched ground rim')
    unused = set(range(len(edges))); candidates = []; components = []
    while unused:
        i = next(iter(unused)); component = {i}; pending = [i]
        while pending:
            for v in edges[pending.pop()]:
                for j in adjacency[int(v)]:
                    if j not in component:
                        component.add(j); pending.append(j)
        unused.difference_update(component)
        ids = sorted(component, key=lambda j: co[edges[j, 0], 1])
        e = edges[ids]
        require(np.array_equal(e[:-1, 1], e[1:, 0]),
                'Nonmonotone or ambiguous ground rim component')
        vertices = np.r_[e[:, 0], e[-1, 1]]
        yy = co[vertices, 1]
        components.append((vertices, source[ids]))
        if yy[0] <= lo+1e-10 and yy[-1] >= hi-1e-10:
            candidates.append((vertices, source[ids]))
    # Join only source-proven endpoint seams: either exact XYZ aliases or
    # exact XY plus an actual zero-XY topological edge path. Nonzero XY gaps
    # remain hard failures, regardless of how small their distance is.
    starts = {}
    for i,(vertices,_) in enumerate(components):
        starts.setdefault(tuple(co[vertices[0],:2]),[]).append(i)
    successor={};predecessor={};join_parent={}
    for i,(vertices,_) in enumerate(components):
        a=int(vertices[-1]);choices=[]
        for j in starts.get(tuple(co[a,:2]),[]):
            if j==i:continue
            b=int(components[j][0][0])
            actual_path=(a in zero_parent and b in zero_parent and root(a)==root(b))
            if np.array_equal(co[a],co[b]) or actual_path:
                choices.append((j,zero_lookup.get(tuple(sorted((a,b))),-2 if actual_path else -1)))
        require(len(choices)<=1,'Ambiguous exact-coordinate ground rim seam')
        if choices:
            j,parent=choices[0]
            require(j not in predecessor,'Multiple predecessors at actual rim seam')
            successor[i]=j;predecessor[j]=i;join_parent[i]=parent
    joined=[];visited=set()
    for start in range(len(components)):
        if start in predecessor:continue
        vertex_parts=[];source_parts=[];i=start
        while True:
            require(i not in visited,'Cyclic ground rim alias seam')
            visited.add(i);v,t=components[i];vertex_parts.append(v);source_parts.append(t)
            if i not in successor:break
            source_parts.append(np.array([join_parent[i]],np.int32));i=successor[i]
        joined.append((np.concatenate(vertex_parts),np.concatenate(source_parts)))
    require(len(visited)==len(components),'Cyclic or inaccessible ground rim component')
    candidates=[(v,t) for v,t in joined if co[v[0],1]<=lo+1e-10 and co[v[-1],1]>=hi-1e-10]
    if not candidates:
        ordered = sorted(components,key=lambda item:(float(co[item[0][0],1]),
                                                      float(co[item[0][0],0])))
        records = []
        for i,(vertices,parents) in enumerate(ordered[:100]):
            ends = vertices[[0,-1]]; q = co[ends].astype(float)
            records.append(dict(component_index=i,edge_count=int(len(parents)),
                endpoint_vertex_ids=ends.astype(int).tolist(),endpoint_xyz=q.tolist(),
                x_bounds_m=[float(co[vertices,0].min()),float(co[vertices,0].max())],
                y_bounds_m=[float(q[0,1]),float(q[1,1])],
                endpoint_source_triangle_ids=parents[[0,-1]].astype(int).tolist(),
                covers_requested_start=bool(q[0,1]<=lo+1e-10),
                covers_requested_end=bool(q[1,1]>=hi-1e-10)))
        gaps = []
        for i in range(min(100,max(0,len(ordered)-1))):
            a,b=int(ordered[i][0][-1]),int(ordered[i+1][0][0])
            qa,qb=co[a].astype(float),co[b].astype(float);delta=qb-qa
            gaps.append(dict(from_component=i,to_component=i+1,
                endpoint_vertex_ids=[a,b],from_xyz=qa.tolist(),to_xyz=qb.tolist(),
                delta_xyz_m=delta.tolist(),distance_m=float(np.linalg.norm(delta)),
                same_source_vertex=a==b,exact_coincident_coordinates=bool(np.array_equal(qa,qb))))
        diagnostics=dict(extraction,requested_y_bounds_m=[lo,hi],
            source_vertex_count=int(len(co)),component_count=len(components),joined_component_count=len(joined),
            spanning_component_count=0,components=records,
            component_records_truncated=len(ordered)>100,consecutive_component_gaps=gaps,
            gap_records_truncated=len(ordered)>101,
            excluded_horizontal_edges=excluded_horizontal,
            excluded_horizontal_records_truncated=len(horizontal)>100,
            thresholds=dict(positive_delta_y_m=1e-12,west_interior_xy_cross=1e-14,
                            collar_coverage_tolerance_m=1e-10),
            source_ids_are_original_input_indices=True,geometry_or_tolerances_modified=False)
        raise RimTopologyError('Actual ground rim does not continuously cover boundary collars',diagnostics)
    # A hole may supply another upward chain. The actual external rim must
    # dominate all alternatives over their complete overlapping intervals.
    probes = np.unique(np.r_[lo, hi, *[co[v, 1] for v, _ in candidates]])
    probes = probes[(probes >= lo) & (probes <= hi)]
    heights = np.array([np.interp(probes, co[v, 1], co[v, 0]) for v, _ in candidates])
    wins = [i for i in range(len(candidates))
            if np.all(heights[i] >= np.max(heights, axis=0)-1e-10)]
    require(len(wins) == 1, 'Crossing or ambiguous rightmost ground boundary')
    winner = candidates[wins[0]]
    v = winner[0]; wy, wx = co[v,1], co[v,0]
    for other, _ in components:
        cy, cx = co[other,1], co[other,0]
        a, b = max(lo,cy[0]), min(hi,cy[-1])
        if b <= a: continue
        q = np.unique(np.r_[a,b,cy[(cy>a)&(cy<b)],wy[(wy>a)&(wy<b)]])
        require(np.all(np.interp(q,cy,cx) <= np.interp(q,wy,wx)+1e-10),
                'Disconnected or ambiguous support lies right of the selected ground rim')
    return winner


def _monotone_zipper(left, right, coordinate):
    """Conforming monotone-polygon zipper, including same-chain diagonals.

    Unlike a Y-only two-pointer zipper this remains valid for grain-scale
    jagged edges against coarse source edges; no rim subdivisions/T-junctions.
    """
    chain = {int(i): 0 for i in left}
    chain.update({int(i): 1 for i in right})
    ids = sorted(set(map(int, np.r_[left, right])),
                 key=lambda i: (coordinate(i)[1], coordinate(i)[0]))
    require(len(ids) >= 3, 'Bridge has no polygon area')
    stack = ids[:2]; out = []
    def cross(a, b, c):
        p, q, r = coordinate(a)[:2], coordinate(b)[:2], coordinate(c)[:2]
        u, v = q-p, r-p
        return u[0]*v[1]-u[1]*v[0]
    def emit(a, b, c):
        area = cross(a, b, c)
        if abs(area) > 1e-15:
            out.append((a,b,c) if area > 0 else (a,c,b))
    for pos in range(2, len(ids)-1):
        cur = ids[pos]
        if chain[cur] != chain[stack[-1]]:
            while len(stack) > 1:
                last = stack.pop(); emit(cur, last, stack[-1])
            stack = [ids[pos-1], cur]
        else:
            last = stack.pop()
            while stack:
                turn = cross(cur, last, stack[-1])
                if not (turn > 1e-15 if chain[cur] == 0 else turn < -1e-15):
                    break
                emit(cur, last, stack[-1]); last = stack.pop()
            stack.extend((last, cur))
    cur = ids[-1]
    while len(stack) > 1:
        last = stack.pop(); emit(cur, last, stack[-1])
    return np.asarray(out, np.int32).reshape(-1,3)


def plan_soil_bridge(co, triangles, boundary, road_top_z,
                     triangle_polygons=None, spec=None):
    """Append soil to max(boundary.x+4 mm, actual old rim+1 mm).

    road_top_z is either a same-length array at boundary.y, or a callable
    accepting Nx2 world XY (the actual asphalt overlap coordinates). The
    callable is preferred because it can sample exact retained road facets.
    Ground top uses actual road Z minus 0.8 mm. Input and source-rim Y
    knots are both retained; existing inboard soil is never pushed backwards.
    All provenance triangle IDs index the ORIGINAL triangles argument, even
    when triangle_polygons is supplied (which is only validated here).
    """
    spec = spec or BridgeSpec(); co = np.asarray(co); tri = np.asarray(triangles)
    require(co.ndim == 2 and co.shape[1] == 3 and tri.ndim == 2 and tri.shape[1] == 3,
            'Actual XYZ and triangle arrays required')
    require(np.isfinite(co).all() and np.issubdtype(tri.dtype, np.integer),
            'Finite coordinates and actual integer topology required')
    require(.001 <= spec.overlap_m <= .006 and .0004 <= spec.clearance_m <= .002,
            'Bounded asphalt overlap and positive clearance required')
    require(spec.extra_buffer_cap_mib <= 60 and spec.max_edge_occurrences <= 650000 and
            spec.max_additions <= 30000 and spec.max_exposed_edges <= 16000,
            'Helper allocation cap is 60 MiB')
    by, bx = np.asarray(boundary.y, float), np.asarray(boundary.x, float)
    require(by.ndim == 1 and bx.shape == by.shape and 2 <= len(by) <= spec.max_additions,
            'Bounded actual road boundary required')
    require(np.isfinite(by).all() and np.isfinite(bx).all() and np.all(np.diff(by)>0),
            'Finite strictly increasing boundary Y required')
    require(by[0] < 0 and by[-1] > 15, 'Endpoint collars must be outside visible 0..15 m')
    if triangle_polygons is not None:
        require(len(triangle_polygons) == len(tri), 'Triangle/polygon provenance mismatch')
    old, oldsrc = actual_right_rim(co, tri, (by[0], by[-1]), bx.min(), spec)
    oy = co[old, 1]
    lower = max(0, np.searchsorted(oy, by[0], side='right')-1)
    upper = min(len(old)-1, np.searchsorted(oy, by[-1], side='left'))
    old, oldsrc = old[lower:upper+1], oldsrc[lower:upper]; oy = co[old, 1]
    input_y,input_x = by,bx
    # A generated double-precision regular-grid knot can differ from a source
    # float32 Y by 1e-15 m (for example 7.499999999999999 versus 7.5). Retaining
    # both manufactures an edge that collapses on Blender storage. Only such
    # generated knots are canonicalized; original rim coordinates are exact.
    generated_y=input_y.copy();stored_source_y={float(np.float32(v)):float(v) for v in oy}
    stored_knot_aliases=0
    for j in range(1,len(generated_y)-1):
        canonical_y=stored_source_y.get(float(np.float32(generated_y[j])))
        if canonical_y is not None and canonical_y!=generated_y[j]:
            before_x=np.interp(generated_y[j],input_y,input_x)
            after_x=np.interp(canonical_y,input_y,input_x)
            require(np.float32(before_x)==np.float32(after_x),
                    'Generated support Y alias has distinct stored X; cannot collapse it')
            generated_y[j]=canonical_y;stored_knot_aliases+=1
    by = np.unique(np.r_[generated_y,oy[(oy>=input_y[0])&(oy<=input_y[-1])]])
    require(len(by) <= spec.max_additions,'Combined input/source rim knots exceed bridge vertex cap')
    bx = np.interp(by,input_y,input_x)
    seg = np.clip(np.searchsorted(oy, by, side='right')-1, 0, len(old)-2)
    require(np.all(oy[seg+1]>oy[seg]),'New support sample selected a zero-Y source seam')
    require(np.all(oldsrc[seg]>=0),'New support sample lacks actual positive-area source provenance')
    weight = (by-oy[seg])/(oy[seg+1]-oy[seg])
    pairs = np.c_[old[seg], old[seg+1]]
    weights = np.c_[1-weight, weight]
    oldx = np.sum(co[pairs,0]*weights,axis=1)
    requested_x = bx+spec.overlap_m
    adapted = oldx+.001 > requested_x
    target_x = np.maximum(requested_x,oldx+.001)
    require(np.all(target_x <= -3.04-1e-6),
            'Actual bridge support exceeds fixed AQ right audit boundary -3.04 m')
    xy = np.c_[target_x, by]
    require(np.all(xy[:,0] > oldx+1e-9),
            'Requested bridge would overlap/reverse existing soil; no blind inward pushes')
    if callable(road_top_z):
        z = np.asarray(road_top_z(xy),float)
    else:
        supplied_z = np.asarray(road_top_z,float)
        require(supplied_z.shape == input_y.shape and np.isfinite(supplied_z).all(),
                'Road top Z array must match original input boundary knots')
        z = np.interp(by,input_y,supplied_z)
    require(z.shape == by.shape and np.isfinite(z).all(), 'Exact finite road top Z required')
    additions = np.c_[xy, z-spec.clearance_m]
    new = np.arange(len(co),len(co)+len(additions),dtype=np.int32)
    right = new
    # Close outer collar tips on exact source IDs, never invent extrapolated
    # source support or subdivide an existing edge without its adjacent face.
    if oy[0] < by[0]-1e-10: right = np.r_[old[0], right]
    if oy[-1] > by[-1]+1e-10: right = np.r_[right, old[-1]]
    def coord(i): return co[i] if i < len(co) else additions[i-len(co)]
    zero_segments=np.flatnonzero(np.diff(oy)==0)
    require(all(np.array_equal(co[old[k],:2],co[old[k+1],:2]) for k in zero_segments),
            'Ground rim has a nonzero horizontal step, not an exact alias seam')
    # Each original positive-Y run keeps its own endpoint IDs. Neighboring
    # runs share the exact same new support vertex at the seam Y.
    cuts=np.r_[0,zero_segments+1,len(old)]
    face_parts=[]
    for lo_run,hi_run in zip(cuts[:-1],cuts[1:]):
        left=old[lo_run:hi_run]
        require(len(left)>=2,'Zero-area-only source rim run')
        low,high=co[left[[0,-1]],1]
        inner=right[np.array([(coord(i)[1]>=low and coord(i)[1]<=high) for i in right])]
        require(len(inner)>=2,'Source run has no complete new support boundary')
        face_parts.append(_monotone_zipper(left,inner,coord))
    faces=np.concatenate(face_parts)
    require(len(faces) <= 2*(len(old)+len(new)), 'Bounded bridge triangle cap exceeded')
    old_lookup = {int(v): i for i,v in enumerate(old)}
    def provenance(i):
        if i >= len(co):
            j=i-len(co); return pairs[j], weights[j], oldsrc[seg[j]]
        j=old_lookup[int(i)]
        k=j if j<len(oldsrc) and oy[j+1]>oy[j] else j-1
        require(k>=0 and oldsrc[k]>=0 and oy[k+1]>oy[k],
                'Original bridge corner lacks adjacent positive-area source facet')
        return np.array([i,i]), np.array([1.,0.]), oldsrc[k]
    cp = np.empty((len(faces),3,2),np.int32)
    cw = np.empty((len(faces),3,2),float)
    cs = np.empty((len(faces),3),np.int32)
    for k, face in enumerate(faces):
        for j, vertex in enumerate(face): cp[k,j],cw[k,j],cs[k,j]=provenance(int(vertex))
    # Face material follows the real old rim segment at the face centroid Y.
    face_y=np.array([np.mean([coord(i)[1] for i in face]) for face in faces])
    fs=oldsrc[np.clip(np.searchsorted(oy,face_y,side='right')-1,0,len(oldsrc)-1)]
    used_edges={};original_edge_uses={}
    # This equivalence is for the XY coverage certificate only. Face vertex
    # IDs and every source XYZ remain verbatim, including a source Z step.
    canonical={int(v):int(v) for v in old}
    for k in zero_segments:canonical[int(old[k+1])]=canonical[int(old[k])]
    def edge_key(a,b):
        return tuple(sorted((canonical.get(int(a),int(a)),canonical.get(int(b),int(b)))))
    area=0.
    for f in faces:
        p=np.array([coord(i)[:2] for i in f]);a=p[1]-p[0];b=p[2]-p[0]
        area+=(a[0]*b[1]-a[1]*b[0])/2
        for a,b in zip(f,np.roll(f,-1)):
            e=edge_key(a,b);used_edges[e]=used_edges.get(e,0)+1
            original_key=tuple(sorted((int(a),int(b))))
            original_edge_uses[original_key]=original_edge_uses.get(original_key,0)+1
    polygon=list(map(int,old))+list(map(int,right[::-1]))
    polygon=[v for i,v in enumerate(polygon) if i==0 or v!=polygon[i-1]]
    if polygon[0]==polygon[-1]: polygon.pop()
    perimeter={edge_key(a,b) for a,b in zip(polygon,polygon[1:]+polygon[:1])
               if edge_key(a,b)[0]!=edge_key(a,b)[1]}
    for k in np.flatnonzero(np.diff(oy)>0):
        require(original_edge_uses.get(tuple(sorted(map(int,old[k:k+2]))),0)==1,
                'An original positive-area source rim edge did not gain exactly one bridge face')
    bad_edges=[(e,n) for e,n in used_edges.items() if n!=(1 if e in perimeter else 2)]
    missing_edges=list(perimeter.difference(used_edges))
    if bad_edges or missing_edges:
        detail=dict(bad_edge_count=len(bad_edges),missing_perimeter_count=len(missing_edges),
            bad_edges=[dict(vertex_ids=list(e),uses=n,xyz=[coord(i).tolist() for i in e]) for e,n in bad_edges[:12]],
            missing_edges=[dict(vertex_ids=list(e),xyz=[coord(i).tolist() for i in e]) for e in missing_edges[:12]])
        raise RimTopologyError('Nonconforming bridge topology; refusing T-junctions',detail)
    p=np.array([coord(i)[:2] for i in polygon]); p=p-p[0]
    expected=abs(np.sum(p[:,0]*np.roll(p[:,1],-1)-p[:,1]*np.roll(p[:,0],-1)))/2
    require(abs(area-expected) <= max(1e-10,expected*1e-10),
            'Bridge triangulation does not exactly cover the rim polygon')
    buffers=sum(a.nbytes for a in (additions,faces,pairs,weights,cp,cw,cs,fs))
    require(buffers < spec.extra_buffer_cap_mib*1024**2, 'Bridge output allocation cap exceeded')
    return SoilBridgePlan(additions,faces,pairs,weights,oldsrc[seg],fs,cp,cw,cs,
        old,oldsrc,right,dict(source_object=GROUND,added_vertices=len(additions),
        added_triangles=len(faces),actual_rim_vertices=len(old),area_m2=float(area),
        overlap_m=spec.overlap_m,road_clearance_m=spec.clearance_m,
        source_rim_positive_y_runs=int(len(cuts)-1),exact_xy_alias_seams=int(len(zero_segments)),
        source_zero_xy_edges=int(np.count_nonzero(oldsrc[zero_segments]>=0)),
        exact_xyz_alias_seams=int(sum(np.array_equal(co[old[k]],co[old[k+1]]) for k in zero_segments)),
        maximum_preserved_source_seam_z_step_m=float(max((abs(float(co[old[k+1],2])-float(co[old[k],2])) for k in zero_segments),default=0)),
        original_positive_y_rim_edges_each_gain_one_face=True,
        xy_alias_coverage_certificate=True,source_vertex_ids_welded=False,
        id_watertight_bridge_claim=not bool(len(zero_segments)),
        source_seam_topology_policy='Original IDs and zero-XY seams retained; geometric XY coverage certified without welding',
        source_zero_xy_path_seams=int(np.count_nonzero(oldsrc[zero_segments]==-2)),
        exact_xyz_only_alias_seams=int(np.count_nonzero(oldsrc[zero_segments]==-1)),
        nonzero_xy_gaps_bridged=0,new_support_seam_vertex_ids_shared=True,
        input_boundary_knots=int(len(input_y)),combined_source_boundary_knots=int(len(by)),
        generated_float32_storage_knot_aliases_collapsed=stored_knot_aliases,
        target_adaptation_count=int(np.count_nonzero(adapted)),
        maximum_target_adaptation_m=float(np.max(target_x-requested_x,initial=0)),
        old_rim_dominance_count=int(np.count_nonzero(oldx>requested_x)),
        maximum_old_rim_dominance_m=float(np.max(oldx-requested_x,initial=0)),
        minimum_outward_append_width_m=float(np.min(target_x-oldx)),
        final_support_x_max_m=float(target_x.max()),aq_right_audit_boundary_m=-3.04,
        source_vertices_unchanged=True,source_faces_unchanged=True,
        source_attributes_unchanged=True,world_coordinates=True,
        endpoint_collars_y_m=[float(oy[0]),float(oy[-1])],output_buffer_bytes=buffers,
        requires_exact_road_soil_overlap_audit=True))


def transport_corner_normals(source_normals, source_triangle_xyz,
                             target_triangle_xyz):
    """Transport source corner detail by the actual old/new facet rotation.

    Inputs: source_normals (N,3,3), source_triangle_xyz (N,3,3,3),
    target_triangle_xyz (N,3,3). Each generated corner can have a different
    supplying source facet. Returns float64 unit normals shaped (N,3,3).
    Rotation is the unique shortest arc between oriented facet normals; no
    averaging across facets or deletion of the source normal's detail angle.
    Degenerate triangles, invalid normals and near-antiparallel facets fail.
    Input arrays are borrowed; bounded 2048-face batches avoid full-size work
    arrays. The result plus temporary numerical buffers stays below 190 MiB.
    """
    normals = np.asarray(source_normals)
    source = np.asarray(source_triangle_xyz)
    target = np.asarray(target_triangle_xyz)
    require(normals.ndim == 3 and normals.shape[1:] == (3,3),
            'Source corner normals must have shape (N,3,3)')
    n = len(normals)
    require(source.shape == (n,3,3,3) and target.shape == (n,3,3),
            'Actual source-per-corner and target-per-face triangles required')
    require(n*3*3*8 + 8*1024**2 < 190*1024**2,
            'Normal transport numerical buffer cap exceeded')
    result = np.empty((n,3,3),np.float64)

    def facet_normal(p):
        require(np.isfinite(p).all(), 'Nonfinite actual facet coordinates')
        u,v = p[...,1,:]-p[...,0,:], p[...,2,:]-p[...,0,:]
        normal = np.cross(u,v)
        length = np.linalg.norm(normal,axis=-1)
        scale = np.linalg.norm(u,axis=-1)*np.linalg.norm(v,axis=-1)
        require(np.all(length > np.maximum(1e-20,scale*1e-12)),
                'Degenerate actual facet in normal transport')
        return normal/length[...,None]

    for first in range(0,n,2048):
        last = min(first+2048,n)
        old = facet_normal(np.asarray(source[first:last],np.float64))
        new = facet_normal(np.asarray(target[first:last],np.float64))[:,None,:]
        dot = np.clip(np.sum(old*new,axis=-1),-1.,1.)
        require(np.all(dot > -.99),
                'Near-antiparallel source/target facets in normal transport')
        v = np.asarray(normals[first:last],np.float64)
        length = np.linalg.norm(v,axis=-1)
        require(np.isfinite(v).all() and np.all(length > 1e-12),
                'Finite nonzero source detail normals required')
        v = v/length[...,None]
        axis = np.cross(old,new)
        cross = np.cross(axis,v)
        rotated = v+cross+np.cross(axis,cross)/(1.+dot)[...,None]
        length = np.linalg.norm(rotated,axis=-1)
        require(np.isfinite(rotated).all() and np.all(length > 1e-12),
                'Invalid transported detail normal')
        result[first:last] = rotated/length[...,None]
    return result
