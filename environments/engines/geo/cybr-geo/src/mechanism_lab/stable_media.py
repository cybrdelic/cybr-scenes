"""Offline spatial-AA frame rendering for the existing CYBR GEO VTK studio.

This module reuses the actual Studio geometry/material/light pipeline. It does
not interpolate frames, replace geometry, or relabel the raster output as path
tracing. A separate, cut-aware temporal resolve consumes its lossless frames.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json
import math
import time
from typing import Any
import cv2
import numpy as np
import vtk
from vtk.util.numpy_support import vtk_to_numpy
from .core import Assembly, View
from .render import Studio
from .media import Shot

@dataclass(frozen=True)
class SpatialAA:
    width: int = 1440
    height: int = 936
    supersample: int = 2
    fps: int = 24
    ao_samples: int = 64
    ao: bool = False
    fixed_clipping: bool = True
    overscan_pixels: int = 48
    ao_bias_mm: float = 1.2

    def validate(self) -> None:
        if min(self.width,self.height,self.fps,self.supersample,self.ao_samples) <= 0:
            raise ValueError('All dimensions and sample counts must be positive')
        if self.width%2 or self.height%2:
            raise ValueError('4:2:0 delivery requires even dimensions')
        if self.supersample not in (1,2,3,4):
            raise ValueError('Supported linear spatial supersampling factors: 1..4')

_SRGB_TO_LINEAR = np.where(np.arange(256,dtype=np.float32)/255 <= .04045,
    np.arange(256,dtype=np.float32)/255/12.92,
    ((np.arange(256,dtype=np.float32)/255+.055)/1.055)**2.4).astype(np.float32)

def linear_to_srgb(image: np.ndarray) -> np.ndarray:
    x = np.clip(image,0,1)
    encoded = np.where(x<=.0031308,12.92*x,1.055*np.power(x,1/2.4)-.055)
    return np.clip(np.rint(encoded*255),0,255).astype(np.uint8)

def resolve_spatial(rgb: np.ndarray, size: tuple[int,int]) -> np.ndarray:
    """Area-integrate supersampled display pixels in linear-light space.

    This is a post-tone-map resolve (the inherited studio renders a tone-mapped
    RGB8 buffer), not an HDR radiance accumulation. No sharpening is applied.
    """
    if rgb.dtype!=np.uint8 or rgb.ndim!=3 or rgb.shape[-1]!=3:
        raise ValueError('Expected HxWx3 RGB8')
    if (rgb.shape[1],rgb.shape[0])==size: return rgb.copy()
    if rgb.shape[1] < size[0] or rgb.shape[0] < size[1]:
        raise ValueError('Spatial-AA resolve cannot upscale')
    linear = _SRGB_TO_LINEAR[rgb]
    integrated = cv2.resize(linear,size,interpolation=cv2.INTER_AREA)
    return linear_to_srgb(integrated)

class StableStudio(Studio):
    """The CYBR GEO studio with explicit high-resolution capture and stable depth."""
    def __init__(self,assembly: Assembly,view: View,quality: SpatialAA):
        quality.validate()
        super().__init__(assembly,size=(quality.width,quality.height),
                         supersample=quality.supersample,section=view.section,ao=quality.ao,
                         floor=view.floor,exposure=view.exposure)
        self.quality = quality
        self.guard = int(quality.overscan_pixels*quality.supersample)
        self.win.SetSize(quality.width*quality.supersample+2*self.guard,
                         quality.height*quality.supersample+2*self.guard)
        self.fixed_clip: tuple[float,float] | None = None
        # Studio.render explicitly renders. WindowToImageFilter otherwise
        # renders it a second time when updated; capture only the finished back
        # buffer here. This reduces redundant work, not sample count.
        self.capture.SetShouldRerender(False)
        if quality.supersample > 1: self.ren.UseFXAAOff()
        for p in self.passes:
            if isinstance(p,vtk.vtkSSAOPass):
                p.SetKernelSize(quality.ao_samples)
                p.SetBias(quality.ao_bias_mm)
                p.SetDepthFormat(vtk.vtkTextureObject.Float32)
                p.BlurOn()
        self.visible(lambda p:p.group not in view.hide)
        self.set_view(view)

    def render_rgb(self) -> np.ndarray:
        if self.fixed_clip is not None:
            self.cam.SetClippingRange(*self.fixed_clip)
        # Render a guard band for screen-space effects, then crop it away.
        # Increase the frustum to preserve the exact delivered framing.
        original_angle=self.cam.GetViewAngle()
        original_scale=self.cam.GetParallelScale()
        factor=(self.quality.height*self.quality.supersample+2*self.guard)/(self.quality.height*self.quality.supersample)
        if self.cam.GetParallelProjection():
            self.cam.SetParallelScale(original_scale*factor)
        else:
            self.cam.SetViewAngle(math.degrees(2*math.atan(math.tan(math.radians(original_angle)/2)*factor)))
        self.cam.Modified()
        self.win.Render()
        self.capture.Modified()
        self.capture.Update()
        image = self.capture.GetOutput()
        w,h,_ = image.GetDimensions()
        pixels = vtk_to_numpy(image.GetPointData().GetScalars()).reshape(h,w,3)
        rgb = np.ascontiguousarray(np.flipud(pixels))
        if self.guard:
            rgb=rgb[self.guard:-self.guard,self.guard:-self.guard].copy()
        self.cam.SetViewAngle(original_angle)
        self.cam.SetParallelScale(original_scale)
        return resolve_spatial(rgb,self.output_size)

def frame_state(shot: Shot,view: View,local_frame: int,n: int,
                global_frame: int,fps: int) -> dict[str,Any]:
    u = local_frame/max(1,n-1)
    e = (.5-.5*math.cos(math.tau*u)) if shot.action=='explode' else view.explode
    az = view.az+shot.orbit_degrees*(u-.5) if shot.action=='orbit' else view.az
    t = global_frame/fps
    return dict(time_seconds=t,pose_seconds=t if shot.action in ('motion','orbit') else 0.,
                azimuth_degrees=az,explosion=e)

def apply_state(studio: StableStudio,view: View,state: dict[str,Any]) -> None:
    studio.pose(state['pose_seconds'],state['explosion'])
    studio.set_camera(state['azimuth_degrees'],view.el,view.scale,view.target,
                      view.camera_distance_mm,view.projection,
                      view.focal_length_mm,view.sensor_width_mm)


def shot_clipping(studio: StableStudio,shot: Shot,view: View,
                  first_frame: int,n: int,fps: int) -> tuple[float,float]:
    """Conservative full-shot bounds, including rotor swept envelopes and floor.

    Clipping remains constant during the shot. For every component we bound all
    shaft rotation by an origin-centered radial envelope and all translation by
    the zero and maximum-explosion endpoint boxes. Views are sampled through the
    complete orbit with generous margin; these AERIS arcs are only 28 degrees.
    """
    corners=[]
    for part in studio.parts:
        lo,hi=part.bounds
        if part.motion!='fixed':
            r=float(np.max(np.linalg.norm(part.vertices[:,1:],axis=1)))
            lo=np.array([lo[0],-r,-r]);hi=np.array([hi[0],r,r])
        pts=np.array([[x,y,z] for x in (lo[0],hi[0])
                             for y in (lo[1],hi[1]) for z in (lo[2],hi[2])])
        for e in ((0.,1.) if shot.action=='explode' else (view.explode,)):
            corners.extend(pts+np.asarray(part.explode)*e)
    corners=np.asarray(corners)
    near_candidates=[]; far_candidates=[]
    for f in np.unique(np.linspace(0,n-1,17,dtype=int)):
        state=frame_state(shot,view,int(f),n,first_frame+int(f),fps)
        apply_state(studio,view,state)
        eye=np.asarray(studio.cam.GetPosition());target=np.asarray(studio.cam.GetFocalPoint())
        forward=target-eye;forward/=np.linalg.norm(forward)
        depth=(corners-eye)@forward
        near_candidates.append(float(depth.min()));far_candidates.append(float(depth.max()))
        if studio.floor_actor is not None:
            bounds=studio.floor_actor.GetBounds()
            floor_corners=np.array([[x,y,z] for x in bounds[:2] for y in bounds[2:4] for z in bounds[4:]])
            far_candidates.append(float(((floor_corners-eye)@forward).max()))
    near=max(1.,min(near_candidates)*.45)
    far=max(near+1.,max(far_candidates)*1.25)
    return float(near),float(far)


def render_lossless_frames(assembly: Assembly,output: Path,shots: list[Shot],
                           quality: SpatialAA,limit: int|None=None) -> dict[str,Any]:
    quality.validate()
    if any(s.view not in assembly.views or s.duration<=0 or
           s.action not in ('motion','orbit','explode','still') for s in shots):
        raise ValueError('Invalid shot specification')
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    rows=[]; shot_rows=[]; global_frame=0; start=time.monotonic()
    for si,shot in enumerate(shots):
        view=assembly.views[shot.view];full_n=round(shot.duration*quality.fps)
        n=full_n if limit is None else min(full_n,limit)
        studio=StableStudio(assembly,view,quality)
        try:
            if quality.fixed_clipping:
                studio.fixed_clip=shot_clipping(studio,shot,view,global_frame,full_n,quality.fps)
            repeatability=None
            for f in range(n):
                state=frame_state(shot,view,f,full_n,global_frame,quality.fps)
                apply_state(studio,view,state)
                rgb=studio.render_rgb()
                if f==0:
                    # Discard initial lazy resource setup before checking the
                    # frozen-camera repeatability contract.
                    rgb=studio.render_rgb()
                    repeated=studio.render_rgb()
                    delta=np.abs(rgb.astype(np.int16)-repeated.astype(np.int16))
                    repeatability={'max_rgb8_difference':int(delta.max()),
                                   'mean_rgb8_difference':float(delta.mean()),
                                   'identical':bool(np.array_equal(rgb,repeated))}
                    if delta.max()>1:
                        raise RuntimeError('Stationary rerender differs: '+str(repeatability))
                digest=hashlib.sha256(rgb.tobytes()).hexdigest()
                path=output/f'{global_frame:05d}.png'
                if not cv2.imwrite(str(path),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR),
                                   [cv2.IMWRITE_PNG_COMPRESSION,2]):
                    raise OSError('Could not save '+str(path))
                rows.append(dict(frame=global_frame,shot=si,local_frame=f,
                                 source_sha256=digest,file=path.name,**state))
                global_frame+=1
                if f%12==0 or f==n-1:
                    print(f'{assembly.name}: shot {si+1}/{len(shots)} frame {f+1}/{n}; '
                          f'{time.monotonic()-start:.1f}s elapsed',flush=True)
            shot_rows.append(dict(index=si,shot=asdict(shot),view=asdict(view),frames=n,
                                  first_frame=global_frame-n,
                                  clipping_range_mm=studio.fixed_clip,
                                  stationary_repeatability=repeatability))
        finally:
            studio.close()
    report=dict(model=assembly.name,renderer='CYBR GEO VTK PBR (not path traced)',
                geometry_source=assembly.metadata.get('source','assembly'),
                parts=len(assembly.parts),triangles=sum(len(p.faces) for p in assembly.parts),
                spatial_aa=asdict(quality),raster_resolution=[quality.width*quality.supersample,
                                                          quality.height*quality.supersample],
                guarded_raster_resolution=[quality.width*quality.supersample+2*quality.overscan_pixels*quality.supersample,quality.height*quality.supersample+2*quality.overscan_pixels*quality.supersample],
                final_resolution=[quality.width,quality.height],
                resolve='Linear-light area integration of tone-mapped RGB8 render',
                fxaa=quality.supersample==1,frame_interpolation=False,
                shading_note='Unstable SSAO pass disabled; existing PBR materials, geometry and lights retained' if not quality.ao else 'SSAO enabled',
                temporal_processing='Not yet applied; these are lossless independent frames',
                frames=global_frame,unique_frames=len({r['source_sha256'] for r in rows}),
                seconds_to_render=time.monotonic()-start,shots=shot_rows,frames_log=rows)
    (output/'render_manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
