"""AQ source-only physical bank continuation over the complete visible 0..15 m.

Run AFTER existing AH/AC/AL/AI geometry, before new margin assembly. No asphalt edits, meshes, materials,
scene saves, random fields or new transport solve. The actual current ground
provides anchor heights; AP's unchanged connected historical reaches determine
where grading leaves exposure. Outside those reaches, soil is near flush.
The inherited scalloped asphalt XY boundary remains an explicit limitation.
"""
from dataclasses import dataclass
from types import SimpleNamespace
import gc
import time
import numpy as np
from context_mesh_refine_ab import SourceSampler, intersecting_triangles, _read
from metric_edge_strip_aa import TriangleSampler
from contact_bank_continuity_al import contained_vertex_mask, move_retained
from contact_triangle_clearance_al import _clip, _area
from road_margin_composition_ap import fields as history_fields

GROUND = 'Graded shoulder and alluvial plain -1'
ROAD = 'Crowned asphalt crust / longitudinal rise'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def smooth(t):
    t = np.clip(np.asarray(t, float), 0., 1.)
    return t*t*t*(t*(6*t-15)+10)


@dataclass(frozen=True)
class ContactSpec:
    y_min_m: float = -.35
    y_max_m: float = 15.65
    visible_y_min_m: float = 0.
    visible_y_max_m: float = 15.
    outer_x_m: float = -3.95
    outer_anchor_x_m: float = -3.80
    inner_anchor_x_m: float = -3.45
    right_x_m: float = -3.04
    clearance_m: float = .0008
    exposed_min_m: float = .006
    exposed_max_m: float = .024
    max_movement_m: float = .040
    max_abs_grade: float = .10
    max_local_triangles: int = 360_000
    extra_buffer_cap_mib: float = 250.

    @property
    def bounds(self):
        return self.outer_x_m, self.right_x_m, self.y_min_m, self.y_max_m

    def validate(self):
        require(self.visible_y_min_m == 0 and self.visible_y_max_m == 15,
                'AQ visible contact must cover all of y=0..15 m')
        require(-.6 <= self.y_min_m <= -.25 and 15.4 <= self.y_max_m <= 16.,
                'Transition collars must remain outside the visible interval')
        require(-4.1 <= self.outer_x_m < self.outer_anchor_x_m < self.inner_anchor_x_m <= -3.45,
                'Actual anchor span must lie outside AC reconstruction')
        require(.10 <= self.inner_anchor_x_m-self.outer_anchor_x_m <= .40,
                'Bounded physical anchor span required')
        require(self.right_x_m == -3.04 and .0004 <= self.clearance_m <= .002,
                'Unsupported contact domain or clearance')
        require(.004 <= self.exposed_min_m < self.exposed_max_m <= .028 and
                0 < self.max_movement_m <= .040 and 0 < self.max_abs_grade <= .10,
                'Physical bank limits exceeded')
        require(self.max_local_triangles <= 360_000 and self.extra_buffer_cap_mib <= 250,
                'Bounded buffers required')
        return self


def gate(xy, spec):
    p = np.asarray(xy); x, y = p[..., 0], p[..., 1]
    w = (smooth((x-spec.outer_x_m)/(spec.inner_anchor_x_m-spec.outer_x_m)) *
         smooth((y-spec.y_min_m)/(spec.visible_y_min_m-spec.y_min_m)) *
         smooth((spec.y_max_m-y)/(spec.y_max_m-spec.visible_y_max_m)))
    return np.where(x <= spec.right_x_m, w, 0.)


def slabs(spec):
    # Dense unchanged AC triangles require narrow slabs, without decimation.
    cuts = np.unique(np.r_[spec.y_min_m, 0., np.arange(.1, 2.0001, .1),
                           np.arange(2.5, 15.51, .5), spec.y_max_m])
    return list(zip(cuts[:-1], cuts[1:]))


def road_slab(co, tri, lo, hi, right_x):
    ids = intersecting_triangles(co, tri, (-3.30, right_x, lo-1e-5, hi+1e-5))
    t = tri[ids]; q = co[t, :2].astype(float)
    u, v = q[:, 1]-q[:, 0], q[:, 2]-q[:, 0]
    t = t[np.abs(u[:, 0]*v[:, 1]-u[:, 1]*v[:, 0]) > 1e-13]
    used, inverse = np.unique(t, return_inverse=True)
    return TriangleSampler(co[used], inverse.reshape(-1, 3), cell=.0125,
                           max_bucket_entries=500_000)


def anchor_profile(ground_sampler, road, ys, spec):
    """Actual source heights + existing connected chronology, without new noise."""
    edge_x = road.left_edge(ys)
    edge_z = road.sample(road.co[:, 2], np.c_[edge_x, ys])
    a = ground_sampler.height(np.c_[np.full(len(ys), spec.outer_anchor_x_m), ys])
    b = ground_sampler.height(np.c_[np.full(len(ys), spec.inner_anchor_x_m), ys])
    raw_grade = (b-a)/(spec.inner_anchor_x_m-spec.outer_anchor_x_m)
    grade = np.clip(raw_grade, -spec.max_abs_grade, spec.max_abs_grade)
    # Longitudinal derivative uses actual irregular source-Y knots.
    gy = np.gradient(b, ys) if len(ys) > 1 else np.zeros_like(b)
    chronology = history_fields(np.c_[np.full(len(ys), spec.inner_anchor_x_m), ys],
                                np.c_[grade, gy])
    channel = chronology['channel']
    raw = b + grade*(edge_x-spec.inner_anchor_x_m)
    available = np.clip(edge_z-raw, spec.exposed_min_m, spec.exposed_max_m)
    exposure = spec.clearance_m + channel*(available-spec.clearance_m)
    return np.c_[ys, edge_x, edge_z, b, grade, raw, exposure, channel, raw_grade]


def profile_targets(q, profile, spec):
    p = np.column_stack([np.interp(q[:, 1], profile[:, 0], profile[:, k])
                         for k in range(1, 9)])
    edge_x, edge_z, inner_z, grade, raw, exposure = p[:, :6].T
    transfer = smooth((q[:, 0]-spec.inner_anchor_x_m)/(edge_x-spec.inner_anchor_x_m))
    return inner_z + grade*(q[:, 0]-spec.inner_anchor_x_m) + (edge_z-exposure-raw)*transfer


def overlap_constraints(co, triangles, road, bounds, clearance_m=0., correction=None):
    """Every actual XY overlap polygon, all linear clearance extrema.

    If correction is supplied, accumulate a conservative downward correction
    on ALL three soil vertices. This is an actual facet constraint, not a
    vertex-only test. The final post-rounding audit is a separate full pass.
    """
    xmin, xmax, ymin, ymax = bounds
    box = np.array([[xmin,ymin],[xmax,ymin],[xmax,ymax],[xmin,ymax]])
    minimum = np.inf; polygons = vertices = bad = 0; area = 0.
    rlo, rhi = road.tri[:, :, :2].min(1), road.tri[:, :, :2].max(1)
    for ids in triangles:
        p = np.asarray(co[ids], float)
        lo, hi = p[:, :2].min(0), p[:, :2].max(0)
        if hi[0]<xmin or lo[0]>xmax or hi[1]<ymin or lo[1]>ymax or _area(p)<1e-14:
            continue
        for a,b in zip(box,np.roll(box,-1,axis=0)):
            p = _clip(p,a,b)
            if len(p)<3:
                break
        if len(p)<3:
            continue
        low, high = p[:, :2].min(0), p[:, :2].max(0)
        blo=np.floor((low-1e-10)/road.cell).astype(int)
        bhi=np.floor((high+1e-10)/road.cell).astype(int)
        candidates=set()
        for x in range(blo[0],bhi[0]+1):
            for y in range(blo[1],bhi[1]+1):
                candidates.update(road.bins.get((x,y),()))
        candidates=np.asarray(sorted(candidates),dtype=np.int32)
        candidates=candidates[np.all(rhi[candidates]>=low-1e-10,axis=1)&
                              np.all(rlo[candidates]<=high+1e-10,axis=1)]
        needed=0.
        for k in candidates:
            r=road.tri[k]
            signed=(r[1,0]-r[0,0])*(r[2,1]-r[0,1])-(r[1,1]-r[0,1])*(r[2,0]-r[0,0])
            r=r if signed>0 else r[::-1]; poly=p
            for a,b in zip(r,np.roll(r,-1,axis=0)):
                poly=_clip(poly,a,b)
                if len(poly)<3:
                    break
            overlap=_area(poly)
            if overlap<1e-14:
                continue
            d=poly[:,:2]-r[0,:2];u=r[1,:2]-r[0,:2];v=r[2,:2]-r[0,:2]
            det=u[0]*v[1]-u[1]*v[0]
            uu=(d[:,0]*v[1]-d[:,1]*v[0])/det;vv=(u[0]*d[:,1]-u[1]*d[:,0])/det
            height=r[0,2]+uu*(r[1,2]-r[0,2])+vv*(r[2,2]-r[0,2])
            lowgap=float(np.min(height-poly[:,2]))
            minimum=min(minimum,lowgap);polygons+=1;vertices+=len(poly);area+=overlap
            bad+=int(lowgap < -1e-7)
            needed=max(needed,clearance_m-lowgap)
        if correction is not None and needed>0:
            correction[ids]=np.maximum(correction[ids],needed+2e-7)
    return dict(overlap_polygons=polygons,overlap_vertices=vertices,
                overlap_area_m2=area,minimum_linear_mesh_clearance_m=minimum if polygons else None,
                penetrating_overlap_polygons=bad)


@dataclass
class ContactPlan:
    before: np.ndarray
    after: np.ndarray
    delta_m: np.ndarray
    local_triangles: np.ndarray
    sampler: object
    spec: ContactSpec
    report: dict

    def height_shift(self, xy):
        # AL's exact existing-particle adapter expects this bounded API.
        from approved_density_lod import _height
        plan=self
        class Surface:
            def height(self,q):
                try:
                    return plan.sampler.sample(plan.delta_m,q)
                except ValueError as error:
                    if any(s in str(error) for s in ('outside bounded support','coverage gap','outside actual source triangles')):
                        raise ValueError('contact queries leave exact local triangle patch') from error
                    raise
        return _height(Surface(),xy,allow_missing=True)


def plan_contact(ground_co, ground_triangles, road_co, road_triangles, spec=None):
    spec=(spec or ContactSpec()).validate()
    co, tri=np.asarray(ground_co),np.asarray(ground_triangles)
    require(co.ndim==2 and co.shape[1]==3 and np.isfinite(co).all(),'Finite ground required')
    require(len(co)<=2_000_000 and len(tri)<=3_600_000,'Source mesh allocation cap exceeded')
    require(np.issubdtype(co.dtype,np.floating) and tri.shape[1:]==(3,),'Actual source triangles required')
    a,b,c,d=spec.bounds
    local_ids=intersecting_triangles(co,tri,(a-.1,b+.1,c-.1,d+.1));local=tri[local_ids]
    require(len(local)<=spec.max_local_triangles,'Local actual ground triangle cap exceeded')
    anchor_ids=intersecting_triangles(co,local,(spec.outer_anchor_x_m-.04,spec.inner_anchor_x_m+.01,c-.05,d+.05))
    anchors=SourceSampler(co,local,anchor_ids,cell_m=.06,max_triangles=spec.max_local_triangles)
    allowed=contained_vertex_mask(co,local,spec.bounds)
    weight=gate(co[:,:2],spec); weight[~allowed]=0
    active=np.flatnonzero(weight>0)
    after=co.copy();profiles=[];clipped=0;peak_road_triangles=0
    for lo,hi in slabs(spec):
        rows=active[(co[active,1]>=lo)&(co[active,1]<=hi)]
        if not len(rows):
            continue
        ground_slab=local[intersecting_triangles(co,local,(-3.31,b,lo,hi))]
        right=max(-3.15,float(co[ground_slab,0].max(initial=-3.2))+.001)
        road=road_slab(road_co,road_triangles,lo,hi,right)
        peak_road_triangles=max(peak_road_triangles,len(road.triangles))
        # All local terrain knots plus actual road knots, not a copied edge equation.
        yy=road.co[:,1].astype(float)
        ys=np.unique(np.r_[lo,hi,co[rows,1].astype(float),yy[(yy>lo)&(yy<hi)]])
        ys=ys[np.r_[True,np.diff(ys)>1e-8]]
        profile=anchor_profile(anchors,road,ys,spec);profiles.append(profile)
        target=profile_targets(co[rows],profile,spec)
        requested=target-co[rows,2]
        bounded=np.clip(requested,-spec.max_movement_m,spec.max_movement_m)
        clipped+=int(np.count_nonzero(requested!=bounded))
        after[rows,2]=co[rows,2]+weight[rows]*bounded
    del anchors
    # Correct physical plane overlaps on the entire visible interval. Collars
    # may retain old exposure but are outside the promised 0..15 m result.
    correction=np.zeros(len(co),dtype=np.float64)
    audit_slices=[]
    for lo,hi in slabs(spec):
        if hi<=0 or lo>=15:
            continue
        lo,hi=max(0.,lo),min(15.,hi)
        ts=local[intersecting_triangles(co,local,(-3.31,b,lo,hi))]
        if not len(ts):
            continue
        right=max(-3.15,float(co[ts,0].max())+.001)
        road=road_slab(road_co,road_triangles,lo,hi,right)
        overlap_constraints(after,ts,road,(-3.30,b,lo,hi),spec.clearance_m,correction)
        audit_slices.append((lo,hi,right))
    require(not np.any((correction>0)&~allowed),'Clearance correction would escape physical bank collar')
    after[:,2]-=correction
    delta=after[:,2].astype(float)-co[:,2]
    require(np.max(np.abs(delta))<=spec.max_movement_m+1e-6,'Exact clearance exceeds physical movement cap')
    corrected_vertices=int(np.count_nonzero(correction));maximum_correction=float(correction.max(initial=0));del correction
    audits=[]
    for lo,hi,right in audit_slices:
        ts=local[intersecting_triangles(co,local,(-3.31,b,lo,hi))]
        road=road_slab(road_co,road_triangles,lo,hi,right)
        audits.append(overlap_constraints(after,ts,road,(-3.30,b,lo,hi)))
    exact={k:sum(r[k] for r in audits) for k in ('overlap_polygons','overlap_vertices','overlap_area_m2','penetrating_overlap_polygons')}
    minima=[r['minimum_linear_mesh_clearance_m'] for r in audits if r['minimum_linear_mesh_clearance_m'] is not None]
    exact.update(minimum_linear_mesh_clearance_m=min(minima) if minima else None,
                 roi_xy_m=[-3.30,b,0.,15.],method='All exact XY overlap polygon vertices; extrema of the actual linear road and soil facets',
                 post_float32_storage=True,excludes='Particles, section sidewalls and shader normal fields; no visible Y onset/fade exclusion')
    require(exact['penetrating_overlap_polygons']==0,'Exact visible bank/road audit failed')
    if minima:
        require(min(minima)>=spec.clearance_m-1e-6,'Final rounded triangle clearance is insufficient')
    profile=np.concatenate(profiles)
    # Compact source-delta sampler supports exact rigid body/origin re-seating.
    sampler=SourceSampler(co,local,np.arange(len(local)),cell_m=.035,
                          max_triangles=spec.max_local_triangles,max_bin_entries=1_500_000)
    visible=profile[(profile[:,0]>=0)&(profile[:,0]<=15)]
    report=dict(model='Continuous actual-triangle graded bank with exposure inherited from AP connected runoff chronology',
                bounds_xy_m=list(spec.bounds),visible_y_m=[0.,15.],changed_vertices=int(np.count_nonzero(delta)),
                vertex_movement_range_m=[float(delta.min(initial=0)),float(delta.max(initial=0))],
                clipped_requested_vertices=clipped,exact_triangle_clearance=exact,
                overlap_constraint_corrected_vertices=corrected_vertices,maximum_facet_correction_m=maximum_correction,
                target_exposure_range_m=[float(visible[:,6].min()),float(visible[:,6].max())],
                near_flush_profile_fraction=float(np.mean(visible[:,6]<=.0015)),
                exposed_profile_fraction=float(np.mean(visible[:,6]>=.004)),
                source_grade_clipped_samples=int(np.count_nonzero(profile[:,4]!=profile[:,8])),
                local_ground_triangles=len(local),peak_road_slab_triangles=peak_road_triangles,
                existing_topology_unchanged=True,world_xy_unchanged=True,original_asphalt_unchanged=True,
                exact_original_asphalt_world_xy_phase_m=.25,original_materials_and_prototype_shapes_unchanged=True,
                new_meshes=0,new_particles=0,periodic_or_random_edge_pattern=False,
                AH_field_extrapolation=False,sediment_mass_conservation_claim=False,
                limits='Actual terrain anchors include existing AH/AC/AL history, with AP reach exposure as an authored geometric interpretation. '
                       'No fresh erosion solve. Original asphalt planform, including inherited scallops, remains unchanged. '
                       'Near-flush target is 0.8 mm; actual faceted contact may be lower after exact clearance correction. '
                       'No claim of particle-footprint collision clearance or automatic visual acceptance.')
    return ContactPlan(co,after,delta,local,sampler,spec,report)


def rotate_normals_in_place(mesh, plan, normals):
    """Same shortest-arc detail transport as AH, without a second full corner buffer."""
    active=np.any(np.abs(plan.delta_m[plan.local_triangles])>1e-12,axis=1)
    tri=plan.local_triangles[active]
    if not len(tri):
        return dict(changed_corner_normals=0)
    ids,iv=np.unique(tri,return_inverse=True);t=iv.reshape(-1,3)
    def broad(co):
        out=np.zeros((len(ids),3))
        for first in range(0,len(tri),8192):
            v=co[tri[first:first+8192]].astype(float)
            face=np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0])
            for k in range(3):
                np.add.at(out,t[first:first+8192,k],face)
        length=np.linalg.norm(out,axis=1);good=length>1e-15
        out[good]/=length[good,None];out[~good]=[0,0,1]
        return out
    old,new=broad(plan.before),broad(plan.after)
    axis=np.cross(old,new);dot=np.sum(old*new,axis=1)
    require(np.all(dot>-.5),'Unexpected near-reversal of bank normal')
    loops=_read(mesh.loops,'vertex_index',1,np.int32);changed=0
    for first in range(0,len(loops),32768):
        q=loops[first:first+32768];pos=np.searchsorted(ids,q)
        rows=np.flatnonzero(pos<len(ids));rows=rows[ids[pos[rows]]==q[rows]]
        ix=pos[rows];dst=first+rows;v=normals[dst].astype(float)
        cross=np.cross(axis[ix],v)
        v=v+cross+np.cross(axis[ix],cross)/(1+dot[ix,None])
        v/=np.linalg.norm(v,axis=1)[:,None];normals[dst]=v;changed+=len(dst)
    mesh.normals_split_custom_set(normals)
    return dict(changed_corner_normals=changed,policy='Preserved pre-edit corner detail, shortest-arc rotation by actual old/new facet normals; one full corner buffer',maximum_broad_rotation_degrees=float(np.rad2deg(np.arccos(np.clip(dot,-1,1))).max()))


def apply(scene, config=None, output_directory=None):
    """In-memory adapter before new margin assembly; caller owns persistence."""
    started=time.monotonic();config=config or {};spec=(config.get('spec') or ContactSpec()).validate()
    ground,road=scene.objects[GROUND],scene.objects[ROAD]
    require(not ground.modifiers and ground.data.shape_keys is None and ground.data.users==1,'Singly owned raw ground required')
    for ob in (ground,road):
        require(np.allclose(np.asarray(ob.matrix_world),np.eye(4),atol=1e-9,rtol=0),'Identity terrain/road transforms required')
    mesh=ground.data;mesh.calc_loop_triangles();road.data.calc_loop_triangles()
    # Conservative peak Python/NumPy buffer allowance; Blender allocations and
    # pre-existing scene storage are outside this explicit added-buffer budget.
    estimate=max(
        len(mesh.vertices)*40 + len(mesh.loop_triangles)*12 +
        len(road.data.vertices)*12 + len(road.data.loop_triangles)*12 +
        spec.max_local_triangles*120 + 16*1024**2,
        len(mesh.vertices)*32 + len(mesh.loops)*16 +
        spec.max_local_triangles*120 + 20*1024**2)
    require(estimate/1024**2<spec.extra_buffer_cap_mib,'AQ added-buffer estimate exceeds 250 MiB; refuse before extraction')
    co=_read(mesh.vertices,'co',3);tri=_read(mesh.loop_triangles,'vertices',3,np.int32)
    rc=_read(road.data.vertices,'co',3);rt=_read(road.data.loop_triangles,'vertices',3,np.int32)
    plan=plan_contact(co,tri,rc,rt,spec);del tri,rc,rt;gc.collect()
    normals=_read(mesh.corner_normals,'vector',3)
    mesh.vertices.foreach_set('co',plan.after.ravel());mesh.update()
    normal_report=rotate_normals_in_place(mesh,plan,normals)
    del normals;gc.collect()
    movement,roots=move_retained(scene,plan)
    # AP's true shared-mesh instances need only exact rigid origin translations.
    extra=[]
    for name in ('AP graded margin / exact metric lag instances',):
        ob=scene.objects.get(name)
        if ob is None:
            continue
        import prepare_physical_lenses as legacy
        before=legacy.read_coordinates(ob.data);world=legacy.world_coordinates(ob,before)
        g=gate(world[:,:2],spec);rows=np.flatnonzero(g>0);shift=np.zeros(len(before))
        dz=plan.height_shift(world[rows,:2]);valid=np.isfinite(dz);shift[rows[valid]]=dz[valid]
        legacy.write_world_z(ob,before,shift)
        extra.append(dict(object=name,moved_origins=int(np.count_nonzero(shift)),unchanged_prototype_shape_scale_materials=True))
    report=dict(plan.report,normals=normal_report,moved_existing=movement,moved_roots=roots,
                moved_AP_instances=extra,estimated_peak_added_buffer_mib=estimate/1024**2,
                elapsed_seconds=time.monotonic()-started,scene_assigned=True)
    del plan,co;gc.collect()
    print('CONTINUOUS_CONTACT_AQ',report,flush=True)
    return report
