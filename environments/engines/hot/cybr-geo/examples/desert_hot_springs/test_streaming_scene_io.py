"""Exercise the actual CYBR GEO archive round-trip and bounded-memory hashing."""
from __future__ import annotations
import json,hashlib,tempfile,sys
from pathlib import Path
import numpy as np
REPO=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPO/'src'))
from cybrgeo import Assembly,Part,Material
from cybrgeo.core import _stream_sha256

def main():
    rng=np.random.default_rng(421)
    with tempfile.TemporaryDirectory() as folder:
        root=Path(folder)
        parts=[]
        for i in range(4):
            v=rng.normal(size=(900,3));f=np.arange(900).reshape(-1,3)
            n=v/np.linalg.norm(v,axis=1,keepdims=True)
            parts.append(Part(f'part_{i}',v,f,n,material=0))
        original=Assembly('round_trip',parts,[Material()]);original.save(root)
        path=root/'meshes.npz'
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        hashes_equal=all(_stream_sha256(path,s)==digest for s in [7,1024,65536,4*1024*1024])
        loaded=Assembly.load(root)
        arrays_equal=all(np.array_equal(getattr(a,k),getattr(b,k)) for a,b in zip(original.parts,loaded.parts) for k in ['vertices','faces','normals'])
        # Loaded arrays remain valid after the archive handle has closed, and
        # changing the loaded result cannot mutate the source in memory.
        loaded.parts[0].vertices[0,0]+=2
        independent=not np.array_equal(original.parts[0].vertices,loaded.parts[0].vertices)
        with path.open('ab') as out:out.write(b'tamper')
        rejected=False
        try:Assembly.load(root)
        except ValueError as error:rejected='SHA256' in str(error)
        result={'scope':'Streamed archive hashes, exact round-trip, ownership, tamper detection; no visual-quality assertion',
                'stream_hash_matches_whole_file_for_4_chunk_sizes':hashes_equal,
                'round_trip_exact':arrays_equal,'loaded_arrays_independent':independent,
                'tampering_rejected':rejected,'passed':hashes_equal and arrays_equal and independent and rejected}
        print(json.dumps(result,indent=2))
        if not result['passed']:raise SystemExit(1)
if __name__=='__main__':main()
