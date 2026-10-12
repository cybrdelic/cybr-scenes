"""Actual matched Cycles views for the relief/paint/dust integration.

Metric material parameters and scene geometry are not altered here. Preview
and native views use identical cameras; each render preserves raw OIDN guides.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys

r = Path(__file__).resolve().parents[1]
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--scene', type=Path, default=r/'relief_correction/road_r6_s_coupled.blend')
p.add_argument('--preview', action='store_true')
p.add_argument('--detail-only', action='store_true')
p.add_argument('--hero-only', action='store_true')
p.add_argument('--tag', default='s')
p.add_argument('--compact-bvh', action='store_true', help='Use Cycles compact BVH without altering geometry or shading')
p.add_argument('--asphalt-preview-grid-stride',type=int,choices=(2,),help='Metric native-grid context preview LOD')
p.add_argument('--cull-offscreen-terrain',action='store_true',help='Preview-only expanded-frustum cull of static terrain faces')
p.add_argument('--asphalt-preview-map-size', type=int, choices=(1024,2048), help='In-memory asphalt-map mip for bounded scene preview')
p.add_argument('--cull-offscreen-asphalt', action='store_true', help='Preview-only expanded-frustum cull of dense native asphalt instances')
p.add_argument('--lens-check', action='store_true', help='Matched crop of the visible graded-shoulder lenses')
a = p.parse_args()
source = a.scene.resolve()
digest = hashlib.sha256(source.read_bytes()).hexdigest()
if a.preview:
    views = [('edge',900,600,32,(-3.45,.10,.33),(-2.96,.65,.085),50),
             ('context',1000,667,24,None,None,None)]
else:
    views = [('edge',1800,1200,64,(-3.45,.10,.33),(-2.96,.65,.085),50),
             ('hero',2048,1365,64,None,None,None)]
if a.lens_check:
    views = [('lenses',900 if a.preview else 1800,600 if a.preview else 1200,32 if a.preview else 64,(-4.65,.40,.47),(-4.02,1.65,.06),55)]
if a.detail_only: views = views[:1]
if a.hero_only: views = views[1:]
env = dict(os.environ,OPENBLAS_NUM_THREADS='2',OMP_NUM_THREADS='2',MKL_NUM_THREADS='2')
for label,w,h,samples,loc,target,lens in views:
    name = a.tag+'_'+label+('_preview' if a.preview else '_native')
    out = r/'captures'/name
    out.mkdir(exist_ok=True)
    if (out/'resource_receipt.json').exists():
        raise FileExistsError('Preserve prior run; choose a new --tag: '+name)
    job = dict(source=str(source),source_sha256=digest,engine='CYCLES',width=w,height=h,
               samples=samples,capture_mode='guided',save_guides=True,light_tree=False,
               color_depth=16,dither_intensity=0,use_adaptive_sampling=False,
               rss_cap_mib=6144,time_limit_seconds=1800,sync_limit_seconds=180,
               output=str(out/'INTERNAL_PANEL.png'))
    if a.compact_bvh: job['compact_bvh'] = True
    if a.cull_offscreen_asphalt:
        assert a.preview, 'Cull is a preview adaptation'
        job.update(camera_cull_prefixes=['Original asphalt native tile '],camera_cull_margin=.12,rss_cap_mib=4096)
    if a.asphalt_preview_map_size:
        assert a.preview, 'Map mips are for bounded preview only'
        job.update(asphalt_preview_map_size=a.asphalt_preview_map_size,rss_cap_mib=4096)
    if a.cull_offscreen_terrain:
        assert a.preview, 'Preview only'
        job.update(preview_cull_terrain_faces=True,terrain_cull_margin=.20,rss_cap_mib=4096)
    if a.asphalt_preview_grid_stride:
        assert a.preview, 'Preview LOD only'
        job.update(asphalt_preview_grid_stride=a.asphalt_preview_grid_stride,rss_cap_mib=4096)
    if loc: job.update(camera_location=loc,camera_target=target,lens=lens)
    (out/'job.json').write_text(json.dumps(job,indent=2))
    subprocess.run([sys.executable,str(r/'pipeline/bounded_clean_run.py'),str(out/'job.json'),
                    str(r/(name+'.log')),str(out/'resource_receipt.json'),str(job['rss_cap_mib'])],env=env,check=True)
    receipt = json.loads((out/'resource_receipt.json').read_text())
    if not receipt['resource_contract_passed'] or receipt['exit_code'] != 0:
        raise RuntimeError('Render resource contract failed: '+name)
    target_path = r/('preview' if a.preview else 'deliverables')/(name+'.png')
    shutil.copy2(out/'CLEAN_OIDN_PANEL.png',target_path)
    record = dict(path=str(target_path),bytes=target_path.stat().st_size,
                  sha256=hashlib.sha256(target_path.read_bytes()).hexdigest(),
                  scene_sha256=digest,resolution=[w,h],samples=samples,
                  status='Rendered; visual inspection remains separate')
    (r/'receipts'/(name+'_ready.json')).write_text(json.dumps(record,indent=2))
    print('VIEW_READY',json.dumps(record),flush=True)
