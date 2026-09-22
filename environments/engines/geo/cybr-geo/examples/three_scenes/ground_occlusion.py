"""Conservative dry-ground certificate for zero reflected-sun contributions.

A complete, explicitly checked height-field part proves that a candidate water
point is below opaque terrain. Native interval bounds enclose every accepted
reflection root and require its sun ray to cross that terrain before leaving its
domain. This is an occlusion rejection, not a substitute lighting cache.
"""
from pathlib import Path
import hashlib,json,struct
import numpy as np


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()


def build_ground_certificate(folder:Path)->Path:
    folder=Path(folder);source=folder/'assembly/meshes.npz'
    scene=json.loads((folder/'assembly/scene.json').read_text())
    geometry=json.loads((folder/'geometry.json').read_text())
    certificate=folder/'ground_occlusion.bin';report_path=certificate.with_suffix('.json')
    identity={'source_assembly_sha256':sha(source),'source_scene_sha256':sha(folder/'assembly/scene.json'),
              'source_native_mesh_sha256':geometry['mesh_sha256'],'generator_sha256':sha(Path(__file__))}
    if certificate.is_file() and report_path.is_file():
        old=json.loads(report_path.read_text())
        if all(old.get(k)==v for k,v in identity.items()) and old.get('certificate_sha256')==sha(certificate):return certificate
    if scene.get('units')!='mm':raise ValueError('Expected metre-normalized CYBR GEO input')
    part=scene['parts'][0]
    if part['material'] in (3,6,7,9):raise ValueError('The terrain certificate requires an opaque part')
    with np.load(source,allow_pickle=False) as z:
        vertices=(z[part['key']+'_vertices']*.001).astype('<f4')
        nx=int(np.count_nonzero(vertices[:,1]==vertices[0,1]));nv=len(vertices)
        if nx<2 or nv%nx:raise ValueError('First part is not a regular complete height field')
        ny=nv//nx;grid=vertices.reshape(ny,nx,3);x=grid[0,:,0];y=grid[:,0,1]
        if not (np.all(np.diff(x)>0) and np.all(np.diff(y)>0)):raise ValueError('Height-field axes must increase')
        if not np.array_equal(grid[:,:,0],np.broadcast_to(x,(ny,nx))) or not np.array_equal(grid[:,:,1],np.broadcast_to(y[:,None],(ny,nx))):raise ValueError('Terrain has non-grid XY coordinates')
        if not np.allclose(np.diff(x),np.diff(x).mean(),rtol=0,atol=3e-5) or not np.allclose(np.diff(y),np.diff(y).mean(),rtol=0,atol=3e-5):raise ValueError('Nonuniform spacing needs a different certificate')
        if not np.isfinite(vertices).all():raise ValueError('Nonfinite terrain positions')
        cells=(nx-1)*(ny-1);faces=z[part['key']+'_faces']
        if faces.shape!=(2*cells,3):raise ValueError('Terrain contains holes or extra faces')
        # Verify every triangle, not just a random subset or the vertex count.
        for first in range(0,cells,65536):
            ids=np.arange(first,min(cells,first+65536));a=(ids//(nx-1))*nx+ids%(nx-1)
            if not np.array_equal(faces[first:first+len(ids)],np.stack([a,a+1,a+nx+1],axis=1)):raise ValueError('First triangle topology differs')
            if not np.array_equal(faces[cells+first:cells+first+len(ids)],np.stack([a,a+nx+1,a+nx],axis=1)):raise ValueError('Second triangle topology differs')
        h=grid[:,:,2]
        cell_min=np.minimum(np.minimum(h[:-1,:-1],h[1:,:-1]),np.minimum(h[:-1,1:],h[1:,1:]))
        minimum=float(h.min());maximum=float(h.max())
        x0,x1,y0,y1=map(float,[x[0],x[-1],y[0],y[-1]])
        with certificate.open('wb') as f:
            f.write(struct.pack('<4sII6f',b'GOC1',nx,ny,x0,x1,y0,y1,minimum,maximum))
            f.write(cell_min.astype('<f4').tobytes())
    report={'scope':__doc__,**identity,'terrain_part':part['name'],'grid_vertices':[nx,ny],
            'every_grid_triangle_checked':True,'triangles_checked':2*cells,
            'cell_min_is_bound_for_both_linear_triangles':True,'bounds_m':[x0,x1,y0,y1,minimum,maximum],
            'certificate_sha256':sha(certificate)}
    report_path.write_text(json.dumps(report,indent=2)+'\n');return certificate

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('scene_directory',type=Path)
    a=p.parse_args();print(build_ground_certificate(a.scene_directory))
