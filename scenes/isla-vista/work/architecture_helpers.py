"""Retained CYBR metric facade helpers. Dimensions are metres."""
import numpy as np
CHART=1.25

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
