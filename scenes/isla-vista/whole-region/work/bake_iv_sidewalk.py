"""Verified CYBR MATERIALS brushed concrete through full metric-height transport."""
from pathlib import Path
import sys,json,hashlib,numpy as np
r=Path(__file__).resolve().parent.parent
sys.path[:0]=[str(r/'original/cybr-material-concrete'),str(r/'whole-iv-vendor'),str(r/'work/iv-component-runtime')]
from mineral_construction_bounded import construction
from cybr_terrain.materials import write_pfm
from cybr_light import Scene
root=r/'original/cybr-material-concrete';spec=json.loads((root/'sidewalk_recipe.json').read_text());fields,report=construction(spec,1024)
rgb=fields['BaseColor'];linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4);day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.asarray(day['native_basis_to_linear_rgb']);controls=(linear*(M@np.ones(3)))@np.linalg.inv(M).T;assert controls.min()>=0
height=(fields['Height']-.5)*spec['height_scale_m'];out=r/'evidence/full-iv-street-materials';out.mkdir(exist_ok=True)
for name,field in [('color_native',controls),('height_metres',np.repeat(height[:,:,None],3,axis=2)),('roughness',np.repeat(fields['Roughness'][:,:,None],3,axis=2))]:write_pfm(out/('brushed_concrete_'+name+'.pfm'),np.asarray(field,'f4'))
s=Scene();s.materials=72;s.material('plastic',(1,1,1),rough=.82,ior=1.5);s.emit('texture',72,'"brushed_concrete_color_native.pfm"',1.25/.32,1.25/.32,1);s.emit('roughness_texture',72,'"brushed_concrete_roughness.pfm"',1.25/.32,1.25/.32,1);s.material('bumpmap');s.emit('texture',73,'"brushed_concrete_height_metres.pfm"',1.25/.32,1.25/.32,1);s.emit('nested',73,72,-1,.5);s.emit('metric_bump',73);s.save(out/'materials.cys')
report.update(source_commit='12848c82f60bc58fa88640545868009b90298b32',source_blob='a775185955c9651aba3a037ee485279c618f484b',resolution=[1024,1024],tile_m=.32,height_encoding_scale_m=spec['height_scale_m'],actual_height_range_m=[float(height.min()),float(height.max())],source_mean_linear_rgb=linear.mean((0,1),dtype=float).tolist(),material_offset=72,material_count=2,physical_pixel_spacing_m=.32/1024,normal_contract='Full physical scalar height transported once in the actual reciprocal UV basis. The sidewalk maps brush direction across the path. Original authored microgrooves are submillimetric; pixel sampling still bounds visibility.',limits='Scene adapter of the merged original construction, not selected Blender native4096 slab appearance parity or measured Pardall reflectance. Roughness/color/height stay linked; no photo textures, upsampling, displaced silhouette or coupled hydration claim.',input_hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir() if p.is_file()})
(out/'SIDEWALK_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print('SIDEWALK_FIELDS',json.dumps(report),flush=True)
