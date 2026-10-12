"""AN: bounded, read-only sampling of the CURRENT physical road/soil surface.

Call sample(scene, output_directory, config=None) after AH, AC and AL in the
existing pipeline. Never opens/saves a blend, evaluates particles, builds a
scene BVH, changes geometry, or installs materials. Exact current mesh loop
triangles and the existing native 512-square tile triangles are the sources.
The existing AC inclined section also participates, using its actual FACE
layer: asphalt course vs mineral subgrade. Clasts/particles are excluded.
The old Z height field and historical film inventory are never read.

Pure-NumPy helpers import without Blender. Only sample() reads scene objects.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json
import time
import numpy as np

GROUND = 'Graded shoulder and alluvial plain -1'
ROAD = 'Crowned asphalt crust / longitudinal rise'
SECTION = 'AC supported pavement section'
TILE_PREFIX = 'Original asphalt native tile '
BOUNDS = (-3.8, -2.7, -.3, 2.3)
SPACING = .00625


def _require(ok, message):
    if not ok:
        raise ValueError(message)


@dataclass(frozen=True)
class SampleConfig:
    bounds_m: tuple = BOUNDS
    spacing_m: float = SPACING
    local_triangle_cap: int = 1_000_000
    source_triangle_cap: int = 3_000_000
    source_vertex_cap: int = 1_600_000
    bin_entry_cap: int = 4_000_000
    query_product_cap: int = 250_000
    estimated_extra_memory_cap_mib: float = 600.
    stage_label: str = 'current scene after AH + AC + AL'


def nested_axes(bounds=BOUNDS, spacing=SPACING):
    """Inclusive coincident cell-centre axes; coarser grids are exact strides."""
    b = np.asarray(bounds, dtype=float)
    _require(b.shape == (4,) and np.isfinite(b).all() and b[0] < b[1] and b[2] < b[3], 'Finite ordered bounds required')
    _require(np.isfinite(spacing) and spacing > 0, 'Positive finite spacing required')
    axes = []
    for lo, hi in (b[:2], b[2:]):
        count = int(round((hi-lo)/spacing))
        _require(count >= 4 and count % 4 == 0 and abs(count*spacing-(hi-lo)) < 1e-10, 'Bounds must hold an integral multiple of four finest-grid intervals')
        axes.append(lo + np.arange(count+1, dtype=float)*spacing)
    return tuple(axes)


class PartialSurfaceSampler:
    """Compact exact topmost triangle sampler, allowing gaps as NaN.

    A bounded spatial hash is built by vectorized variable-length expansion.
    Query products are capped; overlapping triangles select the highest actual
    Z hit, rather than a nearest triangle or a most-interior heuristic.
    """
    def __init__(self, coordinates, triangles, *, cell_m=.0125,
                 max_triangles=1_000_000, max_bin_entries=4_000_000,
                 max_query_products=250_000):
        co = np.asarray(coordinates, dtype=float)
        ids = np.asarray(triangles)
        _require(co.ndim == 2 and co.shape[1] == 3 and np.isfinite(co).all(), 'Finite coordinates(N,3) required')
        _require(ids.ndim == 2 and ids.shape[1] == 3 and np.issubdtype(ids.dtype, np.integer), 'Integer triangles(M,3) required')
        _require(0 < len(ids) <= max_triangles and ids.min() >= 0 and ids.max() < len(co), 'Triangle count/index limit exceeded')
        _require(np.isfinite(cell_m) and cell_m > 0 and max_query_products > 0, 'Invalid sampler limits')
        tri = co[ids]
        u = tri[:,1,:2]-tri[:,0,:2]; v = tri[:,2,:2]-tri[:,0,:2]
        det = u[:,0]*v[:,1]-u[:,1]*v[:,0]
        good = np.abs(det) > 1e-13
        self.omitted_degenerate_triangles = int((~good).sum())
        self.tri = tri[good]
        _require(len(self.tri) > 0, 'No nondegenerate XY surface triangles')
        self.a = self.tri[:,0,:2]
        self.u, self.v, self.det = u[good], v[good], det[good]
        del tri, u, v, det, good
        self.cell = float(cell_m); self.max_query_products = int(max_query_products)
        lo = np.floor((self.tri[:,:,:2].min(1)-1e-9)/self.cell).astype(np.int64)
        hi = np.floor((self.tri[:,:,:2].max(1)+1e-9)/self.cell).astype(np.int64)
        span = hi-lo+1; counts = np.prod(span, axis=1)
        entries = int(counts.sum())
        _require(entries <= max_bin_entries, 'Local triangle-bin entry cap exceeded')
        self.origin = lo.min(0); self.shape = hi.max(0)-self.origin+1
        repeated = np.repeat(np.arange(len(self.tri), dtype=np.int32), counts)
        offset = np.arange(entries)-np.repeat(np.cumsum(counts)-counts, counts)
        xx = lo[repeated,0] + offset % span[repeated,0] - self.origin[0]
        yy = lo[repeated,1] + offset // span[repeated,0] - self.origin[1]
        keys = yy*self.shape[0]+xx
        order = np.argsort(keys, kind='stable')
        self.keys = keys[order]; self.entries = repeated[order]
        self.report = dict(triangles=int(len(self.tri)), omitted_degenerate_triangles=self.omitted_degenerate_triangles,
                           bin_entries=entries, cell_m=self.cell, max_query_products=self.max_query_products,
                           triangle_xy_bounds_m=[float(self.tri[:,:,0].min()),float(self.tri[:,:,0].max()),float(self.tri[:,:,1].min()),float(self.tri[:,:,1].max())])

    def height(self, xy):
        p = np.asarray(xy, dtype=float)
        _require(p.ndim >= 2 and p.shape[-1] == 2 and np.isfinite(p).all(), 'Finite points(...,2) required')
        shape = p.shape[:-1]; p = p.reshape(-1,2)
        answer = np.full(len(p), np.nan)
        bins = np.floor(p/self.cell).astype(np.int64)-self.origin
        supported = np.all((bins >= 0) & (bins < self.shape), axis=1)
        rows0 = np.flatnonzero(supported)
        keys = bins[rows0,1]*self.shape[0]+bins[rows0,0]
        unique, inverse = np.unique(keys, return_inverse=True)
        order = rows0[np.argsort(inverse, kind='stable')]
        cuts = np.r_[0, np.cumsum(np.bincount(inverse, minlength=len(unique)))]
        for group, key in enumerate(unique):
            candidates = self.entries[np.searchsorted(self.keys,key,'left'):np.searchsorted(self.keys,key,'right')]
            if not len(candidates):
                continue
            # Also split candidates: no single densely overlapping bin bypasses
            # the product bound or changes the explicit highest-hit policy.
            row_step=min(128,self.max_query_products)
            for first in range(cuts[group], cuts[group+1], row_step):
                rows = order[first:min(first+row_step,cuts[group+1])]
                best = np.full(len(rows), -np.inf)
                step = max(1, self.max_query_products//len(rows))
                for start in range(0,len(candidates),step):
                    c = candidates[start:start+step]
                    d = p[rows,None,:]-self.a[c]
                    s = (d[:,:,0]*self.v[c,1]-d[:,:,1]*self.v[c,0])/self.det[c]
                    t = (self.u[c,0]*d[:,:,1]-self.u[c,1]*d[:,:,0])/self.det[c]
                    inside = (s >= -2e-7) & (t >= -2e-7) & (s+t <= 1+2e-7)
                    z = self.tri[c,0,2] + s*(self.tri[c,1,2]-self.tri[c,0,2]) + t*(self.tri[c,2,2]-self.tri[c,0,2])
                    best = np.maximum(best, np.where(inside,z,-np.inf).max(1))
                answer[rows] = np.where(np.isfinite(best),best,np.nan)
        return answer.reshape(shape)

    def left_edge(self, y):
        """Exact leftmost XY triangle-union intersection at each supplied Y."""
        y = np.asarray(y, dtype=float)
        _require(np.isfinite(y).all(), 'Finite edge Y required')
        out = np.full(y.size, np.nan)
        low, high = self.tri[:,:,1].min(1), self.tri[:,:,1].max(1)
        for k, value in enumerate(y.ravel()):
            tri = self.tri[(low <= value+1e-10) & (high >= value-1e-10)]
            best = np.inf
            for j in range(3):
                a, b = tri[:,j], tri[:,(j+1)%3]
                dy = b[:,1]-a[:,1]; normal = np.abs(dy)>1e-14
                f = np.divide(value-a[:,1],dy,out=np.zeros(len(tri)),where=normal)
                valid = normal & (f >= -1e-9) & (f <= 1+1e-9)
                if valid.any():
                    best = min(best,float(np.min(a[valid,0]+f[valid]*(b[valid,0]-a[valid,0]))))
                horizontal = (~normal) & (np.abs(a[:,1]-value)<1e-9)
                if horizontal.any():
                    best = min(best,float(a[horizontal,0].min()),float(b[horizontal,0].min()))
            if np.isfinite(best):
                out[k] = best
        return out.reshape(y.shape)


def coverage_diagnostics(xy, ground_z, road_z):
    """Describe missing ACTUAL surface support; never fill or reclassify it."""
    xy=np.asarray(xy,float);zg=np.asarray(ground_z,float);zr=np.asarray(road_z,float)
    _require(xy.shape==zg.shape+(2,) and zg.shape==zr.shape,'Coverage diagnostic shapes differ')
    missing=~(np.isfinite(zg)|np.isfinite(zr));points=xy[missing]
    bounds=None if not len(points) else [float(points[:,0].min()),float(points[:,0].max()),float(points[:,1].min()),float(points[:,1].max())]
    return dict(missing_xy_count=int(missing.sum()),missing_xy_bounds_m=bounds,
                missing_xy_examples_m=points[:24].tolist(),
                ground_finite_queries=int(np.isfinite(zg).sum()),road_finite_queries=int(np.isfinite(zr).sum()),
                both_finite_queries=int((np.isfinite(zg)&np.isfinite(zr)).sum()),
                missing_count_by_row=missing.sum(axis=1).tolist() if missing.ndim==2 else [],
                missing_count_by_column=missing.sum(axis=0).tolist() if missing.ndim==2 else [],
                policy='No nearest/extrapolated/bilinear height is substituted for missing physical support.')


def nearest_triangle_witness(sampler, points):
    """Read-only gap diagnosis against ALL bounded triangles, without hash bins.

    Closest XY edge points and their interpolated Z are witnesses only. They
    NEVER become sampled surface heights. A zero-distance witness identifies a
    sampler-lookup issue; positive distances describe unsupported XY separation.
    """
    points=np.asarray(points,float).reshape(-1,2)
    _require(len(points)<=16 and np.isfinite(points).all(),'At most 16 finite gap witnesses')
    result=[]
    for point in points:
        best=np.inf;record=None;contains=False
        for first in range(0,len(sampler.tri),32768):
            tri=sampler.tri[first:first+32768]
            a=tri[:,0,:2];u=tri[:,1,:2]-a;v=tri[:,2,:2]-a;d=point-a
            det=u[:,0]*v[:,1]-u[:,1]*v[:,0]
            s=(d[:,0]*v[:,1]-d[:,1]*v[:,0])/det;t=(u[:,0]*d[:,1]-u[:,1]*d[:,0])/det
            inside=(s>=0)&(t>=0)&(s+t<=1)
            if inside.any():
                k=int(np.flatnonzero(inside)[0]);contains=True;best=0.
                record=dict(distance_m=0.,nearest_xy_m=point.tolist(),edge_z_m=float(tri[k,0,2]+s[k]*(tri[k,1,2]-tri[k,0,2])+t[k]*(tri[k,2,2]-tri[k,0,2])),triangle_vertices_m=tri[k].tolist());break
            for edge in range(3):
                a,b=tri[:,edge],tri[:,(edge+1)%3];e=b[:,:2]-a[:,:2]
                n=np.sum(e*e,axis=1);f=np.divide(np.sum((point-a[:,:2])*e,axis=1),n,out=np.zeros(len(tri)),where=n>0)
                f=np.clip(f,0,1);q=a[:,:2]+f[:,None]*e;dist=np.sum((q-point)**2,axis=1);k=int(dist.argmin())
                if dist[k]<best:
                    best=float(dist[k]);record=dict(distance_m=float(np.sqrt(best)),nearest_xy_m=q[k].tolist(),edge_z_m=float(a[k,2]+f[k]*(b[k,2]-a[k,2])),triangle_vertices_m=tri[k].tolist())
        result.append(dict(query_xy_m=point.tolist(),exact_interior_hit=contains,**record))
    return result


def select_topmost(ground_z, road_z, road_owner=None, soil_owner=None):
    """Strict topmost ownership; an exact road/soil Z tie belongs to road."""
    ground, road = np.asarray(ground_z,float), np.asarray(road_z,float)
    _require(ground.shape == road.shape and not np.isinf(ground).any() and not np.isinf(road).any(), 'Matching heights may contain NaN gaps, never infinity')
    z = np.fmax(ground,road)
    _require(np.isfinite(z).all(), 'Current road/ground surface has unhandled XY gaps')
    pavement = np.isfinite(road) & (~np.isfinite(ground) | (road >= ground))
    kinds = np.ones(z.shape,np.uint8) if road_owner is None else np.asarray(road_owner,np.uint8)
    _require(kinds.shape == z.shape and np.all((kinds==1)|(kinds==2)|(kinds==3)), 'Road owner must identify base(1), native tile(2), or asphalt section(3)')
    soils=np.zeros(z.shape,np.uint8) if soil_owner is None else np.asarray(soil_owner,np.uint8)
    _require(soils.shape==z.shape and np.all((soils==0)|(soils==4)), 'Soil owner must identify ground(0) or section subgrade(4)')
    return z, pavement, np.where(pavement,kinds,soils).astype(np.uint8)


def include_section_support(ground_z,road_z,road_owner,section_asphalt_z,section_subgrade_z):
    """Topmost actual support, keeping road course and mineral subgrade distinct."""
    zg,zr,za,zs=(np.asarray(a,float) for a in (ground_z,road_z,section_asphalt_z,section_subgrade_z))
    _require(zg.shape==zr.shape==za.shape==zs.shape and not any(np.isinf(a).any() for a in (zg,zr,za,zs)), 'Matching actual layer heights required')
    road_kind=np.asarray(road_owner,np.uint8).copy()
    _require(road_kind.shape==zg.shape and np.all((road_kind==1)|(road_kind==2)), 'Original top-road owner required')
    asphalt_wins=np.isfinite(za)&(~np.isfinite(zr)|(za>zr))
    soil_wins=np.isfinite(zs)&(~np.isfinite(zg)|(zs>zg))
    road_kind[asphalt_wins]=3;soil_kind=np.where(soil_wins,4,0).astype(np.uint8)
    return np.fmax(zg,zs),np.fmax(zr,za),soil_kind,road_kind


def _mesh_sampler(obj, bounds, cfg, cell_m, section_layer=None):
    _require(obj is not None and obj.type == 'MESH', 'Expected current physical mesh object')
    _require(not obj.modifiers and obj.data.shape_keys is None, 'Evaluated mesh deformation is unsupported; do not sample an unevaluated substitute')
    mesh = obj.data
    _require(len(mesh.vertices) <= cfg.source_vertex_cap, 'Source vertex cap exceeded')
    co = np.empty((len(mesh.vertices),3),np.float32)
    mesh.vertices.foreach_get('co',co.ravel())
    matrix = np.asarray(obj.matrix_world,float)
    world = co.astype(float) @ matrix[:3,:3].T + matrix[:3,3]
    del co
    mesh.calc_loop_triangles()
    _require(len(mesh.loop_triangles) <= cfg.source_triangle_cap, 'Source triangle cap exceeded')
    triangles = np.empty((len(mesh.loop_triangles),3),np.int32)
    mesh.loop_triangles.foreach_get('vertices',triangles.ravel())
    if section_layer is not None:
        _require(obj.name==SECTION and section_layer in (0,1),'Only explicit current AC section layers are supported')
        attr=mesh.attributes.get('ac_section_layer')
        _require(attr is not None and attr.domain=='FACE' and attr.data_type=='INT','Actual AC section FACE layer attribution missing')
        layers=np.empty(len(mesh.polygons),np.int32);attr.data.foreach_get('value',layers)
        _require(np.all((layers==0)|(layers==1)),'Unknown actual AC section layer')
        parent=np.empty(len(mesh.loop_triangles),np.int32);mesh.loop_triangles.foreach_get('polygon_index',parent)
        triangles=triangles[layers[parent]==section_layer]
        del layers,parent
    parts = []; count = 0
    xmin,xmax,ymin,ymax = bounds
    for first in range(0,len(triangles),32768):
        ids = triangles[first:first+32768]
        xy = world[ids,:2]
        low,high = xy.min(1),xy.max(1)
        keep = ((high[:,0]>=xmin-1e-8)&(low[:,0]<=xmax+1e-8)&
                (high[:,1]>=ymin-1e-8)&(low[:,1]<=ymax+1e-8))
        parts.append(ids[keep]); count += int(keep.sum())
        _require(count <= cfg.local_triangle_cap, 'Bounded local triangle cap exceeded')
    local = np.concatenate(parts); del triangles,parts
    _require(len(local)>0,'No source triangles in bounded rectangle')
    used,inverse = np.unique(local,return_inverse=True)
    compact = world[used]; local = inverse.reshape(-1,3).astype(np.int32)
    del world,used,inverse
    fingerprint = hashlib.sha256(compact.tobytes()+local.tobytes()).hexdigest()
    result = PartialSurfaceSampler(compact,local,cell_m=cell_m,
        max_triangles=cfg.local_triangle_cap,max_bin_entries=cfg.bin_entry_cap,
        max_query_products=cfg.query_product_cap)
    result.report.update(object=obj.name, mesh=mesh.name, source_vertices=len(mesh.vertices),
                         source_loop_triangles=len(mesh.loop_triangles), local_geometry_sha256=fingerprint,
                         matrix_world=matrix.tolist(),section_layer=section_layer,
                         source_materials=[ma.name if ma else None for ma in mesh.materials])
    return result


def _sample_tiles(scene, xy, road_z):
    flat = np.asarray(xy,float).reshape(-1,2)
    z = np.asarray(road_z,float).ravel().copy(); owner = np.ones(len(z),np.uint8)
    queries = templates = tiles = 0; fingerprints = []; tile_records=[]; cache = {}
    xmin,ymin = flat.min(0); xmax,ymax = flat.max(0)
    for obj in scene.objects:
        if not obj.name.startswith(TILE_PREFIX):
            continue
        _require(obj.type == 'MESH' and not obj.modifiers and obj.data.shape_keys is None, 'Native tile must be an unevaluated physical mesh')
        m = np.asarray(obj.matrix_world,float)
        _require(np.max(abs(m[:2,:2]-np.eye(2)))<1e-7 and np.max(abs(m[:2,2]))<1e-7, 'Native tile XY transform contract changed')
        ox,oy = m[:2,3]
        if ox > xmax+1e-8 or ox+.25 < xmin-1e-8 or oy > ymax+1e-8 or oy+.25 < ymin-1e-8:
            continue
        local = flat-m[:2,3]
        take = (local[:,0]>=-1e-8)&(local[:,0]<=.25+1e-8)&(local[:,1]>=-1e-8)&(local[:,1]<=.25+1e-8)
        if not take.any():
            continue
        key = obj.data.name
        if key not in cache:
            _require(len(cache)<8,'Native-template cache cap exceeded')
            mesh = obj.data
            _require(len(mesh.vertices)==513*513 and len(mesh.polygons)==2*512*512, 'Native 512-square tile topology count changed')
            g = np.empty((513*513,3),np.float32); mesh.vertices.foreach_get('co',g.ravel()); g=g.reshape(513,513,3)
            axis = np.arange(513)*(.25/512)
            _require(np.allclose(g[:,:,0],axis[None,:],atol=1e-8,rtol=0) and np.allclose(g[:,:,1],axis[:,None],atol=1e-8,rtol=0), 'Native tile lattice changed')
            # Verify ACTUAL A-C topology once per shared template. Counts alone
            # cannot prove its diagonal matches the native height sampler.
            loops = np.empty(len(mesh.loops),np.int32); mesh.loops.foreach_get('vertex_index',loops)
            _require(len(loops)==6*512*512,'Native tile has nontriangular polygons')
            actual = loops.reshape(-1,3)
            a = (np.arange(512)[:,None]*513+np.arange(512)[None,:]).ravel()
            expected = np.concatenate((np.column_stack((a,a+1,a+514)),np.column_stack((a,a+514,a+513))))
            _require(np.array_equal(np.sort(actual,axis=1),np.sort(expected,axis=1)), 'Native tile A-C triangulation/order changed')
            fingerprints.append(dict(mesh=key,coordinate_sha256=hashlib.sha256(g.tobytes()).hexdigest(),topology_sha256=hashlib.sha256(loops.tobytes()).hexdigest()))
            cache[key]=g; templates+=1
        g=cache[key]; q=np.clip(local[take]/.25*512,0,512); ij=np.minimum(q.astype(int),511)
        f=q-ij; i,j=ij[:,0],ij[:,1]; fx,fy=f[:,0],f[:,1]
        a,b,c,d=g[j,i,2],g[j,i+1,2],g[j+1,i+1,2],g[j+1,i,2]
        h=np.where(fx>=fy,a*(1-fx)+b*(fx-fy)+c*fy,a*(1-fy)+c*fx+d*(fy-fx))
        h=local[take,0]*m[2,0]+local[take,1]*m[2,1]+h*m[2,2]+m[2,3]
        rows=np.flatnonzero(take); wins=(~np.isfinite(z[rows]))|(h>=z[rows])
        z[rows[wins]]=h[wins]; owner[rows[wins]]=2
        queries+=int(take.sum()); tiles+=1
        tile_records.append(dict(object=obj.name,xy_bounds_m=[float(ox),float(ox+.25),float(oy),float(oy+.25)],query_count=int(take.sum())))
    return z.reshape(road_z.shape),owner.reshape(road_z.shape),dict(native_tile_queries=queries,native_tiles_sampled=tiles,native_templates_read=templates,template_fingerprints=fingerprints,tile_support=tile_records)


def sample(scene, output_directory, config=None):
    """Write AN_FINAL_SURFACE.{npz,json}; return a serializable receipt.

    config is SampleConfig or a mapping of its fields. Production domain and
    6.25 mm spacing are fixed. All arrays are (Y,X); owner: 0 soil, 1 base road,
    2 native road, 3 asphalt section, 4 mineral subgrade. Ground/road NaNs
    separately mean that mesh has no XY hit; separate AC layer maps are stored.
    """
    started=time.perf_counter()
    cfg = config if isinstance(config,SampleConfig) else SampleConfig(**(config or {}))
    _require(tuple(cfg.bounds_m)==BOUNDS and cfg.spacing_m==SPACING,'AN production source domain/resolution is fixed')
    _require(0<cfg.local_triangle_cap<=1_000_000 and 0<cfg.bin_entry_cap<=4_000_000 and
             0<cfg.query_product_cap<=250_000 and 0<cfg.source_vertex_cap<=1_600_000 and
             0<cfg.source_triangle_cap<=3_000_000, 'Allocation limits may be lowered, never expanded')
    # Conservative simultaneous NumPy allocation envelope, with extra allowance
    # for Blender tessellation. Ground/road samplers are deliberately sequential.
    estimate=(cfg.source_vertex_cap*36 + cfg.source_triangle_cap*32 +
              cfg.local_triangle_cap*240 + cfg.bin_entry_cap*40 +
              cfg.query_product_cap*64 + 16_000_000)/(1024**2)
    _require(estimate<=cfg.estimated_extra_memory_cap_mib<=600.,'Estimated extra memory exceeds the 600 MiB hard budget')
    x,y=nested_axes(cfg.bounds_m,cfg.spacing_m);xx,yy=np.meshgrid(x,y);xy=np.stack((xx,yy),-1)
    out=Path(output_directory);out.mkdir(parents=True,exist_ok=True)
    fields=out/'AN_FINAL_SURFACE.npz';receipt=out/'AN_FINAL_SURFACE.json'
    _require(not fields.exists() and not receipt.exists(),'Refusing to overwrite a sampled source receipt')
    ground=_mesh_sampler(scene.objects.get(GROUND),cfg.bounds_m,cfg,.025)
    zg=ground.height(xy);ground_report=ground.report;del ground
    road=_mesh_sampler(scene.objects.get(ROAD),cfg.bounds_m,cfg,.0125)
    zr=road.height(xy);edge=road.left_edge(y);road_report=road.report;del road
    _require(np.isfinite(edge).all() and np.all(edge>cfg.bounds_m[0]+.025) and np.all(edge<cfg.bounds_m[1]-.025), 'Road edge is missing or truncated by the local source rectangle')
    zr,road_owner,tiles=_sample_tiles(scene,xy,zr)
    before_section=coverage_diagnostics(xy,zg,zr);section_maps=[];section_reports=[]
    for layer in (0,1):
        section=_mesh_sampler(scene.objects.get(SECTION),cfg.bounds_m,cfg,.0125,section_layer=layer)
        section_maps.append(section.height(xy));section_reports.append(section.report);del section
    soil_z,pavement_z,soil_owner,road_owner=include_section_support(zg,zr,road_owner,*section_maps)
    coverage=coverage_diagnostics(xy,soil_z,pavement_z)
    section_coverage=dict(missing_before_section=before_section['missing_xy_count'],
        missing_after_section=coverage['missing_xy_count'],missing_before_section_bounds_m=before_section['missing_xy_bounds_m'],
        missing_after_section_bounds_m=coverage['missing_xy_bounds_m'],
        previously_missing_supplied_by_actual_section=int(np.sum(~(np.isfinite(zg)|np.isfinite(zr))&(np.isfinite(soil_z)|np.isfinite(pavement_z)))),
        policy='Actual AC course layer 0 is pavement; actual FACE subgrade layer 1 is soil. Strict topmost height; no invented bridge, extrapolation, clast or particle support.')
    print('AN_CURRENT_SUPPORT_COVERAGE',json.dumps(section_coverage),flush=True)
    if coverage['missing_xy_count']:
        missing=~(np.isfinite(soil_z)|np.isfinite(pavement_z));points=xy[missing]
        diagnostic_path=out/'AN_INCOMPLETE_SURFACE.npz'
        np.savez_compressed(diagnostic_path,x_m=x,y_m=y,ground_z_m=zg,road_z_m=zr,
                            section_asphalt_z_m=section_maps[0],section_subgrade_z_m=section_maps[1],
                            valid_mask=~missing,missing_xy_m=points,road_edge_x_m=edge,
                            surface_schema=np.array('AN_INCOMPLETE_DIAGNOSTIC_ONLY'))
        details=dict(coverage=coverage,before_section_coverage=before_section,section_coverage=section_coverage,section=section_reports,ground=ground_report,road=road_report,tiles=tiles,
                     diagnostic_fields_path=str(diagnostic_path),filled_missing_points=False,
                     classification='Unresolved missing current physical support; diagnostic only, not an admissible event source')
        failure_path=out/'AN_SURFACE_GAPS.json';failure_path.write_text(json.dumps(details,indent=2)+'\n')
        print('AN_SURFACE_GAPS',json.dumps(coverage),flush=True)
        witness=points[np.unique(np.linspace(0,len(points)-1,min(16,len(points))).astype(int))]
        details['nearest_triangle_witnesses']={}
        for role,name,cell,layer in (('ground',GROUND,.025,None),('road',ROAD,.0125,None),('section_asphalt',SECTION,.0125,0),('section_subgrade',SECTION,.0125,1)):
            sampler=_mesh_sampler(scene.objects.get(name),cfg.bounds_m,cfg,cell,section_layer=layer)
            details['nearest_triangle_witnesses'][role]=nearest_triangle_witness(sampler,witness)
            del sampler
        details['other_named_support_meshes']=[dict(name=ob.name,vertices=len(ob.data.vertices),polygons=len(ob.data.polygons))
            for ob in scene.objects if ob.type=='MESH' and ob.name not in (GROUND,ROAD) and not ob.name.startswith(TILE_PREFIX)
            and any(word in ob.name.lower() for word in ('asphalt','shoulder','alluvial','road'))]
        failure_path.write_text(json.dumps(details,indent=2)+'\n')
        raise ValueError(f"{len(points)} current-surface XY gaps in {coverage['missing_xy_bounds_m']}; exact diagnostics saved to {failure_path}; no gap filled")
    z,pavement,owner=select_topmost(soil_z,pavement_z,road_owner,soil_owner)
    np.savez_compressed(fields,x_m=x,y_m=y,actual_surface_z_m=z,ground_z_m=zg,road_z_m=zr,
                        pavement=pavement,owner=owner,road_edge_x_m=edge,
                        section_asphalt_z_m=section_maps[0],section_subgrade_z_m=section_maps[1],
                        sampling_stage=np.array(cfg.stage_label),surface_schema=np.array('AN_CURRENT_PHYSICAL_V1'))
    report=dict(fields_path=str(fields),fields_sha256=hashlib.sha256(fields.read_bytes()).hexdigest(),
        module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),configuration=asdict(cfg),
        shape_yx=list(z.shape),queries=int(z.size),ground=ground_report,road=road_report,tiles=tiles,coverage=coverage,
        section=section_reports,section_coverage=section_coverage,before_section_coverage=before_section,
        soil_queries=int((~pavement).sum()),pavement_queries=int(pavement.sum()),
        owner_counts={str(k):int((owner==k).sum()) for k in range(5)},
        ownership='Strict highest actual road/ground Z; exact ties belong to road. Owner 0=ground, 1=road base, 2=native road tile, 3=actual asphalt section, 4=actual mineral subgrade.',
        road_edge='Leftmost actual current base-road crown triangle-union intersection at each Y, excluding the inclined section below the crown; no analytic planform.',
        surface='Current physical loop triangles after caller-applied AH/AC/AL and verified native 512-square A-C tile triangles.',
        old_Z_fields_read=False,scene_geometry_modified=False,materials_modified=False,
        estimated_extra_memory_mib=estimate,memory_estimate_is_measurement=False,
        limits='Bounded local surface diagnostic, including actual inclined AC section but excluding particles and anchored clasts. No evaluated scene or BVH. No claim to resolve sub-6.25 mm hydraulic relief or render visibility.',
        elapsed_s=time.perf_counter()-started)
    receipt.write_text(json.dumps(report,indent=2)+'\n')
    print('AN_FINAL_SURFACE_READY',json.dumps(report),flush=True)
    return report
