"""Pure numerical helpers for optional metric tile instances. No scene I/O."""
from __future__ import annotations
import numpy as np
from relief_math import TILE_M, HEIGHT_SCALE_M, smoothstep, grid_shape


def road_height(x, y):
    """Unchanged broad profile from R6 build_scene.py; validated against input."""
    y = np.asarray(y)
    grade = (.003*y + 1.2*np.exp(-((y-105)/85)**2)
             - 1.2*np.exp(-(105/85)**2) + .55*np.exp(-((y-430)/150)**2))
    return grade + .07 + .064*(1-np.minimum(np.sqrt(np.asarray(x)**2+.02**2)/3.2,1))


class SourceGrid:
    """Exact XY barycentrics on the existing regular-row source triangles."""
    def __init__(self, co, diagonal):
        self.co = np.asarray(co, dtype=np.float64)
        self.ny, self.nx = grid_shape(self.co)
        self.grid = self.co.reshape(self.ny, self.nx, 3)
        self.ys = self.grid[:, 0, 1]
        self.diagonal = np.asarray(diagonal, dtype=bool)
        fractions = np.linspace(0, 1, self.nx)
        expected = self.grid[:, :1, 0]*(1-fractions)+self.grid[:, -1:, 0]*fractions
        if np.max(np.abs(expected-self.grid[:, :, 0])) > 1e-5:
            raise ValueError('Source grid columns are not uniform fractions of each row')

    def weights(self, xy, clamp_x=False, extrapolate_x=False):
        xy = np.asarray(xy, dtype=np.float64).copy()
        j = np.clip(np.searchsorted(self.ys, xy[:,1], side='right')-1, 0, self.ny-2)
        t = (xy[:,1]-self.ys[j])/(self.ys[j+1]-self.ys[j])
        if np.any((t < -1e-6) | (t > 1+1e-6)):
            raise ValueError('Query outside source longitudinal extent')
        left = self.grid[j,0,0]*(1-t)+self.grid[j+1,0,0]*t
        right = self.grid[j,-1,0]*(1-t)+self.grid[j+1,-1,0]*t
        if clamp_x:
            xy[:,0] = np.clip(xy[:,0], left, right)
        elif not extrapolate_x and np.any((xy[:,0] < left-1e-7) | (xy[:,0] > right+1e-7)):
            raise ValueError('Query outside source cross-road extent')
        i = np.clip(np.floor((xy[:,0]-left)/(right-left)*(self.nx-1)).astype(int),0,self.nx-2)
        q = j*self.nx+i
        ids = np.column_stack((q,q+1,q+self.nx+1,q+self.nx))
        p = self.co[ids,:2]
        ac = self.diagonal[j,i]
        # The source cell may be a slightly skewed trapezoid. Solve actual XY
        # barycentrics, not an approximate rectangular/bilinear parameter map.
        cross_ac = ((p[:,2,0]-p[:,0,0])*(xy[:,1]-p[:,0,1])
                    -(p[:,2,1]-p[:,0,1])*(xy[:,0]-p[:,0,0]))
        cross_bd = ((p[:,3,0]-p[:,1,0])*(xy[:,1]-p[:,1,1])
                    -(p[:,3,1]-p[:,1,1])*(xy[:,0]-p[:,1,0]))
        patterns = [(ac & (cross_ac <= 0),(0,1,2)),
                    (ac & (cross_ac > 0),(0,2,3)),
                    (~ac & (cross_bd >= 0),(0,1,3)),
                    (~ac & (cross_bd < 0),(1,2,3))]
        weights = np.zeros((len(xy),4), dtype=float)
        for mask, columns in patterns:
            v = p[mask][:,columns]
            d1,d2,d = v[:,1]-v[:,0],v[:,2]-v[:,0],xy[mask]-v[:,0]
            det = d1[:,0]*d2[:,1]-d1[:,1]*d2[:,0]
            w1 = (d[:,0]*d2[:,1]-d[:,1]*d2[:,0])/det
            w2 = (d1[:,0]*d[:,1]-d1[:,1]*d[:,0])/det
            rows = np.flatnonzero(mask)
            weights[rows,columns[0]] = 1-w1-w2
            weights[rows,columns[1]] = w1
            weights[rows,columns[2]] = w2
        check=weights[(xy[:,0]>=left)&(xy[:,0]<=right)] if extrapolate_x else weights
        if len(check) and (np.min(check) < -5e-5 or np.max(check) > 1+5e-5):
            raise ValueError('Source triangle lookup escaped its cell')
        return ids,weights

    def sample(self, values, xy, clamp_x=False, extrapolate_x=False):
        ids,w = self.weights(xy,clamp_x,extrapolate_x)
        return np.einsum('ni,ni...->n...',w,np.asarray(values)[ids])


def tile_matrix(x0,y0):
    z00 = float(road_height(x0,y0))
    a = float(road_height(x0+TILE_M,y0)-z00)/TILE_M
    b = float(road_height(x0,y0+TILE_M)-z00)/TILE_M
    return np.array([[1,0,0,x0],[0,1,0,y0],[a,b,1,z00],[0,0,0,1]],dtype=float)


def tile_template(height, flags, fade_m=.05):
    """flags = (left,right,bottom,top); each variant shares adjacent edges."""
    g = np.asarray(height)
    if g.shape != (513,513):
        raise ValueError('Only pinned native 513×513 geometry is supported')
    axis = np.linspace(0,TILE_M,len(g))
    x,y = np.meshgrid(axis,axis)
    weight = np.ones_like(x)
    for flag,d in zip(flags,(x,TILE_M-x,y,TILE_M-y)):
        if flag:
            weight *= smoothstep(0,fade_m,d)
    z = (g[::-1]-.5)*HEIGHT_SCALE_M*weight
    co = np.stack((x,y,z),axis=-1).reshape(-1,3).astype(np.float32)
    n = len(g);q=(np.arange(n-1)[:,None]*n+np.arange(n-1)[None]).ravel()
    tri = np.concatenate((np.column_stack((q,q+1,q+n+1)),np.column_stack((q,q+n+1,q+n)))).astype(np.int32)
    return co,tri


def bilinear_raster(data, xy, bounds):
    """Match Blender Linear image sampling of center-sampled bottom-up pixels."""
    xmin,xmax,ymin,ymax = bounds
    h,w = data.shape[:2]
    p = (np.asarray(xy)-[xmin,ymin])/[xmax-xmin,ymax-ymin]*[w,h]-.5
    p = np.maximum(0,np.minimum(p,[w-1,h-1]))
    ij = np.floor(p).astype(int);f=p-ij
    ix,iy=ij[:,0],ij[:,1];jx=np.minimum(ix+1,w-1);jy=np.minimum(iy+1,h-1)
    fx,fy=f[:,0,None],f[:,1,None]
    return ((data[iy,ix]*(1-fx)+data[iy,jx]*fx)*(1-fy)
            +(data[jy,ix]*(1-fx)+data[jy,jx]*fx)*fy)


def split_halfplane(poly, axis, edge, greater):
    """Clip XY + barycentric payload, retaining exact axis-aligned cut value."""
    if len(poly)==0:
        return np.empty((0,5)),np.empty((0,5))
    inside=[];outside=[]
    for a,b in zip(poly,np.roll(poly,-1,axis=0)):
        ia = a[axis] >= edge if greater else a[axis] <= edge
        ib = b[axis] >= edge if greater else b[axis] <= edge
        (inside if ia else outside).append(a)
        if ia != ib:
            t=(edge-a[axis])/(b[axis]-a[axis]);p=a+t*(b-a);p[axis]=edge
            inside.append(p);outside.append(p)
    return np.asarray(inside).reshape(-1,5),np.asarray(outside).reshape(-1,5)


def subtract_rectangle(triangle_xy, bounds):
    """Conforming cut-line arrangement, then remove the rectangle interior.

    Splitting only the current inside polygon causes a T junction at a rectangle
    corner. Instead every piece is split by every line. The caller propagates
    new points on original edges into untouched adjacent source triangles.
    """
    xmin,xmax,ymin,ymax = bounds
    pieces=[np.column_stack((triangle_xy,np.eye(3)))]
    for axis,edge,greater in ((0,xmin,True),(0,xmax,False),(1,ymin,True),(1,ymax,False)):
        following=[]
        for poly in pieces:
            for part in split_halfplane(poly,axis,edge,greater):
                if len(part)<3:continue
                area=np.sum(part[:,0]*np.roll(part[:,1],-1)-part[:,1]*np.roll(part[:,0],-1))
                if abs(area)>1e-16:following.append(part)
        pieces=following
    return [p for p in pieces if not (xmin < p[:,0].mean() < xmax and ymin < p[:,1].mean() < ymax)]
