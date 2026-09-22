#!/usr/bin/env python3
"""Install the memory-bounded hot-springs build without changing geometric formulas."""
from pathlib import Path
import difflib,json
r=Path(__file__).resolve().parents[1]
rel=Path('engines/hot/cybr-geo/examples/desert_hot_springs/build_scene.py');p=r/rel;b=r/'provenance/native-before'/rel
if not b.exists():b.parent.mkdir(parents=True,exist_ok=True);b.write_text(p.read_text())
s=b.read_text();s=s.replace('start=time.time();rng=np.random.default_rng(args.seed);parts=[]','start=time.time();rng=np.random.default_rng(args.seed);parts=[]\n    from stream_scene_r2 import PartSpool,roundtrip_to_native\n    spool=PartSpool(out/".part-spool")')
s=s.replace('parts.append(Part(name,np.asarray(v)*1000,np.asarray(f),np.asarray(n),material=mat,group=group,\n                          role=\'Authored environmental mesh; not a surveyed or simulated landform\',metadata=meta))','parts.append(spool.store(Part(name,np.asarray(v)*1000,np.asarray(f),np.asarray(n),material=mat,group=group,\n                          role=\'Authored environmental mesh; not a surveyed or simulated landform\',metadata=meta)))')
start=s.index("    del assembly,parts,stones,grass,wood,leaves,chips,templates;gc.collect()")
end=s.index("    (out/'geometry_verification.json').write_text",start)
s=s[:start]+'''    total=sum(len(p.faces) for p in parts)
    del assembly,parts,stones,grass,wood,leaves,chips,templates;gc.collect()
    meshpath=out/'scene.meshbin'
    report=roundtrip_to_native(out/'scene',meshpath,total)
    report.update(counts=counts,triangles=total,seconds=time.time()-start,
        mesh_sha256=stream_hash(meshpath),memory_bounded_part_spooling=True,image_generation=False)
'''+s[end:]
if s==b.read_text() or 'spool.store(Part' not in s:raise RuntimeError('Builder patch failed')
p.write_text(s)
(r/'provenance/builder-upgrade.diff').write_text(''.join(difflib.unified_diff(b.read_text().splitlines(True),s.splitlines(True),fromfile='a/'+str(rel),tofile='b/'+str(rel))))
print('Hot Springs: exact-dtype disk-backed Parts and streaming archive/native roundtrip installed.')
