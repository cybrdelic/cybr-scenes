#!/usr/bin/env python3
"""Collect verified execution evidence without claiming a new scene revision."""
from pathlib import Path
import difflib,json,re,shutil,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from execution_runtime import read_json,atomic_json,sha256,utc
from cybr_scenes import SOURCES,dependency_fingerprint

def main():
    out=ROOT/'execution-repair';out.mkdir(exist_ok=True)
    tests=read_json(ROOT/'execution-jobs/final-tests-v2/state.json')
    compile_job=read_json(ROOT/'execution-jobs/compile-native-fresh/state.json')
    native=read_json(ROOT/'execution-jobs/native-render-repeat/state.json')
    first_native=read_json(ROOT/'execution-jobs/native-render-proof/state.json')
    assert all(x['state']=='succeeded' and x['returncode']==0 for x in [tests,compile_job,native,first_native])
    text=(ROOT/'execution-jobs/final-tests-v2/output.log').read_text()
    count=int(re.search(r'Ran (\d+) tests',text)[1])
    assert count==36 and text.strip().endswith('OK')
    builds={}
    for engine in SOURCES:
        info=read_json(ROOT/'build'/f'{engine}_r2.build.json')
        assert info['source_fingerprint']==dependency_fingerprint(engine)
        assert info['executable_sha256']==sha256(ROOT/'build'/f'{engine}_r2')
        assert info['returncode']==0
        builds[engine]={'passed':True,'executable_sha256':info['executable_sha256'],
                        'source_fingerprint':info['source_fingerprint']}
        if engine!='obsidian':
            numerical=read_json(ROOT/'evidence'/f'self-test-{engine}.log')
            assert numerical['passed']
            builds[engine]['native_self_test']=numerical
    proof=ROOT/'renders/execution-proof/obsidian-reach/hero'
    verification=read_json(proof/'verification.json');assert verification['passed']
    receipt=read_json(proof/'receipt.json')
    assert receipt['mesh_sha256']==sha256(ROOT/'geometry-r2/obsidian/scene.bin')
    assert receipt['verification']['png_sha256']==sha256(proof/'hero.png')
    shutil.copytree(proof,out/'native-proof',dirs_exist_ok=True)
    for name in ['final-tests-v2','compile-native-fresh','native-render-proof','native-render-repeat']:
        dest=out/'jobs'/name;dest.mkdir(parents=True,exist_ok=True)
        for filename in ['state.json','spec.json','output.log']:
            shutil.copy2(ROOT/'execution-jobs'/name/filename,dest/filename)
    edits=['cybr_scenes.py','tools/package_delivery.py','tests/test_pipeline.py']
    before={'cybr_scenes.py':'cybr_scenes.py','tools/package_delivery.py':'package_delivery.py','tests/test_pipeline.py':'test_pipeline.py'}
    additions=['execution_runtime.py','execctl.py','README_EXECUTION.md','tests/test_execution_runtime.py','tools/report_execution_repair.py']
    diffs=[]
    for rel in edits+additions:
        old=(ROOT/'provenance/execution-before'/before[rel]).read_text().splitlines(True) if rel in before else []
        diffs.extend(difflib.unified_diff(old,(ROOT/rel).read_text().splitlines(True),
                      fromfile='a/'+rel if rel in before else '/dev/null',tofile='b/'+rel))
    (out/'execution-repair.patch').write_text(''.join(diffs))
    report={'checked_at':utc(),'passed':True,'scope':'Local execution repair on recovered R2; not a recovered R3 or a six-scene visual upgrade.',
            'diagnosis':read_json(out/'diagnosis.json'),'test_count':count,'tests_passed':True,'tests_log_sha256':sha256(ROOT/'execution-jobs/final-tests-v2/output.log'),
            'compiled_backends':builds,'fresh_native_render_runs':2,'native_proof':{'scene':'obsidian-reach','triangles':verification['renderer_metadata'].get('triangles'),
                'resolution':verification['dimensions'],'spp':8,'full_geometry':True,'fresh_render':True,'verification':verification,
                'controller_seconds':native['elapsed_seconds'],'peak_sampled_tree_rss_bytes':native['peak_tree_rss_bytes'],
                'receipt_sha256':sha256(proof/'receipt.json'),'image_generation':False},
            'modified_source_files':{rel:sha256(ROOT/rel) for rel in edits+additions},
            'r3_workspace_recovered':False,'partial_native_samples_resumable':False,
            'limitations':['The controller survives short launch calls, not container destruction.',
                          'Memory is sampled; the watchdog cannot prevent every transient memory spike.',
                          'The small proof render verifies execution, not artistic improvements or convergence.']}
    atomic_json(out/'verification.json',report)
    shutil.copy2(proof/'hero.png','/mnt/data/CYBR_Execution_Proof.png')
    atomic_json('/mnt/data/CYBR_Execution_Repair_Verification.json',report)
    print(json.dumps({'passed':True,'tests':count,'compiled':list(builds),'proof':report['native_proof']['resolution']},indent=2))

if __name__=='__main__':main()
