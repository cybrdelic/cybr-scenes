"""Derive a navigation proxy from actual published Gaussian centers, not a flat plane."""
import io,json,zipfile,pathlib
import numpy as np
from PIL import Image
root=pathlib.Path('public/data/259c0051')
with zipfile.ZipFile(root/'scene.sog') as z:
 m=json.loads(z.read('meta.json'));n=m['count'];arrays=[np.array(Image.open(io.BytesIO(z.read(f)))).reshape(-1,4)[:n,:3].astype(np.float32) for f in m['means']['files']]
 p=(arrays[0]+arrays[1]*256)/65535*(np.array(m['means']['maxs'])-m['means']['mins'])+m['means']['mins'];p=np.sign(p)*np.expm1(np.abs(p));p*=np.array([-1,-1,1])
 alpha=np.array(Image.open(io.BytesIO(z.read(m['sh0']['files'][0])))).reshape(-1,4)[:n,3]
step=.25;ox,oz=-16,-16;nx,nz=105,113
sel=(alpha>45)&(p[:,1]>-4)&(p[:,1]<7)&(p[:,0]>=ox)&(p[:,0]<10)&(p[:,2]>=oz)&(p[:,2]<12)
p=p[sel];gx=np.rint((p[:,0]-ox)/step).astype(int);gz=np.rint((p[:,2]-oz)/step).astype(int);valid=(gx>=0)&(gz>=0)&(gx<nx)&(gz<nz);p=p[valid];keys=gz[valid]*nx+gx[valid];order=np.argsort(keys);keys=keys[order];p=p[order];unique,starts=np.unique(keys,return_index=True);ends=np.r_[starts[1:],len(keys)];heights=[None]*(nx*nz)
for k,a,b in zip(unique,starts,ends):
 if b-a>=5:heights[int(k)]=round(float(np.quantile(p[a:b,1],.13)),4)
route=[[4.8,-.6122,7.2],[4.7,-1.1093,5.5],[4.2,-.6936,3.0],[2.2,-.3929,1.8],[.5223,-.1091,.5178],[-1.65,.5043,-1.7],[-3.3,1.2193,-4.1],[-5.5,1.2357,-5.4],[-7.7,2.0386,-6.4],[-9,2.4948,-7.6],[-9.7,2.8673,-9],[-9.9,3.083,-10.9]]
result={'version':1,'frame':'Y-up; raw Gaussians rotated pi around Z','scale':'Capture units, not surveyed metres','method':'0.25-unit height grid; 13th percentile of locally supported Gaussian centers with opacity >45/255. Approximate navigation only.','origin':[ox,oz],'step':step,'size':[nx,nz],'heights':heights,'route':route,'eyeHeight':.82,'corridorRadius':.6}
(root/'navigation.json').write_text(json.dumps(result,separators=(',',':')))
print('Navigation generated:',len(p),'points;',sum(h is not None for h in heights),'supported cells')
