#!/usr/bin/env python3
"""Frozen geometry builder plus narrow R2 paint and durable affine adapters.

The successfully built O-capable source remains unchanged. This entry point
substitutes only its paint copier and tile-transform storage in memory. It
copies existing R2 dust settings, adds no dust recipe changes, does not render,
and reopens its saved candidate to validate evaluated affine seams.
"""
from __future__ import annotations
import os
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'):os.environ[k]='2'
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
EXPECTED_CORE_SHA256='ed726e9bc52964535d818991a54b7ad2500d511052ca213078d4d9e72034a286'
EXPECTED_PAINT_SHA256='57b3b2b13bcca6f2ddf08a21cf221472f059ebc52fcd88c8482144466b7b1e88'

def main(argv):
    core_path=ROOT/'prepare_tiled_relief.py'
    digest=hashlib.sha256(core_path.read_bytes()).hexdigest()
    if digest!=EXPECTED_CORE_SHA256:raise ValueError('Frozen geometry source changed; review before this run')
    paint_sha=hashlib.sha256((ROOT/'paint_shader_adapter_r2.py').read_bytes()).hexdigest()
    if paint_sha!=EXPECTED_PAINT_SHA256:raise ValueError('Reviewed R2 paint adapter changed')
    sys.path.insert(0,str(ROOT))
    import bpy
    import prepare_tiled_relief as core
    from paint_shader_adapter_r2 import attach_shared_surface_paint
    from affine_tile_adapter import install_affine_parent,validate_affine_tiles
    core.attach_shared_surface_paint=attach_shared_surface_paint
    original_create_tiles=core.create_tiles
    def create_durable_affine_tiles(scene,height,bounds,fade,material):
        sides,report=original_create_tiles(scene,height,bounds,fade,material)
        report['affine_pre_save']=install_affine_parent(scene,bounds)
        report['max_adjacent_coordinate_mismatch_m']=max(report['affine_pre_save']['evaluated_max_seam_xyz_m'])
        return sides,report
    core.create_tiles=create_durable_affine_tiles
    core.main(argv)
    parser=argparse.ArgumentParser(add_help=False);parser.add_argument('--output',type=Path,required=True)
    args,_=parser.parse_known_args(argv)
    receipt=args.output.resolve().with_suffix('.receipt.json')
    report=json.loads(receipt.read_text())
    report['source_entry_point']='prepare_tiled_relief_r2.py'
    report['frozen_geometry_builder_sha256']=digest
    report['r2_paint_adapter_sha256']=paint_sha
    report['affine_tile_adapter_sha256']=hashlib.sha256((ROOT/'affine_tile_adapter.py').read_bytes()).hexdigest()
    report['r2_integration_contract']={
        'original_alpha_coordinates':'Original reference paint position for Geometry ancestors of original Alpha',
        'dust_coordinates':'Actual shared road hit for R2-added Geometry Position nodes',
        'all_geometry_normal_inputs':'Preserved broad normal; never the displaced tile slope',
        'new_dust_parameters_authored':False,
        'frozen_geometry_source_changed':False,
        'tile_transform_storage':'Identity parent with full matrix_parent_inverse, evaluated before save and after reload',
        'render_run':False,
    }
    try:
        bpy.ops.wm.open_mainfile(filepath=str(args.output.resolve()))
        report['affine_post_reload']=validate_affine_tiles(bpy.context.scene,report['effective_bounds'])
    except Exception as error:
        report['status']='REJECTED_AFFINE_RELOAD';report['failure']=str(error);receipt.write_text(json.dumps(report,indent=2)+'\n');raise
    receipt.write_text(json.dumps(report,indent=2)+'\n')
    print('R2_SHARED_SURFACE_AND_AFFINE_RELOAD_PASSED',json.dumps(report['affine_post_reload']),flush=True)

if __name__=='__main__':main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
