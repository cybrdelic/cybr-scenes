"""CYBR GEO core contract vendored from cybrdelic/cybr-geo.
The scene builder uses this exact Part/Assembly data model for named mesh geometry.
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any
import hashlib, json, re
import numpy as np
import trimesh

@dataclass(frozen=True)
class Material:
    name: str = "Machined alloy"
    color: tuple[float, float, float] = (.48, .50, .53)
    metal: float = .9
    rough: float = .28
    ior: float = 1.5
    coat: float = 0.0
    coat_rough: float = .2
    anisotropy: float = 0.0
    anisotropy_rotation: float = 0.0
    opacity: float = 1.0
    microfinish: str = 'none'
    material_source: str = ''

@dataclass
class Part:
    name: str
    vertices: np.ndarray
    faces: np.ndarray
    normals: np.ndarray
    material: int = 0
    group: str = "assembly"
    explode: np.ndarray = field(default_factory=lambda: np.zeros(3))
    role: str = "Author-created geometry; not qualified manufacturing CAD"
    motion: str = "fixed"
    center: np.ndarray = field(default_factory=lambda: np.zeros(3))
    metadata: dict[str, Any] = field(default_factory=dict)
    def __post_init__(self):
        self.vertices=np.asarray(self.vertices,dtype=np.float64)
        self.faces=np.asarray(self.faces,dtype=np.int64)
        self.normals=np.asarray(self.normals,dtype=np.float64)
        self.explode=np.asarray(self.explode,dtype=float)
        self.center=np.asarray(self.center,dtype=float)
        if not self.name or not re.fullmatch(r"[A-Za-z0-9_.-]+",self.name): raise ValueError(f"Unsafe part name: {self.name!r}")
        if self.vertices.ndim!=2 or self.vertices.shape[1]!=3 or not len(self.vertices): raise ValueError(f"{self.name}: nonempty Nx3 vertices required")
        if self.faces.ndim!=2 or self.faces.shape[1]!=3 or not len(self.faces): raise ValueError(f"{self.name}: nonempty Mx3 triangle faces required")
        if self.normals.shape!=self.vertices.shape: raise ValueError(f"{self.name}: vertex normal count mismatch")
        if not np.isfinite(self.vertices).all() or not np.isfinite(self.normals).all(): raise ValueError(f"{self.name}: nonfinite geometry")
        if self.faces.min()<0 or self.faces.max()>=len(self.vertices): raise ValueError(f"{self.name}: invalid face indices")
    @property
    def bounds(self): return np.array([self.vertices.min(axis=0),self.vertices.max(axis=0)])

@dataclass
class Assembly:
    name: str
    parts: list[Part]
    materials: list[Material] = field(default_factory=lambda:[Material()])
    metadata: dict[str,Any] = field(default_factory=dict)
    cad: dict[str,Any] = field(default_factory=dict,repr=False)
    def __post_init__(self):
        names=[p.name for p in self.parts]
        if not names or len(names)!=len(set(names)): raise ValueError("Assembly needs nonempty, unique part names")
        for p in self.parts:
            if not 0<=p.material<len(self.materials): raise ValueError(f"{p.name}: material index outside palette")
    @property
    def bounds(self):
        return np.array([np.min([p.bounds[0] for p in self.parts],axis=0),np.max([p.bounds[1] for p in self.parts],axis=0)])
    def save(self,folder):
        root=Path(folder);root.mkdir(parents=True,exist_ok=True);payload={};entries=[]
        for i,p in enumerate(self.parts):
            key=f"p{i:05d}"
            for attr in ("vertices","faces","normals"): payload[f"{key}_{attr}"]=getattr(p,attr)
            entries.append(dict(key=key,name=p.name,material=p.material,group=p.group,explode=p.explode.tolist(),center=p.center.tolist(),role=p.role,motion=p.motion,metadata=p.metadata))
        np.savez_compressed(root/'meshes.npz',**payload)
        meta=dict(schema="cybrgeo.scene/1",name=self.name,units="mm",up="Z",materials=[asdict(m) for m in self.materials],parts=entries,metadata=self.metadata,meshes_sha256=hashlib.sha256((root/'meshes.npz').read_bytes()).hexdigest())
        (root/'scene.json').write_text(json.dumps(meta,indent=2)+'\n')
        return root/'scene.json'
    def export_glb(self,path,poses=None):
        sc=trimesh.Scene()
        for p in self.parts:
            m=self.materials[p.material]
            rgba=[*np.clip(np.power(m.color,1/2.2)*255,0,255).astype(np.uint8),255]
            material=trimesh.visual.material.PBRMaterial(name=m.name,baseColorFactor=rgba,metallicFactor=m.metal,roughnessFactor=m.rough)
            mesh=trimesh.Trimesh(p.vertices,p.faces,vertex_normals=p.normals,process=False)
            mesh.visual=trimesh.visual.TextureVisuals(material=material)
            sc.add_geometry(mesh,geom_name=p.name,node_name=p.name,transform=np.eye(4) if poses is None else poses.get(p.name,np.eye(4)))
        sc.apply_transform(np.array([[.001,0,0,0],[0,0,.001,0],[0,-.001,0,0],[0,0,0,1]]))
        sc.metadata.update(units="m",source_units="mm",provenance=self.metadata)
        Path(path).parent.mkdir(parents=True,exist_ok=True);sc.export(str(path))
    def validate(self):
        return dict(schema="cybrgeo.validation/1",name=self.name,part_count=len(self.parts),triangles=sum(len(p.faces) for p in self.parts),bounds_mm=self.bounds.tolist(),analytic_brep_parts=len(self.cad),unique_names=True,finite_vertices=True,valid_indices=True,note="Structural data checks only. No load, tolerance, interference or thermal certification.")

def translation(v):
    result=np.eye(4);result[:3,3]=v;return result

def rotation(angle,axis=(1,0,0),center=(0,0,0)):
    return trimesh.transformations.rotation_matrix(angle,axis,point=center)
