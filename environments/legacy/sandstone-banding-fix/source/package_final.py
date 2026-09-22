"""Package local-only banding correction and bind delivered bytes to executed tests."""
from pathlib import Path
from PIL import Image
import hashlib,json,shutil,zipfile
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT.parent
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
precision=json.loads((ROOT/'evidence/precision_tests/report.json').read_text())
assert precision['result']=='PASS'
verified={}
for tier in ['compact','full']:
    receipt=json.loads((ROOT/f'evidence/delivery_{tier}.json').read_text())
    test=json.loads((ROOT/f'evidence/{tier}_delivery/report.json').read_text())
    path=OUT/test['input_file']
    assert test['result']=='PASS' and not test['errors']
    assert sha(path)==test['html_sha256']==receipt['output_sha256']
    assert receipt['scene_payload_byte_identical'] and receipt['all_photographic_map_payloads_identical']
    assert all(t['complete'] and t['bits']==32 for t in test['runtime']['targets'])
    assert test['runtime']['triangles']==5029800 and test['runtime']['vertices']==2526592
    for name,entry in test['captures'].items():
        p=ROOT/f'evidence/{tier}_delivery/{name}.png'
        assert sha(p)==entry['sha256'] and entry['glError']==0
    verified[tier]={'file':path.name,'bytes':path.stat().st_size,'sha256':sha(path),
        'original_file':receipt['input'],'original_sha256':receipt['input_sha256'],
        'photographic_resolution':receipt['map_resolution'],
        'scene_payload_byte_identical':receipt['scene_payload_byte_identical'],
        'all_photographic_payloads_identical':receipt['all_photographic_map_payloads_identical'],
        'photographic_payload_count':receipt['map_payloads_checked'],
        'test_result':test['result'],'checks_passed':len(test['checks']),
        'report':f'evidence/{tier}_delivery/report.json','runtime':test['runtime']}
    assert sha(OUT/receipt['input'])==receipt['input_sha256']
full=json.loads((ROOT/'evidence/full_delivery/report.json').read_text())
compact=json.loads((ROOT/'evidence/compact_delivery/report.json').read_text())
image=ROOT/'evidence/full_delivery/hero_4k.png'
assert sha(image)==full['export']['sha256']
with Image.open(image) as im:assert im.size==(3840,2560)
shutil.copyfile(image,OUT/'Sandstone_Walk_BandingFixed_4K.png')
shutil.copyfile(ROOT/'evidence/full_delivery/hero.png',OUT/'Sandstone_Walk_BandingFixed_Preview.png')
for name in ['Sandstone_Banding_Comparison.png','Sandstone_Banding_Beauty_Comparison.png']:
    shutil.copyfile(OUT/name,ROOT/'evidence'/name)
report={
 'schema':'sandstone-local-banding-delivery/1','result':'PASS',
 'scope':'Local corrections to supplied v0.5 standalone HTML. No GitHub or other external repository mutations.',
 'repository_pushed':False,'repository_modified':False,'image_generation':False,
 'geometry':{'triangles':5029800,'vertices':2526592,'native_mesh_sha256':'7522cf1848ef94af2593e4a2d2a9df382df11c2e85e9ac4662a364a107656c79',
             'scene_payload_unchanged':True,'new_spectral_bake':False},
 'deliveries':verified,
 'fixes':[
  'Receiving-plane shadow comparisons use the exact sampled texel centers and true raster-triangle normal, with bounded footprint-scaled normal offset.',
  'Fractional blocker search and bilinearly combined depth-comparison results replace quantized binary-tap visibility.',
  'Explicit highp depth, sky, photographic and HDR samplers; actual RGBA32F current/history framebuffers.',
  'Static achromatic triangular dither after the unchanged native tone/sRGB transform, not in the HDR history or material textures.',
  'Native-resolution tiled supersampled export keeps GPU memory bounded and preserves a global dither phase; no upscale or blur.'
 ],
 'isolated_shader_tests':precision,
 'isolated_gradient_column_mean_error_reduction_factor':precision['ramp']['before']['mean_column_error_srgb']/precision['ramp']['after']['mean_column_error_srgb'],
 'export_4k':full['export'],
 'tile_equivalence':compact['tile_equivalence'],
 'unchanged':['Every embedded geometry/index/normal/baked-light-response buffer','All 4K/2K photographic image payloads','Material parallax and microshadowing model','Walking/orbit control code','Tone transform and exposure','Native resolution policy and pixel cap'],
 'image_evidence':{
  'shadow_comparison':{'file':'evidence/Sandstone_Banding_Comparison.png','sha256':sha(ROOT/'evidence/Sandstone_Banding_Comparison.png'),
   'source':'Actual original/corrected Three.js untextured visibility draws; same 1200x800 camera and four samples; identical crops.',
   'edits':'Side-by-side assembly, crop and text labels only; no blur, reconstruction or contrast change.'},
  'beauty_comparison':{'file':'evidence/Sandstone_Banding_Beauty_Comparison.png','sha256':sha(ROOT/'evidence/Sandstone_Banding_Beauty_Comparison.png'),
   'source':'Matched original/corrected four-sample 1200x800 browser renders; labelled, unretouched.'},
  'final_4k':{'file':'evidence/full_delivery/hero_4k.png','sha256':sha(image),'dimensions':[3840,2560],'samples':8,'upscaled':False}
 },
 'verification_limits':{
  'browser_entrypoint':'Exact delivered JS blocks and JSON payload nodes loaded into an in-memory Chromium document; HTTP/file navigation was blocked by the environment administrator.',
  'renderer':full['runtime']['renderer'],
  'controls':'Executed real CDP touch emulation, simultaneous thumbstick/look, cancellation, orbit, pinch and keyboard checks.',
  'physical_phone_benchmark':False,'http_file_url_launch_claimed':False,
  'memory':'Three RGBA32F buffers use 48 bytes/output pixel, versus 24 before; compact maps reduce texture memory. Final tiled 4K export avoids three full-4K float buffers.',
  'remaining_limits':'Finite mesh, static baked-light sampling and finite shadow maps remain. No claim that all future camera/light configurations are artifact-free.'
 },
 'retained_development_failures':[
  {'file':'evidence/initial_delivery_touch_failure.json','resolution':'Test used mobile context and flushed coalesced touch events through real animation frames; no controller changes.'},
  {'file':'evidence/initial_fullframe_export_context_loss.json','resolution':'Runtime export replaced by memory-bounded native-resolution off-axis tiles; final full/compact deliveries retested successfully.'}
 ],
 'source_hashes':{p.relative_to(ROOT).as_posix():sha(p) for folder in ['patch','tests'] for p in sorted((ROOT/folder).glob('*')) if p.is_file()},
}
(ROOT/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
# A reproducible source kit, without the original hundreds of MB of unchanged assets.
entries=set()
for name in ['README.md','LICENSE','apply_local_fix.py','verification.json']:
    entries.add(ROOT/name)
for folder in ['patch','tests','source','before','after','precision_only']:
    entries.update(p for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
for folder in ['evidence/precision_tests','evidence/compact_delivery','evidence/full_delivery','evidence/before','evidence/after']:
    entries.update(p for p in (ROOT/folder).rglob('*') if p.is_file())
for name in ['delivery_compact.json','delivery_full.json','source_identity.json','Sandstone_Banding_Comparison.png','Sandstone_Banding_Beauty_Comparison.png','initial_delivery_touch_failure.json','initial_fullframe_export_context_loss.json']:
    entries.add(ROOT/'evidence'/name)
manifest={p.relative_to(ROOT).as_posix():{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(entries)}
(ROOT/'SHA256SUMS.json').write_text(json.dumps(manifest,indent=2)+'\n');entries.add(ROOT/'SHA256SUMS.json')
archive=OUT/'Sandstone_Banding_Fix_Source.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=5) as z:
    for p in sorted(entries):z.write(p,'Sandstone_Banding_Fix/'+p.relative_to(ROOT).as_posix())
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert not any('/shared/' in name or name.endswith(('.ttf','.otf','.woff','.woff2')) for name in z.namelist())
print(json.dumps({'result':'PASS','source_kit_bytes':archive.stat().st_size,'source_kit_sha256':sha(archive),'source_kit_files':len(entries),'deliveries':verified,'export':full['export']},indent=2))
