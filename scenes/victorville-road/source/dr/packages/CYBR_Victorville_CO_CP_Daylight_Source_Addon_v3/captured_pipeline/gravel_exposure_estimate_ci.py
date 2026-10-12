"""Bounded local-plane/quadrature exposure estimates; no scene/geometry edits.

``estimate_exposure`` accepts convex, watertight prototype records containing
``v``, ``f`` and their true mesh ``volume``, as returned by
``weather_metric_gravel_ch.bank``. Coordinates and returned units are metres.
Yaw is in radians; instances must have unit scale and no pitch/roll. The ground
height and XY gradient describe the *actual terrain triangle at each origin*.
That triangle's plane is extrapolated over the body footprint. This is NOT an
exact intersection with every terrain triangle underneath a body.

The deterministic midpoint grid integrates vertical convex-polyhedron columns.
Area is exposed XY-projected footprint, not rock surface area. Aggregate area
sums bodies (not their union). Raw volume quadrature is deliberately not scaled
to the true solid ledger; its full-body error is reported separately. Moving
bodies changes exposure estimates, never their true solid volumes.
"""

from collections import OrderedDict
from dataclasses import dataclass
import hashlib

import numpy as np
from scipy.spatial import ConvexHull


METHOD = "local terrain-triangle plane / deterministic midpoint-grid quadrature estimate"
LIMITS = (
    "Each origin triangle plane is extrapolated over its body's footprint; not "
    "exact against every ground triangle. Area is XY-projected footprint summed "
    "per body, not exposed surface area or non-overlapping union coverage. "
    "Quadrature errors are separate from the unchanged true-mesh solid ledger. "
    "Unit-scale convex watertight bodies with yaw-only rotations are required."
)
MAX_BATCH_SIZE = 512
MAX_RESOLUTION = 128


@dataclass(frozen=True)
class PrototypeSamples:
    xy: np.ndarray
    bottom: np.ndarray
    top: np.ndarray
    cell_area: float
    true_volume: float
    true_footprint_area: float
    quadrature_volume: float
    resolution: int


class PrototypeSampleCache:
    """Content-addressed, bounded in-memory LRU cache; never modifies inputs."""

    def __init__(self, max_entries=576):
        if not isinstance(max_entries, (int, np.integer)) or max_entries < 1:
            raise ValueError("max_entries must be a positive integer")
        self.max_entries = int(max_entries)
        self._entries = OrderedDict()

    def __len__(self):
        return len(self._entries)

    def samples(self, prototype, resolution=32):
        resolution = _resolution(resolution)
        vertices = np.asarray(prototype["v"], dtype=np.float64)
        faces_raw = np.asarray(prototype["f"])
        if vertices.ndim != 2 or vertices.shape[1] != 3 or len(vertices) < 4:
            raise ValueError("prototype v must have shape (V, 3), V >= 4")
        if not np.isfinite(vertices).all():
            raise ValueError("prototype vertices must be finite")
        if faces_raw.ndim != 2 or faces_raw.shape[1] != 3 or faces_raw.dtype.kind not in "iu":
            raise ValueError("prototype f must be integer triangular faces")
        faces = np.asarray(faces_raw, dtype=np.int64)
        if len(faces) < 4 or faces.min() < 0 or faces.max() >= len(vertices):
            raise ValueError("prototype faces are empty or outside vertex range")
        true_volume = float(prototype["volume"])
        if not np.isfinite(true_volume) or true_volume <= 0:
            raise ValueError("prototype volume must be a positive finite true mesh volume")
        digest = hashlib.sha256()
        digest.update(np.ascontiguousarray(vertices).tobytes())
        digest.update(np.ascontiguousarray(faces).tobytes())
        digest.update(np.asarray([true_volume, resolution], dtype=np.float64).tobytes())
        key = digest.digest()
        if key in self._entries:
            self._entries.move_to_end(key)
            return self._entries[key]
        samples = _sample_prototype(vertices, faces, true_volume, resolution)
        self._entries[key] = samples
        if len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
        return samples


def _resolution(value):
    if not isinstance(value, (int, np.integer)) or isinstance(value, (bool, np.bool_)):
        raise ValueError("resolution must be an integer")
    if not 2 <= value <= MAX_RESOLUTION:
        raise ValueError(f"resolution must be between 2 and {MAX_RESOLUTION}")
    return int(value)


def _sample_prototype(vertices, faces, true_volume, resolution):
    # Check the promised closed convex mesh, rather than quietly filling a
    # concave or open object with its convex hull.
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    if not np.all(np.unique(edges, axis=0, return_counts=True)[1] == 2):
        raise ValueError("prototype must be watertight (two faces per edge)")
    hull = ConvexHull(vertices)
    triangles = (vertices - vertices.mean(axis=0))[faces]
    mesh_volume = abs(float(np.einsum("ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])).sum() / 6))
    if not np.isclose(mesh_volume, hull.volume, rtol=2e-4, atol=1e-15):
        raise ValueError("prototype must be convex with consistently oriented faces")
    if not np.isclose(true_volume, mesh_volume, rtol=2e-4, atol=1e-15):
        raise ValueError("declared true volume does not match the supplied mesh")
    lo, hi = vertices[:, :2].min(axis=0), vertices[:, :2].max(axis=0)
    spacing = (hi - lo) / resolution
    x, y = np.meshgrid(lo[0] + (np.arange(resolution) + .5) * spacing[0],
                       lo[1] + (np.arange(resolution) + .5) * spacing[1], indexing="xy")
    xy = np.column_stack((x.ravel(), y.ravel()))
    top, bottom = np.full(len(xy), np.inf), np.full(len(xy), -np.inf)
    valid = np.ones(len(xy), dtype=bool)
    # Normalize hull inequalities: nx*x + ny*y + nz*z + d <= 0.
    # Limit each temporary matrix to <= 128 planes by resolution**2 samples.
    for start in range(0, len(hull.equations), 128):
        eq = hull.equations[start:start + 128]
        rhs = -(eq[:, :2] @ xy.T + eq[:, 3, None])
        upper, lower = eq[:, 2] > 1e-12, eq[:, 2] < -1e-12
        vertical = ~(upper | lower)
        if upper.any():
            top = np.minimum(top, (rhs[upper] / eq[upper, 2, None]).min(axis=0))
        if lower.any():
            bottom = np.maximum(bottom, (rhs[lower] / eq[lower, 2, None]).max(axis=0))
        if vertical.any():
            valid &= (rhs[vertical] >= -1e-12).all(axis=0)
    valid &= np.isfinite(top) & np.isfinite(bottom) & (top > bottom)
    xy, top, bottom = xy[valid].copy(), top[valid].copy(), bottom[valid].copy()
    if not len(xy):
        raise ValueError("quadrature grid misses prototype footprint; increase resolution")
    for array in (xy, top, bottom):
        array.flags.writeable = False
    cell_area = float(np.prod(spacing))
    return PrototypeSamples(xy, bottom, top, cell_area, true_volume,
                            float(ConvexHull(vertices[:, :2]).volume),
                            float(np.sum(top - bottom) * cell_area), resolution)


def estimate_exposure(prototypes, prototype_indices, yaw, origin_z_before,
                      origin_z_after, ground_height, ground_gradient,
                      resolution=32, batch_size=512, cache=None):
    """Return per-body arrays and JSON-compatible aggregate exposure estimates.

    All per-instance scalar inputs have shape (N,); ``ground_gradient`` is
    (N,2), world-space (dz/dx,dz/dy). The identical supplied ground is used for
    both states. Body positions/IDs/shape/XY are not reconstructed or changed.
    ``origin_z_after = origin_z_before - retained_fine_overburden`` is a caller
    decision. Pass a PrototypeSampleCache to reuse samples across invocations.

    Before/after fields: exposed_footprint_area_m2, exposed_volume_m3,
    exposed_footprint_fraction, exposed_quadrature_volume_fraction. Fractions
    use the same quadrature's full body. ``solid_ledger`` is true mesh volume,
    independent of estimated exposure. Exposed volume may exceed true volume
    slightly because of quadrature; no volume-conserving normalization is used.
    """
    resolution = _resolution(resolution)
    if not isinstance(batch_size, (int, np.integer)) or isinstance(batch_size, (bool, np.bool_)) or not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be an integer from 1 through {MAX_BATCH_SIZE}")
    indices = np.asarray(prototype_indices)
    if indices.ndim != 1 or indices.dtype.kind not in "iu":
        raise ValueError("prototype_indices must be a one-dimensional integer array")
    count = len(indices)
    if count and (indices.min() < 0 or indices.max() >= len(prototypes)):
        raise ValueError("prototype index outside supplied bank")
    inputs = {}
    for name, value in (("yaw", yaw), ("origin_z_before", origin_z_before),
                        ("origin_z_after", origin_z_after), ("ground_height", ground_height)):
        array = np.asarray(value, dtype=np.float64)
        if array.shape != (count,) or not np.isfinite(array).all():
            raise ValueError(f"{name} must be a finite array of shape ({count},)")
        inputs[name] = array
    gradient = np.asarray(ground_gradient, dtype=np.float64)
    if gradient.shape != (count, 2) or not np.isfinite(gradient).all():
        raise ValueError(f"ground_gradient must be finite with shape ({count}, 2)")
    cache = PrototypeSampleCache() if cache is None else cache
    if not isinstance(cache, PrototypeSampleCache):
        raise TypeError("cache must be a PrototypeSampleCache")
    names = ("exposed_footprint_area_m2", "exposed_volume_m3",
             "exposed_footprint_fraction", "exposed_quadrature_volume_fraction")
    before = {key: np.zeros(count, dtype=np.float64) for key in names}
    after = {key: np.zeros(count, dtype=np.float64) for key in names}
    true_volume = np.zeros(count, dtype=np.float64)
    quad_volume = np.zeros(count, dtype=np.float64)
    true_area = np.zeros(count, dtype=np.float64)
    quad_area = np.zeros(count, dtype=np.float64)
    sample_counts = np.zeros(count, dtype=np.int32)
    peak_batch = 0
    for index in np.unique(indices):
        sample = cache.samples(prototypes[int(index)], resolution)
        bodies = np.flatnonzero(indices == index)
        true_volume[bodies] = sample.true_volume
        quad_volume[bodies] = sample.quadrature_volume
        true_area[bodies] = sample.true_footprint_area
        quad_area[bodies] = len(sample.xy) * sample.cell_area
        sample_counts[bodies] = len(sample.xy)
        for start in range(0, len(bodies), batch_size):
            ids = bodies[start:start + batch_size]
            peak_batch = max(peak_batch, len(ids))
            cosine, sine = np.cos(inputs["yaw"][ids]), np.sin(inputs["yaw"][ids])
            # Rotate the world plane gradient back into prototype XY, avoiding
            # allocations for every rotated world-space sample coordinate.
            gx, gy = gradient[ids, 0], gradient[ids, 1]
            local_gradient = np.column_stack((gx * cosine + gy * sine,
                                               -gx * sine + gy * cosine))
            plane_at_xy = local_gradient @ sample.xy.T + inputs["ground_height"][ids, None]
            for result, origin in ((before, "origin_z_before"), (after, "origin_z_after")):
                relative_plane = plane_at_xy - inputs[origin][ids, None]
                thickness = np.maximum(sample.top[None] - np.maximum(sample.bottom[None], relative_plane), 0)
                area = np.count_nonzero(thickness > 0, axis=1) * sample.cell_area
                volume = thickness.sum(axis=1) * sample.cell_area
                result["exposed_footprint_area_m2"][ids] = area
                result["exposed_volume_m3"][ids] = volume
                result["exposed_footprint_fraction"][ids] = area / quad_area[ids]
                result["exposed_quadrature_volume_fraction"][ids] = volume / quad_volume[ids]
    aggregate = {}
    for name, result in (("before", before), ("after", after)):
        aggregate[name] = {key: float(result[key].sum()) for key in names[:2]}
        aggregate[name]["bodies_with_estimated_exposure"] = int(np.count_nonzero(result["exposed_footprint_area_m2"]))
    aggregate["change_after_minus_before"] = {
        key: aggregate["after"][key] - aggregate["before"][key] for key in names[:2]
    }
    total_volume = float(true_volume.sum())
    total_area = float(true_area.sum())
    return {
        "method": METHOD,
        "limitations": LIMITS,
        "resolution": resolution,
        "body_count": count,
        "maximum_body_batch": peak_batch,
        "before": before,
        "after": after,
        "aggregate": aggregate,
        "solid_ledger": {
            "per_body_true_volume_m3": true_volume,
            "total_before_m3": total_volume,
            "total_after_m3": total_volume,
            "total_change_m3": 0.0,
            "meaning": "Unchanged explicit body solid; excludes any unallocated buried stock reserve.",
        },
        "quadrature_diagnostic": {
            "per_body_whole_volume_m3": quad_volume,
            "per_body_whole_footprint_m2": quad_area,
            "per_body_true_footprint_m2": true_area,
            "per_body_sample_count": sample_counts,
            "whole_volume_m3": float(quad_volume.sum()),
            "whole_volume_relative_error": float(quad_volume.sum() / total_volume - 1) if total_volume else 0.0,
            "whole_footprint_m2": float(quad_area.sum()),
            "true_footprint_m2": total_area,
            "whole_footprint_relative_error": float(quad_area.sum() / total_area - 1) if total_area else 0.0,
        },
    }
