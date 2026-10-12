"""Measured original fine-bed reference height, not a new burial parameter."""
from pathlib import Path
import argparse,ast,hashlib,json
import numpy as np
from scipy.ndimage import map_coordinates

def build(source,microbed,builder,out):
 source=Path(source);raw=json.loads(source.read_text());s=Path(builder).read_bytes();assert hashlib.sha256(s).hexdigest()==raw['builder_sha256'];assert hashlib.sha256(Path(microbed).read_bytes()).hexdigest()=='7a09007d50e444c28231fd30cddda185d2f01146f3b1a47b014ebd25c0b415c4'
 env={'np':np};tree=ast.parse(s);functions=[n for n in tree.body if isinstance(n,ast.FunctionDef)and n.name in {'noise','deposit','ground'}];exec(compile(ast.Module(body=functions,type_ignores=[]),'<pinned-source-fields>','exec'),env)
 m=np.load(microbed);n=m['height'].shape[0];axis=np.linspace(-.09,.09,n);xx,yy=np.meshgrid(axis,axis);h=(env['ground'](xx,yy)+m['height']*(.65+.55*(1-env['deposit'](xx,yy)))).astype('f4');records=[]
 for p in raw['particles']:
  orig=np.array(p['original_xy_m']);v=np.array(p['vertices']);world=v+np.r_[orig,float(env['ground'](*orig))];world=world.astype('f4')
  # Existing64 bank was extracted about stored XY centroid; the new sand bank
  # uses original particle origin. Match each actual bank's established datum.
  xy=world[:,:2].mean(0) if p['source_id']<9156 else orig
  ground=float(env['ground'](*xy));uv=(xy+.09)/.18*(n-1);bed=float(map_coordinates(h,[[uv[1]],[uv[0]]],order=1,mode='nearest')[0]);offset=bed-ground
  local=world.astype(float)-np.r_[xy,ground]
  records.append(dict(source_id=p['source_id'],bed_reference_offset_m=offset,reference_xy_m=xy.tolist(),nominal_diameter_m=p['nominal_diameter_m'],before_top_m=float(local[:,2].max()),after_top_to_reference_plane_m=float(local[:,2].max()-offset)))
 rec=dict(builder_sha256=raw['builder_sha256'],source_witnesses_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),microbed_sha256=hashlib.sha256(Path(microbed).read_bytes()).hexdigest(),method='Original float32 R5D microbed sampled bilinearly at each source bank datum, less original analytic broad ground at that datum. Exact physical field; pointwise planar exposure approximation, not full footprint integration.',records=records,offset_um_min_median_max=np.quantile([r['bed_reference_offset_m']*1e6 for r in records],[0,.5,1]).tolist());Path(out).write_text(json.dumps(rec,indent=2)+'\n');print(json.dumps({k:v for k,v in rec.items()if k!='records'}))
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('source');a.add_argument('microbed');a.add_argument('builder');a.add_argument('out');x=a.parse_args();build(x.source,x.microbed,x.builder,x.out)
