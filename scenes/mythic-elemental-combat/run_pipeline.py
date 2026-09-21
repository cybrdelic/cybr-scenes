#!/usr/bin/env python3
"""End-to-end orchestrator for the mythic elemental combat proof."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]


def run(cmd,**kwargs):
    print("+"," ".join(map(str,cmd)),flush=True)
    subprocess.run(list(map(str,cmd)),check=True,**kwargs)


def find_blender(value):
    if value:return Path(value)
    env=os.environ.get("BLENDER")
    if env:return Path(env)
    hit=shutil.which("blender")
    if hit:return Path(hit)
    windows=Path(r"C:/Program Files/Blender Foundation/Blender 4.5/blender.exe")
    if windows.exists():return windows
    raise RuntimeError("Blender not found; pass --blender or set BLENDER")


def find_elements():
    if os.environ.get("CYBR_ELEMENTS_ROOT"):return Path(os.environ["CYBR_ELEMENTS_ROOT"])
    p=REPO.parent/"cybr-elements"
    if p.exists():return p
    raise RuntimeError("CYBR ELEMENTS not found; set CYBR_ELEMENTS_ROOT or clone it beside cybr-scenes")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--blender")
    p.add_argument("--preset",choices=["smoke","preview","reference"],default="preview")
    p.add_argument("--step",type=int,default=1)
    p.add_argument("--start",type=int)
    p.add_argument("--end",type=int)
    p.add_argument("--skip-fetch",action="store_true")
    p.add_argument("--skip-bake",action="store_true")
    p.add_argument("--skip-elements",action="store_true")
    p.add_argument("--skip-render",action="store_true")
    p.add_argument("--assemble",action="store_true")
    a=p.parse_args()

    if not a.skip_fetch:
        run([sys.executable,HERE/"fetch_avatar.py"])
    if not a.skip_bake:
        blender=find_blender(a.blender)
        run([blender,"--background","--factory-startup","--python",HERE/"animate_avatar.py","--","--step",str(a.step)])

    if not a.skip_elements:
        elements=find_elements()
        bridge=elements/"work"/"avatar-combat"/"render_avatar_elements.py"
        run([sys.executable,bridge,
             "--trajectory",HERE/"build"/"trajectory.json",
             "--cues",HERE/"build"/"element_cues.json",
             "--out",HERE/"build"/"elements"])

    if not a.skip_render:
        cmd=[sys.executable,HERE/"render_cybrlight.py","--preset",a.preset,"--step",str(a.step)]
        if a.start is not None:cmd+=["--start",str(a.start)]
        if a.end is not None:cmd+=["--end",str(a.end)]
        run(cmd)

    if a.assemble:
        ffmpeg=shutil.which("ffmpeg")
        if not ffmpeg:raise RuntimeError("ffmpeg not found")
        out=HERE/"renders"/"mythic-elemental-combat.mp4"
        run([ffmpeg,"-y","-framerate","30","-i",str(HERE/"renders"/"frame_%04d.png"),
             "-c:v","libx264","-crf","15","-pix_fmt","yuv420p",out])
        print(out)


if __name__=="__main__":
    main()
