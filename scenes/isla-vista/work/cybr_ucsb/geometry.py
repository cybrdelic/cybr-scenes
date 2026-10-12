"""Retained CYBR source-polygon triangulation and deterministic IDs."""
import hashlib
import numpy as np
import trimesh
from shapely import constrained_delaunay_triangles

def stable_seed(value):
    return int.from_bytes(hashlib.sha256(value.encode()).digest()[:8], "little")

def triangulate_polygon(polygon, max_edge=None):
    triangles = list(constrained_delaunay_triangles(polygon).geoms)
    if not triangles:
        return np.empty((0,2)), np.empty((0,3),np.int64)
    corners = np.array([np.asarray(t.exterior.coords)[:3,:2] for t in triangles])
    vertices, indices = np.unique(corners.reshape(-1,2), axis=0, return_inverse=True)
    faces = indices.reshape(-1,3)
    cross = np.cross(np.c_[vertices[faces[:,1]]-vertices[faces[:,0]],np.zeros(len(faces))],
                     np.c_[vertices[faces[:,2]]-vertices[faces[:,0]],np.zeros(len(faces))])[:,2]
    faces[cross<0] = faces[cross<0][:,::-1]
    if max_edge:
        v, faces = trimesh.remesh.subdivide_to_size(np.c_[vertices,np.zeros(len(vertices))], faces,
                                                   max_edge=max_edge,max_iter=12)
        vertices = v[:,:2]
    total_area = np.sum(np.abs(np.cross(np.c_[vertices[faces[:,1]]-vertices[faces[:,0]],np.zeros(len(faces))],
                                        np.c_[vertices[faces[:,2]]-vertices[faces[:,0]],np.zeros(len(faces))])[:,2]))/2
    if not np.isclose(total_area, polygon.area, rtol=1e-7,atol=1e-6):
        raise ValueError("Constrained triangulation changed footprint area")
    return vertices, faces
