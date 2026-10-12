"""Pure NumPy helpers for a bounded, original-asphalt interior specimen.

No bpy import, scene changes, network access, or renders occur in this module.
The input grid is the original row-major, +Y road mesh from the R6 builder.
"""
from __future__ import annotations
import numpy as np

TILE_M = 0.25
HEIGHT_SCALE_M = 0.004
HEIGHT_SHA256 = "9c6ebba3a109088842a73434cea02069aa3a5a98e1b871a3f7b7b5e246de0c83"


def smoothstep(a, b, value):
    t = np.clip((np.asarray(value) - a) / (b - a), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def sample_height(height_top_down, xy):
    """Metres, exact source midlevel/amplitude, periodic world XY / 0.25.

    PNG rows and GeometryHeight source rows run downward. Blender image V and
    world Y run upward. The geometry file includes the duplicated wrap endpoint:
    reversing its rows and sampling indices fract(XY / tile) * (N - 1) matches
    the original specimen's g[::-1], without an additional half-texel shift.
    """
    g = np.asarray(height_top_down)
    if g.ndim != 2 or g.shape[0] != g.shape[1] or g.shape[0] < 3:
        raise ValueError("Expected a square periodic vertex grid with duplicate endpoints")
    if not np.isfinite(g).all():
        raise ValueError("Height field contains non-finite values")
    if not (np.allclose(g[0], g[-1], atol=1e-7, rtol=0)
            and np.allclose(g[:, 0], g[:, -1], atol=1e-7, rtol=0)):
        raise ValueError("Periodic endpoints are inconsistent")
    n = len(g) - 1
    uv = np.mod(np.asarray(xy, dtype=np.float64) / TILE_M, 1.0) * n
    ij = np.floor(uv).astype(np.int64)
    f = uv - ij
    ix, iy = ij[:, 0], ij[:, 1]
    fx, fy = f[:, 0], f[:, 1]
    up = g[::-1]
    h = ((up[iy, ix] * (1-fx) + up[iy, ix+1] * fx) * (1-fy)
         + (up[iy+1, ix] * (1-fx) + up[iy+1, ix+1] * fx) * fy)
    return (h - 0.5) * HEIGHT_SCALE_M


def grid_shape(co):
    """Validate the source road's strictly row-major rectangular topology."""
    co = np.asarray(co)
    # A row has exactly one y; authoring stores all vertices as float32.
    nx = int(np.flatnonzero(co[:, 1] != co[0, 1])[0])
    if len(co) % nx:
        raise ValueError("Road vertices are not a complete row-major grid")
    ny = len(co) // nx
    g = co.reshape(ny, nx, 3)
    if not np.all(g[:, :, 1] == g[:, :1, 1]):
        raise ValueError("Road rows have inconsistent Y")
    if not (np.all(np.diff(g[:, 0, 1]) > 0) and np.all(np.diff(g[:, :, 0], axis=1) > 0)):
        raise ValueError("Road grid is not monotonic")
    return ny, nx


def patch_indices(co, bounds, minimum_inset_m=0.20):
    """Resolve a rectangle outward to existing row/column edges, fail at contact."""
    ny, nx = grid_shape(co)
    grid = np.asarray(co).reshape(ny, nx, 3)
    xmin, xmax, ymin, ymax = map(float, bounds)
    if not (xmin < xmax and ymin < ymax):
        raise ValueError("Bounds must be xmin < xmax and ymin < ymax")
    ys = grid[:, 0, 1]
    j0 = int(np.searchsorted(ys, ymin, side='right') - 1)
    j1 = int(np.searchsorted(ys, ymax, side='left'))
    if j0 < 1 or j1 >= ny - 1:
        raise ValueError("Patch cannot reach the road's longitudinal boundary")
    rows = grid[j0:j1+1]
    i0 = min(int(np.searchsorted(row[:, 0], xmin, side='right') - 1) for row in rows)
    i1 = max(int(np.searchsorted(row[:, 0], xmax, side='left')) for row in rows)
    if i0 < 1 or i1 >= nx - 1:
        raise ValueError("Patch cannot reach the physical asphalt boundary")
    if i1-i0 < 4 or j1-j0 < 4:
        raise ValueError("Patch needs at least four source cells per axis")
    inset = min(float(np.min(rows[:, i0, 0]-rows[:, 0, 0])),
                float(np.min(rows[:, -1, 0]-rows[:, i1, 0])))
    if inset < minimum_inset_m:
        raise ValueError(f"Patch is only {inset:.4f} m from contact; need {minimum_inset_m:.3f} m")
    return j0, j1, i0, i1


def sample_grid(co, nx, uv, diagonal_ac=None):
    """Return source IDs and weights using its actual piecewise-linear triangles.

    uv is in source column/row units. diagonal_ac marks the source quad's 0–2
    diagonal; false means its 1–3 diagonal. Interpolation is never smoothing.
    """
    co = np.asarray(co)
    uv = np.asarray(uv, dtype=np.float64)
    ny = len(co) // nx
    ix = np.clip(np.floor(uv[:, 0]).astype(np.int64), 0, nx-2)
    iy = np.clip(np.floor(uv[:, 1]).astype(np.int64), 0, ny-2)
    x, y = uv[:, 0]-ix, uv[:, 1]-iy
    q = iy * nx + ix
    ids = np.column_stack((q, q+1, q+nx+1, q+nx))
    ac = np.ones(len(uv), dtype=bool) if diagonal_ac is None else diagonal_ac[iy, ix]
    weights = np.empty((len(uv), 4), dtype=np.float64)
    mask = ac & (x >= y)
    weights[mask] = np.column_stack((1-x[mask], x[mask]-y[mask], y[mask], np.zeros(mask.sum())))
    mask = ac & (x < y)
    weights[mask] = np.column_stack((1-y[mask], np.zeros(mask.sum()), x[mask], y[mask]-x[mask]))
    mask = ~ac & (x+y <= 1)
    weights[mask] = np.column_stack((1-x[mask]-y[mask], x[mask], np.zeros(mask.sum()), y[mask]))
    mask = ~ac & (x+y > 1)
    weights[mask] = np.column_stack((np.zeros(mask.sum()), 1-y[mask], x[mask]+y[mask]-1, 1-x[mask]))
    return ids, weights, iy*(nx-1)+ix


def interpolate(values, ids, weights, discrete=False):
    values = np.asarray(values)
    if discrete:
        return values[ids[np.arange(len(ids)), np.argmax(weights, axis=1)]]
    return np.einsum('ni,ni...->n...', weights, values[ids])


def zipper(a, b, ta=None, tb=None):
    """Triangulate a strip between parallel polylines sharing parameter direction.

    The result has no T junctions even when one side has far more segments.
    Face orientation is corrected once in build_patch from actual XY positions.
    """
    if ta is None:
        ta = np.linspace(0, 1, len(a))
    if tb is None:
        tb = np.linspace(0, 1, len(b))
    result = []
    i = j = 0
    while i < len(a)-1 or j < len(b)-1:
        if i < len(a)-1 and (j == len(b)-1 or ta[i+1] <= tb[j+1]):
            result.append((a[i], a[i+1], b[j]))
            i += 1
        else:
            result.append((a[i], b[j+1], b[j]))
            j += 1
    return np.asarray(result, dtype=np.int32)


def build_patch(co, indices, spacing_m, max_new_vertices, diagonal_ac=None):
    """New dense interior plus zero-relief collar, with exact old boundary IDs.

    The new grid is a source-cell inset from the replaced rectangle. No new
    vertices occur on the old/fine seam. Caller displaces only dense vertices,
    using an envelope that is exactly zero on every dense-grid boundary.
    """
    co = np.asarray(co, dtype=np.float64)
    ny, nx = grid_shape(co)
    j0, j1, i0, i1 = indices
    u0, u1, v0, v1 = i0+1, i1-1, j0+1, j1-1
    g = co.reshape(ny, nx, 3)
    width = float(np.max(g[j0:j1+1, u1, 0] - g[j0:j1+1, u0, 0]))
    height = float(g[v1, 0, 1]-g[v0, 0, 1])
    ncols = int(np.ceil(width / spacing_m)) + 1
    nrows = int(np.ceil(height / spacing_m)) + 1
    if ncols*nrows > max_new_vertices:
        raise ValueError(f"Patch needs {ncols*nrows:,} new vertices; cap is {max_new_vertices:,}. Shrink bounds; do not enlarge grain scale.")
    # This scene uses uniform source column fractions. Use source coordinates
    # for X, but physical Y so source LOD changes cannot undersample relief.
    u = np.linspace(u0, u1, ncols)
    yy = np.linspace(g[v0, 0, 1], g[v1, 0, 1], nrows)
    v = np.interp(yy, g[:, 0, 1], np.arange(ny))
    uu, vv = np.meshgrid(u, v)
    uv = np.column_stack((uu.ravel(), vv.ravel()))
    ids, weights, source_face = sample_grid(co, nx, uv, diagonal_ac)
    base = interpolate(co, ids, weights)
    off = len(co)
    fine = np.arange(off, off+len(base), dtype=np.int32).reshape(nrows, ncols)
    q = fine[:-1, :-1].ravel()
    triangles = np.concatenate((np.column_stack((q, q+1, q+ncols+1)),
                                np.column_stack((q, q+ncols+1, q+ncols))))
    boundary = [np.arange(j0*nx+i0, j0*nx+i1+1),
                np.arange(j0*nx+i1, (j1+1)*nx+i1, nx),
                np.arange(j1*nx+i0, j1*nx+i1+1),
                np.arange(j0*nx+i0, (j1+1)*nx+i0, nx)]
    inner = [fine[0], fine[:, -1], fine[-1], fine[:, 0]]
    strips = [zipper(a, b) for a, b in zip(boundary, inner)]
    triangles = np.concatenate([triangles, *strips]).astype(np.int32)
    allco = np.concatenate((co, base))
    tri = allco[triangles, :2]
    signed = ((tri[:, 1, 0]-tri[:, 0, 0])*(tri[:, 2, 1]-tri[:, 0, 1])
              -(tri[:, 1, 1]-tri[:, 0, 1])*(tri[:, 2, 0]-tri[:, 0, 0]))
    if np.any(np.abs(signed) < 1e-16):
        raise ValueError("Degenerate transition face")
    triangles[signed < 0] = triangles[signed < 0, ::-1]
    # Envelope distance is measured inside the fine rectangle, so no relief is
    # fed into the thin/fan triangles of the coarse transition collar.
    b = base.reshape(nrows, ncols, 3)
    dx = np.minimum(b[:, :, 0] - b[:, :1, 0], b[:, -1:, 0] - b[:, :, 0])
    dy = np.minimum(b[:, :, 1] - b[:1, :, 1], b[-1:, :, 1] - b[:, :, 1])
    edge_distance = np.minimum(dx, dy).ravel()
    removed = np.zeros((ny-1, nx-1), dtype=bool)
    removed[j0:j1, i0:i1] = True
    return dict(base=base, ids=ids, weights=weights, source_face=source_face,
                triangles=triangles, remove_faces=removed.ravel(),
                edge_distance=edge_distance, fine_shape=(nrows, ncols),
                inner_vertex_ids=np.unique(np.concatenate(inner)),
                outer_vertex_ids=np.unique(np.concatenate(boundary)))


def footprint_weight(points, view_projection, width, height, height_extent_m,
                     fade_pixels=(0.3, 0.9)):
    """Fade by the projected pixel size of the original peak-to-valley relief.

    This is camera-specific LOD. It changes no physical tile size or height
    scale; away from the footprint plateau the geometry contribution fades.
    """
    points = np.asarray(points, dtype=np.float64)
    p = np.column_stack((points, np.ones(len(points))))
    top = p.copy()
    top[:, 2] += height_extent_m
    a, b = p @ np.asarray(view_projection).T, top @ np.asarray(view_projection).T
    front = (a[:, 3] > 1e-6) & (b[:, 3] > 1e-6)
    wa, wb = np.where(front, a[:, 3], 1), np.where(front, b[:, 3], 1)
    delta = ((b[:, :2] / wb[:, None] - a[:, :2] / wa[:, None])
             * np.array([width/2, height/2]))
    pixels = np.linalg.norm(delta, axis=1)
    return np.where(front, smoothstep(*fade_pixels, pixels), 0), pixels
