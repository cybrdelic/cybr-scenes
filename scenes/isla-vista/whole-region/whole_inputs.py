"""Restore ODbL snapshots and fetch byte-checked public dependencies.

The coastal archive extraction is separate so an ordinary street rebuild does
not silently acquire large datasets. No credentials or private Library access.
"""
from pathlib import Path
import argparse,gzip,hashlib,json,os,shutil,subprocess,sys,tempfile,urllib.request
from public_inputs import resolve,validate
R=Path(__file__).resolve().parent
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def restore_osm():
 for row in json.loads((R/'BUNDLED_OSM.json').read_text())['files']:
  archive=R/row['archive'];assert sha(archive)==row['gzip_sha256']
  with gzip.open(archive,'rb') as f:data=f.read(row['bytes']+1)
  assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256']
  out=R/row['path'];out.parent.mkdir(parents=True,exist_ok=True)
  if out.exists():assert sha(out)==row['sha256']
  else:out.write_bytes(data)
def download(row,path):
 path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():assert sha(path)==row['sha256'];return
 if shutil.disk_usage(R).free<1024**3+row['bytes']:raise RuntimeError('Insufficient disk reserve')
 h=hashlib.sha256();count=0;tmp=path.with_suffix(path.suffix+'.partial')
 try:
  with urllib.request.urlopen(urllib.request.Request(row['url'],headers={'User-Agent':'CYBR-Isla-Vista-source-replay/1','Accept-Encoding':'identity'}),timeout=60) as response,tmp.open('wb') as out:
   for chunk in iter(lambda:response.read(1<<20),b''):
    count+=len(chunk)
    if count>row['bytes']:raise ValueError('Dated source archive size changed')
    out.write(chunk);h.update(chunk)
  if count!=row['bytes'] or h.hexdigest()!=row['sha256']:raise ValueError('Dated source archive changed; compatible accessible snapshot required')
  os.replace(tmp,path)
 finally:
  if tmp.exists():tmp.unlink()
def raster_contract(path):
 import rasterio,numpy as np
 with rasterio.open(path) as f:
  a=f.read(1)
  return {'epsg':f.crs.to_epsg(),'transform':list(f.transform),'shape':list(a.shape),'dtype':str(a.dtype),'nodata':f.nodata,'ordered_band_sha256':hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()}
def coastal():
 # Fail before large downloads if setup was omitted or the declared environment drifted.
 from importlib.metadata import version
 for dependency in (R/'requirements.txt').read_text().splitlines():
  if not dependency.strip() or dependency.startswith('#'):continue
  name,pinned=dependency.split('==');actual=version(name)
  if actual!=pinned:raise RuntimeError('Run ./run.sh setup: '+name+' requires '+pinned+', found '+actual)
 expected=json.loads((R/'DERIVED_INPUTS.json').read_text());report=[]
 with tempfile.TemporaryDirectory(prefix='.geographic-extract-',dir=R) as directory:
  t=Path(directory)
  inputs=['data/full-iv-20261011/manifest.json','evidence/whole-iv-coverage/isla_vista_cdp.geojson','references/urban-canopy-2022/COUNTY_ARCHIVE_RECEIPT.json']
  for name in inputs:
   p=t/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(R/name,p)
  for script in ['acquire_iv_coned_subset.py','extract_iv_kelp_2016.py','extract_iv_canopy_2022.py']:
   p=t/'work'/script;p.parent.mkdir(exist_ok=True);shutil.copyfile(R/'work'/script,p)
  for folder,receipt,filename in [('coastal-kelp-2016','data/coastal-kelp-2016/SOURCE_RECEIPT.json','BIO_CA_Kelp2016.zip'),('urban-canopy-2022','references/urban-canopy-2022/COUNTY_ARCHIVE_RECEIPT.json','CALFIRE_UrbanCanopy_SantaBarbaraCounty.zip')]:
   row=json.loads((R/receipt).read_text());download(row,t/'data'/folder/filename)
  for script in ['acquire_iv_coned_subset.py','extract_iv_kelp_2016.py','extract_iv_canopy_2022.py']:
   subprocess.run([sys.executable,str(t/'work'/script)],check=True,cwd=t,timeout=600)
  for row in expected['rasters']:
   p=t/row['path'];actual=raster_contract(p)
   if actual!=row['raster_contract']:raise ValueError('Raster scene input changed: '+row['path'])
   out=R/row['path'];out.parent.mkdir(parents=True,exist_ok=True);os.replace(p,out)
   report.append({'path':row['path'],'historical_raw_sha256':row['sha256'],'current_raw_sha256':sha(out),'band_crs_grid_contract_exact':True})
  kelp='data/coastal-kelp-2016/iv_kelp_2016_local.geojson';p=t/kelp
  if sha(p)!=expected['kelp']['subset_sha256']:raise ValueError('Kelp subset changed; preserve the original ordered geometry/attributes contract')
  out=R/kelp;out.parent.mkdir(parents=True,exist_ok=True);os.replace(p,out);report.append({'path':kelp,'raw_sha256':sha(out),'exact':True})
 # Raster container metadata/compression may differ despite exact scene inputs.
 # Preserve the historical receipt alongside an explicit installed-file hash.
 receipt=R/'references/urban-canopy-2022/IV_NATIVE_SUBSET_RECEIPT.json'
 original=json.loads(receipt.read_text());original.setdefault('historical_subset_sha256',original['subset_sha256']);original['subset_sha256']=sha(R/'data/urban-canopy-2022/iv_canopy_2022_native_060m.tif');original['raster_contract_exact']=True
 receipt.write_text(json.dumps(original,indent=2)+'\n')
 (R/'COASTAL_INPUT_VALIDATION.json').write_text(json.dumps({'passed':True,'files':report,'qualification':'Dated classifications/elevations, not current surveyed vegetation or coastline. Each provider retains its own attribution and conditions.'},indent=2)+'\n')
p=argparse.ArgumentParser();p.add_argument('action',choices=['fetch','verify','coastal']);a=p.parse_args()
if a.action in {'fetch','verify'}:restore_osm();resolve(R,a.action=='fetch')
else:coastal()
