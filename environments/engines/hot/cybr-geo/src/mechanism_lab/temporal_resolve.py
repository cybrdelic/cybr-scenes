"""Conservative, non-recursive, bidirectional motion-aware temporal video resolve.

Consumes real independent rendered frames. The current frame always remains the
anchor. Two adjacent frames are warped to it, rejected on occlusions/inconsistent
flow, clipped to a current-frame neighborhood, and mixed only where consistent.
Shot boundaries explicitly reset the neighborhood. No synthesized video frames,
recursive history accumulation, or unconstrained multi-frame averaging is used.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
from pathlib import Path
from typing import Sequence
import hashlib
import json
import subprocess
import time
import cv2
import numpy as np
from PIL import Image
from .render import labelled
from .media import probe

@dataclass(frozen=True)
class TemporalSettings:
    neighbor_weight: float = .55
    consistency_px: float = 1.25
    photometric_sigma: float = 18.0
    flow_scale: float = .5
    neighborhood_radius: int = 1
    clamp_margin: float = 1.5
    crf: int = 14
    preset: str = 'slow'

    def validate(self) -> None:
        if not 0<=self.neighbor_weight<=1:raise ValueError('neighbor_weight must be in [0,1]')
        if self.consistency_px<=0 or self.photometric_sigma<=0:raise ValueError('Positive rejection thresholds required')
        if not 0<self.flow_scale<=1:raise ValueError('flow_scale must be in (0,1]')
        if self.neighborhood_radius not in (1,2):raise ValueError('Neighborhood radius must be 1 or 2')
        if not 0<=self.crf<=51:raise ValueError('Invalid H.264 CRF')

class TemporalResolver:
    def __init__(self,settings: TemporalSettings=TemporalSettings()):
        settings.validate();self.settings=settings
        self.flow=cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        self.flow.setFinestScale(1)
        self.flow.setVariationalRefinementIterations(5)
        self.flow.setUseSpatialPropagation(True)
        self.flow.setUseMeanNormalization(True)
        self.grid: tuple[np.ndarray,np.ndarray]|None=None

    def optical_flow(self,current: np.ndarray,neighbor: np.ndarray) -> np.ndarray:
        h,w=current.shape[:2];scale=self.settings.flow_scale
        small=(max(32,round(w*scale)),max(32,round(h*scale)))
        a=cv2.resize(cv2.cvtColor(current,cv2.COLOR_RGB2GRAY),small,interpolation=cv2.INTER_AREA)
        b=cv2.resize(cv2.cvtColor(neighbor,cv2.COLOR_RGB2GRAY),small,interpolation=cv2.INTER_AREA)
        f=self.flow.calc(a,b,None)
        full=cv2.resize(f,(w,h),interpolation=cv2.INTER_LINEAR)
        full[:,:,0]*=w/small[0];full[:,:,1]*=h/small[1]
        return full

    def resolve(self,current: np.ndarray,neighbors: Sequence[np.ndarray]) -> tuple[np.ndarray,dict]:
        if current.dtype!=np.uint8 or current.ndim!=3 or current.shape[-1]!=3:
            raise ValueError('Current frame must be RGB8')
        if any(n.shape!=current.shape or n.dtype!=np.uint8 for n in neighbors):
            raise ValueError('All frames must have matching dimensions and type')
        if not neighbors:
            return current.copy(),{'neighbors':0,'accepted_fraction':0.,'mean_abs_change_rgb8':0.}
        s=self.settings;h,w=current.shape[:2]
        if self.grid is None or self.grid[0].shape!=(h,w):
            xx,yy=np.meshgrid(np.arange(w,dtype=np.float32),np.arange(h,dtype=np.float32));self.grid=(xx,yy)
        xx,yy=self.grid
        anchor=current.astype(np.float32)
        kernel=np.ones((2*s.neighborhood_radius+1,)*2,np.uint8)
        low=cv2.erode(anchor,kernel)-s.clamp_margin
        high=cv2.dilate(anchor,kernel)+s.clamp_margin
        numerator=anchor.copy();denominator=np.ones((h,w),np.float32)
        accepted=[];avg_weights=[]
        for neighbor in neighbors:
            forward=self.optical_flow(current,neighbor)
            backward=self.optical_flow(neighbor,current)
            mx=xx+forward[:,:,0];my=yy+forward[:,:,1]
            warped=cv2.remap(neighbor,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE).astype(np.float32)
            reverse=cv2.remap(backward,mx,my,cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
            error=np.linalg.norm(forward+reverse,axis=-1)
            valid=(mx>=1)&(mx<w-2)&(my>=1)&(my<h-2)&(error<s.consistency_px)
            # Current-frame neighborhood clipping prevents a mismatched history
            # sample from placing a bright moving blade on the dark background.
            warped=np.clip(warped,low,high)
            change=np.max(np.abs(warped-anchor),axis=-1)
            flow_confidence=np.exp(-.5*(error/(s.consistency_px*.55))**2)
            photo_confidence=np.exp(-.5*(change/s.photometric_sigma)**2)
            weight=s.neighbor_weight*valid*flow_confidence*photo_confidence
            numerator+=warped*weight[:,:,None];denominator+=weight
            accepted.append(float(valid.mean()));avg_weights.append(float(weight.mean()))
        result=np.clip(np.rint(numerator/denominator[:,:,None]),0,255).astype(np.uint8)
        change=np.abs(result.astype(np.int16)-current.astype(np.int16))
        return result,dict(neighbors=len(neighbors),accepted_fraction=float(np.mean(accepted)),
                           mean_neighbor_weight=float(np.mean(avg_weights)),
                           mean_abs_change_rgb8=float(change.mean()),max_abs_change_rgb8=int(change.max()))


def resolve_video(frame_folder: Path,output: Path,settings: TemporalSettings=TemporalSettings(),
                  captions: bool=True,save_clean: bool=True) -> dict:
    settings.validate();cv2.setNumThreads(1)
    folder=Path(frame_folder);output=Path(output)
    output.parent.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((folder/'render_manifest.json').read_text())
    rows=manifest['frames_log'];shots=manifest['shots'];q=manifest['spatial_aa']
    width,height=manifest['final_resolution'];fps=q['fps']
    partial=output.with_name(output.stem+'.partial.mp4')
    command=['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24',
             '-s',f'{width}x{height}','-framerate',str(fps),'-i','-',
             '-an','-vf','scale=out_color_matrix=bt709:out_range=tv,format=yuv420p',
             '-c:v','libx264','-threads','1','-preset',settings.preset,'-crf',str(settings.crf),
             '-colorspace','bt709','-color_primaries','bt709','-color_trc','bt709',
             '-movflags','+faststart',str(partial)]
    resolver=TemporalResolver(settings);cache={};stats=[];start=time.monotonic()
    clean=folder/'resolved'
    if save_clean:clean.mkdir(exist_ok=True)
    def read(i):
        if i not in cache:
            bgr=cv2.imread(str(folder/rows[i]['file']))
            if bgr is None:raise OSError('Missing frame '+rows[i]['file'])
            cache[i]=cv2.cvtColor(bgr,cv2.COLOR_BGR2RGB)
        return cache[i]
    proc=subprocess.Popen(command,stdin=subprocess.PIPE)
    try:
        for i,row in enumerate(rows):
            indices=[j for j in (i-1,i+1) if 0<=j<len(rows) and rows[j]['shot']==row['shot']]
            current=read(i);result,info=resolver.resolve(current,[read(j) for j in indices])
            info.update(frame=i,shot=row['shot'],neighbor_frames=indices,
                        clean_rgb_sha256=hashlib.sha256(result.tobytes()).hexdigest())
            if save_clean:
                if not cv2.imwrite(str(clean/f'{i:05d}.png'),cv2.cvtColor(result,cv2.COLOR_RGB2BGR),
                                   [cv2.IMWRITE_PNG_COMPRESSION,2]):
                    raise OSError('Could not save resolved frame')
            if captions:
                shot=shots[row['shot']]
                footer=(f"{row['time_seconds']:05.2f} s  |  {fps} fps  |  "
                        f"{shot['shot']['action'].upper()}  |  prescribed geometry motion, not force simulation")
                result=np.array(labelled(Image.fromarray(result),shot['shot']['title'],
                    f"{q['supersample']**2}x spatial samples / motion-aware temporal resolve / actual geometry",
                    footer,tag='CYBR GEO / SUPERSAMPLED PBR'))
            proc.stdin.write(np.ascontiguousarray(result).tobytes());stats.append(info)
            for k in list(cache):
                if k<i-1:del cache[k]
            if i%24==0 or i==len(rows)-1:
                print(f'{output.stem}: resolved {i+1}/{len(rows)} frames; {time.monotonic()-start:.1f}s',flush=True)
        proc.stdin.close()
        if proc.wait()!=0:raise RuntimeError('FFmpeg failed')
        partial.replace(output)
    except BaseException:
        try:proc.stdin.close()
        except (BrokenPipeError,OSError):pass
        proc.kill();proc.wait();partial.unlink(missing_ok=True);raise
    report=dict(file=output.name,frames=len(rows),duration_seconds=len(rows)/fps,
                resolution=[width,height],fps=fps,method='New supersampled VTK geometry renders + guarded bidirectional temporal resolve',
                renderer_is_path_traced=False,frame_interpolation=False,
                spatial_render=manifest,temporal_settings=asdict(settings),
                temporal_notes=['Symmetric adjacent frames; original current-frame anchor',
                                'Optical-flow estimated reprojection, not exact renderer motion vectors',
                                'Forward-backward consistency rejection and neighborhood clipping',
                                'History cannot cross a declared shot cut',
                                'No recursive history, motion blur, global deflicker, sharpening or frame synthesis',
                                'Small raster/specular artifacts can remain; not a claim of perfect temporal stability'],
                output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
                seconds_to_resolve=time.monotonic()-start,probe=probe(output),frames_log=stats)
    output.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    return report
