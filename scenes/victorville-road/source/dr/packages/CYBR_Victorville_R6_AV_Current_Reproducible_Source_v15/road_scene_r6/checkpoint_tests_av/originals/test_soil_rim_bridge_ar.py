"""Pure CPU fixtures for exact AR exposed-rim append/provenance contracts."""
from types import SimpleNamespace
import numpy as np
from soil_rim_bridge_ar import plan_soil_bridge, actual_right_rim, transport_corner_normals


def fixture():
    y=np.array([-.4,0.,.7,2.,5.,9.,15.,15.4])
    co=np.array([(x,yv,.1+.0002*yv) for yv in y for x in (-3.6,-3.2)])
    tri=[]
    for j in range(len(y)-1):
        a=2*j;tri.extend(((a,a+1,a+3),(a,a+3,a+2)))
    return co,np.array(tri,np.int32)


def main():
    co,tri=fixture(); before=co.copy();oldtri=tri.copy()
    y=np.linspace(-.12,15.12,1501)
    # Strong fine jaggedness stresses the geometric zipper, not a Y-only fan.
    x=-3.15+.006*np.where(np.arange(len(y))%2,1.,-1.)
    b=SimpleNamespace(y=y,x=x)
    top=lambda xy:.102+.0002*xy[:,1]
    p=plan_soil_bridge(co,tri,b,top)
    assert np.array_equal(co,before) and np.array_equal(tri,oldtri)
    assert np.array_equal(p.old_rim_vertex_ids,np.arange(1,len(co),2))
    assert np.max(abs(p.additions[:,2]-(top(p.additions[:,:2])-.0008)))<1e-14
    assert np.max(abs(p.additions[:,0]-np.interp(p.additions[:,1],y,x)-.004))<1e-14
    assert np.allclose(p.addition_weights.sum(1),1)
    assert np.allclose((co[p.addition_source_vertex_pairs,1]*p.addition_weights).sum(1),p.additions[:,1])
    for pair,t in zip(p.addition_source_vertex_pairs,p.addition_source_triangles):
        assert all(v in tri[t] for v in pair)
    for pair,t in zip(p.corner_source_vertex_pairs.reshape(-1,2),p.corner_source_triangles.ravel()):
        assert all(v in tri[t] for v in pair)
    # Reversed source winding cannot alter actual topological rim extraction.
    rev=plan_soil_bridge(co,tri[:,::-1],b,top)
    assert np.array_equal(rev.old_rim_vertex_ids,p.old_rim_vertex_ids)
    # Actual existing soil may already intrude under the new asphalt. Append
    # only a narrow continuation rather than reversing or moving that source.
    inside=plan_soil_bridge(co,tri,SimpleNamespace(y=y,x=np.full(len(y),-3.3)),top)
    np.testing.assert_allclose(inside.additions[:,0],-3.199,atol=1e-14)
    assert inside.report['target_adaptation_count']==len(inside.additions)
    assert inside.report['old_rim_dominance_count']==len(inside.additions)
    assert np.array_equal(co,before)
    assert np.all(np.isin(co[1::2,1][1:-1],inside.additions[:,1]))
    # Array-based top Z accepts the original knots and interpolates new ones.
    arr=plan_soil_bridge(co,tri,b,top(np.c_[x+.004,y]))
    np.testing.assert_allclose(arr.additions,p.additions,atol=1e-14)
    try: plan_soil_bridge(co,tri,SimpleNamespace(y=y,x=np.full(len(y),-3.043)),top)
    except ValueError as error: assert 'AQ right audit boundary' in str(error)
    else: raise AssertionError('Unaudited support outside AQ bounds was accepted')
    # Ground coverage gap must fail, even though geometry exists on both sides.
    broken=np.delete(tri,[6,7],axis=0)
    try: actual_right_rim(co,broken,(-.12,15.12),-3.15)
    except ValueError as error: assert 'continuously cover' in str(error)
    else: raise AssertionError('Gap was bridged with invented support')
    check_normal_transport()
    check_alias_seams()
    print('PASS actual rim identity, jagged conforming zipper, collar joins, provenance, clearance, immutable input, reversed winding and support gap rejection')
    print(p.report)


def check_normal_transport():
    base=np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.]])
    source=np.broadcast_to(base,(2,3,3,3)).copy()
    detail=np.array([[[.2,.1,1.],[-.1,.3,1.],[.05,-.25,1.]]]*2)
    detail/=np.linalg.norm(detail,axis=2,keepdims=True)
    target=np.broadcast_to(base,(2,3,3)).copy()
    identity=transport_corner_normals(detail,source,target)
    np.testing.assert_allclose(identity,detail,atol=1e-14)
    angle=.7;c,s=np.cos(angle),np.sin(angle)
    rotation=np.array([[c,0,s],[0,1,0],[-s,0,c]])
    target=target@rotation.T
    tilted=transport_corner_normals(detail,source,target)
    np.testing.assert_allclose(tilted,detail@rotation.T,atol=1e-14)
    np.testing.assert_allclose(np.linalg.norm(tilted,axis=2),1,atol=1e-14)
    new_normal=rotation@np.array([0.,0.,1.])
    np.testing.assert_allclose(tilted@new_normal,detail[:,:,2],atol=1e-14)
    # Independent source facets for each target corner also transport correctly.
    source[:,1]=source[:,1]@rotation.T
    rotated_detail=detail.copy();rotated_detail[:,1]=detail[:,1]@rotation.T
    mixed=transport_corner_normals(rotated_detail,source,target)
    np.testing.assert_allclose(mixed,tilted,atol=1e-14)
    for bad_source,bad_target,message in (
        (np.zeros_like(source),target,'Degenerate'),
        (source,np.zeros_like(target),'Degenerate'),
        (np.broadcast_to(base,(2,3,3,3)),np.broadcast_to(base[::-1],(2,3,3)),'antiparallel'),
    ):
        try: transport_corner_normals(detail,bad_source,bad_target)
        except ValueError as error: assert message in str(error)
        else: raise AssertionError('Invalid facet accepted')
    print('PASS identity/tilted/mixed-source shortest-arc normal transport, unit length, preserved detail angle, degenerate and antiparallel rejection')


def check_alias_seams():
    from soil_rim_bridge_ar import RimTopologyError
    original,tri=fixture();co=np.r_[original,original[6:8]].astype(np.float32)
    tri=tri.copy();tri[6:][tri[6:]==6]=16;tri[6:][tri[6:]==7]=17
    boundary=SimpleNamespace(y=np.array([-.12,2.,7.5-1e-15,15.12]),
                             x=np.full(4,-3.12))
    top=lambda xy:np.full(len(xy),.15)
    # Exact-XYZ aliases can meet geometrically without welding either ID.
    before=co.copy();p=plan_soil_bridge(co,tri,boundary,top)
    assert p.report['exact_xy_alias_seams']==1
    assert not p.report['id_watertight_bridge_claim']
    assert 7 in p.old_rim_vertex_ids and 17 in p.old_rim_vertex_ids
    assert np.array_equal(co,before)
    seam=np.flatnonzero(p.additions[:,1]==2.)+len(co)
    assert len(seam)==1
    for old_id in (7,17):
        assert any(old_id in face and seam[0] in face for face in p.triangles)
    # A real zero-XY source connector certifies an unmodified one-ULP Z step.
    co[17,2]=np.nextafter(co[17,2],np.float32(np.inf));step=float(co[17,2])-float(co[7,2])
    connected=np.r_[tri,[[7,17,6]]];before=co.copy()
    p=plan_soil_bridge(co,connected,boundary,top)
    assert p.report['maximum_preserved_source_seam_z_step_m']==step
    assert p.report['source_zero_xy_edges']==1 and np.array_equal(co,before)
    assert len(connected)-1 not in p.corner_source_triangles
    # Without the actual connector the same-XY/different-Z gap is not inferred.
    try:plan_soil_bridge(co,tri,boundary,top)
    except RimTopologyError:pass
    else:raise AssertionError('An unproven Z seam was joined')
    # A real nonzero XY gap remains forbidden even with an original edge.
    co[17,0]=np.nextafter(co[17,0],np.float32(np.inf))
    try:plan_soil_bridge(co,connected,boundary,top)
    except RimTopologyError:pass
    else:raise AssertionError('A nonzero XY gap was bridged')
    print('PASS exact aliases retain both IDs, shared new seam IDs, original connector preserves one-ULP Z step, unproven/nonzero gaps rejected')


def check_actual_fixture(path):
    from integrate_fracture_ar import ActualRoadHeights
    from soil_rim_bridge_ar import BridgeSpec
    from context_mesh_refine_ab import intersecting_triangles
    import json,time,hashlib
    started=time.monotonic()
    with np.load(path,allow_pickle=False) as f:data={k:f[k] for k in f.files}
    co,tri=data['ground_co'],data['ground_triangles']
    source_hash=hashlib.sha256(co.tobytes()+tri.tobytes()).hexdigest()
    road=object.__new__(ActualRoadHeights);road.co=data['road_co'];road.tri=data['road_triangles']
    boundary=SimpleNamespace(y=data['support_y'],x=data['support_x'])
    plan=plan_soil_bridge(co,tri,boundary,road,spec=BridgeSpec(rim_search_width_m=.1))
    assert hashlib.sha256(co.tobytes()+tri.tobytes()).hexdigest()==source_hash
    cs=plan.corner_source_triangles
    assert cs.min()>=0 and cs.max()<len(tri)
    source_vertex_triples=tri[cs]
    for k in range(2):
        assert np.all(np.any(source_vertex_triples==plan.corner_source_vertex_pairs[:,:,k,None],axis=2))
    source_xyz=co[source_vertex_triples].astype(float)
    source_normal=np.cross(source_xyz[:,:,1]-source_xyz[:,:,0],source_xyz[:,:,2]-source_xyz[:,:,0])
    assert np.all(abs(source_normal[:,:,2])>1e-14)
    source_normal/=np.linalg.norm(source_normal,axis=2,keepdims=True)
    full=np.r_[co,plan.additions];target=full[plan.triangles]
    target_normal=np.cross(target[:,1]-target[:,0],target[:,2]-target[:,0])
    assert np.all(target_normal[:,2]>0)
    target_normal/=np.linalg.norm(target_normal,axis=1,keepdims=True)
    transported=transport_corner_normals(source_normal,source_xyz,target)
    np.testing.assert_allclose(transported,np.repeat(target_normal[:,None,:],3,axis=1),atol=2e-13)
    vertex_ids=np.unique(plan.triangles)
    bounds=full[vertex_ids,:2]
    assert bounds[:,0].min()>=-3.95 and bounds[:,0].max()<=-3.04
    assert bounds[:,1].min()>=-.35 and bounds[:,1].max()<=15.65
    coverage=np.interp(data['boundary_y'],plan.additions[:,1],plan.additions[:,0])-data['boundary_x']
    assert coverage.min()>=.004-1e-12
    zero=np.flatnonzero(np.diff(co[plan.old_rim_vertex_ids,1])==0)
    assert len(zero)==52 and plan.report['exact_xyz_alias_seams']==51
    assert plan.report['maximum_preserved_source_seam_z_step_m']==np.float64(2**-26)
    for k in zero:
        a,b=plan.old_rim_vertex_ids[k:k+2]
        assert np.array_equal(co[a,:2],co[b,:2])
    local=len(intersecting_triangles(co,tri,(-4.05,-2.94,-.45,15.75)))
    report=dict(passed=True,bridge=plan.report,actual_source_corner_indices_valid=True,
        all_corner_source_pairs_on_actual_source_facet=True,
        all_corner_source_facets_positive_xy_area=True,normal_transport_passed=True,
        entire_bridge_inside_AQ_contact_bounds=True,
        minimum_support_inboard_of_fine_asphalt_m=float(coverage.min()),
        cropped_fixture_AQ_triangles_after=local+len(plan.triangles),
        full_AQ_triangle_cap_proven=False,
        full_AQ_cap_note='Fixture crop omits the outer AQ bank; original full-scene guard must run',
        source_arrays_sha256=source_hash,original_source_arrays_bitwise_unchanged=True,
        seconds=time.monotonic()-started)
    print('ACTUAL_SOURCE_BRIDGE_PROOF '+json.dumps(report,sort_keys=True))
    return report

if __name__=='__main__':
    import sys
    main()
    if len(sys.argv)>1:check_actual_fixture(sys.argv[1])
