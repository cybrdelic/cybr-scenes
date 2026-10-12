"""Receipt for an explicitly requested unfiltered capture; no noise acceptance."""
import json,sys,hashlib,shutil
from pathlib import Path
from capture_modes import capture_mode,final_image,is_workbench_raw
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def create(report_path):
    r=json.loads(Path(report_path).read_text());j=r['job'];assert capture_mode(j)=='unfiltered'
    raw=Path(j['output']);out=final_image(j);g=raw.parent/(raw.stem+'_guides')
    assert not out.exists() and not out.with_suffix('.png.json').exists(),'Refuse stale unfiltered output'
    assert sha(j['source'])==r['source_sha256']
    workbench=is_workbench_raw(j);guides=list(map(Path,r['guide_paths']))
    if workbench:
        assert r['engine']=='BLENDER_WORKBENCH' and not guides
        native=json.loads(raw.with_suffix('.png.native.json').read_text())
        assert native['opaque'] and native['bit_depth']==int(j.get('color_depth',16))
        assert [native['width'],native['height']]==r['resolution']
        bridge=None;contract=None;extra=[raw.with_suffix('.png.native.json')]
    else:
        assert r['engine']=='CYCLES' and len(guides)==3
        bridge=json.loads((g/'png_roundtrip_check.json').read_text())
        assert bridge['opaque'] and bridge['max_error_native']<=1 and bridge['bit_depth']==int(j.get('color_depth',16))
        native=bridge;contract=json.loads((g/'guide_contract.json').read_text())
        stats=json.loads((g/'guide_stats.json').read_text());assert stats['beauty']['finite'] and stats['beauty']['min']>=0
        extra=[g/'raw_passthrough.png',g/'png_roundtrip_check.json',g/'guide_contract.json',g/'guide_stats.json']
    shutil.copyfile(raw,out);assert sha(raw)==sha(out)
    r.update(capture_mode='unfiltered',postprocess='none',oidn_executed=False,raw_path=str(raw),unfiltered_path=str(out),image_path=str(out),noise_acceptance=False,quality_acceptance=False,requires_visual_detail_QA=True,raw_guides_retained=not workbench,raw_hdr_retained=not workbench,physical_lighting_evaluated=not workbench,geometry_study=workbench,color_bridge_native_precision=bridge,native_png_validation=native,diagnostic_guide_contract=contract,files_sha256={str(p):sha(p) for p in [raw,out,*guides,*extra]})
    out.with_suffix('.png.json').write_text(json.dumps(r,indent=2))
    print('UNFILTERED_CANDIDATE',out)
if __name__=='__main__':create(sys.argv[1])

