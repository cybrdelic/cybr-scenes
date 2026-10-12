"""Shared geographic and authored-state contracts for the coastal prototype."""
from pathlib import Path
import sys,json,numpy as np
r=Path(__file__).resolve().parent.parent
for p in [r/'geo-deps',r/'work/cybr-iv-full/src',r/'whole-iv-vendor',r/'work/iv-component-runtime']:sys.path.insert(0,str(p))
import rasterio,shapely
from scipy.ndimage import map_coordinates
from shapely.geometry import shape
from pyproj import Transformer
source=json.loads((r/'data/full-iv-20261011/manifest.json').read_text())['sector'];origin=np.array(source['local_origin_utm_m']);features=json.loads((r/'evidence/full-iv-roofs/normalized.geojson').read_text())['features']
coast=[]
for f in features:
 if f['properties']['category']!='coastline':continue
 g=shape(f['geometry'])
 for line in (g.geoms if hasattr(g,'geoms') else [g]):
  xy=np.asarray(line.coords);coast.extend(np.stack([xy[:-1],xy[1:]],axis=1))
shore=shapely.STRtree(shapely.linestrings(np.asarray(coast)))
state=json.loads((r/'evidence/full-iv-coastal-water/WATER_RECEIPT.json').read_text())
def distance(p):
 index,d=shore.query_nearest(shapely.points(p),all_matches=False,return_distance=True);out=np.empty(len(p));out[index[0]]=d;return out
def water_height(p):
 p=np.asarray(p);fade=1-np.exp(-(distance(p)/18)**2);h=np.zeros(len(p))
 for w in state['waves']:
  d=np.array([np.cos(np.deg2rad(w['direction_deg'])),np.sin(np.deg2rad(w['direction_deg']))]);h+=w['amplitude_m']*np.sin((p@d)*2*np.pi/w['wavelength_m']+w['phase'])
 return state['authored_mean_level_m']+fade*h
class Bathymetry:
 def __init__(self):
  with rasterio.open(r/'data/coastal-coned-20261011/coned_native_1m_iv_subset.tif') as f:self.a=f.read(1);self.transform=f.transform;self.crs=f.crs
  self.project=Transformer.from_crs(32611,self.crs,always_xy=True)
 def sample(self,xy):
  xy=np.asarray(xy)+origin;x,y=self.project.transform(xy[:,0],xy[:,1]);t=self.transform;cols=(x-t.c)/t.a-.5;rows=(y-t.f)/t.e-.5
  assert np.min(cols)>-1 and np.max(cols)<self.a.shape[1] and np.min(rows)>-1 and np.max(rows)<self.a.shape[0]
  return map_coordinates(self.a,[rows,cols],order=1,mode='nearest')
def canopy_polygons():
 data=json.loads((r/'data/coastal-kelp-2016/iv_kelp_2016_local.geojson').read_text());return [(f['id'],f['properties']['source_dbf_attributes']['Class_Name'],shape(f['geometry'])) for f in data['features']]
