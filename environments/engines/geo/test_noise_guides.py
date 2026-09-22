"""Native auxiliary passes must not change beauty radiance or fake path variance."""
from pathlib import Path
import os,sys,json,subprocess,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parent
TOOLS=ROOT/'cybr-geo/examples/three_scenes';sys.path.insert(0,str(TOOLS))
from render_scenes import compile_renderer
from noise_resolve import read_buffer


def run():
    root=ROOT/'verification/noise_guide_test';root.mkdir(parents=True,exist_ok=True)
    binary,build=compile_renderer()
    # A six-triangle fixture with two floor materials and a vertical occluder.
    v=np.array([[-3,-1,0],[3,-1,0],[3,5,0],[-3,5,0]],np.float32)
    entries=[]
    for a,b,c in [(0,1,2),(0,2,3)]:
        row=np.zeros(20,np.float32);row[:9]=v[[a,b,c]].ravel();row[9:18]=np.tile([0,0,1],3);row[18]=0;entries.append(row)
    v=np.array([[-.3,.8,0],[.3,.8,0],[.3,.8,2],[-.3,.8,2]],np.float32)
    for a,b,c in [(0,1,2),(0,2,3)]:
        row=np.zeros(20,np.float32);row[:9]=v[[a,b,c]].ravel();row[9:18]=np.tile([0,-1,0],3);row[18]=2;entries.append(row)
    mesh=root/'fixture.meshbin'
    with mesh.open('wb') as f:
        np.array([len(entries)],'<u4').tofile(f);np.array(entries,'<f4').tofile(f)
    common=[str(binary),str(mesh),'PLACEHOLDER','--scene','canyon','--camera','0,-3,1.2','--target','0,1,.5',
            '--fov','64','--w','48','--h','32','--spp','8','--threads','1','--seed','331','--aperture','0',
            '--no-clouds','--no-steam','--no-water']
    results={}
    for label,spp,only in [('one',1,False),('sixteen',16,False),('features',16,True)]:
        cmd=common.copy();cmd[2]=str(root/label);cmd+=['--guide-spp',str(spp)]
        if only:cmd+=['--guides-only']
        with (root/(label+'.log')).open('w') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
        results[label]=json.loads((root/(label+'.json')).read_text())
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    g=read_buffer(root/'features.guides',9,(32,48))
    support=read_buffer(root/'features.support',4,(32,48))
    checks={'beauty_bitwise_unchanged_when_guide_spp_changes':digest(root/'one.pfm')==digest(root/'sixteen.pfm'),
      'spectral_buffer_bitwise_unchanged':digest(root/'one.spectral')==digest(root/'sixteen.spectral'),
      'guide_only_does_not_create_beauty':not (root/'features.pfm').exists(),
      'guide_only_has_zero_path_variance':bool((g[:,:,7]==0).all()),
      'multisample_guides_exercised':results['sixteen'].get('guide_spp')==16,
      'coverage_within_bounds':bool((support[:,:,0]>0).all() and (support[:,:,0]<=1).all()),
      'mixed_coverage_edges_present':bool((support[:,:,0]<1).any()),
      'finite_guides':bool(np.isfinite(g).all() and np.isfinite(support).all())}
    report={'scope':'Small native integration fixture; not production scene rerender or convergence proof','checks':checks,'passed':all(checks.values()),'native_build':build}
    (ROOT/'verification/noise_guides.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
    return report
if __name__=='__main__':
    if not run()['passed']:raise SystemExit(1)
