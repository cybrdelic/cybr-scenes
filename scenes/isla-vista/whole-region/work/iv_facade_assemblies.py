"""Reusable metric exterior assemblies; all dimensions are authored estimates.

Source plans/roof edges are provided by the caller. This module neither chooses
geographic positions nor changes source story counts, roof forms or heights.
"""
import hashlib
import numpy as np

CHART_M = 1.25

def family(source_id, kind):
    """Stable building-scale choice, never a claim about the individual facade."""
    index = hashlib.sha256(('iv-facade-v2:' + source_id).encode()).digest()[0] % 3
    residential = [
        dict(name='paired_slider', width=1.55, height=1.24, sill=.95, pitch=3.05, reveal=.18, panes=2, light_frame=True),
        dict(name='broad_picture', width=1.95, height=1.28, sill=.91, pitch=3.65, reveal=.21, panes=3, light_frame=False),
        dict(name='compact_pair', width=1.22, height=1.34, sill=.92, pitch=2.85, reveal=.16, panes=2, light_frame=True),
    ]
    result = residential[index].copy()
    if kind == 'house':
        result['pitch'] += .20
        result['width'] *= .92
    elif kind == 'commercial':
        result.update(width=2.15, pitch=3.35, panes=3, light_frame=False)
    elif kind == 'institution':
        result.update(width=1.65, pitch=3.25, panes=2, light_frame=False)
    result['basis'] = 'Deterministic authored family informed by local reference proportions; not an observation of this building.'
    return result

class FacadeFrame:
    """x runs along wall; y is exterior; z is absolute height, all in metres."""
    def __init__(self, buffer, a, b):
        self.buffer = buffer
        self.a = np.asarray(a, float)
        self.t = np.asarray(b, float) - self.a
        self.t /= np.linalg.norm(self.t)
        self.n = np.array([self.t[1], -self.t[0]])

    def world(self, local):
        q = np.asarray(local, float)
        return np.c_[self.a + q[:, :1]*self.t + q[:, 1:2]*self.n, q[:, 2]]

    def quad(self, local, material):
        xyz = self.world(local)
        u = xyz[1] - xyz[0]; u /= np.linalg.norm(u)
        n = np.cross(u, xyz[-1] - xyz[0]); n /= np.linalg.norm(n)
        v = np.cross(n, u)
        uv = np.c_[(xyz-xyz[0])@u, (xyz-xyz[0])@v] / CHART_M
        self.buffer.quad(xyz.tolist(), material, uv.tolist())

    def panel(self, x0, x1, z0, z1, material, y=0):
        self.quad([(x0,y,z0),(x1,y,z0),(x1,y,z1),(x0,y,z1)],material)

    def box(self, x0, x1, y0, y1, z0, z1, material, slope=0):
        """Closed prism; optional dz/dx follows an existing inclined edge."""
        q=np.array([[x,y,z+slope*(x-x0)] for z in [z0,z1] for y in [y0,y1] for x in [x0,x1]])
        # Tangent/exterior/up is left handed, so reverse the six cube faces.
        for ids in [[0,2,3,1],[4,5,7,6],[0,1,5,4],[2,6,7,3],[0,4,6,2],[1,3,7,5]]:
            self.quad(q[ids][::-1],material)

    def opening(self, x0, x1, z0, z1, wall, frame, glass, backing,
                sill, depth=.18, panes=2, door=False, curtains=False):
        """True void return, closed frames, inset pane and metre-scale sill."""
        for x, reverse in [(x0,False),(x1,True)]:
            q=[(x,0,z0),(x,-depth,z0),(x,-depth,z1),(x,0,z1)]
            self.quad(q[::-1] if reverse else q,wall)
        for z, reverse in [(z0,False),(z1,True)]:
            q=[(x0,0,z),(x1,0,z),(x1,-depth,z),(x0,-depth,z)]
            self.quad(q[::-1] if reverse else q,wall)
        self.panel(x0,x1,z0,z1,backing,-depth-.30)
        glazing_y=-depth+.035
        self.panel(x0,x1,z0,z1,glass,glazing_y)
        width=.052; front=glazing_y+.034; rear=glazing_y-.027
        for x in [x0,x1]:
            self.box(x-width/2,x+width/2,rear,front,z0-.028,z1+.028,frame)
        for z in [z0,z1]:
            self.box(x0+width/2,x1-width/2,rear,front,z-.028,z+.028,frame)
        if not door:
            for i in range(1,panes):
                x=x0+(x1-x0)*i/panes
                self.box(x-.018,x+.018,rear+.006,front-.006,z0+.028,z1-.028,frame)
            # Solid sill with end faces, projecting 75 mm beyond wall.
            self.box(x0-.055,x1+.055,-depth,.075,z0-.061,z0-.026,sill)
            self.box(x0-.045,x1+.045,.067,.080,z0-.070,z0-.050,sill)
        if curtains and not door:
            # A bounded side panel behind glazing; authored occupancy estimate.
            # Fold pitch 75 mm and depth 12 mm are physical, not texture noise.
            end=x0+(x1-x0)*.31
            xs=np.linspace(x0+.028,end,max(3,int((end-x0)/.075)+1))
            for i,(a,b) in enumerate(zip(xs[:-1],xs[1:])):
                ya=-depth-.070+(.012 if i%2 else 0)
                yb=-depth-.070+(.012 if (i+1)%2 else 0)
                self.quad([(a,ya,z0+.028),(b,yb,z0+.028),(b,yb,z1-.028),(a,ya,z1-.028)],sill)

    def roof_edge(self, length, za, zb, material, flat):
        """Trim only, following the supplied roof edge without raising it."""
        slope=(zb-za)/length
        self.box(0,length,-.105,.025,za-.145,za-.030,material,slope)
        if flat:
            self.box(0,length,-.145,.042,za-.030,za-.003,material,slope)
        else:
            self.box(0,length,-.120,.035,za-.027,za-.003,material,slope)
