"""Source-topology, metric, inward-only asphalt perimeter ravel.

This is an APPROXIMATE crown segmentation of the approved macro relief, not the
mineral generator's semantic IDs. No material fields are generated or altered.
The 2.5--7.5 mm authored coarse grading is identified by finite relief footprints;
polygon/aspect variation permits a few measured footprints up to 8.9 mm. Smaller
unresolved sand remains the original material. No grain is enlarged, relocated,
or replaced by a sine/noise scallop. Hashes select finite missing crowns only.

Usage (metres, world texture origin unchanged)::
    f = EdgeRavelField(path_to_GeometryHeight_npy)
    p = f.project(old_left_edge, (0., 2.), side=-1)
    new_x = p.x_edge(y)                  # continuous linear micro-boundary
    fields = p.sample(world_xy)          # occupancy/distance/approximate labels

At both ends the caller may taper recession into its existing mesh. The projected
boundary is a single-valued lateral envelope: it cannot represent overhangs or
isolated holes. edge_distance_m is signed LATERAL distance, not Euclidean SDF.
Source alignment is GeometryHeight[::-1], period .25 m, origin world (0, 0).
NumPy + standard library only. No Blender, full-resolution state load or render.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import numpy as np

PINNED_GEOMETRY_SHA256 = '9c6ebba3a109088842a73434cea02069aa3a5a98e1b871a3f7b7b5e246de0c83'
TILE_M = .25
HEIGHT_SCALE_M = .004
MAX_RECESSION_M = .015
_KEY_BITS = 14
_TILE_BIAS = 1 << 20
_TILE_MASK = (1 << 21) - 1


def _uniform(keys, salt=0):
    """Stable integer selection, never a spatial displacement/noise field."""
    x = np.asarray(keys, dtype=np.uint64) ^ np.uint64(salt)
    with np.errstate(over='ignore'):
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xbf58476d1ce4e5b9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94d049bb133111eb)
        x ^= x >> np.uint64(31)
    return (x >> np.uint64(11)).astype(np.float64) / float(1 << 53)


def _finite(a, name):
    a = np.asarray(a, dtype=float)
    if not np.all(np.isfinite(a)):
        raise ValueError(name + ' must be finite')
    return a


def _call(fn, values, name):
    result = fn(values) if callable(fn) else fn
    return np.broadcast_to(_finite(result, name), np.shape(values))


@dataclass
class RavelProfile:
    source: 'EdgeRavelField'
    old_edge_x: object
    y: np.ndarray
    recession_m: np.ndarray
    side: int
    removed_keys: np.ndarray
    removed_clusters: np.ndarray
    receipt: dict

    def x_edge(self, y):
        """Absolute continuous world X. Outside prepared interval: old edge."""
        y = _finite(y, 'world Y')
        depth = np.interp(y, self.y, self.recession_m, left=0., right=0.)
        return _call(self.old_edge_x, y, 'old edge X') - self.side * depth

    __call__ = x_edge

    def sample(self, world_xy):
        """Positive distance/occupancy is pavement; labels are approximate IDs.

        removed_chip labels a selected finite original crown footprint, even if
        it was outside the old slab; newly missing pavement is separately given
        by missing_pavement. chip_label is stable per world tile/crown instance.
        Caller must still intersect with the other boundaries of the road.
        """
        xy = _finite(world_xy, 'world XY')
        if xy.shape[-1:] != (2,):
            raise ValueError('world_xy must have last dimension 2')
        x, y = xy[..., 0], xy[..., 1]
        new = self.x_edge(y)
        old = _call(self.old_edge_x, y, 'old edge X')
        distance = self.side * (new - x)
        keys = self.source.chip_labels(xy)
        idx = np.searchsorted(self.removed_keys, keys)
        safe = np.minimum(idx, max(0, len(self.removed_keys) - 1))
        selected = ((idx < len(self.removed_keys)) & (self.removed_keys[safe] == keys)
                    if len(self.removed_keys) else np.zeros(keys.shape, bool))
        cluster = np.where(selected, self.removed_clusters[safe], 0) if len(self.removed_keys) else np.zeros(keys.shape, np.int32)
        occupied = distance >= 0.
        was_inside = self.side * (old - x) >= 0.
        return dict(occupancy=occupied, edge_distance_m=distance,
                    chip_label=keys, removed_chip=selected, cluster_id=cluster,
                    missing_pavement=was_inside & ~occupied,
                    recession_m=self.side * (old - new))


class EdgeRavelField:
    """Read-only source and finite steepest-ascent crown footprint approximation."""
    def __init__(self, geometry_height_path, *, origin_xy=(0., 0.), verify=True):
        path = Path(geometry_height_path)
        if verify:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if digest != PINNED_GEOMETRY_SHA256:
                raise ValueError('GeometryHeight is not the exact approved native4096 input')
        raw = np.load(path, mmap_mode='r', allow_pickle=False)
        if raw.shape != (513, 513) or raw.dtype != np.float32 or not np.isfinite(raw).all():
            raise ValueError('Expected finite float32 approved 513 x 513 GeometryHeight')
        self.path, self.origin = str(path), _finite(origin_xy, 'origin XY')
        if self.origin.shape != (2,):
            raise ValueError('origin_xy must contain X and Y')
        self.pixel_m = TILE_M / 512
        # Original geometry uses the vertically flipped image field; end rows
        # duplicate the periodic zero boundary and are not additional pixels.
        h = np.array(raw[::-1][:-1, :-1], dtype=np.float32)
        n = h.shape[0]
        index = np.arange(n*n, dtype=np.int32).reshape(n, n)
        best, parent = h.copy(), index.copy()
        for dy, dx in ((-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)):
            neighbor = np.roll(h, (dy, dx), (0, 1))
            ii = np.roll(index, (dy, dx), (0, 1))
            wins = (neighbor > best) | ((neighbor == best) & (ii < parent))
            best[wins], parent[wins] = neighbor[wins], ii[wins]
        root = parent.ravel()
        for _ in range(20):
            next_root = root[root]
            if np.array_equal(root, next_root):
                break
            root = next_root
        else:
            raise ValueError('Crown ascent did not converge')
        # -0.24 mm is a relief-footprint cutoff, not a claimed mineral boundary.
        support = h.ravel() >= (.5 - .00024 / HEIGHT_SCALE_M)
        roots, inverse = np.unique(root[support], return_inverse=True)
        counts = np.bincount(inverse)
        diameter = 2 * np.sqrt(counts / np.pi) * self.pixel_m
        eligible = (diameter >= .0025) & (diameter <= .0089)
        lookup = np.zeros(len(roots), np.int32)
        lookup[eligible] = np.arange(1, np.sum(eligible)+1)
        label = np.zeros(n*n, np.int32)
        label[support] = lookup[inverse]
        self.labels = label.reshape(n,n)
        self.count = int(np.sum(eligible))
        if self.count >= (1 << _KEY_BITS):
            raise ValueError('Too many footprint IDs for stable key encoding')
        valid_roots = roots[eligible]
        self.peaks = np.zeros((self.count+1,2), dtype=float)
        self.peaks[1:,0] = valid_roots % n * self.pixel_m
        self.peaks[1:,1] = valid_roots // n * self.pixel_m
        self.diameter_m = np.r_[0., diameter[eligible]]
        # Exact finite support bbox relative to its peak, periodic-seam aware.
        jj, ii = np.nonzero(self.labels)
        lab = self.labels[jj, ii]
        delta = np.stack((ii*self.pixel_m, jj*self.pixel_m),-1) - self.peaks[lab]
        delta = (delta + TILE_M/2) % TILE_M - TILE_M/2
        self.lo = np.full((self.count+1,2), np.inf)
        self.hi = np.full((self.count+1,2), -np.inf)
        for axis in (0,1):
            np.minimum.at(self.lo[:,axis], lab, delta[:,axis] - self.pixel_m/2)
            np.maximum.at(self.hi[:,axis], lab, delta[:,axis] + self.pixel_m/2)
        self.lo[0] = self.hi[0] = 0.
        self.metadata = dict(segmentation='Approximate finite macro-relief ascent basins; NOT semantic generator IDs',
                             source_sha256=PINNED_GEOMETRY_SHA256, tile_m=TILE_M,
                             source_pixel_m=self.pixel_m, coarse_crowns=self.count,
                             authored_coarse_grading_m=[.0025,.0075],
                             measured_footprint_diameter_m=[float(diameter[eligible].min()),float(diameter[eligible].max())],
                             footprint_threshold_height_m=-.00024,
                             material_fields_modified=False, full4096_regenerated=False)

    def chip_labels(self, world_xy):
        xy = _finite(world_xy, 'world XY')
        if xy.shape[-1:] != (2,):
            raise ValueError('world_xy must have last dimension 2')
        uv = xy - self.origin
        ij = np.floor(uv/self.pixel_m + .5).astype(np.int64) % 512
        labels = self.labels[ij[...,1], ij[...,0]]
        tiles = np.floor((uv - self.peaks[labels])/TILE_M + .5).astype(np.int64)
        if np.any(np.abs(tiles) >= _TILE_BIAS):
            raise ValueError('World tile coordinate exceeds stable ID range')
        a = (tiles[...,0] + _TILE_BIAS).astype(np.uint64)
        b = (tiles[...,1] + _TILE_BIAS).astype(np.uint64)
        keys = (a << np.uint64(35)) | (b << np.uint64(14)) | labels.astype(np.uint64)
        return np.where(labels != 0, keys, np.uint64(0))

    def _instances(self, keys):
        lab = (keys & np.uint64((1<<_KEY_BITS)-1)).astype(np.int32)
        tx = (keys >> np.uint64(35)).astype(np.int64) - _TILE_BIAS
        ty = ((keys >> np.uint64(14)) & np.uint64(_TILE_MASK)).astype(np.int64) - _TILE_BIAS
        center = self.peaks[lab] + np.stack((tx,ty),-1)*TILE_M + self.origin
        return lab, center

    def project(self, old_edge_x, y_bounds, *, side=-1, exposure=None, sample_step_m=None):
        """Build an inward-only continuous projected boundary for a <=4 m patch.

        old_edge_x and optional exposure accept world Y arrays. exposure is 0..1
        longitudinal runoff/erosion exposure; it changes the chance of connected
        multi-crown loss only. It never scales grains or modulates source height.
        The bounds limit keeps the complete helper comfortably below 200 MiB.
        """
        bounds = _finite(y_bounds, 'Y bounds')
        if bounds.shape != (2,) or not 0 < bounds[1]-bounds[0] <= 4.:
            raise ValueError('Use an increasing diagnostic Y interval of at most 4 m')
        if side not in (-1,1):
            raise ValueError('side must be -1 (left) or +1 (right)')
        step = self.pixel_m/2 if sample_step_m is None else float(sample_step_m)
        if not self.pixel_m/4 <= step <= self.pixel_m:
            raise ValueError('sample_step_m must be 0.122--0.488 mm; larger steps lose crowns')
        # Half-pixel X sampling captures finite source footprints without scale
        # changes. Bounded row chunks prevent large coordinate temporaries.
        y = np.linspace(bounds[0], bounds[1], int(np.ceil(np.diff(bounds)[0]/step))+1)
        old = _call(old_edge_x, y, 'old edge X')
        offsets = np.arange(0., MAX_RECESSION_M + self.pixel_m*.51, self.pixel_m/2)
        key_grid = np.empty((len(y),len(offsets)), dtype=np.uint64)
        for first in range(0,len(y),512):
            last = min(first+512,len(y))
            yy = np.broadcast_to(y[first:last,None], (last-first,len(offsets)))
            xx = old[first:last,None] - side*offsets[None,:]
            key_grid[first:last] = self.chip_labels(np.stack((xx,yy),-1))
        keys = np.unique(key_grid)
        keys = keys[keys != 0]
        lab, center = self._instances(keys)
        center_depth = -side*(center[:,0] - _call(old_edge_x, center[:,1], 'old edge X'))
        # Conservative physical bbox depth, permitting no loss beyond 15 mm.
        inward_bound = -side*(self.hi[lab,0] if side == -1 else self.lo[lab,0])
        deepest = center_depth + inward_bound
        baseline = np.unique(key_grid[:,0]); baseline = baseline[baseline != 0]
        boundary_ids = np.searchsorted(keys, baseline)
        missing = np.zeros(len(keys),bool)
        clusters = np.zeros(len(keys),np.int32)
        cluster_serial = 0
        exp = np.full(len(keys),.45) if exposure is None else np.clip(_call(exposure, center[:,1], 'erosion exposure'),0,1)
        seed_order = boundary_ids[np.argsort(center[boundary_ids,1],kind='stable')]
        for seed in seed_order:
            if missing[seed] or deepest[seed] > MAX_RECESSION_M:
                continue
            cluster_serial += 1
            missing[seed], clusters[seed] = True, cluster_serial
            # Every baseline-cut coarse crown is removed as a finite footprint.
            # Some then lose nearby inward crowns; hashes only choose events.
            if float(_uniform(keys[seed], 821)) > .24 + .66*exp[seed]:
                continue
            target = .003 + .012*float(_uniform(keys[seed], 919))
            max_members = 2 + int(3*float(_uniform(keys[seed], 2027)))
            members = [int(seed)]
            for _ in range(max_members-1):
                selected = np.asarray(members)
                delta = center[:,None,:] - center[selected][None,:,:]
                distance = np.sqrt(np.sum(delta*delta,axis=-1))
                # Neighbor relation is a bbox/diameter approximation; the lost
                # region itself always uses the actual finite source footprint.
                gap = distance - .5*(self.diameter_m[lab,None] + self.diameter_m[lab[selected]][None,:])
                eligible = (~missing & (gap.min(axis=1) <= .0015) &
                            (center_depth >= center_depth[seed]-.0005) &
                            (deepest <= target) & (deepest > 0.) &
                            (np.abs(center[:,1]-center[seed,1]) <= .012))
                candidates = np.flatnonzero(eligible)
                if not len(candidates):
                    break
                # Prefer the adjacent source crown moving the break inward.
                score = distance[candidates].min(axis=1) - .4*center_depth[candidates]
                winner = int(candidates[np.argmin(score)])
                missing[winner], clusters[winner] = True, cluster_serial
                members.append(winner)
        removed_keys = keys[missing]
        removed_clusters = clusters[missing]
        pos = np.searchsorted(removed_keys, key_grid)
        safe = np.minimum(pos,max(0,len(removed_keys)-1))
        lost = ((pos < len(removed_keys)) & (removed_keys[safe] == key_grid)
                if len(removed_keys) else np.zeros(key_grid.shape,bool))
        # Exterior connectivity: each finite missing crown opens to the outside;
        # intervening binder is the short connection, not a separate noise cut.
        depth = np.max(np.where(lost,offsets[None,:] + self.pixel_m/4,0.),axis=1)
        depth = np.clip(depth,0.,MAX_RECESSION_M)
        # If this exterior envelope intersects a surviving crown, tuck the cut
        # just outside that crown. Finite source labels, not a smoothed sine wave,
        # determine the remaining cap. This may shorten a ravel bite locally.
        col = np.minimum(np.floor(depth/(self.pixel_m/2)+.5).astype(int),len(offsets)-1)
        row = np.arange(len(y)); at_cut = key_grid[row,col]
        is_missing = lost[row,col]
        touched = (at_cut != 0) & ~is_missing & (depth > 0.)
        for r in np.flatnonzero(touched):
            same = np.flatnonzero(key_grid[r,:col[r]+1] == at_cut[r])
            if len(same):
                depth[r] = max(0., offsets[same[0]] - self.pixel_m/4)
        receipt = dict(self.metadata, y_bounds_m=bounds.tolist(), side=side,
                       boundary_sample_step_m=float(y[1]-y[0]),
                       max_recession_m=float(depth.max()),
                       mean_recession_m=float(depth.mean()),
                       missing_crown_instances=int(missing.sum()),
                       active_clusters=cluster_serial,
                       multi_crown_clusters=int(np.sum(np.bincount(clusters[missing])[1:] > 1)),
                       cluster_target_penetration_m=[.003,.015],
                       contour='Continuous piecewise-linear inward-only source-footprint envelope',
                       endpoint_taper='Caller-owned; x_edge outside interval returns old edge',
                       neighbor_relation='Approximate physical footprint proximity',
                       source_arrays_opened=['GeometryHeight.npy (read-only mmap)'])
        return RavelProfile(self,old_edge_x,y,depth,side,removed_keys,removed_clusters,receipt)
