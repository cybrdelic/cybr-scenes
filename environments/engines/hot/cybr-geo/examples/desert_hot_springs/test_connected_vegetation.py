"""Check blade attachments against the actually emitted twig centerlines.

This checks geometric construction, not species identity or plant mechanics.
"""
from pathlib import Path
import argparse,json
import numpy as np
from build_scene import stem
from v9_landforms import connected_shrub

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    results=[]
    for seed,height,lod in [(314,.42,0),(281,.87,0),(904,1.1,1)]:
        segments=[]
        def capture(p,q,radius):
            segments.append((np.array(p),np.array(q)));return stem(p,q,radius)
        wood,leaves=connected_shrub(np.random.default_rng(seed),np.array([1.4,3.2,.19]),height,lod,capture)
        bases=np.concatenate([v[::5] for v,f,n in leaves]);seg=np.asarray(segments)
        origin=seg[:,0];axis=seg[:,1]-origin;length2=(axis*axis).sum(axis=1)
        errors=[]
        for start in range(0,len(bases),256):
            diff=bases[start:start+256,None,:]-origin[None,:,:]
            t=np.clip((diff*axis).sum(axis=2)/length2,0,1)
            delta=diff-t[:,:,None]*axis[None,:,:]
            errors.append(np.sqrt((delta*delta).sum(axis=2).min(axis=1)))
        error=np.concatenate(errors)
        results.append({'seed':seed,'plant_height_m':height,'lod':lod,'twig_segments':len(segments),
                        'leaf_bases_tested':len(bases),'maximum_distance_to_emitted_twig_centerline_m':float(error.max()),
                        'passed':bool(error.max()<1.e-10)})
    report={'scope':'Constructed leaf-base attachment to modeled twig centerlines; not botany or mechanics',
            'cases':results,'passed':all(case['passed'] for case in results)}
    a.out.mkdir(parents=True,exist_ok=True);(a.out/'connected_vegetation.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
    if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main()
