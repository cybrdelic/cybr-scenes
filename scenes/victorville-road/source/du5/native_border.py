"""Integer native-camera crops with explicit Blender float32 edge qualification.

Bounds are [xmin, xmax, ymin, ymax], bottom-left origin, upper edges exclusive.
No camera, resolution, geometry, filtering or image resizing is performed.
"""
import math
import struct

VERSION = 2

def float32(value):
    return struct.unpack('!f', struct.pack('!f', value))[0]

def pixel_edge(pixel, extent):
    """Nearest float32 at/above the exact edge, valid for float/double products."""
    if type(extent) is not int or not 1 <= extent <= 65536:
        raise ValueError('Native resolution must be an integer in [1, 65536]')
    if type(pixel) is not int or not 0 <= pixel <= extent:
        raise ValueError('Pixel edge must be an integer inside the projection')
    value = float32(pixel / extent)
    # Blender RNA stores a float32. Blender builds may evaluate the subsequent
    # resolution multiplication in float32 or double; admit only a common cell.
    for _ in range(4):
        cells = (math.floor(value * extent), math.floor(float32(value * extent)))
        if cells == (pixel, pixel):
            return value
        if any(cell > pixel for cell in cells):
            break
        bits = struct.unpack('!I', struct.pack('!f', value))[0]
        value = struct.unpack('!f', struct.pack('!I', bits + 1))[0]
    raise ValueError('Cannot represent the requested native pixel edge safely')

def pixel_bounds(job, width, height):
    sizes = (width, width, height, height)
    # Validate resolution even when a malformed job has no useful bounds.
    for size in (width, height):
        pixel_edge(0, size)
    bounds = job.get('render_border_pixels')
    if bounds is not None:
        if not isinstance(bounds, (list, tuple)) or len(bounds) != 4:
            raise ValueError('render_border_pixels must contain four integer edges')
        bounds = list(bounds)
        for value, size in zip(bounds, sizes):
            pixel_edge(value, size)
    if 'render_border' in job:
        legacy = job['render_border']
        if not isinstance(legacy, (list, tuple)) or len(legacy) != 4:
            raise ValueError('Legacy render_border must contain four normalized edges')
        if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in legacy):
            raise ValueError('Invalid normalized border')
        scaled = [v * size for v, size in zip(legacy, sizes)]
        if any(abs(v - round(v)) > 1e-6 for v in scaled):
            raise ValueError('Legacy border must align with integer pixel edges')
        converted = list(map(round, scaled))
        if bounds is not None and bounds != converted:
            raise ValueError('Conflicting integer and normalized borders')
        bounds = converted
    if bounds is None:
        raise ValueError('An explicit native border is required')
    if not (bounds[0] < bounds[1] and bounds[2] < bounds[3]):
        raise ValueError('Native border must have positive width and height')
    return bounds

def configure(scene, job, width, height):
    """Set and read back actual RNA floats; fail before rendering on disagreement."""
    bounds = pixel_bounds(job, width, height)
    sizes = (width, width, height, height)
    normalized = [pixel_edge(value, size) for value, size in zip(bounds, sizes)]
    render = scene.render
    if (render.resolution_x, render.resolution_y, render.resolution_percentage) != (width, height, 100):
        raise ValueError('Native crop requires the declared full projection at 100 percent')
    keys = ('border_min_x', 'border_max_x', 'border_min_y', 'border_max_y')
    for key, value in zip(keys, normalized):
        setattr(render, key, value)
    stored = [getattr(render, key) for key in keys]
    resolved = [math.floor(v * size) for v, size in zip(stored, sizes)]
    resolved_f32 = [math.floor(float32(v * size)) for v, size in zip(stored, sizes)]
    if stored != normalized or resolved != bounds or resolved_f32 != bounds:
        raise ValueError('Blender RNA did not preserve the requested native pixel bounds')
    render.use_border = True
    render.use_crop_to_border = True
    cropped = [bounds[1] - bounds[0], bounds[3] - bounds[2]]
    return (*cropped, {'native_border_version': VERSION,
        'full_projection_resolution': [width, height],
        'native_pixel_bounds_xy': bounds, 'normalized_bounds': stored,
        'exact_edge_ratios': [v / size for v, size in zip(bounds, sizes)],
        'RNA_float32_pixel_bounds_xy': resolved_f32,
        'output_resolution': cropped, 'camera_geometry_material_scale_changed': False})
