#!/usr/bin/env python3
"""Contract validation for the baked rig -> CYBR ELEMENTS -> CYBR LIGHT handoff."""
from __future__ import annotations

import argparse
import json
import math
import struct
from pathlib import Path


HERE=Path(__file__).resolve().parent


def obj_stats(path:Path):
    vertices=faces=0
    with path.open("r",encoding="utf-8",errors="strict") as f:
        for line in f:
            if line.startswith("v "):
                values=[float(x) for x in line.split()[1:4]]
                if len(values)!=3 or not all(math.isfinite(x) for x in values):
                    raise ValueError(f"Non-finite OBJ vertex in {path}")
                vertices+=1
            elif line.startswith("f "):
                faces+=1
    return vertices,faces


def cgrid_stats(path:Path):
    with path.open("rb") as f:
        header=f.read(12)
        if len(header)!=12:raise ValueError(f"Truncated cgrid {path}")
        x,y,z=struct.unpack("<3i",header)
    if min(x,y,z)<2:raise ValueError(f"Invalid cgrid dimensions {x,y,z} in {path}")
    expected=12+x*y*z*4
    actual=path.stat().st_size
    if actual!=expected:raise ValueError(f"cgrid size mismatch {path}: {actual} != {expected}")
    return x,y,z


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--build",type=Path,default=HERE/"build")
    p.add_argument("--elements",type=Path)
    p.add_argument("--allow-sparse",action="store_true")
    a=p.parse_args()
    elements=a.elements or a.build/"elements"
    traj=json.loads((a.build/"trajectory.json").read_text())
    frames=traj["frames"]
    if not frames:raise RuntimeError("No baked frames")
    ids=[int(r["frame"]) for r in frames]
    if ids!=sorted(ids) or len(ids)!=len(set(ids)):raise RuntimeError("Trajectory frame IDs are not strictly ordered/unique")
    if not a.allow_sparse and ids!=list(range(int(traj["frame_start"]),int(traj["frame_end"])+1)):
        raise RuntimeError("Expected a full consecutive frame bake; pass --allow-sparse for diagnostic step bakes")

    obj_vertices=0;obj_faces=0
    for frame in ids:
        for kind in ("avatar","weapon"):
            path=a.build/kind/f"frame_{frame:04d}.obj"
            if not path.exists():raise FileNotFoundError(path)
            v,f=obj_stats(path)
            if v==0 or f==0:raise RuntimeError(f"Empty {kind} geometry on frame {frame}")
            obj_vertices+=v;obj_faces+=f

    manifest_path=elements/"manifest.json"
    element_assets=0;cgrids=0
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text())
        for frame in ids:
            assets=manifest.get("frames",{}).get(str(frame),{})
            for key,rel in assets.items():
                path=elements/rel
                if not path.exists():raise FileNotFoundError(f"Manifest points to missing {key}: {path}")
                element_assets+=1
                if path.suffix==".cgrid":
                    cgrid_stats(path);cgrids+=1
                elif path.suffix==".obj":
                    # Empty geometry is allowed only before an effect's first shard births.
                    obj_stats(path)
                elif path.suffix==".json":
                    json.loads(path.read_text())

    result={
        "frames":len(ids),
        "frameRange":[ids[0],ids[-1]],
        "avatarAndWeaponVerticesVisited":obj_vertices,
        "avatarAndWeaponTrianglesVisited":obj_faces,
        "elementAssets":element_assets,
        "validatedCgrids":cgrids,
        "coordinateSystem":traj.get("coordinate_system"),
        "ok":True,
    }
    (a.build/"validation.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=="__main__":
    main()
