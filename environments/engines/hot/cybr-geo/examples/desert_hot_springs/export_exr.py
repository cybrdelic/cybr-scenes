"""Export native linear RGB PFM to lossless float EXR and verify the round trip.

Optional dependency: an OpenCV build with OpenEXR support. This does not apply
exposure, denoising, tone mapping, white balance, or generative processing.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import numpy as np
from finish import read_pfm

def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    if not args.input.is_file():parser.error(f'Input does not exist: {args.input}')
    if args.output.suffix.lower()!='.exr':parser.error('Output must have an .exr extension')
    os.environ['OPENCV_IO_ENABLE_OPENEXR']='1'
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError('EXR export requires OpenCV with OpenEXR support. Install opencv-python-headless in a compatible environment.') from exc
    rgb=read_pfm(args.input)
    if not np.isfinite(rgb).all():raise ValueError('Nonfinite native RGB radiance')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    params=[cv2.IMWRITE_EXR_TYPE,cv2.IMWRITE_EXR_TYPE_FLOAT]
    if not cv2.imwrite(str(args.output),rgb[:,:,::-1].copy(),params):
        raise RuntimeError('OpenCV did not write the EXR')
    restored=cv2.imread(str(args.output),cv2.IMREAD_UNCHANGED)
    if restored is None or restored.shape!=rgb.shape:
        raise RuntimeError('Could not read the exported EXR with the expected shape')
    restored=restored[:,:,::-1]
    if not np.array_equal(rgb,restored):raise RuntimeError('EXR round trip changed native floating-point RGB values')
    report={'source':str(args.input),'output':str(args.output),'resolution':[rgb.shape[1],rgb.shape[0]],
            'color_space':'Native scene-linear RGB after 16-band integration; no display transform',
            'storage':'float32 RGB OpenEXR','round_trip_exact':True,
            'opencv_version':cv2.__version__,'sha256':hashlib.sha256(args.output.read_bytes()).hexdigest()}
    args.output.with_suffix('.exr.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
