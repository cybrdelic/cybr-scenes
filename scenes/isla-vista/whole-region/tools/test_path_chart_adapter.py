"""Tiny regression for metric path tops and closed vertical curb charts."""
from pathlib import Path
import hashlib,json,os,subprocess,sys,tempfile
import numpy as np
from cybrlight.scene_compat import Meshlets
R=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='path-chart-') as directory:
 root=Path(directory);source=root/'contact.clm';out=root/'repaired'
 xyz=np.array([[[1000.,1000.,2.],[1000.0000610351562,1000.,2.],[1000.,1000.0000610351562,2.]],[[1000.,1000.,2.],[1000.08,1000.,2.],[1000.08,1000.,2.18]],[[1000.,1000.,2.],[1000.08,1000.,2.18],[1000.,1000.,2.18]]],dtype='<f4')
 rows=np.zeros((3,36),dtype='<f4');rows[:,:9]=xyz.reshape(3,9);rows[:,9:18]=np.tile([0,0,1],3);rows[:,18]=11;rows[:,19]=[1,2,2];rows[:,20:26]=(xyz[:,:,:2]/1.25).reshape(3,6);rows[:,26:35]=1
 with Meshlets(source) as w:w.add(rows)
 (root/'CONTACT_RECEIPT.json').write_text(json.dumps({'parts':[{'object':1,'name':'mapped_path_boundary_0'},{'object':2,'name':'mapped_path_closed_edges'}]}))
 subprocess.run([sys.executable,str(R/'tools/replay_retained_iv_script.py'),'rebase_recovered_path_uv.py','--source',str(source),'--output',str(out)],check=True)
 proof=json.loads((out/'UV_REBASE_RECEIPT.json').read_text());assert proof['all_non_uv_fields_exact'] and proof['vertical_edge_triangles_with_physical_arclength_height_chart']==2
 scene=root/'fixture.cys';scene.write_text('metric_bump 11 0.32 0.001\nmeshlets '+json.dumps(str(out/'contact.clm'))+'\n')
 subprocess.run([sys.executable,str(R/'work/audit_scene_metric_uv.py'),str(scene)],check=True)
 audit=json.loads((root/'fixture_metric_uv_audit.json').read_text());assert audit['passed'] and audit['meshes'][0]['metric_faces_tested']==3
 print('PASS: tiny horizontal charts and vertical arclength/height charts preserve all non-UV fields and pass the unchanged metric preflight.')
