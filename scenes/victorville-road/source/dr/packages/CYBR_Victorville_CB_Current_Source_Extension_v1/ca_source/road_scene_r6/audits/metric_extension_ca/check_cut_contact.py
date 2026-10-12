from pathlib import Path
import numpy as np,json
root=Path(__file__).resolve().parent;p=np.load(root/'actual_road_fixture.npz');q=np.load(root/'extension_payload.npz');co=np.r_[p['co'],q['new_co']];old=p['tri'];tri=np.r_[old[q['keep_triangle']],q['new_tri'],q['collar_tri']]
def area(t):
 s=0.
 for a in range(0,len(t),100000):
  v=co[t[a:a+100000],:2].astype(float);d=v[:,1]-v[:,0];e=v[:,2]-v[:,0];s+=np.sum((d[:,0]*e[:,1]-d[:,1]*e[:,0])*.5)
 return s
removed=area(old)-area(tri);assert abs(removed-11)<1e-6,removed
cent=co[tri,:2].mean(1);local=(cent[:,0]>-3.1)&(cent[:,0]<-.15)&(cent[:,1]>1.8)&(cent[:,1]<6.1);t=tri[local];ed=np.concatenate([t[:,[i,(i+1)%3]] for i in range(3)]);v=co[ed,:2];inside=np.all((v[:,:,0]>-3.041)&(v[:,:,0]<-.209)&(v[:,:,1]>1.9)&(v[:,:,1]<6.05),axis=1);ed=ed[inside];u,n=np.unique(np.sort(ed,axis=1),axis=0,return_counts=True);single=u[n==1];v=co[single,:2];expected=np.all(abs(v[:,:,0]+3)<2e-7,axis=1)|np.all(abs(v[:,:,0]+.25)<2e-7,axis=1)|np.all(abs(v[:,:,1]-6)<2e-7,axis=1);bad=single[~expected]
report=dict(removed_projected_area_m2=removed,expected_native_extension_area_m2=11,unpaired_non_native_boundary_edges=len(bad),boundary_examples=co[bad[:10]].tolist(),overused_edges=int((n>2).sum()))
(root/'contact_check.json').write_text(json.dumps(report,indent=2));print(json.dumps(report));assert len(bad)==0 and not (n>2).any()
