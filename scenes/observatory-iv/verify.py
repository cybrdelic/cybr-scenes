"""Executable checks for the delivered scene and native-render output.

These tests cover asset integrity and explicit numerical properties, not a
subjective realism score or an unsupported claim of full physical accuracy.
"""
from __future__ import annotations
import argparse,hashlib,json,struct,subprocess,sys
from pathlib import Path
import numpy as np
import trimesh
ROOT=Path(__file__).resolve().parent

def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for a in iter(lambda:f.read(1<<20),b''):h.update(a)
    return h.hexdigest()

def geometry():
    p=ROOT/'scene/observatory.cvr2';manifest=json.loads((ROOT/'scene/manifest.json').read_text())
    with p.open('rb') as f:magic=f.read(4);count=struct.unpack('<I',f.read(4))[0]
    assert magic==b'CVR2' and p.stat().st_size==8+count*144
    assert count==manifest['triangles'] and sha(p)==manifest['mesh_sha256']
    a=np.memmap(p,'<f4',mode='r',offset=8,shape=(count,36))
    finite=True;nonunit=0;degenerate=0
    for i in range(0,count,100000):
        q=np.array(a[i:i+100000]);finite &= bool(np.isfinite(q).all())
        n=q[:,9:18].reshape(-1,3);nonunit+=int((np.abs(np.linalg.norm(n,axis=1)-1)>.005).sum())
        v=q[:,:9].reshape(-1,3,3);cross=np.cross(v[:,1]-v[:,0],v[:,2]-v[:,0]);degenerate+=int((np.sum(cross*cross,axis=1)<=1e-22).sum())
    assert finite and nonunit==0
    dielectric=[];start=0
    for ob in manifest['objects']:
        end=start+ob['triangles']
        if ob['material']==8:
            v=np.array(a[start:end,:9]).reshape(-1,3);faces=np.arange(len(v)).reshape(-1,3)
            m=trimesh.Trimesh(v,faces,process=True,validate=True)
            edge_counts=np.bincount(m.edges_unique_inverse,minlength=len(m.edges_unique))
            test={'name':ob['name'],'triangles':len(m.faces),'welded_vertices':len(m.vertices),'boundary_edges':int((edge_counts==1).sum()),'nonmanifold_edges':int((edge_counts>2).sum()),'winding_consistent':bool(m.is_winding_consistent),'signed_volume_m3':float(m.volume)}
            test['passed']=test['boundary_edges']==0 and test['nonmanifold_edges']==0 and test['winding_consistent'] and test['signed_volume_m3']>0
            dielectric.append(test)
        start=end
    assert all(q['passed'] for q in dielectric),dielectric
    groups=ROOT/'scene/observatory.groups'
    with groups.open('rb') as f:ng=struct.unpack('<I',f.read(4))[0];g=np.frombuffer(f.read(),'<f4').reshape(ng,7)
    assert ng==manifest['parts'] and np.isfinite(g).all() and np.allclose(np.linalg.norm(g[:,3:6],axis=1),1,atol=1e-5)
    tex=[]
    for r in json.loads((ROOT/'scene/texture_manifest.json').read_text()):
        t=ROOT/'scene/textures'/f"{r['index']}.cvtex"
        with t.open('rb') as f:w,h,c=struct.unpack('<III',f.read(12))
        q=np.memmap(t,'<f4',mode='r',offset=12,shape=(h,w,7))
        norms=np.linalg.norm(q[:,:,3:6],axis=-1);passed=bool(np.isfinite(q).all() and np.min(q[:,:,:3])>=0 and np.max(q[:,:,:3])<=.941 and np.allclose(norms,1,atol=1e-5) and np.min(q[:,:,6])>0 and np.max(q[:,:,6])<=1)
        assert w==h==r['resolution'] and c==7 and sha(t)==r['sha256'] and passed
        tex.append({'name':r['name'],'size':w,'passed':passed})
    return {'passed':True,'triangles_authored':count,'near_zero_area_triangles_reference_float32':degenerate,'parts':ng,'mesh_sha256':sha(p),'finite_geometry':finite,'nonunit_corner_normals':nonunit,'closed_quartz_components':dielectric,'texture_checks':tex,'continuous_machining_axis_groups':int((g[:,6]>0).sum())}

def render(stem):
    from finish import read_pfm,read_guides
    from PIL import Image
    p=Path(stem);meta=json.loads(p.with_suffix('.json').read_text());raw=read_pfm(str(p)+'.pfm');direct=read_pfm(str(p)+'_direct.pfm');indirect=read_pfm(str(p)+'_indirect.pfm');volume=read_pfm(str(p)+'_volume.pfm');guides=read_guides(str(p)+'.guides')
    assert np.isfinite(raw).all() and np.isfinite(guides).all()
    tg=read_guides(str(p)+'_transmitted.guides');assert tg.shape==guides.shape and np.isfinite(tg).all()
    err=float(np.max(np.abs(raw-direct-indirect-volume)));relative=err/max(1,float(np.max(np.abs(raw))))
    assert relative<3e-5
    import cv2
    exr=cv2.imread(str(p)+'_raw.exr',cv2.IMREAD_UNCHANGED)
    assert exr is not None
    exr=exr[:,:,::-1];roundtrip=float(np.max(np.abs(raw-exr)));assert roundtrip==0
    image=Image.open(str(p)+'.png');assert image.size==(meta['width'],meta['height'])
    assert meta['nonfinite_paths']==0 and meta['clamped_path_contributions']==0
    assert meta['finishing']['raw_changed'] is False and meta['finishing']['generative'] is False and meta['finishing']['neural'] is False
    return {'passed':True,'image_dimensions':image.size,'png_sha256':sha(str(p)+'.png'),'raw_sha256':sha(str(p)+'_raw.exr'),'finite_raw':True,'aov_sum_max_abs_error':err,'aov_sum_relative_error':relative,'raw_exr_roundtrip_max_error':roundtrip,'raw_not_clamped':True,'dominant_transmitted_guide_pixels':int((guides[:,:,8]==8).sum()),'native_resolution':True,'sampling':meta['sampling'],'seconds':meta['seconds'],'triangles_actually_traced':meta['triangles']}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--geometry-only',action='store_true');ap.add_argument('--stem',type=Path,default=ROOT/'renders/Observatory_IV');args=ap.parse_args()
    report={'geometry':geometry()}
    report['numeric_transport']=json.loads(subprocess.check_output([str(ROOT/'build/observatory'),'--self-test'],text=True))
    if not args.geometry_only:report['render']=render(args.stem)
    report['passed']=all(v['passed'] for v in report.values());report['scope']='Explicit geometry/material/numerical/raw-output tests; not a photorealism or convergence certification'
    out=ROOT/'verification'/('geometry_and_transport.json' if args.geometry_only else 'delivery_verification.json');out.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
