#!/usr/bin/env python3
"""Spectral offline render pass for the CYBR mythic elemental combat scene."""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def find_cybr_light() -> Path:
    candidates=[]
    if os.environ.get("CYBR_LIGHT_ROOT"):
        candidates.append(Path(os.environ["CYBR_LIGHT_ROOT"]))
    candidates += [REPO.parent/"cybr-light", HERE/"vendor"/"cybr-light"]
    for c in candidates:
        if (c/"python"/"cybrlight"/"__init__.py").exists():
            return c.resolve()
    raise RuntimeError("CYBR LIGHT not found. Set CYBR_LIGHT_ROOT or clone cybr-light beside cybr-scenes.")


CYBR_LIGHT=find_cybr_light()
sys.path.insert(0,str(CYBR_LIGHT/"python"))
from cybrlight import Camera, Scene, Settings, normalized, render  # noqa: E402


PRESETS={
    "smoke": dict(width=320,height=180,spp=12,bands=6,max_depth=12),
    "preview": dict(width=960,height=540,spp=96,bands=10,max_depth=24),
    "reference": dict(width=1920,height=1080,spp=320,bands=12,max_depth=36),
}


def parse_args():
    p=argparse.ArgumentParser()
    p.add_argument("--build",type=Path,default=HERE/"build")
    p.add_argument("--elements",type=Path,default=None)
    p.add_argument("--out",type=Path,default=HERE/"renders")
    p.add_argument("--preset",choices=PRESETS,default="preview")
    p.add_argument("--frame",type=int)
    p.add_argument("--start",type=int)
    p.add_argument("--end",type=int)
    p.add_argument("--step",type=int,default=1)
    p.add_argument("--threads",type=int,default=max(1,min(12,(os.cpu_count() or 4)-1)))
    p.add_argument("--executable",type=Path)
    return p.parse_args()


def v(value): return np.asarray(value,dtype=float)


def has_geometry(path:Path)->bool:
    if not path.exists() or path.stat().st_size<16:return False
    with path.open("r",encoding="utf-8",errors="ignore") as f:
        return any(line.startswith("v ") for line in f)


def camera_for(row):
    root=v(row["root"]);move=row["move"];phase=float(row.get("phase",0))
    if move=="frost_cleave":
        offset=np.array([4.7,2.35,6.6])
    elif move=="flame_slam":
        offset=np.array([3.8,1.95,6.3])
    elif move=="storm_spin":
        a=phase*math.pi*.9-.45
        offset=np.array([math.cos(a)*6.4,2.45,math.sin(a)*6.4])
    elif move=="earth_breaker":
        offset=np.array([5.2,1.70,7.2])
    elif move=="tidal_recall":
        offset=np.array([-4.6,2.45,6.8])
    else:
        offset=np.array([4.6,2.25,6.8])
    target=root+np.array([0,1.0,0])
    return Camera(origin=(root+offset).tolist(),target=target.tolist(),fov=34,focus=float(np.linalg.norm(offset)))


def make_scene(row, frame, build:Path, elements_root:Path|None, manifest, preset, threads):
    s=Scene(f"mythic_elemental_{frame:04d}")
    q=PRESETS[preset]
    s.settings=Settings(width=q["width"],height=q["height"],spp=q["spp"],bands=q["bands"],
                        max_depth=q["max_depth"],rr_depth=7,threads=threads,seed=8700+frame,
                        exposure=.92,film_format="openexr",filter="tent",sampler=1)
    s.camera=camera_for(row)
    s.asset_base=str(HERE)

    # Materials.
    floor=s.material(name="wet basalt arena",type="plastic",color=(.045,.052,.060),roughness=.32)
    avatar=s.material(name="graphite combat dummy",type="plastic",color=(.13,.14,.16),roughness=.24)
    metal=s.material(name="axe steel",type="metal",eta=(.22,.55,1.15),k=(3.9,3.0,2.2),roughness=.16)
    stone=s.material(name="fractured earth",type="diffuse",color=(.12,.075,.038),roughness=.82)
    ice=s.material(name="frost shards",type="roughglass",color=(.78,.91,1.0),ior_a=1.31,ior_b=.004,
                   roughness=.14,absorption=(.03,.012,.005))
    water=s.material(name="swept liquid",type="glass",color=1,ior_a=1.333,ior_b=.002,
                     absorption=(.32,.075,.018))
    lightning=s.material(name="ionized channel",type="emitter",color=(.28,.50,1.0),emission=34,kelvin=9000)
    fire=s.material(name="hot flame core",type="emitter",color=(1.0,.075,.004),emission=18,kelvin=2050)
    key=s.material(name="large cold key",type="emitter",color=1,emission=7.5,kelvin=5900)
    rim=s.material(name="warm rim",type="emitter",color=1,emission=5.2,kelvin=3600)

    # Arena and real area emitters.
    s.rectangle((0,-.015,0),(0,0,28),(28,0,0),floor)
    s.rectangle((-3.8,6.2,-1.5),(5.5,0,0),(0,0,5.0),key)
    s.rectangle((4.8,3.2,-4.7),(0,3.5,0),(3.8,0,0),rim)
    # Low walls and monoliths give the indirect pass scale cues.
    for x,z,h in [(-4.6,-2.5,2.5),(4.8,-3.0,3.1),(-5.2,3.2,2.0),(5.5,2.8,2.6)]:
        s.box((x-.28,0,z-.28),(x+.28,h,z+.28),stone)
    s.environment.update(color=[.055,.075,.12],strength=.17)

    avatar_obj=build/"avatar"/f"frame_{frame:04d}.obj"
    weapon_obj=build/"weapon"/f"frame_{frame:04d}.obj"
    if not avatar_obj.exists() or not weapon_obj.exists():
        raise FileNotFoundError(f"Missing baked geometry for frame {frame}; run animate_avatar.py")
    s.obj(avatar_obj,avatar,smooth=True)
    s.obj(weapon_obj,metal,smooth=True)

    assets={}
    if manifest:
        assets=manifest.get("frames",{}).get(str(frame),{})
        bounds=manifest.get("bounds",{})
        lo=bounds.get("lower",[-4,0,-4]);hi=bounds.get("upper",[4,5,4])
        def ep(key):
            rel=assets.get(key)
            return elements_root/rel if rel and elements_root else None

        # CYBR ELEMENTS scalar fields enter CYBR LIGHT as native heterogeneous volumes.
        p=ep("fire_density")
        if p and p.exists():
            s.volume(lo,hi,kind=2,grid=str(p),extinction=1.65,albedo=.72,g=.35,phase="hg")
        p=ep("air_density")
        if p and p.exists():
            s.volume(lo,hi,kind=2,grid=str(p),extinction=.58,albedo=.94,g=.62,phase="hg")

        p=ep("frost_mesh")
        if p and has_geometry(p):s.obj(p,ice,smooth=False)
        p=ep("water_mesh")
        if p and has_geometry(p):s.obj(p,water,smooth=True)
        p=ep("earth_mesh")
        if p and has_geometry(p):s.obj(p,stone,smooth=False)

        p=ep("fire_core")
        if p and p.exists():
            points=json.loads(p.read_text()).get("points",[])
            # Emissive geometry provides spectral energy; a few point lights
            # reinforce near-field fire bounce without screen-space bloom.
            for i,item in enumerate(points[:18]):
                pos=item["p"];temp=float(item.get("temperature",1))
                s.sphere(pos,.035+.016*min(temp,2),fire)
            for item in points[::max(1,len(points)//5)][:5]:
                s.point_light(item["p"],(1.0,.14,.018),scale=9.0)

        p=ep("lightning")
        if p and p.exists():
            data=json.loads(p.read_text())
            for a,b in data.get("segments",[]):
                a=v(a);b=v(b);d=b-a;length=float(np.linalg.norm(d))
                if length<1e-4:continue
                s.cylinder(((a+b)*.5).tolist(),.0085,length,lightning,axis=(d/length).tolist(),caps=True)
            head=v(row["axe_head"])
            s.point_light(head.tolist(),(.32,.55,1.0),scale=30.0)

    # Element-colored physical lights track the weapon even when the effect's
    # geometry/volume is outside the camera frustum.
    head=v(row["axe_head"])
    if row["move"]=="frost_cleave":
        s.point_light(head.tolist(),(.40,.72,1.0),scale=12)
    elif row["move"]=="flame_slam":
        s.point_light(head.tolist(),(1.0,.12,.015),scale=20)
    elif row["move"]=="storm_spin":
        s.point_light(head.tolist(),(.25,.48,1.0),scale=22)
    elif row["move"]=="earth_breaker":
        s.point_light(head.tolist(),(.55,.18,.035),scale=6)
    elif row["move"]=="tidal_recall":
        s.point_light(head.tolist(),(.08,.32,.75),scale=9)

    s.notes += [
        "Character mesh is an evaluated skeletal bake from Blender; no image generation.",
        "Element assets come from CYBR ELEMENTS world-space trajectory bridge.",
        "CYBR LIGHT performs the final explicit-geometry spectral transport pass.",
        "Three-component spectral controls are authoring values, not calibrated measured spectra.",
    ]
    return s


def main():
    a=parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    trajectory=json.loads((a.build/"trajectory.json").read_text())
    rows={int(r["frame"]):r for r in trajectory["frames"]}
    elements=a.elements or (a.build/"elements")
    manifest=None
    if (elements/"manifest.json").exists():
        manifest=json.loads((elements/"manifest.json").read_text())

    if a.frame is not None:
        frames=[a.frame]
    else:
        start=a.start if a.start is not None else int(trajectory["frame_start"])
        end=a.end if a.end is not None else int(trajectory["frame_end"])
        frames=list(range(start,end+1,a.step))
    reports={}
    for frame in frames:
        if frame not in rows:
            raise KeyError(f"Frame {frame} was not baked")
        scene=make_scene(rows[frame],frame,a.build,elements,manifest,a.preset,a.threads)
        prefix=a.out/f"frame_{frame:04d}"
        report=render(scene,prefix,executable=a.executable)
        reports[str(frame)]=report
        print("RENDERED",frame,prefix.with_suffix(".png"),flush=True)
    (a.out/"render_reports.json").write_text(json.dumps(reports,indent=2,default=str))


if __name__=="__main__":
    main()
