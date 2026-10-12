"""Fresh native4096 evaluation of the retained procedural recipe (no resizing)."""
from pathlib import Path
import sys,json,time,hashlib,resource,struct,zlib,gc
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter,map_coordinates
from height_normals import height_normals,encode16
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'vendor'));from mineral_construction import construction
N=4096;s=json.loads((R/'material.json').read_text());out=R/'native4096';out.mkdir(exist_ok=True);start=time.monotonic();v,construction_report=construction(s,N)
assert v['Height'].shape==(N,N)
files={}
for name in ['BaseColor','Roughness','Metallic']:
 a=np.rint(np.clip(v[name],0,1)*255).astype('u1');p=out/(name+'.png');Image.fromarray(a).save(p,compress_level=4);files[name]={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'resolution':[N,N],'bit_depth':8}
h=v['Height'].copy();del v;gc.collect();np.save(out/'HeightState.npy',h)
macro=gaussian_filter(h,max(.5,N/512*1.15),mode='wrap');coord=np.linspace(-.5,N-.5,513,dtype='f4');y,x=np.meshgrid(coord,coord,indexing='ij');g=map_coordinates(macro,np.stack((y,x)),order=1,mode='grid-wrap');np.save(out/'GeometryHeight.npy',g.astype('f4'));del macro,x,y;gc.collect()
n=height_normals(h,tile_m=s['tile_m'],height_scale_m=s['height_scale_m'],periodic=True);a=encode16(n);del n;gc.collect()
def chunk(t,b):return struct.pack('>I',len(b))+t+b+struct.pack('>I',zlib.crc32(t+b)&0xffffffff)
p=out/'Normal_Object_RGB16.png';comp=zlib.compressobj(4);blocks=[]
for row in a:blocks.append(comp.compress(b'\0'+row.astype('>u2').tobytes()))
blocks.append(comp.flush());p.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',N,N,16,2,0,0,0))+chunk(b'IDAT',b''.join(blocks))+chunk(b'IEND',b''));files['Normal_Object']={'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'resolution':[N,N],'bit_depth':16}
for name in ['HeightState.npy','GeometryHeight.npy']:files[name]={'sha256':hashlib.sha256((out/name).read_bytes()).hexdigest()}
r={'resolution':[N,N],'native_evaluation':True,'upscaled':False,'source_recipe_seed':s['seed'],'tile_m':s['tile_m'],'height_scale_m':s['height_scale_m'],'geometry_grid':512,'files':files,'seconds':time.monotonic()-start,'peak_rss_mib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'physical_qualification':False,'historical_identity_claim':False,'scope':'Same procedural recipe evaluated at native4096; color/roughness/state/geometry resampled from the procedural generator, not from a lower-resolution image.'};(out/'receipt.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)
