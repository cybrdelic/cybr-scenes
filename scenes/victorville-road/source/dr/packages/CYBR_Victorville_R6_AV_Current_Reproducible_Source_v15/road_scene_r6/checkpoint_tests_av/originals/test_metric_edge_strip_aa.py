"""CPU-only, no bpy, no scene I/O: exact clip/triangle sampler/join fixture."""
import numpy as np
from metric_edge_strip_aa import TriangleSampler,clip_source,build_strip,load_height,sample_original_height
from pathlib import Path


def fixture():
    # Irregular rows/width and alternating actual tessellation, with a mixture
    # of old quads and existing clipped triangles. Not a rectangular grid API.
    ys=np.array([-.1,.35,.85,1.4,2.1])
    rows=[[-3.2+.004*y,-3.12+.002*y,-3.02,-2.9] for y in ys]
    co=np.array([(x,y,.11+.004*x+.008*y) for y,row in zip(ys,rows) for x in row])
    triangles=[];tp=[];polygons=[]
    for j in range(len(ys)-1):
        for i in range(3):
            q=j*4+i;quad=[q,q+1,q+5,q+4]
            ts=[[q,q+1,q+5],[q,q+5,q+4]] if (i+j)%2 else [[q,q+1,q+4],[q+1,q+5,q+4]]
            if i==1 and j==2:
                for t in ts:tp.append(len(polygons));polygons.append(t);triangles.append(t)
            else:
                triangles.extend(ts);tp.extend([len(polygons)]*2);polygons.append(quad)
    return co,np.array(triangles,np.int32),np.array(tp,np.int32),polygons


def main():
    co,tri,tp,polys=fixture();sampler=TriangleSampler(co,tri)
    yy=np.linspace(0,2,41);assert np.max(abs(sampler.left_edge(yy)-(-3.2+.004*yy)))<1e-12
    rng=np.random.default_rng(27);xy=np.column_stack((rng.uniform(-3.16,-3.08,1000),rng.uniform(0,2,1000)))
    z=sampler.sample(co[:,2],xy);assert np.max(abs(z-(.11+.004*xy[:,0]+.008*xy[:,1])))<1e-12
    clip=clip_source(co,tri,tp,len(polys),(-3.3,-3.07,0,2))
    cc=np.concatenate((co,clip.additions));retained=np.concatenate((tri[np.isin(tp,clip.keep_polygons)],clip.triangles))
    centers=cc[retained,:2].mean(axis=1);assert not np.any((centers[:,0]>-3.3)&(centers[:,0]<-3.07)&(centers[:,1]>0)&(centers[:,1]<2))
    # Every point on the three join lines belongs to exact source triangle.
    for side in clip.boundary:assert np.max(abs(cc[side,2]-sampler.sample(co[:,2],cc[side,:2])))<1e-12
    height=load_height(Path(__file__).parents[3]/'materials-cloud-20261009/work/normal_fix/native4096/GeometryHeight.npy')
    edge=lambda y:sampler.left_edge(y)+.004*(.5+.5*np.sin(np.asarray(y)*2*np.pi/.007))
    strip=build_strip(sampler,np.arange(len(tri)),clip,co,height,edge,spacing_m=.001,max_vertices=350000)
    assert strip.report['fine_vertices']<350000
    assert strip.report['max_inward_ravel_m']<=.004+1e-12
    assert strip.report['max_actual_displacement_m']<.004
    full=np.concatenate((co,clip.additions,strip.coordinates));fine=strip.triangles
    a=full[fine];areas=np.cross(a[:,1,:2]-a[:,0,:2],a[:,2,:2]-a[:,0,:2]);assert np.all(areas>0)
    assert np.array_equal(strip.new_edge_x[[0,-1]],strip.old_edge_x[[0,-1]])
    print('PASS: mixed-tessellation exact sampler, clipping, finite metric relief and conforming inner/end joins')
    print(strip.report)

if __name__=='__main__':main()
