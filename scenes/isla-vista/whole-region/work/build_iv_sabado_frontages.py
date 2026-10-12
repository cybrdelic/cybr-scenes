"""Original, reference-guided Sabado Tarde architecture in retained OSM plans.

No photograph is sampled as a texture. Exterior observations support form;
all dimensions within the retained footprint/height envelope and all optical
controls are authored estimates. Run only under the shared CYBR resource lock.
"""
from pathlib import Path
import hashlib
import json
import struct
import sys
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(path) for path in [ROOT/'geo-deps', ROOT/'work/iv-component-runtime', ROOT/'work/cybr-iv-full/src', ROOT/'whole-iv-vendor']]
from shapely.geometry import shape, Point, Polygon, box
from shapely.geometry.polygon import orient
from cybr_ucsb.geometry import triangulate_polygon
from cybr_ucsb.coordinates import Sector
from cybr_ucsb.ingest import DEM
from cybr_light import Scene
from cybr_light.runtime import read_pfm
from cybr_terrain.materials import write_pfm
from iv_mesh_parts import Parts

OUT = ROOT/'evidence/full-iv-sabado-frontages'
MATERIAL_OFFSET = 286
OBJECT_OFFSET = 16100000
CHART = 1.25
PLASTER_TILE = .65
SOURCE_COMMIT = '12848c82f60bc58fa88640545868009b90298b32'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Buffer:
    """Per-material parts with explicit metric UV charts and validation."""
    def __init__(self, source):
        self.source = source
        self.groups = {}
        self.validation = {'triangles': 0, 'degenerate_triangles': 0, 'nonfinite': 0, 'uv_degenerate_triangles': 0}
        self.details = {}

    def mesh(self, vertices, faces, material, uv):
        vertices = np.asarray(vertices, float)
        faces = np.asarray(faces, int)
        uv = np.asarray(uv, float)
        assert vertices.ndim == 2 and vertices.shape[1] == 3
        assert uv.shape == (len(vertices), 2)
        assert np.isfinite(vertices).all() and np.isfinite(uv).all()
        tris = vertices[faces]
        cross = np.cross(tris[:, 1]-tris[:, 0], tris[:, 2]-tris[:, 0])
        area2 = np.linalg.norm(cross, axis=1)
        keep = area2 > 1e-10
        self.validation['degenerate_triangles'] += int((~keep).sum())
        faces = faces[keep]
        tex = uv[faces]
        e, f = tex[:, 1]-tex[:, 0], tex[:, 2]-tex[:, 0]
        self.validation['uv_degenerate_triangles'] += int((abs(e[:, 0]*f[:, 1]-e[:, 1]*f[:, 0]) < 1e-12).sum())
        self.validation['triangles'] += len(faces)
        group = self.groups.setdefault(material, {'v': [], 'f': [], 'uv': []})
        offset = len(group['v'])
        group['v'].extend(vertices.tolist())
        group['f'].extend((faces+offset).tolist())
        group['uv'].extend(uv.tolist())

    def quad(self, vertices, material, uv=None):
        vertices = np.asarray(vertices, float)
        if uv is None:
            u = vertices[1]-vertices[0]
            u /= np.linalg.norm(u)
            normal = np.cross(u, vertices[-1]-vertices[0])
            normal /= np.linalg.norm(normal)
            v = np.cross(normal, u)
            rel = vertices-vertices[0]
            uv = np.c_[rel@u, rel@v]/CHART
        self.mesh(vertices, [[0, 1, 2], [0, 2, 3]], material, uv)

    def box(self, center, size, material, frame=None):
        vertices = np.array([[x,y,z] for z in [-1,1] for y in [-1,1] for x in [-1,1]])*np.asarray(size)/2+center
        if frame is not None:
            vertices = frame(vertices)
        for ids in [[0,2,3,1], [4,5,7,6], [0,1,5,4], [2,6,7,3], [0,4,6,2], [1,3,7,5]]:
            q = vertices[ids]
            if frame is not None:
                q = q[::-1]  # Edge-tangent, outward, up has negative determinant.
            self.quad(q, material)

    def finish(self, parts):
        for material, group in sorted(self.groups.items()):
            parts.mesh(self.source.replace(':', '_')+'_'+str(material), group['v'], group['f'], material,
                       self.source, 'Photo-guided form; dimensions, pigment, hidden elevations and A/B assignment estimated', uv=group['uv'])


class Facade:
    def __init__(self, buffer, a, z, datum):
        self.b = buffer
        self.a = np.asarray(a)
        self.length = float(np.linalg.norm(z-a))
        self.t = (z-a)/self.length
        self.n = np.array([self.t[1], -self.t[0]])
        self.datum = datum

    def world(self, x, y, z):
        return np.array([*(self.a+self.t*x+self.n*y), self.datum+z])

    def frame(self, vertices):
        return np.array([self.world(*q) for q in vertices])

    def box(self, center, size, material):
        self.b.box(center, size, material, self.frame)

    def panel(self, x0, x1, z0, z1, material, depth=0):
        if x1-x0 <= 1e-8 or z1-z0 <= 1e-8:
            return
        self.b.quad([self.world(x0,depth,z0), self.world(x1,depth,z0), self.world(x1,depth,z1), self.world(x0,depth,z1)],
                    material, np.array([[x0,z0],[x1,z0],[x1,z1],[x0,z1]])/CHART)

    def opening(self, opening, wall, trim):
        x0,x1,z0,z1,kind = opening
        depth = .20
        # Actual wall voids, inset glazing and four correctly wound reveals.
        for xx, reverse in [(x0,False),(x1,True)]:
            q = [self.world(xx,0,z0),self.world(xx,-depth,z0),self.world(xx,-depth,z1),self.world(xx,0,z1)]
            self.b.quad(q[::-1] if reverse else q,wall)
        for zz, reverse in [(z0,True),(z1,False)]:
            q = [self.world(x0,0,zz),self.world(x1,0,zz),self.world(x1,-depth,zz),self.world(x0,-depth,zz)]
            self.b.quad(q[::-1] if reverse else q,wall)
        if kind == 'passage':
            return
        self.panel(x0,x1,z0,z1,70,-.52)
        self.panel(x0,x1,z0,z1,69,-.14)
        for xx in [x0,x1,(x0+x1)/2]:
            self.box((xx,-.105,(z0+z1)/2),(.065,.075,z1-z0+.07),trim)
        for zz in [z0,z1]:
            self.box(((x0+x1)/2,-.105,zz),(x1-x0+.07,.075,.065),trim)
        self.box(((x0+x1)/2,.045,z0-.045),(x1-x0+.16,.23,.08),trim)

    def wall(self, openings, height, wall, trim, floor=-.20):
        xs = sorted(set([0.,self.length]+[q for op in openings for q in op[:2]]))
        zs = sorted(set([floor,height]+[q for op in openings for q in op[2:4]]))
        for x0,x1 in zip(xs[:-1],xs[1:]):
            for z0,z1 in zip(zs[:-1],zs[1:]):
                if not any(o[0]<(x0+x1)/2<o[1] and o[2]<(z0+z1)/2<o[3] for o in openings):
                    self.panel(x0,x1,z0,z1,wall)
        for opening in openings:
            self.opening(opening,wall,trim)
        self.b.details['actual_wall_openings'] = self.b.details.get('actual_wall_openings',0)+len(openings)

    def rail(self, x0, x1, y, floor, material, side_depth=0):
        height=1.03
        for z in [floor+.10,floor+height]:
            self.box(((x0+x1)/2,y,z),(x1-x0+.065,.055,.060),material)
        for x in np.linspace(x0,x1,max(2,int((x1-x0)/.16)+1)):
            self.box((x,y,floor+.54),(.028,.032,.97),material)
        if side_depth:
            for x in [x0,x1]:
                self.box((x,y-side_depth/2,floor+height),(.055,side_depth,.060),material)
                for yy in np.arange(y-side_depth+.12,y,.16):
                    self.box((x,yy,floor+.54),(.032,.028,.97),material)

    def balcony(self,x0,x1,floor,depth,slab,rail):
        self.box(((x0+x1)/2,depth/2,floor-.10),(x1-x0,depth,.20),slab)
        self.rail(x0+.04,x1-.04,depth-.05,floor,rail,depth-.10)
        self.b.details['balcony_decks'] = self.b.details.get('balcony_decks',0)+1

    def stair(self, front_x, run, floor, depth, concrete, rail):
        # Open underside flight, discrete treads/risers and continuous guards.
        count=int(np.ceil(floor/.18))
        rise=floor/count
        tread=run/count
        for k in range(count):
            x=front_x-(k+.5)*tread
            z=(k+1)*rise
            self.box((x,depth/2,z-.085),(tread+.025,depth,.17),concrete)
            self.box((x-tread/2,depth/2,z-rise/2),(.045,depth,rise),concrete)
        # Solid, inclined stringers with face charts; no stacked filler cubes.
        for yy in [.04,depth-.04]:
            q=[(front_x,yy,.03),(front_x-run,yy,floor-.15),(front_x-run,yy,floor+.02),(front_x,yy,.20)]
            self.b.quad(self.frame(q),concrete)
            q=[(front_x,yy,.99),(front_x-run,yy,floor+.99),(front_x-run,yy,floor+1.045),(front_x,yy,1.045)]
            self.b.quad(self.frame(q),rail)
            for k in range(0,count,2):
                self.box((front_x-(k+.5)*tread,yy,(k+1)*rise+.53),(.035,.035,1.02),rail)
        self.b.details['exterior_stair_flights'] = self.b.details.get('exterior_stair_flights',0)+1


def setup_materials():
    day=json.loads((ROOT/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text())
    basis=np.array(day['native_basis_to_linear_rgb']);white=basis@np.ones(3);inverse=np.linalg.inv(basis)
    def native(rgb):
        return np.maximum(0,(np.asarray(rgb)*white)@inverse.T)
    scene=Scene();scene.materials=MATERIAL_OFFSET
    fields=ROOT/'evidence/full-iv-street-finishes'
    reference=read_pfm(fields/'6574_cream_stucco_native.pfm')
    # Recover the already-linear, source-correlated colour field and preserve
    # it while changing only the explicit, estimated mean pigment controls.
    linear=(reference@basis.T)/white
    variation=linear/np.mean(linear,axis=(0,1))
    mapping={}
    textures=[]
    def plaster(name,mean):
        color=OUT/'textures'/f'{name}_native.pfm'
        write_pfm(color,native(np.minimum(.95,variation*np.asarray(mean))))
        base=scene.material('plastic',(1,1,1),.76,ior=1.48,texture=color)
        frequency=CHART/PLASTER_TILE
        scene.lines[-1]=scene.lines[-1].rsplit(' ',3)[0]+f' {frequency} {frequency} 1'
        scene.emit('roughness_texture',base,json.dumps(str((fields/'lime_roughness.pfm').resolve())),frequency,frequency,1)
        bump=scene.material('bumpmap',texture=fields/'lime_height_metres.pfm')
        scene.lines[-1]=scene.lines[-1].rsplit(' ',3)[0]+f' {frequency} {frequency} 1'
        scene.emit('nested',bump,base,-1,.5);scene.emit('metric_bump',bump)
        mapping[name]={'base':base,'surface':bump,'estimated_linear_rgb_mean':mean,'tile_m':PLASTER_TILE}
        textures.append(color)
        return bump
    wall={6515:plaster('6515_pale_lime',(.57,.55,.50)),6522:plaster('6522_cream_lime',(.62,.58,.48)),6531:plaster('6531_warm_white_lime',(.64,.605,.51))}
    mortar=plaster('masonry_mortar',(.30,.29,.265))
    # Original CYBR porous stone fields support a mineral response on the
    # independently authored chunks. Travertine is an optical analogy only;
    # the local stone species and optical spectrum have not been established.
    sys.path.insert(0,str(ROOT/'original/cybr-material-finishes/source'))
    from finish_structures import travertine
    n=256;x=((np.arange(n)+.5)/n)[None,:];y=x.T
    rgb,h,rough,ao,metal,wear=travertine(x,y,n)
    rgb=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
    mean=(.34,.325,.285)
    color=OUT/'textures/fieldstone_native.pfm';height=OUT/'textures/fieldstone_height_metres.pfm';roughness=OUT/'textures/fieldstone_roughness.pfm'
    write_pfm(color,native(np.minimum(.95,rgb/rgb.mean(axis=(0,1))*mean)))
    physical_height=(h-.5)*.006
    write_pfm(height,np.repeat(physical_height[:,:,None],3,axis=2))
    write_pfm(roughness,np.repeat(rough[:,:,None],3,axis=2))
    frequency=CHART/.65
    base=scene.material('plastic',(1,1,1),.62,ior=1.5,texture=color)
    scene.lines[-1]=scene.lines[-1].rsplit(' ',3)[0]+f' {frequency} {frequency} 1'
    scene.emit('roughness_texture',base,json.dumps(str(roughness.resolve())),frequency,frequency,1)
    stone=scene.material('bumpmap',texture=height)
    scene.lines[-1]=scene.lines[-1].rsplit(' ',3)[0]+f' {frequency} {frequency} 1'
    scene.emit('nested',stone,base,-1,.5);scene.emit('metric_bump',stone)
    mapping['fieldstone_porosity_analogy']={'base':base,'surface':stone,'estimated_linear_rgb_mean':mean,'tile_m':.65,'source_function':'finish_structures.travertine',
        'source_height_scale_m':.006,'height_range_m':[float(physical_height.min()),float(physical_height.max())],
        'roughness_range':[float(rough.min()),float(rough.max())],'not_a_local_stone_species_identification':True}
    textures.extend([color,height,roughness])
    for name,color,rough in [('white_trim',(.72,.725,.70),.54),('charcoal_rail',(.10,.115,.112),.62),('sage_shutter',(.22,.28,.245),.73),('red_masonry',(.43,.21,.14),.86),('dark_roof',(.075,.069,.055),.85),('roof_soffit',(.55,.53,.47),.80)]:
        mapping[name]={'surface':scene.material('plastic',native(color),rough,ior=1.48),'estimated_linear_rgb_mean':color}
    return scene,wall,mortar,stone,mapping,textures


def fieldstone(facade,x0,x1,z0,z1,stone):
    # Original, deterministic clipped irregular blocks. Geometry is not a
    # reconstruction of individual stones in the photograph.
    rng=np.random.default_rng(6515)
    z=z0
    row=0
    while z<z1-.04:
        height=min(rng.uniform(.35,.53),z1-z)
        x=x0
        while x<x1-.035:
            width=min(rng.uniform(.40,.84),x1-x)
            if width<.07:
                break
            gap=.025
            corners=np.array([[x+gap,z+height*.20],[x+width*.18,z+gap],[x+width*.80,z+gap],[x+width-gap,z+height*.25],[x+width-gap,z+height*.78],[x+width*.71,z+height-gap],[x+width*.20,z+height-gap],[x+gap,z+height*.76]])
            center=corners.mean(axis=0)
            depth=.048+.035*((row%3)/2)
            verts=[facade.world(xx,depth,zz) for xx,zz in corners]+[facade.world(center[0],depth+.018,center[1])]
            faces=[[k,(k+1)%8,8] for k in range(8)]
            facade.b.mesh(verts,faces,stone,np.vstack([corners,center])/CHART)
            for k in range(8):
                p,q=corners[k],corners[(k+1)%8]
                facade.b.quad([facade.world(p[0],.018,p[1]),facade.world(q[0],.018,q[1]),facade.world(q[0],depth,q[1]),facade.world(p[0],depth,p[1])],stone)
            x+=width
        z+=height
        row+=1


def masonry_panel(facade,x0,x1,height,mortar,brick):
    facade.panel(x0,x1,0,height,mortar,.025)
    pitch=.205
    for row,z in enumerate(np.arange(.018,height,pitch)):
        for x in np.arange(x0-.47,x1,.47):
            a=max(x0+.018,x+(.235 if row%2 else 0)+.014)
            b=min(x1-.018,x+(.235 if row%2 else 0)+.452)
            top=min(z+.178,height-.016)
            if b-a>.04 and top>z:
                facade.box(((a+b)/2,.065,(z+top)/2),(b-a,.08,top-z),brick)


def roof(buffer,poly,datum,eave,height,kind,roof_material,soffit,trim):
    outer=poly.buffer(.52,join_style=2)
    xy,faces=triangulate_polygon(outer)
    if kind=='gable':
        # Split at a physically defined ridge parallel to the long plan axis,
        # then retain the exact shell plan underneath the overhang.
        rectangle=poly.minimum_rotated_rectangle
        rc=np.array(rectangle.exterior.coords)[:-1]
        lengths=np.linalg.norm(np.roll(rc,-1,axis=0)-rc,axis=1)
        i=int(np.argmax(lengths));long=(rc[(i+1)%4]-rc[i])/lengths[i]
        cross=np.array([-long[1],long[0]])
        center=np.array(poly.centroid.coords[0]);half=max(abs((np.array(outer.exterior.coords)-center)@cross))
        def gable_z(points):
            return eave+(height-eave)*(1-abs((np.asarray(points)-center)@cross)/half)
        def split_edge(a,b):
            qa,qb=(a-center)@cross,(b-center)@cross
            if qa*qb<0:
                ridge=a+(b-a)*qa/(qa-qb)
                return [(a,ridge),(ridge,b)]
            return [(a,b)]
        extent=100.
        for sign in [-1,1]:
            clip=Polygon([center-long*extent,center+long*extent,center+long*extent+sign*cross*extent,center-long*extent+sign*cross*extent])
            wing=outer.intersection(clip)
            vx,ff=triangulate_polygon(wing)
            zz=gable_z(vx)
            # Sloped surface chart preserves arclength, not horizontal scale.
            scale=np.sqrt(1+((height-eave)/half)**2)
            uv=np.c_[(vx-center)@long,((vx-center)@cross)*scale]/CHART
            buffer.mesh(np.c_[vx,datum+zz],ff,roof_material,uv)
        for a,b in zip(np.array(poly.exterior.coords)[:-1],np.array(poly.exterior.coords)[1:]):
            for a0,b0 in split_edge(a,b):
                za,zb=gable_z([a0,b0])
                buffer.quad([[*a0,datum+eave],[*b0,datum+eave],[*b0,datum+zb],[*a0,datum+za]],trim)
    else:
        inset=poly.buffer(-2.8 if kind=='hip' else -.7,join_style=2)
        if inset.is_empty:
            inset=poly.buffer(-.4,join_style=2)
        ring=outer.difference(inset)
        for piece in (list(ring.geoms) if hasattr(ring,'geoms') else [ring]):
            vx,ff=triangulate_polygon(piece)
            zz=np.array([height if Point(q).distance(inset.boundary)<1e-6 else eave for q in vx])
            # Each triangle gets an explicit orthonormal face chart so even
            # pitched faces retain metric physical bump scale.
            v3=np.c_[vx,datum+zz]
            for f in ff:
                q=v3[f];u=q[1]-q[0];u/=np.linalg.norm(u);n=np.cross(u,q[2]-q[0]);n/=np.linalg.norm(n);v=np.cross(n,u)
                uv=np.c_[(q-q[0])@u,(q-q[0])@v]/CHART
                buffer.mesh(q,[[0,1,2]],roof_material,uv)
        for piece in (list(inset.geoms) if hasattr(inset,'geoms') else [inset]):
            vx,ff=triangulate_polygon(piece)
            buffer.mesh(np.c_[vx,np.full(len(vx),datum+height)],ff,roof_material,vx/CHART)
    ring=outer.difference(poly)
    if kind=='gable':
        for sign in [-1,1]:
            clip=Polygon([center-long*extent,center+long*extent,center+long*extent+sign*cross*extent,center-long*extent+sign*cross*extent])
            sx,sf=triangulate_polygon(ring.intersection(clip))
            zz=gable_z(sx)
            scale=np.sqrt(1+((height-eave)/half)**2)
            uv=np.c_[(sx-center)@long,((sx-center)@cross)*scale]/CHART
            buffer.mesh(np.c_[sx,datum+zz-.03],sf[:,::-1],soffit,uv)
    else:
        sx,sf=triangulate_polygon(ring)
        buffer.mesh(np.c_[sx,np.full(len(sx),datum+eave-.03)],sf[:,::-1],soffit,sx/CHART)
    for a,b in zip(np.array(outer.exterior.coords)[:-1],np.array(outer.exterior.coords)[1:]):
        segments=split_edge(a,b) if kind=='gable' else [(a,b)]
        for a0,b0 in segments:
            za,zb=gable_z([a0,b0]) if kind=='gable' else [eave,eave]
            buffer.quad([[*a0,datum+za-.13],[*b0,datum+zb-.13],[*b0,datum+zb],[*a0,datum+za]],trim)


def curved_court(facade,x0,x1,y,height,wall):
    # Two raised ends and a low rounded center, visibly shaped silhouette.
    xs=np.linspace(x0,x1,41)
    for a,b in zip(xs[:-1],xs[1:]):
        def top(x):
            q=abs((x-(x0+x1)/2)/((x1-x0)/2))
            return .48+(height-.48)*(1-np.sqrt(max(0,1-q*q)))
        za,zb=top(a),top(b)
        for depth,reverse in [(y-.10,True),(y+.10,False)]:
            verts=facade.frame([(a,depth,0),(b,depth,0),(b,depth,zb),(a,depth,za)])
            uv=np.array([[a,0],[b,0],[b,zb],[a,za]])/CHART
            facade.b.quad(verts[::-1] if reverse else verts,wall,uv[::-1] if reverse else uv)
        facade.b.quad(facade.frame([(a,y-.10,za),(b,y-.10,zb),(b,y+.10,zb),(a,y+.10,za)]),wall)


def validate_serialized(path, material_count, expected_parts):
    dtype=np.dtype([('indices','u1',(3,)),('material','<u4'),('object','<u4')])
    observed=0;bad_uv=0;min_area=float('inf');objects=set();materials=set();max_normal_error=0
    expected_objects={p['object'] for p in expected_parts}
    allowed_materials=set(range(MATERIAL_OFFSET,MATERIAL_OFFSET+material_count))|{9,69,70,186}
    with path.open('rb') as stream:
        magic,total,packets=struct.unpack('<4sQI',stream.read(16))
        assert magic==b'CLM1'
        for packet in range(packets):
            count,ntri=struct.unpack('<HH',stream.read(4));assert 0<count<=64 and 0<ntri<=124
            vertices=np.frombuffer(stream.read(count*44),dtype='<f4').reshape(count,11)
            triangles=np.frombuffer(stream.read(ntri*11),dtype=dtype)
            assert np.isfinite(vertices).all() and triangles['indices'].max()<count
            objects.update(int(q) for q in triangles['object']);materials.update(int(q) for q in triangles['material'])
            points=vertices[triangles['indices'],:3].astype(float)
            area=np.linalg.norm(np.cross(points[:,1]-points[:,0],points[:,2]-points[:,0]),axis=1)/2
            assert (area>1e-12).all();min_area=min(min_area,float(area.min()))
            tex=vertices[triangles['indices'],6:8].astype(float)
            a,b=tex[:,1]-tex[:,0],tex[:,2]-tex[:,0]
            bad_uv+=int((abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])<1e-12).sum())
            max_normal_error=max(max_normal_error,float(abs(np.linalg.norm(vertices[:,3:6],axis=1)-1).max()))
            observed+=ntri
        assert not stream.read(1),'Trailing mesh data'
    assert total==observed and bad_uv==0 and materials<=allowed_materials and objects==expected_objects
    assert max_normal_error<1e-5
    return {'format':'CLM1','triangles':observed,'meshlets':packets,'finite_vertices':True,'valid_indices':True,
            'valid_material_references':True,'material_ids':sorted(materials),'object_ids':sorted(objects),
            'nondegenerate_geometry':True,'minimum_triangle_area_m2':min_area,'nondegenerate_uvs':True,
            'maximum_unit_normal_error':max_normal_error,'no_trailing_data':True}


def build():
    OUT.mkdir(exist_ok=True);(OUT/'textures').mkdir(exist_ok=True)
    scene,walls,mortar,stone,mats,textures=setup_materials()
    get=lambda name:mats[name]['surface']
    trim=get('white_trim');rail=get('charcoal_rail');roofmat=get('dark_roof');red=get('red_masonry')
    features={f['id']:f for f in json.loads((ROOT/'evidence/full-iv-roofs/normalized.geojson').read_text())['features']}
    manifest=json.loads((ROOT/'references/residential-street-v2/REFERENCE_MANIFEST.json').read_text())
    old=json.loads((ROOT/'evidence/full-iv-facades/FACADE_RECEIPT.json').read_text())
    layout=json.loads((ROOT/'evidence/full-iv-roofs/glb-part-layout.json').read_text())
    dem=DEM(ROOT/'data/full-iv-20261011/dem.tif',Sector(longitude=-119.8614,latitude=34.413,extent=2600).frame)
    parts=Parts(OUT/'architecture.clm',OBJECT_OFFSET)
    records=[];exclude_facades=[];exclude_base=[]
    for address,oid,levels in [(6515,42753162,2),(6522,42753151,2),(6531,42753168,3),(6531,42753169,3)]:
        source=f'osm:way:{oid}';feature=features[source];poly=orient(shape(feature['geometry']),sign=1)
        xy,ff=triangulate_polygon(poly);datum=float(np.median(dem.sample(xy[:,0],xy[:,1])))
        maxheight=levels*3.3;eave=6.35 if address==6515 else 5.95 if address==6522 else 9.05
        floor=3.10;wall=walls[address];buffer=Buffer(source);coords=np.array(poly.exterior.coords)[:,:2]
        facades=[Facade(buffer,a,b,datum) for a,b in zip(coords[:-1],coords[1:])]
        front=[q for q in facades if q.n[1]>(.7) and q.length>5] if address!=6522 else [q for q in facades if q.n[1]<-.7 and q.length>5]
        front_edge_ids=[facades.index(q) for q in front]
        south=min((q.a[1]+q.t[1]*q.length/2) for q in front) if address==6522 else None
        for face in facades:
            length=face.length;isfront=face in front
            gallery=address==6531 and face.n[0]>.7 and length>30
            recessed=address==6522 and isfront and face.a[1]+face.t[1]*length/2>south+3
            openings=[]
            if address==6515 and isfront:
                for lev in range(2):
                    lo=lev*floor+(.30 if lev else .87)
                    openings.append((length*.12,length*.43,lo,lev*floor+2.45,'slider' if lev else 'window'))
                    openings.append((length*.55,length*.61,lev*floor+1.50,lev*floor+2.28,'window'))
            elif address==6522 and isfront:
                if recessed:
                    openings.append((length*.23,length*.79,-.20,2.60,'passage'))
                    for center in [.24,.74]:
                        openings.append((length*center-.85,length*center+.85,floor+.20,floor+2.40,'slider'))
                else:
                    for lev in range(2):
                        openings.append((length*.28,length*.74,lev*floor+.94,lev*floor+2.27,'window'))
            elif address==6531 and isfront:
                for lev in range(3):
                    for center in [.24,.77]:
                        openings.append((length*center-1.32,length*center+1.32,lev*floor+.17,lev*floor+2.40,'slider'))
            elif length>3.5:
                bays=max(1,int(length/(5.5 if gallery else 6.0)))
                for lev in range(levels):
                    for k in range(bays):
                        center=length*(k+.5)/bays
                        gallery_door=gallery and lev==1 and center<length-6.05
                        low=lev*floor+(.14 if gallery_door else 1.08)
                        high=min(eave-.35,lev*floor+2.20)
                        width=.82 if gallery_door else .62
                        openings.append((center-width,center+width,low,high,'slider' if gallery_door else 'window'))
            face.wall(openings,eave,wall,trim)
            if address==6515 and isfront:
                face.balcony(length*.10,length*.46,floor,1.20,186,rail)
                face.panel(length*.68,length,0,eave,mortar,.01)
                fieldstone(face,length*.68,length,0,eave,stone)
                face.box((length*.34,3.7,.72),(length*.68,.20,1.44),wall)
                face.box((length*.34,3.7,1.46),(length*.68+.08,.26,.075),red)
                face.box((.06,1.85,.72),(.20,3.7,1.44),wall)
            if address==6522 and isfront:
                if recessed:
                    face.balcony(.06,length-.06,floor,1.38,186,rail)
                    # A short, actual tunnel with ceiling, sides and roadway
                    # extends behind the open façade. Hidden plan is estimated.
                    left,right=length*.23,length*.79
                    depth=3.3
                    for xx,reverse in [(left,False),(right,True)]:
                        q=face.frame([(xx,0,-.20),(xx,-depth,-.20),(xx,-depth,2.60),(xx,0,2.60)])
                        buffer.quad(q[::-1] if reverse else q,wall)
                    buffer.quad(face.frame([(left,0,2.60),(right,0,2.60),(right,-depth,2.60),(left,-depth,2.60)]),get('roof_soffit'))
                    buffer.quad(face.frame([(left,0,-.025),(left,-depth,-.025),(right,-depth,-.025),(right,0,-.025)]),9)
                    buffer.details['open_vehicle_passages']=1
                else:
                    for op in openings:
                        x0,x1,z0,z1,_=op
                        for xx in [x0-.40,x1+.40]:
                            face.box((xx,.075,(z0+z1)/2),(.58,.075,z1-z0),get('sage_shutter'))
                            for zz in np.arange(z0+.10,z1,.14):
                                face.box((xx,.125,zz),(.54,.035,.025),trim)
                    curved_court(face,.03,length-.03,2.35,1.62,wall)
            if address==6522 and 5.8<length<7.3 and face.n[0]<-.7:
                # Along the inner eastern wing: the stair meets the recessed
                # gallery while leaving its central vehicle opening clear.
                face.stair(length-.25,4.9,floor,1.05,186,rail)
            if address==6531 and isfront:
                left,right=length*.43,length*.56
                masonry_panel(face,left,right,eave,mortar,red)
                for lev in [1,2]:
                    face.balcony(.04,left-.10,lev*floor,1.37,186,rail)
                    face.balcony(right+.10,length-.04,lev*floor,1.37,186,rail)
                # Entrance boundary piers and low wall remain below glazing.
                for xa,xb in [(.05,length*.40),(length*.60,length-.05)]:
                    face.box(((xa+xb)/2,3.0,.41),(xb-xa,.20,.82),wall)
                    face.box(((xa+xb)/2,3.0,.85),(xb-xa+.08,.28,.07),red)
                    for x in [xa,xb]:
                        face.box((x,3.0,.61),(.37,.37,1.22),red)
                        face.box((x,3.0,1.25),(.45,.45,.09),red)
            if gallery:
                # The observed lower external gallery continues down the long
                # side; upper small windows remain separate from this access.
                start=1.2;end=length-.40;depth=1.12
                stair_end=length-.55;stair_start=stair_end-5.5
                face.box(((start+stair_start)/2,depth/2,floor-.10),(stair_start-start,depth,.20),186)
                face.rail(start,stair_start-.12,depth-.06,floor,rail)
                for x in np.arange(start+.10,stair_start,5.4):
                    face.box((x,depth-.13,(floor-.2)/2),(.14,.14,floor-.2),wall)
                face.stair(stair_end,5.5,floor,depth,186,rail)
                buffer.details['long_external_gallery_length_m']=stair_start-start
        roof(buffer,poly,datum,eave,maxheight,'gable' if address==6531 else 'hip' if address==6522 else 'shallow',roofmat,get('roof_soffit'),trim)
        emitted_vertices=np.vstack([np.asarray(g['v']) for g in buffer.groups.values()])
        actual_max=float(emitted_vertices[:,2].max()-datum)
        assert abs(actual_max-maxheight)<1e-7,(source,actual_max,maxheight)
        assert poly.equals(shape(feature['geometry']))
        buffer.finish(parts)
        prior=[p['object'] for p in old['parts'] if p['source']==source]
        base=[p['component'] for group in layout.values() for p in group['parts'] if p['part'].startswith(source.replace(':','_')+'_') and (p['part'].endswith('_walls') or p['part'].endswith('_roof'))]
        exclude_facades.extend(prior);exclude_base.extend(base)
        records.append({'address':f'{address} Sabado Tarde Road','source_id':source,'source_url':f'https://www.openstreetmap.org/way/{oid}',
                        'footprint':feature['geometry'],'footprint_retained_exactly':True,'plan_area_m2':poly.area,'foundation_datum_m':datum,
                        'mapped_levels':levels,'retained_estimated_max_height_m':maxheight,'estimated_eave_height_m':eave,'estimated_floor_spacing_m':floor,
                        'verified_emitted_max_height_m':actual_max,'source_shell_boundary_symmetric_difference_m2':poly.symmetric_difference(shape(feature['geometry'])).area,
                        'street_facing_edges':front_edge_ids,'excluded_prior_facade_objects':prior,'excluded_base_components':base,
                        'reference_assignment':'Property photo. A/B identification unverified; both elevations use explicitly labeled architectural analogy.' if address==6531 else 'Address-identified manager photograph.',
                        'details':buffer.details,'validation':buffer.validation})
    report=parts.close();scene.save(OUT/'materials.cys')
    assert report['triangles']<150000,report['triangles']
    assert all(rec['validation']['nonfinite']==0 and rec['validation']['uv_degenerate_triangles']==0 for rec in records)
    serialized=validate_serialized(OUT/'architecture.clm',scene.materials-MATERIAL_OFFSET,report['parts'])
    camera=manifest['camera_candidate'].copy()
    cx,cy=camera['support_local_xy_m'];tx,ty=camera['look_at_local_xy_m']
    camera['eye_local_m']=[cx,cy,float(dem.sample(cx,cy))+camera['eye_height_above_sampled_ground_m']]
    camera['target_local_m']=[tx,ty,float(dem.sample(tx,ty))+camera['target_height_above_sampled_ground_m']]
    report.update({'material_offset':MATERIAL_OFFSET,'material_count':scene.materials-MATERIAL_OFFSET,'materials':mats,
                   'object_offset':OBJECT_OFFSET,'buildings':records,'exclude_prior_facade_objects':exclude_facades,'replace_sector_components':exclude_base,
                   'reference_manifest':'references/residential-street-v2/REFERENCE_MANIFEST.json','reference_manifest_sha256':digest(ROOT/'references/residential-street-v2/REFERENCE_MANIFEST.json'),
                   'camera_recommendation':camera,'source_generator':'work/build_iv_sabado_frontages.py','source_generator_sha256':digest(Path(__file__)),
                   'finish_source_commit':SOURCE_COMMIT,'finish_source_receipt':'evidence/full-iv-street-finishes/FINISH_RECEIPT.json',
                   'material_contract':{'uv_chart_m_per_unit':CHART,'plaster_tile_m':PLASTER_TILE,'plaster_texture_frequency':CHART/PLASTER_TILE,
                       'height':'Original CYBR lime height in metres; metric_bump; no AO in pigment.',
                       'stone':'Original geometric fieldstone shapes with pinned CYBR travertine porosity fields at 0.65 m and 0.006 m source height scale. Explicit optical analogy, not a verified local stone species.',
                       'native_spectra':'Photo-informed linear colour controls fit to scene basis, not measured material spectra.',
                       'unchanged_existing_material_ids':{'asphalt_metric_bump':9,'glazing':69,'interior_backing':70,'concrete_metric_bump':186}},
                   'textures':{str(p.relative_to(ROOT)):{'sha256':digest(p),'bytes':p.stat().st_size} for p in textures},
                   'validation':{'finite_geometry':True,'uv_degenerate_triangles':sum(r['validation']['uv_degenerate_triangles'] for r in records),'bounded_below_150000_triangles':True,'render_validated':False,'serialized_geometry':serialized},
                   'limits':'Manager photo dates unknown. All internal dimensions, rail spacing, roof slope, hidden/rear elevations, stairs and optical controls are estimates. Existing mapped heights 6.6/9.9 m are retained. A/B photo assignment is unresolved. No source photo is used as a texture. No scene assembly is changed.'})
    report['geometry_sha256']=digest(OUT/'architecture.clm')
    (OUT/'ARCHITECTURE_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'triangles':report['triangles'],'parts':len(report['parts']),'materials':report['material_count'],'replace_sector_components':exclude_base,'exclude_prior_facade_objects':exclude_facades,'camera':camera['eye_local_m'],'validation':report['validation']}),flush=True)


if __name__=='__main__':
    build()
