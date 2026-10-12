"""Exact polygon/TIN classification through a bounded boundary-segment index."""
import numpy as np,shapely

def polygon_tin_masks(area,triangles,tree,centroids):
 # A connected triangle that has no polygon-boundary intersection is entirely
 # inside or outside. Testing its centroid is sufficient in that case, including
 # polygons with holes. Segment/TIN queries avoid repeated full-polygon tests.
 rings=[]
 for poly in (area.geoms if hasattr(area,'geoms') else [area]):
  if poly.geom_type!='Polygon':continue
  for ring in [poly.exterior,*poly.interiors]:
   p=np.asarray(ring.coords)[:,:2];rings.append(np.stack([p[:-1],p[1:]],axis=1))
 boundary=np.zeros(len(triangles),dtype=bool)
 if rings:
  seg=np.concatenate(rings)
  for start in range(0,len(seg),20000):
   pairs=tree.query(shapely.linestrings(seg[start:start+20000]),predicate='intersects')
   boundary[pairs[1]]=True
 shapely.prepare(area);inside=shapely.contains_xy(area,centroids[:,0],centroids[:,1])&~boundary
 return inside,boundary

class LocalPolygonClipper:
 """Cache exact local polygon portions before repeated small TIN intersections.

 The padded cell contains every vertex of the requested triangle. Therefore
 intersection with the clipped polygon equals intersection with the full one.
 Robust polygon overlay is used once per cell. The fast rectangle clipper is
 intentionally avoided: retained narrow coastal rings can collapse inside it.
 """
 def __init__(self,area,cell=40.,padding=8.):
  self.area=area;self.cell=cell;self.padding=padding;self.cache={}
 def intersection(self,triangle):
  bounds=triangle.bounds;cx=(bounds[0]+bounds[2])*.5;cy=(bounds[1]+bounds[3])*.5
  key=(int(np.floor(cx/self.cell)),int(np.floor(cy/self.cell)))
  if key not in self.cache:
   x,y=np.asarray(key)*self.cell;p=self.padding
   local=self.area.intersection(shapely.box(x-p,y-p,x+self.cell+p,y+self.cell+p))
   self.cache[key]=local
  assert bounds[2]-bounds[0]<=self.padding*2 and bounds[3]-bounds[1]<=self.padding*2
  return triangle.intersection(self.cache[key])
