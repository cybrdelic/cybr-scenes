#!/usr/bin/env python3
"""Exercise multi-material semantic groups through the actual CYBR GEO adapter."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import tempfile
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'cybr-geo/examples/three_scenes'))
from build_scenes import Builder, Assembly

def run() -> dict:
    with tempfile.TemporaryDirectory(prefix='cybr_namespace_') as temporary:
        target=Path(temporary)
        b=Builder('namespace_regression',20260915)
        vertices=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
        face=np.array([[0,1,2]])
        b.add('Shared_label',vertices,face,mat=0)
        b.add('Shared_label',vertices+np.array([2.,0.,0.]),face,mat=1)
        b.finish(target,{'test':'multi-material semantic namespace'},glb=False)
        scene=Assembly.load(target/'assembly/scene.json')
        names=[p.name for p in scene.parts]
        passed=len(names)==2 and len(set(names))==2 and {p.material for p in scene.parts}=={0,1}
        expected=[vertices*1000,(vertices+np.array([2.,0.,0.]))*1000]
        passed=passed and all(np.array_equal(p.vertices,q) for p,q in zip(scene.parts,expected))
        if not passed:raise AssertionError('Material namespace / saved geometry regression')
        return {'test':'Multi-material semantic group survives actual save/load without duplicate part names',
                'names':names,'triangles':sum(len(p.faces) for p in scene.parts),
                'vertices_and_materials_preserved':True,'passed':True}

if __name__=='__main__':
    report=run();(ROOT/'verification').mkdir(exist_ok=True)
    (ROOT/'verification/material_namespace.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))
