"""Extend a frozen macro catalog over the fixed road domain, without a huge asset."""
from pathlib import Path
import sys,time,json,hashlib,gc
import numpy as np
O=Path(__file__).resolve().parent;sys.path[:0]=[str(O/'core')];import stable_catalog as ref;import compact_catalog as compact
assert not(O/'FULL_ROAD_PACKING_STATUS.npz').exists(),'Completed world already exists; do not rerun'
import multiscale_packing as tier
assert json.loads((O/'RADIUS_TIER_PARITY.json').read_text())['module_sha256']==hashlib.sha256(Path(tier.__file__).read_bytes()).hexdigest()
compact._pack_records=tier.pack_records
start=time.monotonic();r=json.loads((O/'ACTUAL_CATALOG.json').read_text());p=r['provenance'];protos=[ref.Prototype(**q)for q in p['prototypes']]
macro_spec=ref.CatalogSpec(seed=p['seed'],cell_size=p['cell_size'],bounds=tuple(p['bounds']),thinning_by_band={int(k):v for k,v in p['thinning_by_band'].items()},catalog_epoch=p['catalog_epoch'],source_pins=p['source_pins'],max_virtual_candidates=2000000,max_catalog_candidates=1500000)
# Recover exact float64 packing blockers for the already inspected macro bodies.
macro=compact.build_compact_catalog(macro_spec,protos,backend='numba',limits=compact.CompactLimits(max_reconstruction_candidates=1500000));assert np.array_equal(macro.status2,np.load(O/'COMPACT_ACTUAL_STATUS.npz')['status2']);g=compact.reconstruct(macro,max_candidates=1500000).grains
actual=np.load(O/'ACTUAL_CATALOG.npz');assert np.array_equal(g.ids,actual['id']);assert np.array_equal(g.xy.astype('f4'),actual['xy'].astype('f4'));blockers=np.c_[g.xy,g.radius];macro_n=len(g);del actual,g,macro;gc.collect()
pins={**p['source_pins'],'frozen_macro_catalog':r['catalog_sha256'],'frozen_macro_status':hashlib.sha256((O/'COMPACT_ACTUAL_STATUS.npz').read_bytes()).hexdigest()}
spec=ref.CatalogSpec(seed=p['seed'],cell_size=p['cell_size'],bounds=(-7.,-3.52,4.7,11.5),thinning_by_band={0:1.,1:1.,2:1.},catalog_epoch='DQ-full-road-fixed-macro-v1',source_pins=pins,max_virtual_candidates=65000000,max_catalog_candidates=60000000,max_cells=10000,max_grid_bins=4000000,chunk_size=65536)
# Compact progress retains processed status and counters if a runtime bound fires.
# It is explicitly incomplete, never consumed as a final catalog/role input.
def checkpoint(status,counts,stage):
 tmp=O/'FULL_ROAD_PACKING_PROGRESS.tmp.npz';dest=O/'FULL_ROAD_PACKING_PROGRESS.npz'
 np.savez_compressed(tmp,status2=status,counts=counts)
 tmp.replace(dest)
 info={'status':'incomplete packing checkpoint','stage':stage,'elapsed_seconds':time.monotonic()-start,'processed_count':int(counts.sum()),'frozen_macro_catalog_sha256':r['catalog_sha256'],'spec':{'seed':spec.seed,'cell_size':spec.cell_size,'bounds':spec.bounds,'catalog_epoch':spec.catalog_epoch},'source_sha256':hashlib.sha256(Path(tier.__file__).read_bytes()).hexdigest(),'data_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'not_a_complete_catalog':True}
 (O/'FULL_ROAD_PACKING_PROGRESS.json').write_text(json.dumps(info,indent=2)+'\n');print('PACK_PROGRESS',info['processed_count'],stage,flush=True)
tier.CHECKPOINT=checkpoint
# Observability only; the exact tested functions receive unchanged arguments.
for name in ['_eligible_records','validate_sorted_ids','_pack_records']:
 original=getattr(compact,name)
 def wrap(*a,_fn=original,_name=name,**kw):
  print('PHASE_START',_name,time.monotonic()-start,flush=True);v=_fn(*a,**kw);print('PHASE_END',_name,time.monotonic()-start,flush=True);return v
 setattr(compact,name,wrap)
print('FROZEN_MACRO_BLOCKERS',macro_n,'FULL_BUILD_START',flush=True)
c=compact.build_compact_catalog(spec,protos,blockers,backend='numba')
np.savez_compressed(O/'FULL_ROAD_PACKING_STATUS.npz',status2=c.status2)
rep={'status':'Full physical candidate packing completed; downstream roles/contact and render integration pending','spec':{'seed':spec.seed,'cell_size':spec.cell_size,'bounds':spec.bounds,'thinning_by_band':spec.thinning_by_band,'catalog_epoch':spec.catalog_epoch,'source_pins':dict(spec.source_pins),'max_virtual_candidates':spec.max_virtual_candidates,'max_catalog_candidates':spec.max_catalog_candidates,'max_cells':spec.max_cells,'max_grid_bins':spec.max_grid_bins,'chunk_size':spec.chunk_size},'prototypes':p['prototypes'],'report':c.report,'provenance':c.provenance,'storage':c.storage,'frozen_macro_bodies':macro_n,'frozen_macro_catalog_sha256':r['catalog_sha256'],'elapsed_seconds':time.monotonic()-start,'radius_tier_parity_sha256':hashlib.sha256((O/'RADIUS_TIER_PARITY.json').read_bytes()).hexdigest(),'status_file_sha256':hashlib.sha256((O/'FULL_ROAD_PACKING_STATUS.npz').read_bytes()).hexdigest(),'status_file_bytes':(O/'FULL_ROAD_PACKING_STATUS.npz').stat().st_size,'limits':['Existing macro identities, roles and contact stay in the exact retained18.48MB catalog. Their bodies block new placement.','Full-road status stores only additional outside packing; no new bulk sediment inventory or optical completeness claim.','A following budget stage must debit the frozen macro representatives before adding outside representatives.','World-domain packing is a fixed authored candidate field, not verified physical particle transport.']};(O/'FULL_ROAD_PACKING_STATUS.json').write_text(json.dumps(rep,indent=2)+'\n');print('FULL_PACKING_DONE',rep['status_file_bytes'],rep['elapsed_seconds'],flush=True)
