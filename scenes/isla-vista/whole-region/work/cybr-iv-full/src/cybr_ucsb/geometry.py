"""Source-anchored geometry expressed through the existing CYBR GEO contract.

Footprint topology, courtyards, shoreline and mapped surfaces stay anchored to
source coordinates. Missing heights and botanical dimensions are explicit
massing estimates; no unseen windows or architectural ornament are invented.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import hashlib
import json
import math
import numpy as np
import trimesh
from scipy.ndimage import gaussian_filter
from shapely import constrained_delaunay_triangles
from shapely.geometry import Polygon, MultiPolygon, Point, LineString
from shapely.ops import unary_union, split
from mechanism_lab.core import Assembly, Part, Material
from cybr_terrain.model import State, Config, LAYERS
from cybr_terrain.geometry import build_geometry as terrain_geometry, Attributes, Geometry
from cybr_terrain.materials import Atlas, make_atlas
from .coordinates import local_to_geo
from .ingest import Dataset, polygons, metres
from .sources import write_json, sha256


def stable_seed(value):
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "little")


def triangulate_polygon(polygon, max_edge=None):
    triangles = list(constrained_delaunay_triangles(polygon).geoms)
    if not triangles:
        return np.empty((0,2)), np.empty((0,3),np.int64)
    corners = np.array([np.asarray(t.exterior.coords)[:3,:2] for t in triangles])
    vertices, indices = np.unique(corners.reshape(-1,2), axis=0, return_inverse=True)
    faces = indices.reshape(-1,3)
    cross = np.cross(np.c_[vertices[faces[:,1]]-vertices[faces[:,0]],np.zeros(len(faces))],
                     np.c_[vertices[faces[:,2]]-vertices[faces[:,0]],np.zeros(len(faces))])[:,2]
    faces[cross<0] = faces[cross<0][:,::-1]
    if max_edge:
        v, faces = trimesh.remesh.subdivide_to_size(np.c_[vertices,np.zeros(len(vertices))], faces,
                                                   max_edge=max_edge,max_iter=12)
        vertices = v[:,:2]
    total_area = np.sum(np.abs(np.cross(np.c_[vertices[faces[:,1]]-vertices[faces[:,0]],np.zeros(len(faces))],
                                        np.c_[vertices[faces[:,2]]-vertices[faces[:,0]],np.zeros(len(faces))])[:,2]))/2
    if not np.isclose(total_area, polygon.area, rtol=1e-7,atol=1e-6):
        raise ValueError("Constrained triangulation changed footprint area")
    return vertices, faces


def estimate_width(feature):
    value = metres(feature.properties.get("width"))
    if value:
        return max(.4,min(50,value)), "explicit OSM width"
    if feature.category == "path":
        return (3.0 if feature.properties.get("highway")=="cycleway" else 1.8), "estimated path width"
    if feature.category == "hedge":
        return .8, "estimated hedge width"
    typ = feature.properties.get("highway")
    widths = {"primary":14,"secondary":11,"tertiary":9,"residential":7,
              "service":4,"track":3,"living_street":5,"unclassified":7}
    return widths.get(typ,6), "estimated width from road class"


def area_geometry(feature, report):
    if isinstance(feature.geometry, (Polygon,MultiPolygon)):
        return feature.geometry
    width, method = estimate_width(feature)
    report.append({"source_id":feature.id, "width_m":width,"method":method})
    return feature.geometry.buffer(width/2,cap_style="flat",join_style="round")


def ocean_from_coastline(dataset):
    lines = [f.geometry for f in dataset.selected("coastline")]
    if not lines:
        return Polygon()
    coast = unary_union(lines)
    try:
        regions = list(split(dataset.sector.clip,coast).geoms)
    except ValueError:
        return Polygon()
    segments = []
    for feature in dataset.selected("coastline"):
        children = list(feature.geometry.geoms) if hasattr(feature.geometry,"geoms") else [feature.geometry]
        for line in children:
            xy = np.asarray(line.coords)
            segments.extend((a,b) for a,b in zip(xy[:-1],xy[1:]) if np.linalg.norm(b-a)>.01)
    ocean = []
    # OSM coastlines run with land on the left. For each split region, the
    # nearest source segment determines which side is water.
    for region in regions:
        p = np.array(region.representative_point().coords[0])
        closest = (np.inf,0)
        for a,b in segments:
            ab = b-a
            t = np.clip((p-a)@ab/(ab@ab),0,1)
            distance = np.linalg.norm(p-a-t*ab)
            side = ab[0]*(p-a)[1]-ab[1]*(p-a)[0]
            if distance < closest[0]:
                closest = distance, side
        if closest[1] < 0:
            ocean.append(region)
    return unary_union(ocean)


def measured_state(dataset, n=257):
    """Adapt the measured DEM to TERRAIN State without rerunning authored demos.

    A thin optical surface reservoir lets the existing solver/material/geometry
    system work with measured terrain. It is explicitly not observed local
    stratigraphy. The datum surface is preserved exactly in the conserved state.
    """
    config = Config(preset="watershed",grid=n,extent=dataset.sector.extent,
                    duration=0,rain_mm_hour=0,inlet_m3_second=0,morphological_factor=1)
    height = dataset.dem.grid(n,config.extent)
    layer = replace(LAYERS["soil"],name="Unclassified mineral surface (optical proxy)")
    thickness = np.full((1,n,n),.10)
    z = np.zeros((n,n))
    state = State(config,(layer,),height-.10,thickness,np.zeros((3,n,n)),np.zeros((3,n,n)),
                  z.copy(),z.copy(),np.zeros((n,n-1)),np.zeros((n-1,n)),np.ones((n,n)),
                  z.copy(),height.copy())
    state.validate()
    if not np.allclose(state.height,height,rtol=0,atol=1e-12):
        raise ValueError("TERRAIN adaptation changed measured elevation")
    return state


def optical_atlas(name, color, roughness, relief, directory, size=256):
    rng = np.random.default_rng(stable_seed(name))
    fine = gaussian_filter(rng.normal(size=(size,size)),.6,mode="wrap")
    broad = gaussian_filter(rng.normal(size=(size,size)),12,mode="wrap")
    fine /= max(fine.std(),1e-8)
    broad /= max(broad.std(),1e-8)
    h = (fine*.75+broad*.25)*relief
    u = (np.roll(h,-1,axis=1)-np.roll(h,1,axis=1))/(2*1.25/size)
    v = (np.roll(h,-1,axis=0)-np.roll(h,1,axis=0))/(2*1.25/size)
    normals = np.stack((-u,-v,np.ones_like(h)),axis=-1)
    normals /= np.linalg.norm(normals,axis=-1,keepdims=True)
    albedo = np.clip(np.asarray(color)[None,None,:]*(1+.06*fine[:,:,None]+.035*broad[:,:,None]),.003,.95)
    rough = np.clip(roughness+.025*fine,.05,.99)
    layer = replace(LAYERS["soil"],name=name,color=tuple(color),roughness=roughness)
    return Atlas(layer,0,albedo.astype("float32"),normals.astype("float32"),
                 rough.astype("float32"),h.astype("float32")).save(directory,name)


class Builder:
    def __init__(self,dataset,directory,grid=257):
        self.dataset,self.directory = dataset,Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.state = measured_state(dataset,grid)
        self.geometry = terrain_geometry(self.state,self.directory,subdivision=1,stones=0)
        # Keep the real topographic surface, discard demo cutaway walls.
        top = [p for p in self.geometry.assembly.parts if p.group=="surface"]
        self.geometry.assembly.parts = top
        self.geometry.attributes = {p.name:self.geometry.attributes[p.name] for p in top}
        for p in top:
            p.provenance = "reference-reconstruction"
            p.role = "USGS terrain; TERRAIN optical surface detail"
        self.provenance = [{"part":p.name,"source_ids":["usgs:3dep"],
                            "measured":"DEM elevation", "estimated":"millimetric material relief and unclassified mineral appearance"} for p in top]
        self.material_map = {}
        self.widths = []
        self.omitted = []
        self.footprint_checks = []

    def material(self,name,color,rough=.8,relief=.0003):
        if name in self.material_map:
            return self.material_map[name]
        i = len(self.geometry.assembly.materials)
        self.geometry.assembly.materials.append(Material(name,tuple(color),rough=rough,
            material_source="Seeded optical proxy on source geometry; not measured reflectance"))
        self.geometry.atlases[i] = optical_atlas(name,color,rough,relief,self.directory/"textures")
        self.material_map[name] = i
        return i

    def add(self,name,vertices,faces,material,group,source_ids,estimated="",normals=None,uv=None):
        if not len(faces):
            return
        vertices,faces = np.asarray(vertices,float),np.asarray(faces,np.int64)
        if normals is None:
            # Duplicate corners for hard architectural edges.
            vv = vertices[faces].reshape(-1,3)
            cross = np.cross(vv[1::3]-vv[::3],vv[2::3]-vv[::3])
            keep = np.linalg.norm(cross,axis=1)>1e-10
            vv = vv.reshape(-1,3,3)[keep].reshape(-1,3)
            normal = cross[keep]/np.linalg.norm(cross[keep],axis=1,keepdims=True)
            normals = np.repeat(normal,3,axis=0)
            uv = vv[:,:2]/1.25 if uv is None else np.asarray(uv)[faces].reshape(-1,3,2)[keep].reshape(-1,2)
            vertices,faces = vv,np.arange(len(vv)).reshape(-1,3)
        else:
            uv = vertices[:,:2]/1.25 if uv is None else uv
        p = Part(name,local_to_geo(vertices),faces.astype("uint32"),np.asarray(normals,"float32"),
                 material=material,group=group,role="Geospatial "+group,
                 provenance="estimated-massing" if estimated else "reference-reconstruction",
                 tags=tuple(source_ids))
        self.geometry.assembly.parts.append(p)
        self.geometry.attributes[name] = Attributes(np.asarray(uv,"float32"),np.ones((len(vertices),3),"float32"))
        self.provenance.append({"part":name,"source_ids":list(source_ids),"estimated":estimated})

    def surface(self,name,geometry,material,source_ids,offset=.075,flat=None,max_edge=18):
        for k, polygon in enumerate(polygons(geometry)):
            if polygon.area < .08:
                continue
            xy,faces = triangulate_polygon(polygon,max_edge)
            z = self.dataset.dem.sample(xy[:,0],xy[:,1]) if flat is None else np.full(len(xy),flat)
            self.add(f"{name}_{k}",np.c_[xy,z+offset],faces,material,name,source_ids,
                     "optical surface thickness/material proxy" if flat is None else "illustrative water level/material",uv=xy/1.25)

    def mask_terrain_water(self,water):
        """Clip measured land triangles at the sourced water boundary.

        Some 3DEP mosaics encode water with a positive constant elevation. A
        sea-level plane below that value would disappear beneath the DEM. Mask
        the land mesh by actual shoreline polygons instead of altering the DEM.
        Boundary triangles are clipped exactly, preserving their planar height
        and interpolated normals/UV/tint; the raw measured state is unchanged.
        """
        if water.is_empty:
            return
        from shapely import contains_xy, points, distance
        for p in [p for p in self.geometry.assembly.parts if p.group=="surface"]:
            v = p.vertices*.001
            f = p.faces
            attrs = self.geometry.attributes[p.name]
            centre = v[f].mean(axis=1)
            radius = np.linalg.norm(v[f][:,:,:2]-centre[:,None,:2],axis=2).max(axis=1)
            near = distance(points(centre[:,:2]),water.boundary)<=radius+1e-6
            inside = contains_xy(water,centre[:,0],centre[:,1])
            keep = ~inside & ~near
            old_faces = f[keep]
            clipped_v,clipped_f,clipped_n,clipped_uv,clipped_tint = [],[],[],[],[]
            for face in f[near]:
                triangle = v[face]
                area = Polygon(triangle[:,:2]).difference(water)
                inverse = np.linalg.inv(np.vstack([triangle[:,:2].T,np.ones(3)]))
                for patch in polygons(area):
                    if patch.area < 1e-8:
                        continue
                    xy,faces = triangulate_polygon(patch)
                    weights = (inverse@np.c_[xy,np.ones(len(xy))].T).T
                    vv = weights@triangle
                    normal = weights@p.normals[face]
                    normal /= np.linalg.norm(normal,axis=1,keepdims=True)
                    offset = len(clipped_v)
                    clipped_v.extend(vv)
                    clipped_f.extend(faces+offset)
                    clipped_n.extend(normal)
                    clipped_uv.extend(weights@attrs.uv[face])
                    clipped_tint.extend(weights@attrs.tint[face])
            used,indices = np.unique(old_faces,return_inverse=True)
            p.vertices = p.vertices[used]
            p.normals = p.normals[used]
            p.faces = indices.reshape(-1,3).astype("uint32")
            self.geometry.attributes[p.name] = Attributes(attrs.uv[used],attrs.tint[used])
            if clipped_f:
                name = p.name+"_shoreline"
                self.add(name,clipped_v,clipped_f,p.material,"surface",["usgs:3dep","osm:coastline"],
                         "TERRAIN optical microrelief; land clipped at source water boundary",
                         normals=clipped_n,uv=clipped_uv)
                self.geometry.attributes[name].tint = np.asarray(clipped_tint,"float32")

    def building(self,feature,wall,roof):
        for k,polygon in enumerate(polygons(feature.geometry)):
            if polygon.area < 2:
                continue
            xy,faces = triangulate_polygon(polygon)
            ground = self.dataset.dem.sample(xy[:,0],xy[:,1])
            base = float(np.median(ground))
            height = feature.properties["height_m"]
            top = base+height
            stem = feature.id.replace(":","_")+f"_{k}"
            # Roof topology is exactly the source polygon, including courtyards.
            self.add(stem+"_roof",np.c_[xy,np.full(len(xy),top)],faces,roof,"roof",[feature.id],
                     feature.properties["height_method"]+"; flat massing roof",uv=xy/1.25)
            area = sum(Polygon(xy[f]).area for f in faces)
            self.footprint_checks.append({"source_id":feature.id,"source_area_m2":polygon.area,
                                          "roof_projected_area_m2":area,"error_m2":abs(polygon.area-area)})
            vertices,indices,uvs = [],[],[]
            for ring in [polygon.exterior,*polygon.interiors]:
                coords = np.asarray(ring.coords)[:,:2]
                travelled = 0.
                for a,b in zip(coords[:-1],coords[1:]):
                    length = np.linalg.norm(b-a)
                    if length < .02:
                        continue
                    # Walls extend to the lowest local DEM vertex, so ground
                    # relief does not leave floating foundations.
                    bottom = min(base-.25,float(self.dataset.dem.sample(a[0],a[1]))-.1,
                                 float(self.dataset.dem.sample(b[0],b[1]))-.1)
                    i = len(vertices)
                    vertices.extend([[*a,bottom],[*b,bottom],[*b,top],[*a,top]])
                    indices.extend([[i,i+1,i+2],[i,i+2,i+3]])
                    uvs.extend([[travelled/1.25,bottom/1.25],[(travelled+length)/1.25,bottom/1.25],
                                [(travelled+length)/1.25,top/1.25],[travelled/1.25,top/1.25]])
                    travelled += length
            self.add(stem+"_walls",vertices,indices,wall,"building",[feature.id],
                     "material/foundation depth; "+feature.properties["height_method"] if feature.uncertainty.get("height_estimated") else
                     "unmeasured facade and foundation depth; height sourced",uv=uvs)

    def vegetation(self,feature,trunk_mat,leaf_mat,building_union):
        if feature.geometry.geom_type != "Point":
            return
        x,y = feature.geometry.x,feature.geometry.y
        if building_union.contains(feature.geometry):
            self.omitted.append({"id":feature.id,"reason":"legacy flora/OSM point intersects current building footprint"})
            return
        genus = str(feature.properties.get("genus","")).strip()
        known_trees = {"Eucalyptus","Corymbia","Pinus","Platanus","Ficus","Jacaranda","Quercus",
                       "Schinus","Liquidambar","Olea","Pyrus","Alnus","Tipuana","Pittosporum","Acacia",
                       "Podocarpus","Cedrus","Cupressus","Sequoia","Lophostemon","Metrosideros"}
        palms = {"Syagrus","Phoenix","Washingtonia","Howea","Butia","Chamaerops","Archontophoenix"}
        if feature.category=="vegetation" and genus not in known_trees|palms:
            return  # Surveyed flora does not imply that every plant is a tree.
        rng = np.random.default_rng(stable_seed(feature.id))
        measured = metres(feature.properties.get("height"))
        height = measured or (11 if genus in palms else 14 if genus in {"Pinus","Eucalyptus","Corymbia"} else 7.5)
        if not measured:
            height *= rng.uniform(.8,1.15)
        radius = height*(.16 if genus in palms else .27)
        z = self.dataset.dem.sample(x,y)
        trunk = trimesh.creation.cylinder(radius=max(.10,height*.018),height=height*.72,sections=8)
        trunk.apply_translation([x,y,z+height*.36])
        stem = feature.id.replace(":","_")
        self.add(stem+"_trunk",trunk.vertices,trunk.faces,trunk_mat,"vegetation",[feature.id],
                 "generic botanical dimensions; source point/species retained",normals=trunk.vertex_normals)
        crown = trimesh.creation.icosphere(subdivisions=1)
        v = crown.vertices.copy()
        v *= (1+rng.uniform(-.15,.15,len(v)))[:,None]
        if genus in palms:
            # Fronds are geometry, anchored at the surveyed palm position.
            vv,ff = [],[]
            for j in range(12):
                phi = 2*math.pi*j/12+rng.uniform(-.1,.1)
                axis = np.array([math.cos(phi),math.sin(phi)])
                side = np.array([-axis[1],axis[0]])
                start = len(vv)
                for t in np.linspace(0,1,6):
                    centre = np.array([x,y])+axis*(radius*1.7*t)
                    zz = z+height+.8*math.sin(math.pi*t)-radius*.8*t*t
                    width = .38*radius*math.sin(math.pi*t)+.015
                    vv.extend([[*(centre-side*width),zz],[*(centre+side*width),zz]])
                for a in range(5):
                    i = start+2*a
                    ff.extend([[i,i+1,i+3],[i,i+3,i+2]])
            self.add(stem+"_fronds",vv,ff,leaf_mat,"vegetation",[feature.id],"generic frond shape/number, not survey measurements")
        else:
            v = v*[radius,radius,height*.35]+[x,y,z+height*.66]
            mesh = trimesh.Trimesh(v,crown.faces,process=False)
            self.add(stem+"_crown",v,crown.faces,leaf_mat,"vegetation",[feature.id],
                     "generic crown silhouette and dimensions",normals=mesh.vertex_normals)

    def build(self):
        d = self.dataset
        materials = {
            "wall":self.material("mineral-plaster",(.55,.50,.41),.82,.00045),
            "roof":self.material("roof-membrane",(.29,.28,.25),.84,.00055),
            "grass":self.material("mapped-grass",(.115,.19,.045),.92,.001),
            "asphalt":self.material("asphalt",(.065,.071,.073),.86,.0006),
            "path":self.material("path-concrete",(.37,.35,.30),.85,.0004),
            "sand":self.material("mapped-sand",(.52,.40,.23),.91,.0012),
            "water":self.material("water-surface-proxy",(.018,.083,.095),.16,.000015),
            "trunk":self.material("tree-bark",(.09,.057,.024),.92,.0015),
            "leaf":self.material("foliage",(.047,.113,.028),.87,.0005),
        }
        buildings = d.selected("building")
        building_union = unary_union([f.geometry for f in buildings])
        ocean = ocean_from_coastline(d)
        water = unary_union([ocean,*[f.geometry for f in d.selected("water") if isinstance(f.geometry,(Polygon,MultiPolygon))]])
        self.mask_terrain_water(water)
        pavement_rows = []
        for category in ("road","pavement","parking","path"):
            source = d.selected(category)
            area = unary_union([area_geometry(f,self.widths) for f in source]).intersection(d.sector.clip)
            pavement_rows.append((category,area,[f.id for f in source]))
        all_paved = unary_union([row[1] for row in pavement_rows])
        cover = unary_union([f.geometry for f in d.selected("landcover") if isinstance(f.geometry,(Polygon,MultiPolygon))])
        cover = cover.difference(unary_union([building_union,all_paved,water]))
        self.surface("mapped_landcover",cover,materials["grass"],[f.id for f in d.selected("landcover")],offset=.045)
        # Reuse soil/aggregate material construction for source-mapped beach areas.
        sand = unary_union([f.geometry for f in d.selected("landcover") if f.properties.get("natural") in ("beach","sand")])
        self.surface("mapped_sand",sand.difference(building_union),materials["sand"],
                     [f.id for f in d.selected("landcover") if f.properties.get("natural") in ("beach","sand")],offset=.06)
        for index,(category,area,ids) in enumerate(pavement_rows):
            material = materials["path"] if category=="path" else materials["asphalt"]
            self.surface("mapped_"+category,area.difference(building_union).difference(water),material,ids,
                         offset=.095+.022*index,max_edge=12)
        self.surface("source_water",water,materials["water"],[f.id for f in d.selected("water")+d.selected("coastline")],
                     offset=.11,flat=0,max_edge=30)
        for feature in buildings:
            self.building(feature,materials["wall"],materials["roof"])
        # GIS survey positions win over nearby OSM tree points; never scatter
        # procedural trees onto empty lots or move them to improve a composition.
        surveyed = d.selected("vegetation")
        from scipy.spatial import cKDTree
        xy = np.array([[f.geometry.x,f.geometry.y] for f in surveyed if f.geometry.geom_type=="Point"])
        tree_index = cKDTree(xy) if len(xy) else None
        trees = list(surveyed)
        for f in d.selected("tree"):
            if tree_index is None or tree_index.query([f.geometry.x,f.geometry.y])[0]>.75:
                trees.append(f)
        for feature in trees:
            self.vegetation(feature,materials["trunk"],materials["leaf"],building_union)
        self.geometry.assembly.name = "CYBR UCSB + ISLA VISTA — source-anchored sector 01"
        self.geometry.assembly.metadata = {"sector":d.sector.metadata(),"truth_intent":"inspection",
            "terrain_system":"CYBR TERRAIN 0.2: measured State adapter, geometry and optical materials",
            "source_layout_invented":False,"image_generation_used":False}
        self.geometry.validate()
        self.state.save(self.directory/"measured-terrain-state.npz")
        d.save(self.directory/"normalized.geojson")
        write_json(self.directory/"ingestion.json",d.report)
        report = {"schema":"cybr-geospatial-geometry/1","coordinate_contract":d.sector.metadata(),
                  "part_count":len(self.geometry.assembly.parts),
                  "triangles":sum(len(p.faces) for p in self.geometry.assembly.parts),
                  "vertices":sum(len(p.vertices) for p in self.geometry.assembly.parts),
                  "footprint_area_regressions":self.footprint_checks,
                  "widths":self.widths,"omitted_vegetation":self.omitted,"parts":self.provenance,
                  "terrain_height_max_error_m":float(np.max(abs(self.state.height-self.state.initial_height))),
                  "surveyed_stratigraphy_available":False,"image_generation_used":False,
                  "scope":"geographic massing; unknown facades, heights, crown dimensions and reflectance retained as uncertainty"}
        write_json(self.directory/"geometry-provenance.json",report)
        self.geometry.asset_directory = self.directory
        print(f"GEO: {report['part_count']:,} parts / {report['triangles']:,} triangles",flush=True)
        return self.geometry,report


def build(dataset,directory,grid=257,export_glb=True):
    builder = Builder(dataset,directory,grid)
    geometry,report = builder.build()
    if export_glb:
        export_batched_glb(geometry,Path(directory)/"sector.glb")
        report["glb_sha256"] = sha256(Path(directory)/"sector.glb")
        write_json(Path(directory)/"geometry-provenance.json",report)
    return geometry,report


def export_batched_glb(geometry,path):
    """Share atlases and batch GEO parts by material for large GIS scenes.

    Retain the exact per-part face spans alongside glTF rather than creating
    thousands of copies of the same material image. Source geometry, normals,
    UVs and colour products are preserved; no simplification is performed.
    """
    from PIL import Image
    from cybr_terrain.materials import srgb
    from mechanism_lab.exporters import NATIVE_TO_GLTF
    geometry.validate()
    path = Path(path)
    scene = trimesh.Scene()
    layout = {}
    component = {p.name:index+1 for index,p in enumerate(geometry.assembly.parts)}
    for material_id in sorted({p.material for p in geometry.assembly.parts}):
        parts = [p for p in geometry.assembly.parts if p.material==material_id]
        vv,ff,nn,uv,tint = [],[],[],[],[]
        spans = []
        vertex_offset,face_offset = 0,0
        for part in parts:
            pose = geometry.assembly.pose(part)
            v = part.vertices@pose[:3,:3].T+pose[:3,3]
            vv.append(v)
            ff.append(part.faces.astype(np.int64)+vertex_offset)
            nn.append(part.normals@pose[:3,:3].T)
            attrs = geometry.attributes[part.name]
            uv.append(attrs.uv)
            tint.append(attrs.tint)
            spans.append({"component":component[part.name],"part":part.name,"first_face":face_offset,
                          "face_count":len(part.faces)})
            vertex_offset += len(v)
            face_offset += len(part.faces)
        vertices = np.vstack(vv)@NATIVE_TO_GLTF[:3,:3].T
        normals = np.vstack(nn)@(NATIVE_TO_GLTF[:3,:3]*1000).T
        tint = np.vstack(tint)
        atlas = geometry.atlases[material_id]
        gain = np.maximum(1,tint.max(axis=0))
        color = Image.fromarray(np.round(srgb(atlas.albedo*gain)*255).astype("uint8"))
        normal_image = Image.fromarray(np.round(np.clip(atlas.normal*.5+.5,0,1)*255).astype("uint8"))
        orm = Image.fromarray(np.round(np.stack([np.ones_like(atlas.roughness),atlas.roughness,
                                                np.zeros_like(atlas.roughness)],axis=-1)*255).astype("uint8"))
        material = trimesh.visual.material.PBRMaterial(name=geometry.assembly.materials[material_id].name,
            baseColorFactor=[255]*4,baseColorTexture=color,normalTexture=normal_image,
            metallicFactor=0,roughnessFactor=1,metallicRoughnessTexture=orm,doubleSided=False)
        mesh = trimesh.Trimesh(vertices,np.vstack(ff),vertex_normals=normals,process=False)
        mesh.visual = trimesh.visual.TextureVisuals(uv=np.vstack(uv),material=material)
        mesh.visual.vertex_attributes["color"] = np.c_[np.round(np.clip(tint/gain,0,1)*255).astype("uint8"),
                                                       np.full(len(tint),255,"uint8")]
        name = f"material_{material_id:03d}"
        scene.add_geometry(mesh,node_name=name,geom_name=name)
        layout[name] = {"parts":spans,"tint_gain":gain.tolist(),"face_count":len(mesh.faces)}
    temporary = path.with_name(path.stem+".partial.glb")
    scene.export(temporary)
    restored = trimesh.load(temporary,force="scene",process=False)
    if sum(len(m.faces) for m in restored.geometry.values())!=sum(len(p.faces) for p in geometry.assembly.parts):
        raise ValueError("Batched GLB changed triangle inventory")
    temporary.replace(path)
    write_json(path.with_name("glb-part-layout.json"),layout)
    print(f"exported {path}: {path.stat().st_size:,} bytes / {len(scene.geometry)} material batches",flush=True)
    return path
