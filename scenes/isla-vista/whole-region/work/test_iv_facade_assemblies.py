"""Independent assembly checks: dimensions, winding, closure and metric charts."""
import json
import numpy as np
from iv_facade_assemblies import FacadeFrame, family, CHART_M

class Capture:
    def __init__(self):self.rows=[]
    def quad(self,vertices,material,uv):
        self.rows.append((np.asarray(vertices,float),material,np.asarray(uv,float)))

def normal(q):
    n=np.cross(q[1]-q[0],q[2]-q[0]);return n/np.linalg.norm(n)

def validate_quads(rows):
    for q,mat,uv in rows:
        assert np.isfinite(q).all() and np.isfinite(uv).all()
        for ids in [[0,1,2],[0,2,3]]:
            xyz=q[ids];chart=uv[ids];assert np.linalg.norm(np.cross(xyz[1]-xyz[0],xyz[2]-xyz[0]))>1e-10
            assert abs(np.linalg.det(np.array([chart[1]-chart[0],chart[2]-chart[0]])))>1e-12
        # UV chart recovers each edge in physical metres.
        assert np.allclose(np.linalg.norm(np.roll(q,-1,axis=0)-q,axis=1),np.linalg.norm(np.roll(uv,-1,axis=0)-uv,axis=1)*CHART_M,atol=1e-10)

b=Capture();frame=FacadeFrame(b,[0,0],[3,0]);frame.opening(.65,2.25,.9,2.2,0,1,2,3,4,curtains=True)
validate_quads(b.rows)
# Exterior is -Y. Left/right jambs face +X/-X; sill/head +Z/-Z.
expected=[[1,0,0],[-1,0,0],[0,0,1],[0,0,-1]]
for i,target in enumerate(expected):assert np.allclose(normal(b.rows[i][0]),target), (i,normal(b.rows[i][0]))
# Each six-quad member is a separately closed outward box, both flat/sloped.
for slope in [0,.35,-.4]:
 c=Capture();f=FacadeFrame(c,[2,7],[4,9]);f.box(0,2,-.12,.04,1,1.15,0,slope)
 validate_quads(c.rows)
 center=np.vstack([q for q,_,_ in c.rows]).mean(0)
 edges={}
 for q,_,_ in c.rows:
  assert normal(q)@(q.mean(0)-center)>0
  for a,z in zip(q,np.roll(q,-1,axis=0)):
   key=tuple(sorted((tuple(a),tuple(z))));edges[key]=edges.get(key,0)+1
 assert set(edges.values())=={2}
# Roof trim follows supplied boundary exactly and remains below it.
for za,zb in [(3,3),(3,4),(4,3)]:
 c=Capture();f=FacadeFrame(c,[0,0],[2,0]);f.roof_edge(2,za,zb,4,za==zb)
 validate_quads(c.rows)
 q=np.vstack([q for q,_,_ in c.rows]);line=za+(zb-za)*q[:,0]/2
 assert np.max(q[:,2]-line)<-0.002999
 assert np.min(q[:,1])>=-.042000001 # Exterior Y is negative.
 assert np.max(q[:,1])<=.145000001
# Repeatable source-level family, bounded and distinct across IDs.
styles=[family(f'osm:way:{i}','unspecified') for i in range(100)]
assert len({s['name'] for s in styles})==3
assert styles==[family(f'osm:way:{i}','unspecified') for i in range(100)]
print(json.dumps({'passed':True,'window_quad_count':len(b.rows),'opposite_reveal_winding':'correct','closed_box_tests':3,'retained_edge_profile_tests':3,'metric_uv_edges':'exact within1e-10m','families':sorted({s['name'] for s in styles})}))
