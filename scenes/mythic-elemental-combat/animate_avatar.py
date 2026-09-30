#!/usr/bin/env python3
"""Blender-side rig animation and geometry bake for CYBR mythic combat.

Run with:
  blender --background --factory-startup --python animate_avatar.py -- --avatar assets/CesiumMan.glb

The animation is authored here from pose keys. It does not contain or retarget
proprietary God of War animation data. The intent is a similar *weight class*:
large anticipation, committed root motion, delayed follow-through, and violent
weapon arcs.

CYBR LIGHT currently supports translating geometry motion but not skeletal
skinning. We therefore evaluate the skinned Blender mesh per frame and export
explicit deformed OBJ geometry. CYBR LIGHT still performs the actual spectral
lighting/path-tracing pass.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"

RIGHT_HAND = "Skeleton_arm_joint_R__3_"
LEFT_HAND = "Skeleton_arm_joint_L__2_"
CONTROL_BONES = [
    "Skeleton_torso_joint_1", "Skeleton_torso_joint_2", "torso_joint_3",
    "Skeleton_neck_joint_1", "Skeleton_neck_joint_2",
    "Skeleton_arm_joint_R", "Skeleton_arm_joint_R__2_", RIGHT_HAND,
    "Skeleton_arm_joint_L__4_", "Skeleton_arm_joint_L__3_", LEFT_HAND,
    "leg_joint_R_1", "leg_joint_R_2", "leg_joint_R_3", "leg_joint_R_5",
    "leg_joint_L_1", "leg_joint_L_2", "leg_joint_L_3", "leg_joint_L_5",
]

MOVES = [
    {"name": "frost_cleave",  "start": 16,  "end": 66,  "element": "frost"},
    {"name": "flame_slam",    "start": 75,  "end": 128, "element": "fire"},
    {"name": "storm_spin",    "start": 138, "end": 198, "element": "lightning"},
    {"name": "earth_breaker", "start": 208, "end": 258, "element": "earth"},
    {"name": "tidal_recall",  "start": 270, "end": 330, "element": "water"},
]


def parse_args():
    argv = sys.argv[sys.argv.index("--")+1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--avatar", type=Path, default=HERE / "assets" / "CesiumMan.glb")
    p.add_argument("--out", type=Path, default=BUILD)
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--step", type=int, default=1, help="Bake every Nth frame for quick tests")
    p.add_argument("--no-glb", action="store_true")
    return p.parse_args(argv)


def deg(v):
    return tuple(math.radians(float(x)) for x in v)


def to_cybr(v: Vector):
    """Blender Z-up -> CYBR LIGHT Y-up, preserving handedness."""
    return [float(v.x), float(v.z), float(-v.y)]


def reset_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.actions, bpy.data.meshes, bpy.data.curves, bpy.data.materials):
        # Do not mutate during iteration.
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def import_avatar(path: Path):
    if not path.exists():
        raise FileNotFoundError(f"Missing avatar: {path}. Run fetch_avatar.py first.")
    bpy.ops.import_scene.gltf(filepath=str(path))
    armatures = [o for o in bpy.context.scene.objects if o.type == "ARMATURE"]
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not armatures or not meshes:
        raise RuntimeError("Imported glTF did not contain an armature and mesh")
    arm = armatures[0]
    arm.animation_data_clear()
    for obj in meshes:
        obj.animation_data_clear()
    missing = [name for name in CONTROL_BONES if name not in arm.pose.bones]
    if missing:
        raise RuntimeError(f"Rig mapping failed; missing bones: {missing}")
    arm.name = "CYBR_Combat_Rig"
    for obj in meshes:
        obj.name = "CYBR_Avatar"
    return arm, meshes


def create_axe(arm):
    # Bone-parented empty establishes a stable local weapon frame.
    root = bpy.data.objects.new("CYBR_Axe_Root", None)
    bpy.context.collection.objects.link(root)
    root.parent = arm
    root.parent_type = "BONE"
    root.parent_bone = RIGHT_HAND
    root.location = (0.02, 0.0, 0.0)
    root.rotation_mode = "XYZ"
    root.rotation_euler = deg((0, 90, 0))

    weapon = []

    def parent_local(obj, location, rotation=(0,0,0), scale=(1,1,1)):
        obj.parent = root
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.location = location
        obj.rotation_euler = deg(rotation)
        obj.scale = scale
        weapon.append(obj)
        return obj

    # Long haft.
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=.032, depth=1.36)
    handle = parent_local(bpy.context.object, (0,0,.24))
    handle.name = "Axe_Haft"

    # Pommel.
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=.055)
    parent_local(bpy.context.object, (0,0,-.47), scale=(.8,.8,1.2)).name = "Axe_Pommel"

    # Head: intentionally broad, asymmetrical silhouette.
    bpy.ops.mesh.primitive_cube_add(size=1)
    head = parent_local(bpy.context.object, (.0,0,.91), rotation=(0,8,0), scale=(.33,.075,.20))
    head.name = "Axe_Head"

    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=.27, radius2=.10, depth=.34)
    blade = parent_local(bpy.context.object, (.28,0,.92), rotation=(0,90,0), scale=(1,.42,1))
    blade.name = "Axe_Blade"

    # Local sampling points used by CYBR ELEMENTS.
    root["cybr_head_local"] = [0.33, 0.0, 0.94]
    root["cybr_tail_local"] = [0.0, 0.0, -0.48]
    return root, weapon


def set_pose_key(arm, frame, root=(0,0,0), yaw=0.0, joints=None):
    joints = joints or {}
    arm.location = Vector(root)
    arm.rotation_mode = "XYZ"
    arm.rotation_euler = (0, 0, math.radians(yaw))
    arm.keyframe_insert("location", frame=frame)
    arm.keyframe_insert("rotation_euler", frame=frame)
    for name in CONTROL_BONES:
        pb = arm.pose.bones[name]
        pb.rotation_mode = "XYZ"
        pb.location = (0,0,0)
        pb.scale = (1,1,1)
        pb.rotation_euler = deg(joints.get(name, (0,0,0)))
        pb.keyframe_insert("rotation_euler", frame=frame)
        pb.keyframe_insert("location", frame=frame)


def J(**kwargs):
    """Short bone-name aliases for readable choreography."""
    alias = {
        "pelvis":"Skeleton_torso_joint_1", "spine":"Skeleton_torso_joint_2", "chest":"torso_joint_3",
        "neck":"Skeleton_neck_joint_1",
        "r_shoulder":"Skeleton_arm_joint_R", "r_elbow":"Skeleton_arm_joint_R__2_", "r_hand":RIGHT_HAND,
        "l_shoulder":"Skeleton_arm_joint_L__4_", "l_elbow":"Skeleton_arm_joint_L__3_", "l_hand":LEFT_HAND,
        "r_hip":"leg_joint_R_1", "r_knee":"leg_joint_R_2", "r_ankle":"leg_joint_R_3",
        "l_hip":"leg_joint_L_1", "l_knee":"leg_joint_L_2", "l_ankle":"leg_joint_L_3",
    }
    return {alias[k]:v for k,v in kwargs.items()}


def author_choreography(arm):
    # Neutral.
    set_pose_key(arm, 1)
    set_pose_key(arm, 12, joints=J(chest=(0,0,-4), r_shoulder=(5,0,-8), l_shoulder=(-4,0,7)))

    # FROST CLEAVE: low load -> deep backswing -> explosive horizontal cut.
    set_pose_key(arm,16, root=(0,0,0), yaw=-8, joints=J(
        pelvis=(0,0,-8), chest=(4,0,-18), r_shoulder=(-24,18,-52), r_elbow=(8,0,-34),
        l_shoulder=(10,-10,18), l_elbow=(0,0,28), r_hip=(0,0,-12), l_hip=(0,0,10)))
    set_pose_key(arm,29, root=(-.06,-.06,-.03), yaw=-38, joints=J(
        pelvis=(0,0,-24), spine=(8,0,-18), chest=(6,0,-38),
        r_shoulder=(-42,22,-88), r_elbow=(10,-8,-52), r_hand=(0,0,-18),
        l_shoulder=(18,-12,38), l_elbow=(-5,0,48),
        r_hip=(0,0,-28), r_knee=(0,0,24), l_hip=(0,0,20)))
    set_pose_key(arm,42, root=(.13,.12,.01), yaw=48, joints=J(
        pelvis=(0,0,30), spine=(-5,0,28), chest=(-8,0,55),
        r_shoulder=(18,-10,86), r_elbow=(-4,6,20), r_hand=(0,0,20),
        l_shoulder=(-18,8,-34), l_elbow=(4,0,18),
        r_hip=(0,0,24), l_hip=(0,0,-25), l_knee=(0,0,16)))
    set_pose_key(arm,55, root=(.20,.20,0), yaw=72, joints=J(
        pelvis=(0,0,38), chest=(-5,0,42), r_shoulder=(12,-8,62), r_elbow=(0,0,10),
        l_shoulder=(-10,6,-22), r_hip=(0,0,16), l_hip=(0,0,-20)))
    set_pose_key(arm,66, root=(.08,.08,0), yaw=15)

    # FLAME SLAM: two-stage overhead lift, body compression, floor contact.
    set_pose_key(arm,75, root=(.08,.08,0), yaw=8, joints=J(chest=(0,0,6), r_shoulder=(-10,0,-20)))
    set_pose_key(arm,92, root=(.03,-.02,0), yaw=-10, joints=J(
        pelvis=(-8,0,-6), spine=(-18,0,-4), chest=(-22,0,-8),
        r_shoulder=(-112,4,-18), r_elbow=(-40,0,-12), r_hand=(0,0,-8),
        l_shoulder=(-92,-8,16), l_elbow=(-48,0,18),
        r_hip=(18,0,-8), l_hip=(18,0,8)))
    set_pose_key(arm,107, root=(.10,.18,.03), yaw=4, joints=J(
        pelvis=(18,0,3), spine=(25,0,4), chest=(30,0,8),
        r_shoulder=(88,-8,12), r_elbow=(50,0,8), r_hand=(10,0,0),
        l_shoulder=(58,8,-12), l_elbow=(35,0,-16),
        r_hip=(-30,0,-10), r_knee=(38,0,12), l_hip=(-26,0,10), l_knee=(34,0,-10)))
    set_pose_key(arm,116, root=(.14,.29,-.16), yaw=6, joints=J(
        pelvis=(34,0,4), spine=(32,0,6), chest=(28,0,10),
        r_shoulder=(110,-6,12), r_elbow=(26,0,10),
        l_shoulder=(76,8,-14), l_elbow=(28,0,-18),
        r_hip=(-48,0,-12), r_knee=(68,0,18), l_hip=(-42,0,12), l_knee=(60,0,-15)))
    set_pose_key(arm,128, root=(.08,.13,0), yaw=4)

    # STORM SPIN: committed full-body 360 with weapon extended.
    set_pose_key(arm,138, root=(.08,.13,0), yaw=0, joints=J(
        pelvis=(0,0,-12), chest=(0,0,-20), r_shoulder=(-20,8,-66), r_elbow=(4,0,-24),
        l_shoulder=(8,-4,35), l_elbow=(0,0,20)))
    for frame,yaw in ((153,90),(168,180),(183,270),(195,360)):
        set_pose_key(arm,frame, root=(.08+.04*math.sin(math.radians(yaw)),.13+.04*math.cos(math.radians(yaw)),0),
            yaw=yaw, joints=J(
                pelvis=(0,0,20), chest=(0,0,42), r_shoulder=(8,-4,88), r_elbow=(0,0,6),
                l_shoulder=(-8,4,-42), l_elbow=(0,0,12),
                r_hip=(0,0,12), l_hip=(0,0,-12)))
    set_pose_key(arm,198, root=(.08,.13,0), yaw=360)

    # EARTH BREAKER: raised side load -> lunging diagonal floor smash.
    set_pose_key(arm,208, root=(.08,.13,0), yaw=8, joints=J(
        chest=(0,0,-12), r_shoulder=(-28,12,-48), r_elbow=(8,0,-28)))
    set_pose_key(arm,226, root=(-.04,.02,.03), yaw=-28, joints=J(
        pelvis=(-12,0,-18), spine=(-20,0,-18), chest=(-28,0,-34),
        r_shoulder=(-96,14,-54), r_elbow=(-36,0,-44), r_hand=(-8,0,-8),
        l_shoulder=(-38,-10,28), l_elbow=(-28,0,24),
        r_hip=(18,0,-22), l_hip=(16,0,18)))
    set_pose_key(arm,243, root=(.22,.34,-.18), yaw=28, joints=J(
        pelvis=(36,0,22), spine=(30,0,24), chest=(26,0,36),
        r_shoulder=(112,-10,52), r_elbow=(18,0,22), r_hand=(12,0,6),
        l_shoulder=(72,8,-20), l_elbow=(20,0,-18),
        r_hip=(-50,0,-14), r_knee=(74,0,20), l_hip=(-32,0,18), l_knee=(54,0,-14)))
    set_pose_key(arm,250, root=(.24,.36,-.20), yaw=31, joints=J(
        pelvis=(40,0,24), chest=(30,0,38), r_shoulder=(118,-8,56), r_elbow=(12,0,18),
        r_hip=(-54,0,-14), r_knee=(78,0,20), l_hip=(-35,0,18), l_knee=(58,0,-14)))
    set_pose_key(arm,258, root=(.10,.16,0), yaw=8)

    # TIDAL RECALL: retreating scoop -> vertical launch -> hard weapon return.
    set_pose_key(arm,270, root=(.10,.16,0), yaw=8, joints=J(
        chest=(4,0,14), r_shoulder=(18,-6,35), r_elbow=(0,0,24)))
    set_pose_key(arm,288, root=(-.08,-.02,-.05), yaw=-36, joints=J(
        pelvis=(12,0,-18), chest=(18,0,-35), r_shoulder=(48,8,-82), r_elbow=(22,0,-36),
        l_shoulder=(-12,-8,36), l_elbow=(0,0,30),
        r_hip=(-20,0,-18), r_knee=(32,0,14), l_hip=(-8,0,18)))
    set_pose_key(arm,307, root=(.16,.27,.08), yaw=26, joints=J(
        pelvis=(-22,0,18), spine=(-18,0,16), chest=(-30,0,35),
        r_shoulder=(-108,-8,48), r_elbow=(-38,0,22), r_hand=(-8,0,10),
        l_shoulder=(-70,8,-26), l_elbow=(-24,0,-12),
        r_hip=(24,0,14), l_hip=(20,0,-14)))
    set_pose_key(arm,322, root=(.14,.22,.02), yaw=42, joints=J(
        chest=(-10,0,28), r_shoulder=(-28,-4,68), r_elbow=(-10,0,12),
        l_shoulder=(-20,4,-26), l_elbow=(-4,0,-10)))
    set_pose_key(arm,330, root=(.08,.12,0), yaw=12)

    # Make authored key spacing control acceleration directly; no Bezier overshoot.
    if arm.animation_data and arm.animation_data.action:
        for fc in arm.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "BEZIER"
                kp.handle_left_type = "AUTO_CLAMPED"
                kp.handle_right_type = "AUTO_CLAMPED"
    for pb in arm.pose.bones:
        if pb.id_data.animation_data and pb.id_data.animation_data.action:
            for fc in pb.id_data.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.handle_left_type = "AUTO_CLAMPED"
                    kp.handle_right_type = "AUTO_CLAMPED"


def move_for_frame(frame):
    for m in MOVES:
        if m["start"] <= frame <= m["end"]:
            phase=(frame-m["start"])/max(1,m["end"]-m["start"])
            return m["name"], float(phase)
    return "recovery", 0.0


def bone_world(arm, name):
    pb=arm.pose.bones[name]
    return arm.matrix_world @ pb.tail


def object_local_point_world(obj, local):
    return obj.matrix_world @ Vector(local)


def evaluated_obj_data(obj, depsgraph):
    eo=obj.evaluated_get(depsgraph)
    mesh=eo.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
    mesh.calc_loop_triangles()
    return eo,mesh


def export_combined_obj(objects, path: Path, depsgraph):
    path.parent.mkdir(parents=True,exist_ok=True)
    records=[]
    vertex_offset=0
    with path.open("w",encoding="utf-8") as out:
        out.write("# Explicit evaluated geometry from Blender; CYBR LIGHT input\n")
        for obj in objects:
            eo,mesh=evaluated_obj_data(obj,depsgraph)
            normal_matrix=eo.matrix_world.to_3x3().inverted().transposed()
            verts=[]
            norms=[]
            for vert in mesh.vertices:
                wp=eo.matrix_world @ vert.co
                wn=(normal_matrix @ vert.normal).normalized()
                verts.append(to_cybr(wp));norms.append(to_cybr(wn))
            out.write(f"o {obj.name}\n")
            for v in verts: out.write(f"v {v[0]:.9f} {v[1]:.9f} {v[2]:.9f}\n")
            for n in norms: out.write(f"vn {n[0]:.9f} {n[1]:.9f} {n[2]:.9f}\n")
            tri_count=0
            for tri in mesh.loop_triangles:
                ids=[int(i)+1+vertex_offset for i in tri.vertices]
                out.write("f "+" ".join(f"{i}//{i}" for i in ids)+"\n")
                tri_count+=1
            records.append({"object":obj.name,"vertices":len(mesh.vertices),"triangles":tri_count})
            vertex_offset+=len(mesh.vertices)
            eo.to_mesh_clear()
    return records


def write_cues(out: Path):
    cues=[]
    for m in MOVES:
        cues.append({"element":m["element"],"start":m["start"],"end":m["end"],"move":m["name"]})
        if m["name"]=="storm_spin":
            cues.append({"element":"air","start":m["start"],"end":m["end"],"move":m["name"]})
    (out/"element_cues.json").write_text(json.dumps({"cues":cues},indent=2))


def main():
    args=parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/"avatar").mkdir(exist_ok=True)
    (args.out/"weapon").mkdir(exist_ok=True)

    reset_scene()
    arm,avatar_meshes=import_avatar(args.avatar)
    axe_root,weapon_meshes=create_axe(arm)
    author_choreography(arm)

    scene=bpy.context.scene
    scene.render.fps=args.fps
    scene.frame_start=1;scene.frame_end=330

    # Preserve an inspectable animated GLB in addition to the per-frame path-trace bake.
    if not args.no_glb:
        bpy.ops.object.select_all(action="DESELECT")
        arm.select_set(True)
        for o in avatar_meshes+weapon_meshes:o.select_set(True)
        bpy.context.view_layer.objects.active=arm
        bpy.ops.export_scene.gltf(
            filepath=str(args.out/"mythic_combat_animated.glb"),
            export_format="GLB", export_animations=True, use_selection=True,
        )

    frames=[]
    geometry_receipts={}
    prev_head=None
    for frame in range(scene.frame_start,scene.frame_end+1,args.step):
        scene.frame_set(frame)
        depsgraph=bpy.context.evaluated_depsgraph_get()
        depsgraph.update()
        move,phase=move_for_frame(frame)
        root=to_cybr(arm.matrix_world.translation)
        right=to_cybr(bone_world(arm,RIGHT_HAND))
        left=to_cybr(bone_world(arm,LEFT_HAND))
        head=to_cybr(object_local_point_world(axe_root,axe_root["cybr_head_local"]))
        tail=to_cybr(object_local_point_world(axe_root,axe_root["cybr_tail_local"]))
        frames.append({
            "frame":frame,"time":frame/args.fps,"move":move,"phase":phase,
            "root":root,"right_hand":right,"left_hand":left,"axe_head":head,"axe_tail":tail,
        })
        avatar_path=args.out/"avatar"/f"frame_{frame:04d}.obj"
        weapon_path=args.out/"weapon"/f"frame_{frame:04d}.obj"
        geometry_receipts[str(frame)]={
            "avatar":export_combined_obj(avatar_meshes,avatar_path,depsgraph),
            "weapon":export_combined_obj(weapon_meshes,weapon_path,depsgraph),
        }
        prev_head=head
        print("BAKED",frame,move,flush=True)

    trajectory={
        "version":1,"fps":args.fps,"frame_start":scene.frame_start,"frame_end":scene.frame_end,
        "coordinate_system":"CYBR LIGHT: +Y up; converted from Blender +Z up as (x,z,-y)",
        "avatar":"CesiumMan / CC BY 4.0","moves":MOVES,"frames":frames,
    }
    (args.out/"trajectory.json").write_text(json.dumps(trajectory,indent=2))
    (args.out/"geometry_receipts.json").write_text(json.dumps(geometry_receipts,indent=2))
    write_cues(args.out)
    (args.out/"choreography.json").write_text(json.dumps({
        "style":"original heavy mythic melee choreography",
        "proprietary_animation_data":False,
        "moves":MOVES,
        "notes":[
            "Large anticipation/contact/recovery windows are intentional.",
            "Root translation/yaw and upper/lower body pose are keyed together.",
            "Per-frame skinned meshes are explicit CYBR LIGHT geometry inputs."
        ]
    },indent=2))
    print(json.dumps({"frames":len(frames),"out":str(args.out.resolve())},indent=2))


if __name__=="__main__":
    main()
