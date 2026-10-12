"""Authored roof construction inside retained source footprints and heights.

Source roof shape, colour and material tags are distinct from inferred finishes.
The regional tier uses area-integrated colour and mean roughness, not enlarged
microstructure. Physical concrete/mineral fields are retained for closer views.
"""
from pathlib import Path
import collections
import hashlib
import json
import sys

r = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(r / p) for p in ['geo-deps', 'work/iv-component-runtime',
    'work/cybr-iv-full/src', 'whole-iv-vendor', 'original/cybr-material-concrete']]
import numpy as np
import shapely
from scipy.optimize import lsq_linear
from cybr_light import Scene
from cybr_light.finishing import read_pfm
from cybr_terrain.materials import write_pfm
from cybr_ucsb.geometry import triangulate_polygon
from cybr_ucsb.ingest import polygons
from iv_mesh_parts import Parts
from mineral_construction_bounded import construction

out = r / 'evidence/full-iv-regional-roofs'
out.mkdir(exist_ok=True)
textures = out / 'textures'
textures.mkdir(exist_ok=True)
audit = json.loads((out / 'RETAINED_ROOF_AUDIT.json').read_text())
assert audit['passed']
data = np.load(out / 'retained_roof_faces.npz')
q, ids = data['vertices'], data['material_object']
by_source = {x['source_id']: x for x in audit['buildings_detail']}
day = json.loads((r / 'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text())
matrix = np.asarray(day['native_basis_to_linear_rgb'])
white = matrix @ np.ones(3)

def native(rgb):
    fit = lsq_linear(matrix / white[:, None], np.asarray(rgb), bounds=(0, .93), tol=1e-12)
    assert fit.success
    return fit.x

spec = {'id': '35_cement_paste', 'family': 'Cement paste', 'finish': 'paste',
        'tile_m': .32, 'height_scale_m': .0014, 'seed': 2090,
        'roughness': .72, 'color': [.52, .51, .47]}
fields, concrete_report = construction(spec, 512)
assert concrete_report['clipped_height_pixels'] == 0
srgb = fields['BaseColor']
linear = np.where(srgb <= .04045, srgb / 12.92, ((srgb + .055) / 1.055) ** 2.4)
controls = (linear * white) @ np.linalg.inv(matrix).T
assert controls.min() >= 0 and controls.max() <= 1
height = (fields['Height'] - .5) * spec['height_scale_m']
for name, array in [('cement_colour_native', controls),
                    ('cement_height_metres', np.repeat(height[:, :, None], 3, axis=2)),
                    ('cement_roughness', np.repeat(fields['Roughness'][:, :, None], 3, axis=2))]:
    write_pfm(textures / (name + '.pfm'), array.astype('f4'))
asphalt = r / 'evidence/full-iv-materials'
granule_controls = read_pfm(asphalt / 'asphalt_color_native.pfm')
granule_height = read_pfm(asphalt / 'asphalt_height_metres.pfm')[:, :, 0] * .35
granule_roughness = read_pfm(asphalt / 'asphalt_roughness.pfm')[:, :, 0]
# Geometry and relief are scaled together for an authored bonded roofing
# granule field. This is not the selected road fracture recipe or a product.
for name, array in [('mineral_colour_relative', granule_controls / granule_controls.mean((0, 1))),
                    ('mineral_height_metres', np.repeat(granule_height[:, :, None], 3, axis=2)),
                    ('mineral_roughness', np.repeat(granule_roughness[:, :, None], 3, axis=2))]:
    write_pfm(textures / (name + '.pfm'), array.astype('f4'))

family = {
    'cementitious': {'rgb': linear.mean((0, 1)).tolist(), 'roughness': float(fields['Roughness'].mean()), 'period_m': .32},
    'bonded_mineral': {'rgb': [.105, .111, .108], 'roughness': float(granule_roughness.mean()), 'period_m': .0875},
    'light_membrane': {'rgb': [.57, .58, .55], 'roughness': .74, 'period_m': None},
    'fired_tile': {'rgb': [.28, .105, .055], 'roughness': .78, 'period_m': None},
}
s = Scene()
s.materials = 192
material_cache = {}

def material(kind, colour=None, shade=1):
    key = (kind, colour or '', round(shade, 4))
    if key in material_cache:
        return material_cache[key]
    target = np.array(family[kind]['rgb'])
    if colour:
        names = {'white': '#ffffff', 'grey': '#808080', 'gray': '#808080', 'silver': '#c0c0c0',
                 'brown': '#805b40', 'red': '#a64b37', 'black': '#242424'}
        value = names.get(str(colour).lower(), str(colour))
        assert len(value) == 7 and value.startswith('#'), value
        rgb = np.array([int(value[i:i + 2], 16) / 255 for i in [1, 3, 5]])
        target = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
        target *= min(1, .78 / max(target.max(), 1e-9))
    result = s.material('plastic', native(target * shade), rough=family[kind]['roughness'], ior=1.5)
    material_cache[key] = result
    return result

coping = s.material('plastic', native([.34, .35, .335]), rough=.67, ior=1.5)
fascia = s.material('plastic', native([.33, .32, .29]), rough=.81, ior=1.5)
parts = Parts(out / 'regional_roofs.clm', 15100000)
records = []
max_height_error = 0.
max_plan_error = 0.
replacements = collections.defaultdict(list)

def seed(source):
    return int.from_bytes(hashlib.sha256((source + ':roof-construction-v1').encode()).digest()[:8], 'little')

def chart(xyz, origin, u, normal):
    u = u - normal * np.dot(u, normal)
    u /= np.linalg.norm(u)
    v = np.cross(normal, u)
    return np.c_[(xyz - origin) @ u, (xyz - origin) @ v]

def surface(name, poly, zfn, mat, source, estimate, origin, u):
    xy, faces = triangulate_polygon(poly)
    z = np.asarray(zfn(xy))
    xyz = np.c_[xy, z]
    normal = np.cross(xyz[faces[0, 1]] - xyz[faces[0, 0]], xyz[faces[0, 2]] - xyz[faces[0, 0]])
    normal /= np.linalg.norm(normal)
    if normal[2] < 0:
        normal = -normal
    parts.mesh(name, xyz, faces, mat, source, estimate, uv=chart(xyz, origin, u, normal), drop_zero_projected_area=True)
    return xyz

for source_id, row in by_source.items():
    props = row['source_properties']
    supplied = props.get('roof:material')
    colour = props.get('roof:colour', props.get('roof:color'))
    pitched = row['max_slope_normal_xy'] > .04
    building_type = props.get('building', 'unspecified')
    if supplied == 'concrete':
        kind, basis = 'cementitious', 'Explicit concrete tag; trowelled cementitious finish is authored.'
    elif supplied == 'roof_tiles':
        kind, basis = 'fired_tile', 'Explicit roof-tile tag; fired body finish is authored and tile composition is not measured.'
    elif pitched:
        kind, basis = 'bonded_mineral', 'Authored mineral covering on retained pitched form; source does not establish covering.'
    elif building_type in {'apartments', 'retail', 'school', 'university', 'commercial', 'office', 'industrial', 'church'} or row['area_m2'] > 350:
        kind, basis = 'light_membrane', 'Authored low-slope sheet finish selected by mapped building type or large roof area.'
    else:
        kind, basis = 'bonded_mineral', 'Authored mineral cap-sheet finish on retained low-slope form.'
    rng = np.random.default_rng(seed(source_id))
    # A bounded weathering tone, explicitly estimated, does not change the
    # construction family selected from shape/type. Tagged colours are retained.
    shade = 1. if colour else float(np.round(rng.uniform(.84, 1.04), 2))
    mat = material(kind, colour, shade)
    construction_counts = collections.Counter()
    start = parts.writer.triangles
    for obj in row['objects']:
        selected = q[ids[:, 1] == obj]
        xyz = selected[:, :, :3].astype(float)
        lo = xyz.reshape(-1, 3).min(0)
        hi = xyz.reshape(-1, 3).max(0)
        normal = selected[:, :, 3:6].mean((0, 1))
        normal /= np.linalg.norm(normal)
        poly = shapely.union_all(shapely.polygons(xyz[:, :, :2]))
        poly = shapely.make_valid(poly)
        assert poly.area > 0
        rect = np.asarray(poly.minimum_rotated_rectangle.exterior.coords)[:4]
        edges = np.roll(rect, -1, axis=0) - rect
        axis = edges[np.argmax(np.linalg.norm(edges, axis=1))]
        axis /= np.linalg.norm(axis)
        u = np.r_[axis, 0.]
        origin = np.r_[rect.mean(0), lo[2]]
        use_parapet = hi[2] - lo[2] < .002 and poly.area > 35 and (
            kind in {'cementitious', 'light_membrane'} or (building_type in {'yes', 'unspecified'} and poly.area > 180))
        name = source_id.replace(':', '_') + '_' + str(obj)
        estimate = 'Retained roof footprint and upper height envelope; construction dimensions and finish are authored estimates.'
        generated_xyz = []
        if use_parapet:
            inner = poly.buffer(-.20, join_style='mitre')
            if inner.is_empty or inner.area < poly.area * .45:
                use_parapet = False
        if use_parapet:
            top = float(hi[2])
            limits = np.asarray(poly.bounds)
            width = max(limits[2] - limits[0], 1.)
            fall = min(.14, width / 100.)
            def deck_z(xy):
                return top - .26 - fall * (xy[:, 0] - limits[0]) / width
            ring = poly.difference(inner)
            for index, polygon in enumerate(polygons(ring)):
                generated_xyz.append(surface(name + '_coping_' + str(index), polygon,
                    lambda xy: np.full(len(xy), top), coping, source_id, estimate, origin, u))
            for index, polygon in enumerate(polygons(inner)):
                generated_xyz.append(surface(name + '_deck_' + str(index), polygon, deck_z, mat, source_id, estimate, origin, u))
                for ring_index, boundary in enumerate([polygon.exterior, *polygon.interiors]):
                    points = np.asarray(boundary.coords)[:, :2]
                    for edge_index, (a, b) in enumerate(zip(points[:-1], points[1:])):
                        low = deck_z(np.vstack([a, b]))
                        vv = np.array([[*a, low[0]], [*b, low[1]], [*b, top], [*a, top]])
                        tangent = np.r_[b - a, 0.]
                        tangent /= np.linalg.norm(tangent)
                        uv = np.c_[(vv - vv[0]) @ tangent, vv[:, 2] - low[0]]
                        parts.mesh(name + f'_inner_flashing_{index}_{ring_index}_{edge_index}', vv,
                            [[0, 1, 2], [0, 2, 3]], mat, source_id, estimate, uv=uv)
                        generated_xyz.append(vv)
            max_plan_error = max(max_plan_error, abs(ring.area + inner.area - poly.area))
            construction_counts['inset_deck_with_coping'] += 1
        else:
            vv = xyz.reshape(-1, 3)
            ff = np.arange(len(vv)).reshape(-1, 3)
            # Each retained facet is charted in its own metric tangent plane.
            uv = chart(vv, origin, u, normal)
            parts.mesh(name + '_retained_covering', vv, ff, mat, source_id, estimate,
                uv=uv, normals=selected[:, :, 3:6].reshape(-1, 3))
            generated_xyz.append(vv)
            construction_counts['retained_roof_form'] += 1
        generated = np.concatenate(generated_xyz)
        max_height_error = max(max_height_error, max(0., float(generated[:, 2].max() - hi[2])))
        assert generated[:, 2].max() <= hi[2] + 1e-6
        assert np.all(generated[:, :2].min(0) >= lo[:2] - 1e-5)
        assert np.all(generated[:, :2].max(0) <= hi[:2] + 1e-5)
        replacements[audit['objects'][str(obj)]['mesh']].append(obj)
    records.append({'source_id': source_id, 'source_roof_shape': props.get('roof:shape'),
        'source_roof_material': supplied, 'source_roof_colour': colour,
        'source_building_type': building_type, 'source_height_method': props.get('height_method'),
        'authored_finish': kind, 'assignment_basis': basis, 'authored_weathering_tone': shade,
        'construction': dict(construction_counts), 'triangles': parts.writer.triangles - start,
        'old_roof_objects': row['objects'], 'native_material': mat})
report = parts.close()
assert report['triangles'] < 250000
assert max_height_error < 1e-6 and max_plan_error < .001
s.save(out / 'materials.cys')
report.update(material_offset=192, material_count=s.materials - 192,
    replace_by_mesh=dict(replacements), buildings=records,
    source_buildings_preserved=len(records), maximum_height_increase_m=max_height_error,
    maximum_projected_partition_error_m2=max_plan_error,
    context_material_families=family, concrete_recipe=spec, concrete_evaluation=concrete_report,
    material_source_commit='12848c82f60bc58fa88640545868009b90298b32',
    context_sampling='Cement uses the original field area-mean colour and roughness. Bonded mineral uses the retained relative field with an authored roof reflectance target and area-mean roughness. Membrane and fired-tile colours/roughness are authored constants, not recovered catalogue fields. No point-sampled millimetric texture or bump in this regional tier. Mean roughness is an explicit approximation, not a qualified filtered BRDF.',
    physical_field_contract={'cement_period_m': .32, 'mineral_period_m': .0875,
        'mineral_scale_relative_to_dense_asphalt': .35,
        'mineral_source': 'Retained dense original recipe, not selected fracture transform.',
        'concrete_source_sha256': hashlib.sha256((r / 'original/cybr-material-concrete/mineral_construction_bounded.py').read_bytes()).hexdigest()},
    source_reference={'NAIP': 'May 2022 central tile used as visual reference only; no pixel colours or imagery projected into the scene.',
        'roof_assembly': 'https://www.energy.gov/energysaver/cool-roofs',
        'parapet_basis': 'https://afcfs.wbdg.org/facilities-exteriors/roof-systems/parapets-and-copings/index.html'},
    limits='Original geographic roof envelope retained. Missing roof construction, drainage fall, parapet dimensions, finishes and weathering are authored. Concrete and tile tags constrain families but do not supply measured finish or product properties. No new rooftop equipment, surveyed detail, coupled drainage, photo texture, or exact selected-material slab parity. Pitched roof faces remain at the existing level of geometric detail in this first regional pass.')
(out / 'REGIONAL_ROOF_RECEIPT.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({'triangles': report['triangles'], 'buildings': len(records),
    'materials': s.materials - 192, 'construction': dict(sum((collections.Counter(x['construction']) for x in records), collections.Counter()))}), flush=True)
