"""Read a bounded original-data window from NOAA's official CoNED tile.

No full remote raster is downloaded, and TLS verification remains enabled.
This does not modify current scene terrain or its shoreline.
"""
from pathlib import Path
import sys,os,ssl,json,hashlib,datetime,math
r=Path(__file__).resolve().parent.parent;sys.path.insert(0,str(r/'geo-deps'))
ca=ssl.get_default_verify_paths().cafile
if ca:os.environ['GDAL_CURL_CA_BUNDLE']=ca
import numpy as np,rasterio
from rasterio.windows import from_bounds,Window
from pyproj import Transformer
url='https://noaa-nos-coastal-lidar-pds.s3.amazonaws.com/dem/CA_Southern_CoNED_DEM_2016_8658/Southern_California_Topobathy_DEM_1m_A_03.tif'
out=r/'data/coastal-coned-20261011';out.mkdir(exist_ok=True)
original=json.loads((r/'data/full-iv-20261011/manifest.json').read_text());scene_bounds=original['sector']['utm_bounds'];transformer=Transformer.from_crs(32611,26911,always_xy=True);bounds=transformer.transform_bounds(*scene_bounds,densify_pts=21)
config=dict(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR',CPL_VSIL_CURL_ALLOWED_EXTENSIONS='.tif',GDAL_HTTP_TIMEOUT='25',GDAL_HTTP_MAX_RETRY='0',GDAL_CACHEMAX=96_000_000)
if ca:config.update(GDAL_CURL_CA_BUNDLE=ca,CURL_CA_BUNDLE=ca,SSL_CERT_FILE=ca)
with rasterio.Env(**config):
 with rasterio.open(url) as src:
  window=from_bounds(*bounds,src.transform);left=math.floor(window.col_off);top=math.floor(window.row_off);right=math.ceil(window.col_off+window.width);bottom=math.ceil(window.row_off+window.height);window=Window(left,top,right-left,bottom-top);assert window.width*window.height<7_000_000
  print('Reading native pixel window',window,flush=True);a=src.read(1,window=window);valid=np.isfinite(a)&(a!=src.nodata);profile=src.profile;profile.update(width=window.width,height=window.height,transform=src.window_transform(window),compress='deflate',predictor=3,tiled=True,blockxsize=256,blockysize=256)
  dest=out/'coned_native_1m_iv_subset.tif'
  with rasterio.open(dest,'w',**profile) as dst:dst.write(a,1);dst.update_tags(AREA_OR_POINT='Point',SOURCE_URL=url)
  with rasterio.open(dest) as check:assert np.array_equal(check.read(1),a)
  receipt={'source_url':url,'catalog_url':'https://coast.noaa.gov/htdata/raster2/elevation/CA_Southern_CoNED_DEM_2016_8658/','metadata_url':'https://www.fisheries.noaa.gov/inport/item/55359','retrieved_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_crs':str(src.crs),'source_vertical_datum':'NAVD88 metres, source metadata; GEOID09 validation convention. No tide or geoid conversion applied here.','source_grid_spacing_m':list(src.res),'source_window':dict(window.todict()),'scene_bounds_epsg32611':scene_bounds,'requested_bounds_epsg26911':list(bounds),'subset_transform':list(profile['transform']),'subset_shape':list(a.shape),'pixel_values_preserved_exact':True,'valid_fraction':float(valid.mean()),'elevation_percentiles_m':np.percentile(a[valid],[0,1,10,50,90,99,100]).tolist(),'file_bytes':dest.stat().st_size,'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'horizontal_transform_description':transformer.description,'horizontal_transform_accuracy_m':transformer.accuracy,'attribution':'USGS CoNED, NOAA Office for Coastal Management and original survey contributors. Compiled2016 from sources1930–2014.','limitations':'Grid spacing is not local survey accuracy. Source date and nearshore interpolation vary spatially; spatial metadata and current DEM/shoreline consistency must be checked before scene use. No current-scene input was replaced.'}
(out/'ACQUISITION_RECEIPT.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
