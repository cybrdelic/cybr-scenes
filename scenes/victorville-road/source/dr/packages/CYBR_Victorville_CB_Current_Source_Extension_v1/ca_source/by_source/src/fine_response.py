"""Read-only, pure-NumPy pinned R5D fine-bed extraction and footprint moments.

No Blender, rendering, scene mutation, random field or particle enlargement.
The immutable NPZ's raw vertex color/height are extracted exactly. Optional
load_response also reproduces hash-pinned build_diagnostic vertex modifiers.
Blender procedural bump and interpolated mesh normals remain explicitly excluded.
"""
from __future__ import annotations

from dataclasses import dataclass
import argparse
import ast
import hashlib
import json
from pathlib import Path
import numpy as np

PINNED_SHA256 = '7a09007d50e444c28231fd30cddda185d2f01146f3b1a47b014ebd25c0b415c4'
PINNED_BYTES = 3913561
SIDE_M = .18
SOURCE_ROUGHNESS = .84
BUILDER_SHA256 = '320dd02e5ac661f4f9f3b470d614e0b3fb103614b0d2cd740aded5964ffa4246'


@dataclass(frozen=True)
class Source:
    height_m: np.ndarray
    color_linear: np.ndarray
    side_m: float
    sha256: str
    variant: str = 'pinned_raw'
    builder_sha256: str | None = None


@dataclass(frozen=True)
class Level:
    """Area-filtered first/second moments, on explicitly bounded footprints.

    slope_second channel order is xx, xy, yy. Colors are linear, not sRGB.
    Endpoints own half a native sample interval. Odd final rows/columns retain
    their true area instead of being duplicated, dropped or padded.
    """
    index: int
    area_m2: np.ndarray
    x_edges_m: np.ndarray
    y_edges_m: np.ndarray
    height_mean_m: np.ndarray
    color_mean: np.ndarray
    color_second: np.ndarray
    slope_mean: np.ndarray
    slope_second: np.ndarray


def read_pinned(path: str | Path) -> Source:
    path = Path(path)
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) != PINNED_BYTES or digest != PINNED_SHA256:
        raise ValueError('Pinned approved microbed bytes/hash differ')
    with np.load(path, allow_pickle=False) as f:
        if set(f.files) != {'height', 'color', 'side_m'}:
            raise ValueError('Unexpected pinned microbed schema')
        height, color, side = f['height'].copy(), f['color'].copy(), float(f['side_m'])
    if height.shape != (1101, 1101) or color.shape != (1101, 1101, 3) or side != SIDE_M:
        raise ValueError('Pinned shape/physical scale differ')
    if not np.isfinite(height).all() or not np.isfinite(color).all():
        raise ValueError('Nonfinite source')
    height.setflags(write=False)
    color.setflags(write=False)
    return Source(height, color, side, digest)


def load_response(microbed_path: str | Path, builder_path: str | Path) -> Source:
    """Evaluate exact pinned original fine-bed vertex modifiers, without bpy.

    Only the three pure NumPy functions noise/deposit/ground are extracted from
    the hash-pinned original builder. Its top-level Blender code is not run.
    The original mesh's float32 vertex and color storage is reproduced. Shader
    bump is deliberately excluded; no invented noise substitutes for it.
    """
    source = read_pinned(microbed_path)
    raw = Path(builder_path).read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != BUILDER_SHA256:
        raise ValueError('Original R5D builder differs from the audited source')
    tree = ast.parse(raw)
    selected = [q for q in tree.body if isinstance(q, ast.FunctionDef) and q.name in {'noise', 'deposit', 'ground'}]
    if {q.name for q in selected} != {'noise', 'deposit', 'ground'}:
        raise ValueError('Pinned pure source functions missing')
    env = {'np': np}
    exec(compile(ast.Module(body=selected, type_ignores=[]), '<pinned-r5d-pure-fields>', 'exec'), env)
    axis = np.linspace(-source.side_m / 2, source.side_m / 2, source.height_m.shape[0])
    # Identical per-node expressions in bounded row blocks: do not keep full
    # native coordinate/modulation temporaries live during scene adaptation.
    height = np.empty_like(source.height_m)
    color = np.empty_like(source.color_linear)
    for start in range(0, len(axis), 64):
        stop = min(start + 64, len(axis))
        xx, yy = np.meshgrid(axis, axis[start:stop])
        deposit = env['deposit'](xx, yy)
        height[start:stop] = env['ground'](xx, yy) + source.height_m[start:stop] * (.65 + .55 * (1 - deposit))
        variance = env['noise'](xx, yy, .003, 12)
        color[start:stop] = (source.color_linear[start:stop] * (1 + variance[..., None] * .06)
                            + deposit[..., None] * np.array([.013, .010, .006]))
    height.setflags(write=False)
    color.setflags(write=False)
    return Source(height, color, source.side_m, source.sha256,
                  variant='original_r5d_fines_vertex_payload_without_shader_bump', builder_sha256=digest)


def vertex_support_edges(count: int, side_m: float) -> np.ndarray:
    """Voronoi footprints of inclusive source nodes; finite, not periodic."""
    if count < 3 or not np.isfinite(side_m) or side_m <= 0:
        raise ValueError('At least three nodes and positive physical extent required')
    nodes = np.linspace(-side_m / 2, side_m / 2, count)
    return np.r_[nodes[0], (nodes[:-1] + nodes[1:]) * .5, nodes[-1]]


def native_level(height_m: np.ndarray, color_linear: np.ndarray, side_m: float) -> Level:
    height = np.asarray(height_m, dtype=np.float64)
    color = np.asarray(color_linear, dtype=np.float64)
    if height.ndim != 2 or min(height.shape) < 3 or color.shape != height.shape + (3,):
        raise ValueError('Expected HxW metric heights and HxWx3 linear color')
    if not np.isfinite(height).all() or not np.isfinite(color).all():
        raise ValueError('Finite arrays required')
    ny, nx = height.shape
    xe, ye = vertex_support_edges(nx, side_m), vertex_support_edges(ny, side_m)
    # Source array row increases in +world Y, column in +world X. No image flip.
    sy, sx = np.gradient(height, side_m / (ny - 1), side_m / (nx - 1), edge_order=2)
    slope = np.stack((sx, sy), axis=-1)
    second = np.stack((sx * sx, sx * sy, sy * sy), axis=-1)
    area = np.diff(ye)[:, None] * np.diff(xe)[None, :]
    return Level(0, area, xe, ye, height.copy(), color.copy(), color * color, slope, second)


def reduce_sum_2x2(array: np.ndarray) -> np.ndarray:
    a = np.asarray(array)
    return np.add.reduceat(np.add.reduceat(a, np.arange(0, a.shape[0], 2), axis=0),
                           np.arange(0, a.shape[1], 2), axis=1)


def coarsen(level: Level) -> Level:
    if level.area_m2.shape == (1, 1):
        raise ValueError('Already at root footprint')
    weights = level.area_m2
    area = reduce_sum_2x2(weights)

    def mean(a):
        w = weights[..., None] if a.ndim == 3 else weights
        denom = area[..., None] if a.ndim == 3 else area
        return reduce_sum_2x2(a * w) / denom

    def edges(e):
        ids = np.unique(np.r_[np.arange(0, len(e) - 1, 2), len(e) - 1])
        return e[ids]

    return Level(level.index + 1, area, edges(level.x_edges_m), edges(level.y_edges_m),
                 mean(level.height_mean_m), mean(level.color_mean), mean(level.color_second),
                 mean(level.slope_mean), mean(level.slope_second))


def slope_covariance(level: Level) -> np.ndarray:
    mean, second = level.slope_mean, level.slope_second
    xx = second[..., 0] - mean[..., 0] ** 2
    xy = second[..., 1] - mean[..., 0] * mean[..., 1]
    yy = second[..., 2] - mean[..., 1] ** 2
    cov = np.empty(level.area_m2.shape + (2, 2), dtype=np.float64)
    cov[..., 0, 0], cov[..., 1, 1] = xx, yy
    cov[..., 0, 1] = cov[..., 1, 0] = xy
    if np.linalg.eigvalsh(cov).min() < -1e-11:
        raise ValueError('Invalid negative footprint variance')
    return cov


def footprint_statistics(level: Level) -> dict:
    """NDF-neutral moments, plus a DECLARED Beckmann moment equivalent.

    A Gaussian/Beckmann slope model has E[sx^2]=alpha_x^2/2. Thus sqrt(trace(C))
    is its isotropic alpha equivalent, not a Blender/GGX roughness value. GGX
    does not have a finite unrestricted second slope moment; do not silently
    add this value to Principled roughness or call that exact variance filtering.
    """
    cov = slope_covariance(level)
    variances = np.maximum(np.linalg.eigvalsh(cov), 0.)
    unresolved = variances.sum(axis=-1)
    area = level.area_m2
    total_area = float(area.sum())

    def avg(a):
        return np.sum(a * (area[..., None] if a.ndim == 3 else area), axis=(0, 1)) / total_area

    resolved = np.sum(level.slope_mean ** 2, axis=-1)
    total = level.slope_second[..., 0] + level.slope_second[..., 2]
    global_mean = avg(level.slope_mean)
    second_rgb = avg(level.color_second)
    mean_rgb = avg(level.color_mean)
    out = {
        'level': level.index, 'shape_yx': list(area.shape), 'total_area_m2': total_area,
        'footprint_width_x_m_min_max': [float(np.diff(level.x_edges_m).min()), float(np.diff(level.x_edges_m).max())],
        'footprint_width_y_m_min_max': [float(np.diff(level.y_edges_m).min()), float(np.diff(level.y_edges_m).max())],
        'global_linear_color_mean': mean_rgb.tolist(),
        'global_linear_color_variance': np.maximum(second_rgb - mean_rgb * mean_rgb, 0.).tolist(),
        'global_slope_mean_xy': global_mean.tolist(),
        'source_slope_second_moment_mean': float(avg(total)),
        'resolved_mean_slope_energy': float(avg(resolved)),
        'unresolved_slope_variance_mean': float(avg(unresolved)),
        'rms_total_slope': float(np.sqrt(avg(total))),
        'rms_resolved_slope': float(np.sqrt(avg(resolved))),
        'rms_unresolved_slope': float(np.sqrt(avg(unresolved))),
        'moment_energy_residual': float(avg(total) - avg(resolved) - avg(unresolved)),
        'beckmann_isotropic_equivalent_alpha_rms': float(np.sqrt(avg(unresolved))),
        'source_principled_roughness_retained': SOURCE_ROUGHNESS,
        'roughness_conversion': 'No GGX/Principled conversion applied; preserve first and second moments for an explicitly selected renderer filter.',
    }
    return out


def iter_levels(height_m, color_linear, side_m):
    level = native_level(height_m, color_linear, side_m)
    while True:
        yield level
        if level.area_m2.shape == (1, 1):
            return
        level = coarsen(level)


def source_report(path: str | Path, builder_path: str | Path | None = None) -> dict:
    source = read_pinned(path) if builder_path is None else load_response(path, builder_path)
    stats = [footprint_statistics(level) for level in iter_levels(source.height_m, source.color_linear, source.side_m)]
    if any(abs(q['moment_energy_residual']) > 1e-11 for q in stats):
        raise AssertionError('Footprint moment energy not preserved')
    return {
        'input_sha256': source.sha256, 'input_bytes': PINNED_BYTES,
        'response_variant': source.variant, 'original_builder_sha256': source.builder_sha256,
        'side_m': source.side_m, 'native_shape_yx': list(source.height_m.shape),
        'native_node_pitch_m': source.side_m / (source.height_m.shape[0] - 1),
        'response_height_range_m': [float(source.height_m.min()), float(source.height_m.max())],
        'nominal_granule_cell_pitch_m': float(np.sqrt(.18 * .18 / 112000)),
        'coordinate_convention': 'row +world Y; column +world X; inclusive [-0.09,+0.09] metre nodes',
        'filter': '2x2 area-weighted first and second moments; endpoint half support; no periodic wrap or image resize',
        'levels': stats,
        'limitations': [
            'pinned_raw is the exact NPZ payload; the original_r5d_fines variant applies the pinned builder height/color modifiers with original float32 storage.',
            'Original fine shader adds Blender noise scale 9200, detail 2, roughness .7, Bump distance 15 micrometres, strength .6. This helper does not approximate that shader with new noise.',
            'Finite-difference slopes of the stored field, not the exact Blender smoothed triangle normals or complete rendered BRDF.',
            'The source patch is not declared periodic. A shader consumer needs consistent source-derived seam handling and coordinates.',
            'Native sample variance starts at zero; sub-node relief and shader bump variance are not recovered.',
            'Mip footprints are actual finite supports with odd edge cells. A GPU texture consumer must respect explicit bounds rather than treating these as an unqualified regular mip chain.',
            'No blend file, pipeline, approved source/cache, particle placement, render setting, or scene graph is changed.',
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('microbed', type=Path)
    parser.add_argument('--builder', type=Path, help='Evaluate original fine-bed vertex modifiers from the exact pinned R5D builder')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        raise FileExistsError('Refusing to overwrite a report')
    args.report.write_text(json.dumps(source_report(args.microbed, args.builder), indent=2) + '\n')


if __name__ == '__main__':
    main()
