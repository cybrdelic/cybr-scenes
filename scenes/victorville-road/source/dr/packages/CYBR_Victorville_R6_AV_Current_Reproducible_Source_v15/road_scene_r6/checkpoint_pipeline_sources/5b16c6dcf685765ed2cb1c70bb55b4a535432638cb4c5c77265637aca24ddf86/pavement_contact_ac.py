"""AC: bounded pavement section and supporting shoulder, source-only adapter.

No Blender import until prepare_contact(), no scene assignment, save or render.
Use with the ORIGINAL coarse road/ground and the unassigned AA strip result::

    spec = ContactSpec()
    result = prepare_edge_strip(road, height_path,
        boundary_builder=boundary_builder(field, spec))
    contact = prepare_contact(scene, result, spec=spec)
    # Parent validates, trims the old wall over y=0..2, then assigns both meshes.
    # Do NOT also call AA.fill_soil_gap or retain an old AA contact overlay.
    # Re-seat existing shoulder particles with contact['ground_delta'] before
    # visual acceptance. This adapter does not move unrelated scene objects.

The 24 mm surface course / 38 mm section are explicit diagnostic assumptions,
not measurements of Victorville. Most of the section is buried by banked soil;
finite angular erosion sectors expose 8--32 mm, sometimes including subgrade.
The original top material, grain source, scale, coordinates and stripe are not
edited. Newly constructed SUBSURFACE clasts use the approved 2.5--7.5 mm grading,
not semantic grain identities or enlarged/repositioned top-surface crowns.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from metric_edge_strip_aa import (TriangleSampler, clip_source, zipper,
                                 interpolate, _read, _attributes)

GROUND = 'Graded shoulder and alluvial plain -1'
WALL = 'Broken exposed asphalt edge -1'


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _smooth(x):
    t = np.clip(np.asarray(x), 0., 1.)
    return t*t*(3.-2.*t)


def _hash(i, salt=0):
    x = np.asarray(i, dtype=np.uint64) ^ np.uint64(salt)
    with np.errstate(over='ignore'):
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xbf58476d1ce4e5b9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94d049bb133111eb)
        x ^= x >> np.uint64(31)
    return (x >> np.uint64(11)).astype(float) / float(1 << 53)


@dataclass(frozen=True)
class ContactSpec:
    bounds_y_m: tuple = (0., 2.)
    outer_x_m: float = -3.43
    source_right_x_m: float = -3.04
    bank_clearance_m: float = .0008
    surface_course_m: float = .024
    section_depth_m: float = .038
    max_erosion_m: float = .032
    max_structural_loss_m: float = .010
    max_total_recession_m: float = .025
    # Finite independently shaped fractures, not a periodic/noise perimeter.
    # Each tuple is (start_y, end_y, peak_exposure_m, structural_loss_fraction).
    sectors: tuple = ((.145, .365, .027, .80), (.585, .735, .019, .60),
                      (1.025, 1.285, .032, 1.), (1.625, 1.775, .023, .70))
    ground_spacing_m: float = .004
    collar_m: float = .002
    end_fade_m: float = .040
    max_patch_vertices: int = 170000
    max_particles: int = 1800
    seed: int = 381721
    support_profile: object = None

    def validate(self):
        _require(tuple(self.bounds_y_m) == (0., 2.), 'AC supports only y=0..2 m')
        _require(-3.50 <= self.outer_x_m <= -3.36, 'Use a narrow actual shoulder band')
        _require(-3.06 <= self.source_right_x_m <= -3.02, 'Unsupported shoulder cut extent')
        _require(.0004 <= self.bank_clearance_m <= .002, 'Bank clearance must be 0.4--2 mm')
        _require(.020 <= self.surface_course_m <= .028, 'Diagnostic surface course must be 20--28 mm')
        _require(.034 <= self.section_depth_m <= .045, 'Section must be 34--45 mm deep')
        _require(.018 <= self.max_erosion_m <= .034 < self.section_depth_m,
                 'Erosion must expose a shallow section with buried support below it')
        _require(0 <= self.max_structural_loss_m <= .010 and self.max_total_recession_m == .025,
                 'Structural loss must respect AA 25 mm total recession cap')
        _require(.002 <= self.ground_spacing_m <= .006, 'Ground grid must resolve 2--6 mm')
        _require(.001 <= self.collar_m <= .003 and .025 <= self.end_fade_m <= .060,
                 'Use bounded collar and end transitions')
        _require(5000 <= self.max_patch_vertices <= 200000 and 1 <= self.max_particles <= 2500,
                 'Allocation cap exceeded')
        end = 0.
        for a,b,depth,loss in self.sectors:
            _require(end + .035 < a < b < 1.965 and .08 <= b-a <= .32,
                     'Erosion sectors must be separated and finite')
            _require(.008 <= depth <= self.max_erosion_m and 0 <= loss <= 1,
                     'Invalid erosion depth or structural-loss fraction')
            end = b
        _require(sum(b-a for a,b,_,_ in self.sectors) < .95,
                 'More than half the edge must remain soil-supported')
        return self


def sector_fields(y, spec=None):
    """Finite fracture polygons with centimeter-scale angular shoulders.

    No wavelength/grain-size change and no sine/noise displacement. Corners are
    linearly interpolated fracture breakpoints, different in every sector.
    """
    spec = (spec or ContactSpec()).validate()
    y = np.asarray(y, float)
    _require(np.isfinite(y).all(), 'Finite world Y required')
    if spec.support_profile is not None:
        result = spec.support_profile.sample(y)
        for key in ('exposure_m','structural_loss_m','sector_id'):
            _require(np.asarray(result[key]).shape == y.shape and np.isfinite(result[key]).all(), 'Invalid explicit bank profile')
        _require(np.all(result['exposure_m'] >= spec.bank_clearance_m-1e-12) and np.all(result['exposure_m'] <= spec.max_erosion_m+1e-12), 'Explicit bank exposure exceeds existing cap')
        _require(np.all(result['structural_loss_m'] == 0), 'Terrain-derived bank profile cannot manufacture structural road loss')
        return result
    exposure = np.full(y.shape, spec.bank_clearance_m)
    recession = np.zeros(y.shape)
    sector = np.zeros(y.shape, np.int32)
    base_u = np.array([0., .10, .23, .37, .52, .68, .82, .93, 1.])
    patterns = np.array([[0., .46, .78, .58, 1., .82, .56, .22, 0.],
                         [0., .34, .83, 1., .65, .79, .47, .31, 0.],
                         [0., .43, .61, .93, .74, 1., .63, .19, 0.],
                         [0., .27, .74, .58, 1., .70, .81, .29, 0.]])
    for k,(a,b,depth,loss) in enumerate(spec.sectors):
        p = np.interp(y, a+(b-a)*base_u, patterns[k % 4], left=0., right=0.)
        exposure += p*(depth-spec.bank_clearance_m)
        # Broad structural fractures remain distinct from fine AA crown loss.
        recession += p*spec.max_structural_loss_m*loss
        sector[(y > a) & (y < b)] = k+1
    return dict(exposure_m=exposure, structural_loss_m=recession, sector_id=sector)


@dataclass
class ContactBoundary:
    micro: object
    old_edge: object
    spec: ContactSpec
    receipt: dict

    def x_edge(self, y):
        y = np.asarray(y, float)
        return self.micro.x_edge(y)

    __call__ = x_edge


def boundary_builder(field, spec=None):
    """Callable for AA.prepare_edge_strip(boundary_builder=...).

    AA crowns are segmented at the finite structural fracture's location, not
    translated from their old location. Total recession is <=10+15=25 mm.
    """
    spec = (spec or ContactSpec()).validate()
    def build(old_edge, y_bounds):
        _require(np.allclose(y_bounds, spec.bounds_y_m, atol=1e-7, rtol=0),
                 'Mismatched road/section diagnostic bounds')
        def fractured(y):
            return old_edge(y) + sector_fields(y, spec)['structural_loss_m']
        micro = field.project(fractured, y_bounds, side=-1)
        probe = np.linspace(*spec.bounds_y_m, 4001)
        _require(np.max(micro.x_edge(probe)-old_edge(probe)) <= .02500001,
                 'Total fracture recession exceeds the unchanged AA cap')
        receipt = dict(micro.receipt, structural_fractures='Finite angular erosion sectors',
                       structural_loss_cap_m=spec.max_structural_loss_m,
                       total_recession_cap_m=spec.max_total_recession_m,
                       top_grain_scale_modified=False, sidewall_is_separate=True)
        return ContactBoundary(micro, old_edge, spec, receipt)
    return build


@dataclass
class SectionGeometry:
    y: np.ndarray
    top: np.ndarray
    wall_vertices: np.ndarray
    wall_faces: np.ndarray
    wall_asphalt_share: np.ndarray
    wall_layer: np.ndarray
    ground_contact: np.ndarray
    layer_depth: np.ndarray
    layer_x: np.ndarray
    spec: ContactSpec
    report: dict

    def top_at(self, y):
        y = np.asarray(y, float)
        _require(np.all((y >= self.y[0]-1e-9) & (y <= self.y[-1]+1e-9)),
                 'Section query outside actual road boundary')
        return np.stack([np.interp(y, self.y, self.top[:,i]) for i in range(3)], -1)

    def wall_x_exact(self,y,z):
        y,z=np.broadcast_arrays(np.asarray(y,float),np.asarray(z,float))
        shape=y.shape;query=np.column_stack((y.ravel(),z.ravel()))
        return self.exact_wall_sampler.sample(self.wall_vertices[:,0],query).reshape(shape)

    def wall_x(self, y, depth):
        y,depth = np.broadcast_arrays(np.asarray(y, float), np.asarray(depth,float))
        # Bilinear interpolation is for clast contact queries only. Mesh facets
        # are separately checked; embedded fraction tolerates <0.5mm faceting.
        cols = self.layer_depth.shape[1]
        d = np.stack([np.interp(y, self.y, self.layer_depth[:,j]) for j in range(cols)], -1)
        x = np.stack([np.interp(y, self.y, self.layer_x[:,j]) for j in range(cols)], -1)
        j = np.clip(np.sum(depth[...,None] >= d, axis=-1)-1, 0, cols-2)
        lo = np.take_along_axis(d, j[...,None], -1)[...,0]
        hi = np.take_along_axis(d, (j+1)[...,None], -1)[...,0]
        f = np.clip((depth-lo)/(hi-lo), 0, 1)
        return ((1-f)*np.take_along_axis(x,j[...,None],-1)[...,0]
                + f*np.take_along_axis(x,(j+1)[...,None],-1)[...,0])


def _strip_faces(rows, cols, *, outward=False):
    q = (np.arange(rows-1)[:,None]*cols + np.arange(cols-1)[None,:]).ravel()
    a = np.column_stack((q, q+1, q+cols+1))
    b = np.column_stack((q, q+cols+1, q+cols))
    # Alternating diagonals avoid one directional run of slender triangles.
    flip = ((np.arange(rows-1)[:,None]+np.arange(cols-1)) % 2).ravel().astype(bool)
    a[flip] = np.column_stack((q[flip], q[flip]+1, q[flip]+cols))
    b[flip] = np.column_stack((q[flip]+1,q[flip]+cols+1,q[flip]+cols))
    f = np.stack((a,b),1).reshape(-1,3)
    return f[:,::-1] if outward else f


def build_section(top_edge_xyz, spec=None, *, base_edge_xyz=None):
    """Exact crown seam; crown chips terminate within 4 mm of original datum.

    base_edge_xyz is the actual original AA old_edge_xyz, before relief/ravel.
    Omission retains the top as a synthetic fallback for backwards-compatible
    pure fixtures; prepare_contact always supplies the actual original datum.
    """
    spec = (spec or ContactSpec()).validate()
    top = np.asarray(top_edge_xyz, float)
    _require(top.ndim == 2 and top.shape[1] == 3 and 20 <= len(top) <= 10000,
             'Supply the actual ordered AA road boundary (20--10000 vertices)')
    _require(np.isfinite(top).all() and np.all(np.diff(top[:,1]) > 0),
             'Road seam must be finite and strictly increasing in Y')
    _require(np.allclose(top[[0,-1],1],spec.bounds_y_m,atol=1e-7,rtol=0),
             'Use the full y=0..2 road boundary including exact endpoint joins')
    y = top[:,1]
    actual_base=base_edge_xyz is not None
    if actual_base:
        old=np.asarray(base_edge_xyz,float)
        _require(old.ndim==2 and old.shape[1]==3 and len(old)>=2 and np.isfinite(old).all(),
                 'Original road edge must be finite ordered XYZ')
        _require(np.all(np.diff(old[:,1])>0) and old[0,1]<=y[0]+1e-7 and old[-1,1]>=y[-1]-1e-7,
                 'Original edge must cover the complete actual crown seam')
        base=np.column_stack([np.interp(y,old[:,1],old[:,k]) for k in range(3)])
        bulk_x=base[:,0]+sector_fields(y,spec)['structural_loss_m']
    else:
        base=top.copy();bulk_x=top[:,0].copy()
    crown_x=top[:,0]-bulk_x;crown_z=top[:,2]-base[:,2]
    _require(np.max(abs(crown_x))<=.026 and np.max(abs(crown_z))<=.008,
             'Crown/source-edge mismatch exceeds the bounded original-source contract')
    transfer_m=.004
    # Facet breakpoints follow metric aggregate lengths; only section offsets
    # change, and they vanish exactly at the original top boundary.
    knots = np.linspace(0,2,251)
    breakage = np.interp(y, knots, .0014*(_hash(np.arange(251),spec.seed)-.5))
    course = spec.surface_course_m + np.interp(y,knots,.002*(_hash(np.arange(251),19)-.5))
    # Explicit 4 mm join row: interpolation cannot carry a residual crown
    # offset down to the next 9 mm bulk layer.
    nominal_dep = np.column_stack((np.zeros(len(y)),np.full(len(y),.002),
        np.full(len(y),transfer_m),course*.39,course*.66,course,
        np.full(len(y),spec.section_depth_m)))
    # Crown-scale loss belongs to the thin broken skin, not to vertical ribs
    # through the whole course. Deep coordinates derive only from the original
    # edge, finite structural fractures and small independent section facets.
    transfer=1.-_smooth(nominal_dep/transfer_m)
    dep=nominal_dep+crown_z[:,None]*(1.-transfer)
    course=dep[:,-2]
    offsets = np.array([0., .0003, .0007, .0020, .0012, .0025, -.0006])
    amp = np.array([0., .25, .5, 1., .6, .8, .3])
    xx = bulk_x[:,None] + offsets + breakage[:,None]*amp + crown_x[:,None]*transfer
    xx[:,0]=top[:,0]
    sec = SectionGeometry(y,top.copy(),None,None,None,None,np.empty_like(top),dep,xx,spec,{})
    exposure_nominal = sector_fields(y,spec)['exposure_m']
    exposure = exposure_nominal+crown_z*_smooth(exposure_nominal/transfer_m)
    sec.ground_contact = np.column_stack((sec.wall_x(y,exposure),y,top[:,2]-exposure))
    # Insert the actual soil-contact line into the wall topology. Separate
    # monotonic zippers above and below it prevent a contact segment crossing
    # an unsplit wall facet, even where erosion crosses a material interface.
    vv=[];share=[];above=[];below=[];pa=[];pb=[];topids=[];contactids=[]
    for i in range(len(y)):
        depths=np.unique(np.r_[dep[i],exposure[i]])
        row=np.arange(len(vv),len(vv)+len(depths),dtype=np.int32)
        x=np.interp(depths,dep[i],xx[i])
        vv.extend(np.column_stack((x,np.full(len(depths),y[i]),top[i,2]-depths)))
        share.extend(np.clip((dep[i,-1]-depths)/(dep[i,-1]-course[i]),0,1))
        a=depths<=exposure[i];b=depths>=exposure[i]
        above.append(row[a]);below.append(row[b]);pa.append(depths[a]/exposure[i])
        pb.append((depths[b]-exposure[i])/(dep[i,-1]-exposure[i]))
        topids.append(row[0]);contactids.append(row[np.argmin(abs(depths-exposure[i]))])
    ff=[]
    for i in range(len(y)-1):
        ff.extend(zipper(above[i],above[i+1],pa[i],pa[i+1]))
        ff.extend(zipper(below[i],below[i+1],pb[i],pb[i+1]))
    vv=np.asarray(vv,float);ff=np.asarray(ff,np.int32)
    # The zipper convention here points to positive X; reverse to the exposed
    # negative-X side. Every y interval has strictly descending layer depth.
    ff=ff[:,::-1]
    layer=(vv[ff,2].mean(1)<np.interp(vv[ff,1].mean(1),y,top[:,2]-course)).astype(np.int32)
    sec.wall_vertices=vv;sec.wall_faces=ff;sec.wall_asphalt_share=np.asarray(share);sec.wall_layer=layer
    sec.top_vertex_ids=np.asarray(topids);sec.contact_vertex_ids=np.asarray(contactids)
    sec.base_edge=base;sec.nominal_layer_depth=nominal_dep
    sec.exact_wall_sampler=TriangleSampler(vv[:,[1,2,0]],ff,cell=.008,max_bucket_entries=250000)
    a = vv[ff]
    cross = np.cross(a[:,1]-a[:,0],a[:,2]-a[:,0])
    _require(np.all(np.linalg.norm(cross,axis=1)>1e-12), 'Degenerate cross-section triangle')
    # Each row is ordered top-to-bottom, so no vertical triangle folding.
    _require(np.all(np.diff(dep,axis=1)>0), 'Cross-section layers crossed')
    sec.report = dict(top_seam_exact=np.array_equal(vv[sec.top_vertex_ids],top),
        assumed_surface_course_m=spec.surface_course_m, buried_section_depth_m=spec.section_depth_m,
        bulk_edge_from_actual_source=actual_base,crown_transfer_depth_m=transfer_m,
        crown_bulk_join_below_top_range_m=[float(np.min(transfer_m+crown_z)),float(np.max(transfer_m+crown_z))],
        crown_lateral_microgeometry_extruded_through_course=False,
        maximum_crown_to_bulk_lateral_m=float(np.max(abs(crown_x))),
        exposure_range_m=[float(exposure.min()),float(exposure.max())],
        supported_length_fraction=float(np.mean(exposure<=.002)),
        exposed_subgrade_fraction=float(np.mean(exposure>course)),
        wall_faces=len(ff), continuous_visible_vertical_ribbon=None if spec.support_profile is not None else False,
        nominal_exposure_over2mm_entire_length=bool(np.all(exposure>.002)),
        explicit_bank_profile=spec.support_profile is not None,
        wall_under_soil_hidden=True, exact_soil_contact_is_wall_edge=True, top_material_or_stripe_modified=False,
        interpretation='Diagnostic shallow weathered surface course, not measured site stratigraphy')
    return sec


@dataclass
class ParticleGeometry:
    vertices: np.ndarray
    faces: np.ndarray
    mineral: np.ndarray
    particle_id: np.ndarray
    centers: np.ndarray
    diameter_m: np.ndarray
    report: dict


_ICO_FACES = np.array([(0,11,5),(0,5,1),(0,1,7),(0,7,10),(0,10,11),
    (1,5,9),(5,11,4),(11,10,2),(10,7,6),(7,1,8),(3,9,4),(3,4,2),
    (3,2,6),(3,6,8),(3,8,9),(4,9,5),(2,4,11),(6,2,10),(8,6,7),(9,8,1)],np.int32)


def build_embedded_particles(section):
    """Packed angular subsurface clasts; every accepted clast crosses the wall.

    Bounding spheres do not overlap. Centers are inside the section, top faces
    stay below actual pavement, and every clast has exterior and buried points.
    No freestanding scatter is made. Material colors are diagnostic mineral
    colors; these are not claimed to be original top-grain semantic geometry.
    """
    spec=section.spec; rng=np.random.default_rng(spec.seed)
    phi=(1+np.sqrt(5))/2
    ico=np.array([(-1,phi,0),(1,phi,0),(-1,-phi,0),(1,-phi,0),
                  (0,-1,phi),(0,1,phi),(0,-1,-phi),(0,1,-phi),
                  (phi,0,-1),(phi,0,1),(-phi,0,-1),(-phi,0,1)],float)
    ico/=np.linalg.norm(ico,axis=1).max()
    vertices=[]; faces=[]; colors=[]; pids=[]; centers=[]; diameters=[]
    bins={}; bin_m=.008; accepted=[]; buried=[]
    # Bounded random sequential packing in the actual exposed section only.
    for _ in range(18000):
        if len(centers)>=spec.max_particles:break
        y=float(rng.uniform(.04,1.96)); exposure=float(np.interp(y,section.y,section.top[:,2]-section.ground_contact[:,2]))
        if exposure<.004:continue
        diameter=float(rng.uniform(.0025,.0075));r=diameter/2
        if exposure<1.9*r:continue
        depth=float(rng.uniform(1.15*r, exposure+.12*r))
        by,bz=int(y/bin_m),int(depth/bin_m)
        neighbors=[j for iy in range(by-1,by+2) for iz in range(bz-2,bz+3)
                   for j in bins.get((iy,iz),())]
        if any((y-accepted[j][0])**2+(depth-accepted[j][1])**2 < (r+accepted[j][2])**2
               for j in neighbors):continue
        top=section.top_at(np.array([y]))[0]
        wall=float(section.wall_x(y,depth)); center=np.array([wall+.30*r,y,top[2]-depth])
        if any(np.linalg.norm(center-centers[j]) < r+accepted[j][2] for j in neighbors):continue
        q,_=np.linalg.qr(rng.normal(size=(3,3)))
        if np.linalg.det(q)<0:q[:,0]*=-1
        shape=ico*rng.uniform(.81,1.,(12,1))
        shape=shape@q.T;shape*=r/np.linalg.norm(shape,axis=1).max()
        v=shape+center
        vt=section.top_at(v[:,1]); vd=vt[:,2]-v[:,2]
        bottom=np.interp(v[:,1],section.y,section.layer_depth[:,-1])
        if np.any(vd<.00025) or np.any(vd>bottom-.001):continue
        inward=v[:,0]-section.wall_x_exact(v[:,1],v[:,2])
        if not (inward.min()<-.15*r and inward.max()>.80*r):continue
        if center[0]<=section.wall_x_exact(center[1],center[2]):continue
        # An inside vertex is the physical anchor; no visible clast floats.
        n=len(centers);base=12*n;vertices.extend(v);faces.extend(_ICO_FACES+base)
        mineral=np.array([[.17,.165,.151,1.],[.105,.102,.094,1.],
                          [.235,.222,.192,1.],[.135,.143,.142,1.]])[int(rng.integers(4))]
        if depth>spec.surface_course_m:mineral[:3]*=np.array([1.08,1.0,.88])
        colors.extend(np.tile(mineral,(12,1)));pids.extend([n]*12)
        centers.append(center);diameters.append(diameter);buried.append(inward.max())
        accepted.append((y,depth,r));bins.setdefault((by,bz),[]).append(n)
    vv=np.asarray(vertices,float).reshape(-1,3); ff=np.asarray(faces,np.int32).reshape(-1,3)
    return ParticleGeometry(vv,ff,np.asarray(colors,float).reshape(-1,4),
        np.asarray(pids,np.int32),np.asarray(centers,float).reshape(-1,3),np.asarray(diameters),
        dict(count=len(centers),diameter_bounds_m=[.0025,.0075],vertices=len(vv),faces=len(ff),
             nonoverlapping_bounding_spheres=True,all_clasts_intersect_pavement=True,
             all_clasts_below_actual_crown=True,free_floating_scatter=False,
             minimum_internal_anchor_m=float(min(buried)) if buried else None,
             provenance='New packed subsurface fracture clasts at approved grading; top material untouched'))


def _near_triangles(co,tri,bounds):
    a,b,c,d=bounds;out=[]
    for start in range(0,len(tri),32768):
        p=co[tri[start:start+32768],:2];lo=p.min(1);hi=p.max(1)
        good=(hi[:,0]>a)&(lo[:,0]<b)&(hi[:,1]>c)&(lo[:,1]<d)
        out.append(start+np.flatnonzero(good))
    return np.concatenate(out).astype(np.int32)


@dataclass
class GroundPatch:
    original_count: int
    additions: np.ndarray
    keep_polygons: np.ndarray
    triangles: np.ndarray
    addition_triangle: np.ndarray
    addition_weights: np.ndarray
    triangle_source: np.ndarray
    corner_weights: dict
    sampler: object
    old_sampler: object
    bounds: tuple
    report: dict

    def coordinates(self,original):
        return np.concatenate((original,self.additions))

    def ground_delta(self,xy):
        """Exact new-triangle minus original-triangle height for existing grains.

        Returns zero outside the bounded edited band. Original-support points
        only; do not use this to reposition road aggregate or remote objects.
        """
        xy=np.asarray(xy,float);shape=xy.shape[:-1];p=xy.reshape(-1,2)
        a,b,c,d=self.bounds;out=np.zeros(len(p))
        m=(p[:,0]>a)&(p[:,0]<b)&(p[:,1]>c)&(p[:,1]<d)
        if np.any(m):
            # If a previously overhanging soil point is now under asphalt, the
            # old grain must be removed/hidden by its caller, not put on a wall.
            new_right=self.sampler.right_edge(p[m,1])
            old_right=self.old_sampler.right_edge(p[m,1])
            inside=(p[m,0]<=new_right+1e-9)&(p[m,0]<=old_right+1e-9)
            _require(np.all(inside),'Existing grain footprint lost soil support; remove or hide it, do not float it')
            out[m]=self.sampler.height(p[m])-self.old_sampler.sample(self.old_sampler.co[:,2],p[m])
        return out.reshape(shape)



class ContactGroundSampler:
    """Exact triangle-height queries without binning a dense 200k-face strip."""
    def __init__(self,grid,collar,edge_y,edge_x):
        self.grid=grid;self.collar=collar;self.edge_y=edge_y;self.edge_x=edge_x

    def right_edge(self,y):
        return np.interp(y,self.edge_y,self.edge_x)

    def height(self,xy):
        p=np.asarray(xy,float).reshape(-1,2);g=self.grid
        _require(np.isfinite(p).all(),'Finite ground query required')
        out=np.empty(len(p));ys=g[:,0,1];left=g[0,0,0];cols=g.shape[1]
        edge=np.interp(p[:,1],ys,g[:,-1,0])
        inside=(p[:,1]>=ys[0])&(p[:,1]<=ys[-1])&(p[:,0]>=left)&(p[:,0]<=edge+1e-10)
        if np.any(~inside):
            out[~inside]=self.collar.sample(self.collar.co[:,2],p[~inside])
        if np.any(inside):
            q=p[inside];r=np.clip(np.searchsorted(ys,q[:,1],side='right')-1,0,len(ys)-2)
            # All cross-row cell boundaries are straight, even on tapered rows.
            u=(q[:,0]-left)/(edge[inside]-left)*(cols-1)
            col=np.clip(np.floor(u).astype(int),0,cols-2)
            quad=np.stack((g[r,col],g[r,col+1],g[r+1,col+1],g[r+1,col]),1)
            flip=((r+col)%2).astype(bool)
            f=np.tile(np.array([[0,1,2],[0,2,3]]),(len(q),1,1))
            f[flip]=[[0,1,3],[1,2,3]]
            t=quad[np.arange(len(q))[:,None,None],f]
            a=t[:,:,0,:2];v1=t[:,:,1,:2]-a;v2=t[:,:,2,:2]-a;d=q[:,None,:]-a
            det=v1[:,:,0]*v2[:,:,1]-v1[:,:,1]*v2[:,:,0]
            u=(d[:,:,0]*v2[:,:,1]-d[:,:,1]*v2[:,:,0])/det
            v=(v1[:,:,0]*d[:,:,1]-v1[:,:,1]*d[:,:,0])/det
            w=np.stack((1-u-v,u,v),-1);best=w.min(-1).argmax(-1)
            w=w[np.arange(len(q)),best]
            _require(np.all(w.min(-1)>-2e-7),'Ground query outside actual replacement triangles')
            out[inside]=np.sum(t[np.arange(len(q)),best,:,2]*w,-1)
        return out


def plan_ground_patch(co,triangles,triangle_polygons,polygon_count,section):
    """Cut one narrow band out of the ACTUAL soil, replace and stitch it.

    Mirroring X reuses AA's tested three-sided conforming clip. Only a bounded
    local halo enters that clip; global triangles are scanned in small batches.
    All original vertices and unedited polygon IDs are retained unchanged.
    """
    spec=section.spec; co=np.asarray(co);tri=np.asarray(triangles,np.int32);tp=np.asarray(triangle_polygons,np.int32)
    _require(co.ndim==2 and co.shape[1]==3 and len(co)<=1800000,'Invalid/big ground coordinates')
    _require(tri.ndim==2 and tri.shape[1]==3 and len(tri)<=3500000,'Invalid/big actual ground tessellation')
    _require(tp.shape==(len(tri),) and np.isfinite(co).all(),'Invalid ground provenance')
    c,d=map(float,section.y[[0,-1]]);outer=spec.outer_x_m;right=spec.source_right_x_m
    chosen=_near_triangles(co,tri,(outer-.04,right+.02,c-.06,d+.06))
    parents=np.unique(tp[chosen]);global_ids=np.flatnonzero(np.isin(tp,parents)).astype(np.int32)
    _require(0<len(global_ids)<=12000,'Ground halo is empty or exceeds 12000 triangles')
    verts=np.unique(tri[global_ids]);lc=co[verts].astype(float).copy();lt=np.searchsorted(verts,tri[global_ids]).astype(np.int32)
    ltp=np.searchsorted(parents,tp[global_ids]).astype(np.int32)
    mirrored=lc.copy();mirrored[:,0]*=-1
    _require(mirrored[:,0].max()>-outer+.015,'Actual soil does not cover the outer seam')
    clip=clip_source(mirrored,lt,ltp,len(parents),(-right,-outer,c,d))
    # The actual source contains nearly coincident arange-union rows. Retain
    # their untouched polygons, but never treat zero-XY-footprint triangles as
    # surface sampling support. Keep an explicit map to full local triangle IDs
    # so every point/corner attribute still addresses the original triangle.
    xytri=lc[lt,:2];du=xytri[:,1]-xytri[:,0];dv=xytri[:,2]-xytri[:,0]
    footprint=du[:,0]*dv[:,1]-du[:,1]*dv[:,0]
    sample_ids=np.flatnonzero(np.abs(footprint)>1e-13).astype(np.int32)
    _require(len(sample_ids)>0,'Actual soil has no nondegenerate XY sampling support')
    sample_tri=lt[sample_ids]
    src=TriangleSampler(lc,sample_tri,cell=.025)
    src._reflected=TriangleSampler(mirrored,sample_tri,cell=.025)
    sy=np.unique(lc[np.unique(sample_tri),1]);sx=-src._reflected.left_edge(sy)
    src.right_edge=lambda yy:np.interp(yy,sy,sx)
    y=section.y[1:-1]
    oldright=src.right_edge(y)
    target=section.ground_contact[1:-1]
    fade=_smooth((y-c-spec.collar_m)/spec.end_fade_m)*_smooth((d-spec.collar_m-y)/spec.end_fade_m)
    edge=oldright*(1-fade)+target[:,0]*fade
    first=outer+spec.collar_m
    cols=int(np.ceil(np.max(edge-first)/spec.ground_spacing_m))+1
    _require(cols>=3 and len(y)*cols<=spec.max_patch_vertices,'Ground patch allocation cap exceeded')
    xx=first+(edge[:,None]-first)*np.linspace(0,1,cols)
    yy=np.broadcast_to(y[:,None],xx.shape)
    xy=np.column_stack((xx.ravel(),yy.ravel()))
    query=xy.copy();query[:,0]=np.minimum(query[:,0],np.repeat(oldright,cols))
    ids,w=src.weights(query);ids=sample_ids[ids]
    base=interpolate(lc,lt[ids],w);fine=base.copy();fine[:,:2]=xy
    source_edge_z=src.sample(lc[:,2],np.column_stack((oldright,y)))
    edge_z=source_edge_z*(1-fade)+target[:,2]*fade
    lateral=_smooth((xx-first)/(edge[:,None]-first))
    fine[:,2]+=(lateral*(edge_z-source_edge_z)[:,None]).ravel()
    # Exact soil/wall interface, including the original source extension gaps.
    fine.reshape(len(y),cols,3)[:,-1,2]=edge_z
    # Original soil outside its old footprint is extended only to actual wall.
    # Its finite bank is modeled, never an extrapolated analytical terrain Z.
    ca=clip.additions.copy();ca[:,0]*=-1
    offset=len(co)+len(ca);grid=np.arange(offset,offset+len(fine),dtype=np.int32).reshape(len(y),cols)
    allco=np.concatenate((co,ca,fine));mapping=np.r_[verts,np.arange(len(co),len(co)+len(ca))]
    ct=mapping[clip.triangles];bounds=[mapping[k] for k in clip.boundary]
    # Mirror returns X-descending end boundaries; sort every seam by actual
    # Cartesian axis so zipper never creates a crossing triangle.
    joins=[]
    for outerids,inner,axis in ((bounds[0],grid[0],0),(bounds[1],grid[:,0],1),(bounds[2],grid[-1],0)):
        outerids=outerids[np.argsort(allco[outerids,axis],kind='stable')]
        inner=inner[np.argsort(allco[inner,axis],kind='stable')]
        ta=allco[outerids,axis];tb=allco[inner,axis]
        ta=(ta-ta[0])/(ta[-1]-ta[0]);tb=(tb-tb[0])/(tb[-1]-tb[0])
        joins.append(zipper(outerids,inner,ta,tb))
    newfaces=np.concatenate((_strip_faces(len(y),cols)+offset,*joins))
    allfaces=np.concatenate((ct,newfaces));p=allco[allfaces,:2]
    area=(p[:,1,0]-p[:,0,0])*(p[:,2,1]-p[:,0,1])-(p[:,1,1]-p[:,0,1])*(p[:,2,0]-p[:,0,0])
    _require(np.all(abs(area)>1e-14),'Ground patch has a degenerate or crossing seam')
    flip=area<0;allfaces[flip]=allfaces[flip,::-1]
    # Provenance for every new corner, including right-boundary fill.
    q=allco[newfaces,:2].reshape(-1,2).copy()
    q[:,0]=np.minimum(q[:,0],src.right_edge(q[:,1]))
    ci,cw=src.weights(q);ci=sample_ids[ci].reshape(-1,3);cw=cw.reshape(-1,3,3)
    # Face source is a representative source triangle; each CORNER can have
    # a different source triangle, tracked separately by prepare_contact().
    tsource=np.r_[global_ids[clip.triangle_source],global_ids[ci[:,0]]]
    corner_payload=dict(clip_count=len(ct),clip_weights=clip.corner_weights.copy(),
                        new_corner_triangle=global_ids[ci],new_corner_weights=cw,flipped=flip)
    addt=np.r_[global_ids[clip.addition_triangle],global_ids[ids]]
    addw=np.concatenate((clip.addition_weights,w))
    removed=np.setdiff1d(np.arange(len(parents)),clip.keep_polygons)
    keep=np.setdiff1d(np.arange(polygon_count,dtype=np.int32),parents[removed])
    # New-surface exact sampler is local; no unused original scene vertices
    # participate in either its bins or its allocation footprint.
    collar=np.concatenate((ct,*joins));iv=np.unique(collar);vv=allco[iv]
    tt=np.searchsorted(iv,collar).astype(np.int32)
    collar_sampler=TriangleSampler(vv,tt,cell=.025,max_bucket_entries=400000)
    sampler=ContactGroundSampler(fine.reshape(len(y),cols,3),collar_sampler,
        np.r_[c,y,d],np.r_[src.right_edge(c),edge,src.right_edge(d)])
    plan=GroundPatch(len(co),np.concatenate((ca,fine)),keep,allfaces,addt,addw,
        tsource,corner_payload,sampler,src,(outer,right,c,d),{})
    # All three interfaces must be conforming. No soil triangle crosses the
    # road-contact graph; the new grid is ordered in X and Y by construction.
    ee=np.sort(np.concatenate([allfaces[:,[j,(j+1)%3]] for j in range(3)]),axis=1)
    keys,uses=np.unique(ee,axis=0,return_counts=True)
    _require(np.all(uses<=2),'Ground patch has non-manifold overlapping triangles')
    used={tuple(e):int(n) for e,n in zip(keys,uses)}
    for ring in (grid[0],grid[:,0],grid[-1]):
        _require(all(used.get(tuple(sorted((int(a),int(b)))))==2 for a,b in zip(ring[:-1],ring[1:])),
                 'Ground fine/collar seam is not conforming')
    delta=fine[:,2]-base[:,2]
    _require(abs(delta).max()<.065,'Actual soil would need >65 mm movement; reject instead of hiding mismatch')
    plan.report=dict(replaced_original_polygons=len(parents[removed]),added_vertices=len(plan.additions),
        replacement_triangles=len(allfaces),all_original_vertices_retained=True,
        original_soil_under_new_patch=False,three_seams_conforming=True,
        exact_actual_soil_triangle_sampling=True,soil_z_change_range_m=[float(delta.min()),float(delta.max())],
        contact_extent_m=[outer,right,c,d],top_crown_unchanged=True,
        interior_contact_shared_with_wall=True,end_contact_preserves_original_soil_bank=True,requires_existing_grain_reprojection=True,
        source_halo_triangles=len(global_ids),source_sampling_triangles=len(sample_ids),
        omitted_zero_footprint_source_triangles=len(lt)-len(sample_ids),
        source_footprint_cross_threshold_m2=1e-13,
        allocation_cap_vertices=spec.max_patch_vertices)
    return plan


def _mesh(name,co,faces,materials):
    import bpy
    me=bpy.data.meshes.new(name)
    try:
        me.from_pydata(co.tolist(),[],faces.tolist())
        for m in materials:me.materials.append(m)
        me.update()
        _require(not me.validate(verbose=False,clean_customdata=False),'Blender repaired prepared mesh')
        return me
    except Exception:
        bpy.data.meshes.remove(me);raise


def _attr(mesh,name,dtype,domain,prop,values):
    a=mesh.attributes.get(name) or mesh.attributes.new(name,dtype,domain)
    a.data.foreach_set(prop,np.asarray(values).ravel())


def _ground_mesh(old,co,tri,tloops,tp,plan,attrs,owned):
    """Preserve original polygon sequence/attributes outside the replacement."""
    import bpy
    starts=_read(old.polygons,'loop_start',1,np.int32);sizes=_read(old.polygons,'loop_total',1,np.int32)
    lv=_read(old.loops,'vertex_index',1,np.int32);km=np.zeros(len(sizes),bool);km[plan.keep_polygons]=True
    keptloops=np.flatnonzero(np.repeat(km,sizes));counts=np.r_[sizes[plan.keep_polygons],np.full(len(plan.triangles),3,np.int32)]
    flat=np.r_[lv[keptloops],plan.triangles.ravel()];allco=plan.coordinates(co)
    new=bpy.data.meshes.new(old.name+' / AC conforming supported contact')
    owned.append(new)  # also cleaned if an attribute write fails mid-build
    new.vertices.add(len(allco));new.vertices.foreach_set('co',allco.ravel())
    new.loops.add(len(flat));new.loops.foreach_set('vertex_index',flat)
    new.polygons.add(len(counts));new.polygons.foreach_set('loop_start',np.r_[0,np.cumsum(counts[:-1])].astype(np.int32))
    new.polygons.foreach_set('loop_total',counts)
    for m in old.materials:new.materials.append(m)
    p=plan.corner_weights;nc=p['clip_count'];aid=tri[plan.addition_triangle]
    for name,(domain,dtype,prop,discrete,values) in attrs.items():
        if domain=='EDGE' or name=='material_index':continue
        if domain=='POINT':v=np.concatenate((values,interpolate(values,aid,plan.addition_weights,discrete)))
        elif domain=='FACE':v=np.concatenate((values[plan.keep_polygons],values[tp[plan.triangle_source]]))
        else:
            ids=tloops[plan.triangle_source[:nc]];cc=values[ids]
            w=p['clip_weights']
            cv=(cc[np.arange(nc)[:,None],w.argmax(-1)] if discrete
                else np.einsum('nki,ni...->nk...',w,cc))
            ni=tloops[p['new_corner_triangle']];nv=values[ni];nw=p['new_corner_weights']
            if discrete:
                ix=nw.argmax(-1);cv2=nv[np.arange(len(nv))[:,None],np.arange(3)[None,:],ix]
            else:cv2=np.einsum('nki,nki...->nk...',nw,nv)
            cv=np.concatenate((cv,cv2));cv[p['flipped']]=cv[p['flipped'],::-1]
            v=np.concatenate((values[keptloops],cv.reshape((-1,)+values.shape[1:])))
        _attr(new,name,dtype,domain,prop,v)
    mats=_read(old.polygons,'material_index',1,np.int32);sm=_read(old.polygons,'use_smooth',1,bool)
    new.polygons.foreach_set('material_index',np.r_[mats[plan.keep_polygons],mats[tp[plan.triangle_source]]])
    new.polygons.foreach_set('use_smooth',np.r_[sm[plan.keep_polygons],np.ones(len(plan.triangles),bool)])
    new.update(calc_edges=True)
    if any(v[0]=='EDGE' for v in attrs.values()):
        oe=_read(old.edges,'vertices',2,np.int32);ne=_read(new.edges,'vertices',2,np.int32)
        radix=len(allco)+1;okey=np.sort(oe,axis=1).astype(np.int64)@np.array([radix,1]);order=np.argsort(okey);keys=okey[order]
        nkey=np.sort(ne,axis=1).astype(np.int64)@np.array([radix,1]);pos=np.searchsorted(keys,nkey)
        good=pos<len(keys);match=np.zeros(len(ne),bool);match[good]=keys[pos[good]]==nkey[good]
        # New cut vertices on an original edge inherit that edge's metadata.
        ve={}
        for k,(ids,w) in enumerate(zip(aid,plan.addition_weights)):
            support=ids[np.abs(w)>1e-9]
            if len(support)==2:ve[len(co)+k]=tuple(sorted(map(int,support)))
        inherited=np.full(len(ne),-1,np.int32);inherited[match]=order[pos[match]]
        for k in np.flatnonzero(~match):
            u,v=map(int,ne[k]);eu,ev=ve.get(u),ve.get(v);edge=None
            if eu is not None and (eu==ev or v in eu):edge=eu
            elif ev is not None and u in ev:edge=ev
            if edge is not None:
                key=edge[0]*radix+edge[1];j=np.searchsorted(keys,key)
                if j<len(keys) and keys[j]==key:inherited[k]=order[j]
        for name,(domain,dtype,prop,discrete,values) in attrs.items():
            if domain!='EDGE':continue
            v=np.zeros(len(ne),values.dtype);good=inherited>=0;v[good]=values[inherited[good]]
            _attr(new,name,dtype,domain,prop,v)
    _require(not new.validate(verbose=False,clean_customdata=False),'Blender repaired the replacement soil')
    # Preserve the actual original corner normals even when they were automatic:
    # recomputing shared-vertex normals can otherwise alter the untouched halo.
    # Replacement corners retain newly computed displaced-geometry normals.
    normal=_read(new.corner_normals,'vector',3)
    original_normal=_read(old.corner_normals,'vector',3)
    normal[:len(keptloops)]=original_normal[keptloops]
    new.normals_split_custom_set(normal)
    for k in old.keys():new[k]=old[k]
    if len(old.uv_layers):
        new.uv_layers.active_index=old.uv_layers.active_index
        for layer in old.uv_layers:
            if layer.name in new.uv_layers:new.uv_layers[layer.name].active_render=layer.active_render
    if len(old.color_attributes):
        new.color_attributes.active_color_name=old.color_attributes.active_color_name
        new.color_attributes.default_color_name=old.color_attributes.default_color_name
    _require(np.array_equal(_read(new.vertices,'co',3)[:len(co)],co),'An original soil coordinate moved')
    _require(np.array_equal(_read(new.loops,'vertex_index',1,np.int32)[:len(keptloops)],lv[keptloops]),'An unedited polygon changed')
    return new


def prepare_contact(scene,strip_result,*,spec=None):
    """Prepare UNASSIGNED Blender meshes. Parent owns atomic scene integration.

    Returns ground_mesh, wall_mesh, particle_mesh, section, ground_plan,
    ground_delta(xy), report, and dispose() for an unassigned candidate.
    No object is linked and no original material/image/node is modified.
    Old wall removal and original-grain re-seating remain explicit parent work.
    """
    import bpy
    spec=(spec or ContactSpec()).validate();ground=scene.objects.get(GROUND);wall=scene.objects.get(WALL)
    _require(ground is not None and wall is not None,'Missing actual ground or old section object')
    _require(not ground.modifiers and ground.data.shape_keys is None and not ground.vertex_groups,
             'Ground must be the unmodified actual source mesh')
    _require(np.allclose(np.asarray(ground.matrix_world),np.eye(4),rtol=0,atol=1e-9),
             'Ground must retain world-space identity transform')
    _require(not any(scene.objects.get(n) for n in ('AA existing-soil support in raveled openings',
                'AA finite exposed crown ends','AC supported pavement section')),
             'Start from clean source, without earlier contact overlays or an applied AC patch')
    old=ground.data;attrs=_attributes(old);co=_read(old.vertices,'co',3)
    old.calc_loop_triangles();tri=_read(old.loop_triangles,'vertices',3,np.int32)
    tp=_read(old.loop_triangles,'polygon_index',1,np.int32);tl=_read(old.loop_triangles,'loops',3,np.int32)
    section=build_section(strip_result['new_edge_xyz'],spec,base_edge_xyz=strip_result['old_edge_xyz'])
    plan=plan_ground_patch(co,tri,tp,len(old.polygons),section)
    particles=build_embedded_particles(section)
    made=[];materials=[]
    def dispose():
        while made:
            me=made.pop()
            if me.users==0:bpy.data.meshes.remove(me)
        while materials:
            ma=materials.pop()
            if ma.users==0:bpy.data.materials.remove(ma)
    try:
        gm=_ground_mesh(old,co,tri,tl,tp,plan,attrs,made)
        wm=_mesh('AC supported pavement section',section.wall_vertices,section.wall_faces,[wall.data.materials[0]])
        made.append(wm)
        _attr(wm,'asphalt_share','FLOAT','POINT','value',section.wall_asphalt_share)
        tint=np.tile([.68,.67,.65,1.],(len(section.wall_vertices),1))
        tint[section.wall_asphalt_share<.5]=[.94,.88,.77,1.]
        _attr(wm,'macro_tint','FLOAT_COLOR','POINT','color',tint)
        _attr(wm,'ac_section_layer','INT','FACE','value',section.wall_layer)
        # A separate rough mineral shader cannot alter the approved road graph.
        ma=bpy.data.materials.new('AC freshly exposed embedded mineral / metric 2.5-7.5mm');materials.append(ma)
        ma.use_nodes=True;n=ma.node_tree.nodes;l=ma.node_tree.links;bs=n.get('Principled BSDF')
        a=n.new('ShaderNodeAttribute');a.attribute_name='mineral';l.new(a.outputs['Color'],bs.inputs['Base Color'])
        bs.inputs['Roughness'].default_value=.89;bs.inputs['IOR'].default_value=1.48
        pm=_mesh('AC anchored subsurface aggregate',particles.vertices,particles.faces,[ma]);made.append(pm)
        _attr(pm,'mineral','FLOAT_COLOR','POINT','color',particles.mineral)
        _attr(pm,'particle_id','INT','POINT','value',particles.particle_id)
        report=dict(section=section.report,ground=plan.report,particles=particles.report,
                    scene_assigned=False,rendered=False,saved=False,
                    original_top_maps_changed=False,original_top_scale_changed=False,
                    original_markings_changed=False,
                    required_integration=['Replace original ground, do not overlay',
                        'Trim old wall over exact strip y bounds; do not also use AA gap fill',
                        'Re-seat or hide existing soil particles whose support changed',
                        'Inspect actual rendered pixels before acceptance'],
                    limits=['Unmeasured diagnostic stratigraphy',
                        'No vertical overhang/undercut holes in the road-top graph',
                        'Subsurface clasts are procedural metric interpretations',
                        'Blender adapter has not run in source-only tests'])
        return dict(ground_mesh=gm,wall_mesh=wm,particle_mesh=pm,section=section,
                    ground_plan=plan,ground_delta=plan.ground_delta,report=report,dispose=dispose)
    except Exception:
        dispose();raise
