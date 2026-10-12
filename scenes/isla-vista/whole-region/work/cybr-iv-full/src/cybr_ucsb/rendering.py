"""Native CYBR LIGHT renders of the exact CYBR GEO sector geometry."""
from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import json
import math
import shutil
import subprocess
import numpy as np
import trimesh
from cybr_light import Scene, Meshlets, render
from cybr_light.runtime import compile_renderer, read_pfm
from cybr_terrain.materials import write_pfm
from cybr_terrain.rendering import daylight
from .sources import write_json, sha256

VIEWS = {
    "overview": ((-800,-1900,2400),(0,0,10),46,(0,0,1),False,2250),
    "north-up": ((0,0,2700),(0,0,0),45,(0,1,0),True,2200),
    "campus": ((1030,-870,410),(480,-60,22),44,(0,0,1),False,1),
    "isla-vista": ((-1270,-930,550),(-450,-60,12),47,(0,0,1),False,1),
}


def prepare(directory):
    """Decode the authoritative metre/Y-up GLB, then pack native meshlets.

    This exercises the GEO export bridge; the renderer cannot drift onto a
    parallel scene recipe. Native attribute precision is recorded explicitly.
    """
    directory = Path(directory).resolve()
    model = directory/"sector.glb"
    archive = directory/"sector.clm"
    receipt = directory/"native-assets.json"
    source_hash = sha256(model)
    if receipt.exists() and archive.exists():
        old = json.loads(receipt.read_text())
        if old["glb_sha256"]==source_hash and sha256(archive)==old["meshlets_sha256"]:
            return old
    gltf = trimesh.load(model,force="scene",process=False)
    # glTF east/up/minus-north -> renderer east/north/up.
    axis = np.array([[1.,0,0],[0,0,-1],[0,1,0]])
    scene = Scene()
    mapping = {}
    node_records = []
    layout = json.loads((directory/"glb-part-layout.json").read_text())
    with Meshlets(archive) as writer:
        for component,node in enumerate(sorted(gltf.graph.nodes_geometry)):
            transform,name = gltf.graph[node]
            mesh = gltf.geometry[name]
            material = mesh.visual.material
            material_name = material.name or "unnamed"
            if material_name not in mapping:
                texture = directory/"textures"/(material_name+"_color.pfm")
                normal = directory/"textures"/(material_name+"_normal.pfm")
                roughness = directory/"textures"/(material_name+"_roughness.pfm")
                if not texture.exists():
                    raise ValueError("Missing original linear material atlas: "+str(texture))
                rough = float(getattr(material,"roughnessFactor",.8) or .8)
                base = scene.material("plastic",(1,1,1),rough,ior=1.5,texture=texture)
                if roughness.exists():
                    scene.emit("roughness_texture",base,json.dumps(str(roughness)),1,1,1)
                wrapper = scene.material("normalmap",texture=normal)
                scene.emit("nested",wrapper,base,-1,.5)
                mapping[material_name] = wrapper
            v = (mesh.vertices@transform[:3,:3].T+transform[:3,3])@axis.T
            normals = (mesh.vertex_normals@transform[:3,:3].T)@axis.T
            normals /= np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
            uv = np.asarray(mesh.visual.uv,float)
            tint = np.ones((len(v),3))
            attrs = getattr(mesh.visual,"vertex_attributes",{})
            if "color" in attrs:
                tint = np.asarray(attrs["color"])[:,:3].astype(float)/255
            # The GEO export folds atlas gain into the glTF image. The native
            # pipeline retains the original linear PFM, so restore that gain.
            tint *= np.asarray(layout[name]["tint_gain"])
            components = np.zeros(len(mesh.faces),np.int64)
            for span in layout[name]["parts"]:
                a = span["first_face"]
                components[a:a+span["face_count"]] = span["component"]
            if np.any(components==0):
                raise ValueError("Lost GEO component span in batched GLB")
            for start in range(0,len(mesh.faces),24000):
                f = mesh.faces[start:start+24000]
                records = np.zeros((len(f),36),"<f4")
                records[:,:9] = v[f].reshape(-1,9)
                records[:,9:18] = normals[f].reshape(-1,9)
                records[:,18] = mapping[material_name]
                records[:,19] = components[start:start+len(f)]
                records[:,20:26] = uv[f].reshape(-1,6)
                records[:,26:35] = tint[f].reshape(-1,9)
                writer.add(records)
            node_records.append({"component":component+1,"source_part":name,
                                 "triangles":len(mesh.faces),"material":material_name,
                                 "GEO_component_count":len(layout[name]["parts"])})
    materials = directory/"materials.cys"
    scene.save(materials)
    result = {"schema":"cybr-ucsb-native-assets/1", "glb_sha256":source_hash,
              "meshlets_sha256":sha256(archive), "triangles":writer.triangles,
              "meshlets":writer.meshlets,"vertices":writer.vertices,"nodes":node_records,
              "material_count":len(mapping), "glb_to_native_axes":"x,-z,y",
              "mesh_precision":"float32 local metres; UTM origin preserved in coordinate metadata",
              "image_generation_used":False}
    write_json(receipt,result)
    print(f"LIGHT assets: {writer.triangles:,} triangles / {writer.meshlets:,} meshlets",flush=True)
    return result


def scene_for(directory,view,width=1280,height=800,spp=64,threads=8,bands=8,camera=None,seed=20260930):
    directory = Path(directory).resolve()
    if view not in VIEWS:
        raise ValueError("Unknown camera view")
    s = Scene()
    # material IDs are already fixed inside the meshlets file.
    s.lines = [line for line in (directory/"materials.cys").read_text().splitlines()
               if line and not line.startswith("#")]
    # Rebase relative texture paths from material file to absolute while writing
    # scenes in a frame subdirectory; Scene.save will make them portable again.
    import re
    s.lines = [re.sub(r'"([^"]+)"',lambda m:json.dumps(str((directory/m.group(1)).resolve())),line) for line in s.lines]
    s.settings(width,height,spp,7,threads,bands,seed,1.05)
    origin,target,fov,up,ortho,scale = VIEWS[view] if camera is None else camera
    s.camera(origin,target,up,fov,orthographic=ortho,scale=scale)
    daylight(s,directory/"textures")
    s.mesh(directory/"sector.clm")
    return s


def render_view(directory,view="overview",width=1280,height=800,spp=64,threads=8,bands=8,output=None):
    prepare(directory)
    directory = Path(directory)
    output = Path(output) if output else directory/view
    s = scene_for(directory,view,width,height,spp,threads,bands)
    report = render(s,output,metadata={
        "generator":"CYBR UCSB 0.1", "renderer":"native CYBR LIGHT spectral CPU",
        "view":view, "source_layout_invented":False,"image_generation_used":False,
        "coordinate_provenance":"geometry-provenance.json", "source_provenance":"data/raw/manifest.json",
        "scope":"geographically anchored massing; unmeasured architectural/botanical dimensions are explicit proxies"})
    report["output_hashes"] = {p.name:sha256(p) for p in output.parent.glob(output.name+"*")
                               if p.is_file() and p.suffix in (".png",".pfm",".exr",".cys")}
    write_json(output.with_suffix(".json"),report)
    print(f"rendered {output.with_suffix('.png')}",flush=True)
    return report


def film(directory,output,frames=48,fps=12,width=640,height=400,spp=12,threads=8,bands=4):
    if frames<2 or fps<1 or width%2 or height%2:
        raise ValueError("Video requires >=2 frames and even dimensions")
    directory = Path(directory)
    output = Path(output)
    prepare(directory)
    frame_directory = directory/"film-frames"
    frame_directory.mkdir(parents=True,exist_ok=True)
    records = []
    target = np.array([180,-30,15])
    for index in range(frames):
        angle = math.radians(-124+35*index/(frames-1))
        origin = target+np.array([1700*math.cos(angle),1700*math.sin(angle),1450])
        camera = (origin,target,44,(0,0,1),False,1)
        stem = frame_directory/f"{index:04d}"
        s = scene_for(directory,"overview",width,height,spp,threads,bands,camera,seed=20260930+index)
        frame_key = {"camera":list(map(float,origin)),"target":target.tolist(),"width":width,"height":height,
                     "spp":spp,"bands":bands,"meshlets_sha256":sha256(directory/"sector.clm")}
        existing = json.loads(stem.with_suffix(".json").read_text()) if stem.with_suffix(".json").exists() else {}
        if existing.get("frame_key")!=frame_key or not stem.with_suffix(".png").exists() or not stem.with_suffix(".pfm").exists():
            record = render(s,stem,metadata={"frame":index,"frame_key":frame_key,"image_generation_used":False})
        else:
            record = existing
        records.append({"frame":index,"camera":origin.tolist(),"film_sha256":sha256(stem.with_suffix(".pfm")),
                        "png_sha256":sha256(stem.with_suffix(".png")),"engine_sha256":record["engine_source_sha256"]})
        print(f"video frame {index+1}/{frames}",flush=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary = output.with_name(output.stem+".partial.mp4")
    subprocess.run(["ffmpeg","-y","-v","error","-framerate",str(fps),"-i",str(frame_directory/"%04d.png"),
                    "-frames:v",str(frames),"-c:v","libx264","-crf","17","-pix_fmt","yuv420p",
                    "-movflags","+faststart",str(temporary)],check=True)
    subprocess.run(["ffmpeg","-v","error","-xerror","-i",str(temporary),"-f","null","-"],check=True)
    probe = json.loads(subprocess.check_output(["ffprobe","-v","error","-count_frames","-select_streams","v:0",
        "-show_entries","stream=width,height,nb_read_frames,r_frame_rate","-of","json",str(temporary)]))
    if int(probe["streams"][0]["nb_read_frames"])!=frames:
        raise ValueError("Encoded video frame count mismatch")
    temporary.replace(output)
    result = {"renderer":"native CYBR LIGHT", "frames":frames,"fps":fps,"seconds":frames/fps,
              "resolution":[width,height],"spp":spp,"bands":bands,"image_generation_used":False,
              "frame_interpolation_used":False,"records":records,"probe":probe,"video_sha256":sha256(output)}
    write_json(output.with_suffix(".json"),result)
    return result
