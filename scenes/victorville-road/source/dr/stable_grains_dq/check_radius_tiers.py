from pathlib import Path
import sys,json,time,dataclasses,hashlib
import numpy as np
O=Path(__file__).resolve().parent;sys.path[:0]=[str(O/'core')]
import compact_catalog as c,stable_catalog as ref,multiscale_packing as m
start=time.monotonic();old=c._pack_records;proof=[]
p=[ref.Prototype(13,0,0,35,.03),ref.Prototype(99,1,1,150,.008),ref.Prototype(1001,2,2,950,.001)]
for seed,bins in [(1,10000),(91,100),(93,1)]:
 spec=ref.CatalogSpec(seed=seed,cell_size=.2,bounds=(-.7,.7,-.4,.8),thinning_by_band={0:1.,1:1.,2:1.},catalog_epoch='radius-tier-parity',source_pins={'geometry':'unchanged-synthetic-fixture'},max_virtual_candidates=10000,max_catalog_candidates=10000,max_grid_bins=bins,chunk_size=129)
 blockers=np.array([[0,0,.1],[-.1,-.1,.002],[.35,.1,.004]])
 c._pack_records=old;a=c.build_compact_catalog(spec,p,blockers,backend='numba');c._pack_records=m.pack_records;b=c.build_compact_catalog(spec,p,blockers,backend='numba');assert np.array_equal(a.status2,b.status2);assert a.provenance==b.provenance
 for key in a.report:
  if key!='packing':assert a.report[key]==b.report[key],key
 proof.append({'seed':seed,'grid_cap':bins,'candidate_count':a.serial_map.virtual_count,'status_and_nonindex_provenance_exact':True})
r=json.loads((O/'ACTUAL_CATALOG.json').read_text());p=r['provenance'];spec=ref.CatalogSpec(seed=p['seed'],cell_size=p['cell_size'],bounds=tuple(p['bounds']),thinning_by_band={int(k):v for k,v in p['thinning_by_band'].items()},catalog_epoch=p['catalog_epoch'],source_pins=p['source_pins'],max_virtual_candidates=2000000,max_catalog_candidates=1500000)
b=c.build_compact_catalog(spec,[ref.Prototype(**q)for q in p['prototypes']],backend='numba');expected=np.load(O/'COMPACT_ACTUAL_STATUS.npz')['status2'];assert np.array_equal(b.status2,expected);assert b.provenance==p
proof.append({'actual_macro_candidates':b.report['catalog_attempt_count'],'actual_macro_status_exact':True,'packing':b.report['packing'],'elapsed':b.storage['seconds']})
receipt={'status':'passed','cases':proof,'elapsed_seconds':time.monotonic()-start,'module_sha256':hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest(),'scope':'Same order/IDs/coordinates/radii/strict narrow phase and bitwise statuses; only conservative broad-phase grids differ.'};(O/'RADIUS_TIER_PARITY.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
