"""Independent source-dimension and single-sheet leaf geometry regressions."""
import json
import numpy as np
from shapely.geometry import LineString,Polygon,MultiPolygon,mapping
from iv_mapped_hedges_v1 import footprint,geometry,LAI,require_resolved_support,require_connected_convex_support,triangle_envelope_bounds

class FlatGround:
    def height(self,xy):return np.zeros(len(xy))

def feature(g,tags=None):
    return {'id':'osm:way:123456','geometry':mapping(g),'properties':{'source_properties':tags or {},'category':'hedge'}}

line=feature(LineString([(0,0),(1,0)]),{'height':'2.1 m','width':'55 cm'})
# Source units are parsed; an unparsed tag must fail instead of being replaced.
support,dims=footprint(line)
assert dims['height_m']==2.1 and dims['height_basis']=='source height tag'
assert dims['width']['basis']=='source width tag' and dims['width']['value_m']==.55
line['properties']['source_properties']['width']='0.55 m'
support,dims=footprint(line);assert dims['width']['value_m']==.55
polygon=feature(Polygon([(0,0),(2,0),(2,1),(0,1)]))
assert footprint(polygon)[0].equals_exact(Polygon(polygon['geometry']['coordinates'][0]),0)
assert footprint(polygon)[1]['width']['basis']=='mapped polygon outline; no replacement width'
invalid=feature(LineString([(0,0),(1,0)]),{'height':'approximately two metres'})
try:footprint(invalid)
except ValueError:pass
else:raise AssertionError('Unparsed existing source dimension was silently estimated')
# Both members of an unresolved pair remain excluded, even if just one is
# requested. No partial selection may sidestep source/dimension review.
coverage={'building_support_conflicts':[{'source_id':'building-conflict'}],
          'overlapping_candidate_pairs':[{'source_ids':['pair-a','pair-b']}]}
for selected in [['building-conflict'],['pair-a'],['pair-b'],['clear','pair-a']]:
    try:require_resolved_support(coverage,selected)
    except ValueError:pass
    else:raise AssertionError('Unresolved support admitted: '+str(selected))
require_resolved_support(coverage,['clear'])
# Fail closed for branch routing not implemented by this bounded form.
concave=Polygon([(0,0),(2,0),(2,.5),(.5,.5),(.5,2),(0,2)])
for support in [concave,MultiPolygon([Polygon([(0,0),(1,0),(1,1),(0,1)]),Polygon([(2,0),(3,0),(3,1),(2,1)])])]:
    try:require_connected_convex_support(support)
    except ValueError:pass
    else:raise AssertionError('Unrouted nonconvex or multipart support admitted')
q=np.array([[[.2,.2,.4],[1.8,.2,.4],[.2,1.8,.4]]])
try:triangle_envelope_bounds(q,concave,FlatGround(),1.2,0.,False)
except ValueError:pass
else:raise AssertionError('Triangle interior escaped a concave support undetected')
box=Polygon([(0,0),(2,0),(2,2),(0,2)])
for z,basal,should_pass in [(-.01,True,True),(-.01,False,False),(-.03,True,False),(1.21,False,False),(.5,False,True)]:
    q[:,:,2]=z
    try:triangle_envelope_bounds(q,box,FlatGround(),1.2,0.,basal)
    except ValueError:assert not should_pass
    else:assert should_pass

results=[]
for f in [line,polygon]:
    a=geometry(f,FlatGround());b=geometry(f,FlatGround())
    assert np.array_equal(a[0],b[0]) and np.array_equal(a[1],b[1])
    v,faces=a[:2];r=a[-1]
    assert len(faces)==4*r['leaf_count'] and len(v)==5*r['leaf_count']
    assert r['leaf_length_m'][0]>=.04 and r['leaf_length_m'][1]<=.08
    q=v[faces];area=np.linalg.norm(np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]),axis=1).sum()/2
    assert abs(area/footprint(f)[0].area-LAI)<1e-5
    assert np.min(v[:,2])>0
    results.append({'type':f['geometry']['type'],'leaves':r['leaf_count'],'one_sided_lai':area/footprint(f)[0].area})
v,faces,*_,r=geometry(polygon,FlatGround(),4.5)
q=v[faces];area=np.linalg.norm(np.cross(q[:,1]-q[:,0],q[:,2]-q[:,0]),axis=1).sum()/2
assert abs(area/footprint(polygon)[0].area-4.5)<1e-5
print(json.dumps({'passed':True,'deterministic':True,'source_tag_priority':True,'unparsed_tags_refused':True,'unresolved_building_and_either_pair_member_refused':True,'one_sheet_without_reversed_duplicates':True,'nonconvex_multipart_refused':True,'native_triangle_interior_and_burial_and_height_tests':True,'higher_lai_scenario':4.5,'cases':results}))
