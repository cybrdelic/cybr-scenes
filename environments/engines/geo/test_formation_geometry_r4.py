#!/usr/bin/env python3
"""Small local topology/attachment tests. Not geological or photographic validation."""
from pathlib import Path
import sys,json
import numpy as np
import trimesh
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'cybr-geo/examples/three_scenes'))
import rebuild_scenes as scene
from build_scenes import Builder,unit

def run():
    results={};rng=np.random.default_rng(638132)
    tested=0;min_area=float('inf')
    for family in ['slab','block','rounded']:
        for seed in range(12):
            v,f=scene.fracture_block(seed+900,(.21,.15,.13),family,2)
            m=trimesh.Trimesh(v,f,process=False)
            assert m.is_watertight and m.is_winding_consistent and m.volume>0
            assert np.isfinite(v).all()
            tested+=1
    results['fracture_products']={'samples':tested,'closed_consistent_positive_volume':True,'passed':True}
    b=Builder('forest',11883)
    errors=[]
    for i in range(160):
        base=rng.uniform(-2,2,3);direction=unit(rng.normal(size=3));length=rng.uniform(.02,.19)
        label='Layered_leaf_litter' if i%3==0 else 'Living_canopy';mat=11 if i%3==0 else 9
        b.leaf(label,base,direction,length,length*rng.uniform(.35,.79),mat,rng.uniform(-2,2),rng.uniform(.02,.25))
        v,f,n=b.groups[(label,mat)][-1];tv=v[f];area=np.linalg.norm(np.cross(tv[:,1]-tv[:,0],tv[:,2]-tv[:,0]),axis=1)
        min_area=min(min_area,float(area.min()));assert area.min()>0 and np.isfinite(n).all()
        errors.append(float(np.min(np.linalg.norm(v-base,axis=1))))
    assert max(errors)<1e-12
    up=Builder('forest',9317)
    up.leaf('Upward_fold',[0,0,0],[1,0,0],.12,.06,11,0,.13)
    lv,lf,ln=up.groups[('Upward_fold',11)][0]
    mid=lv[len(lv)//2]
    assert mid[2]>0 and np.mean(ln[:,2])>.5
    results['leaf_frame_orientation']={'default_fold_above_attachment_plane':True,'mean_normal_z':float(np.mean(ln[:,2])),'passed':True}
    results['leaf_laminae']={'samples':len(errors),'minimum_twice_triangle_area_m2':min_area,'maximum_base_attachment_error_m':max(errors),'finite_nonzero_area':True,'passed':True}
    b=Builder('forest',11883)
    path=np.c_[np.linspace(0,.25,12),np.zeros(12),np.linspace(0,2.6,12)]
    b.tube('Test_barked_trunk',path,np.linspace(.17,.06,12),8,32,True,.37)
    v,f,n=b.groups[('Test_barked_trunk',8)][0];m=trimesh.Trimesh(v,f,process=False)
    assert m.is_watertight and m.is_winding_consistent and m.volume>0
    results['barked_tube']={'triangles':len(f),'closed_consistent_positive_volume':True,'passed':True}
    # Continuous bedding field evaluated across adjacent parameter samples.
    yy,zz=np.meshgrid(np.linspace(-5,35,151),np.linspace(0,12,71))
    for side in [-1,1]:assert np.isfinite(scene.canyon_width(yy,zz,side)).all()
    results['bedding_field']={'samples':yy.size*2,'finite':True,'passed':True}
    report={'scope':__doc__,'components':results,'passed':all(v['passed'] for v in results.values())}
    return report
if __name__=='__main__':
    report=run();out=ROOT/'verification';out.mkdir(exist_ok=True)
    (out/'formation_geometry_r4.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
