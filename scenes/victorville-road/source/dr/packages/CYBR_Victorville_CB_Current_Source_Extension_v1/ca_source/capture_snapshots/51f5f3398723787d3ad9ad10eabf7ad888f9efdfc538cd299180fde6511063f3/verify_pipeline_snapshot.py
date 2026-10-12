"""Resolve and verify the immutable code snapshot recorded by this capture."""
import hashlib,json,pathlib,sys
def verify(report,root):
 root=pathlib.Path(root).resolve();p=report['pipeline'];h=p['sha256'];assert len(h)==64 and all(c in '0123456789abcdef' for c in h),'Invalid pipeline digest'
 expected=root/'pipeline_snapshots'/h;assert pathlib.Path(p['snapshot']).resolve()==expected,'Snapshot path does not match recorded digest'
 hashes=p['files'];assert hashlib.sha256(json.dumps(hashes,sort_keys=True).encode()).hexdigest()==h,'Pipeline manifest digest mismatch'
 for name,digest in hashes.items():
  assert pathlib.Path(name).name==name,'Snapshot entry must be a basename'
  assert hashlib.sha256((expected/name).read_bytes()).hexdigest()==digest,'Modified pipeline snapshot: '+name
 for name in ['oidn_image_bridge.py','png_precision_check.py','oidn_contract.py','clean_receipt.py','capture_modes.py','raw_receipt.py','transport_components.py','component_image_bridge.py','component_receipt.py']:assert name in hashes,'Required capture stage missing: '+name
 return expected
if __name__=='__main__':print(verify(json.load(open(sys.argv[1])),pathlib.Path(__file__).resolve().parent))
