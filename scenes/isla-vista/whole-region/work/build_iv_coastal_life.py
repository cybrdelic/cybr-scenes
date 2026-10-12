"""Original procedural kelp fronds over dated classified geographic support.

Kelp polygons and seafloor heights are measurements. Individual plants, frond
spacing, shape, optical state and subsurface-canopy depth are authored estimates.
"""
from pathlib import Path
import sys,json,hashlib,struct,numpy as np
from iv_coastal_life import r,Bathymetry,canopy_polygons,water_height,state
import shapely
from scipy.optimize import lsq_linear
from cybr_light import Scene,Meshlets
from cybr_terrain.materials import write_pfm
from iv_mesh_parts import Parts,leaf_mesh
out=r/'evidence/full-iv-coastal-life';out.mkdir(exist_ok=True);bathy=Bathymetry();parts=Parts(out/'kelp.clm',14000010);s=Scene();s.materials=187
day=json.loads((r/'evidence/coherent-daylight/COHERENT_DAYLIGHT.json').read_text());M=np.array(day['native_basis_to_linear_rgb']);white=M@np.ones(3)
def native(rgb):
 fit=lsq_linear(M/white[:,None],np.asarray(rgb),bounds=(0,1),tol=1e-12);assert fit.success;return fit.x
# Explicit estimated wet brown-alga optical response. Not measured spectra.
leaf=s.material('plastic',native([.11,.075,.025]),rough=.38,ior=1.4)
stem=s.material('plastic',native([.07,.048,.018]),rough=.36,ior=1.4)
bottom=s.material('diffuse',native([.20,.185,.145]),rough=.85)
water=s.material('roughglass',(1,1,1),rough=state['native_roughness_parameter'],ior=1.333)
absorption=np.array([[360,.30],[400,.22],[440,.15],[490,.085],[520,.074],[550,.085],[580,.15],[620,.27],[660,.46],[700,.70],[750,1.5],[800,2.0],[830,2.3]])
np.savetxt(out/'authored_coastal_water_absorption_m-1.txt',absorption,fmt='%.8g');s.emit('spectrum',water,'absorption',json.dumps(str((out/'authored_coastal_water_absorption_m-1.txt').resolve())))
s.save(out/'materials.cys');rows=[];estimated_leaf_area=0.;blade_count=0;frond_count=0
for source_id,label,area in canopy_polygons():
 shapely.prepare(area);rng=np.random.default_rng(201627+(0 if label=='Kelp Canopy' else 1));bounds=area.bounds;pitch=2.7;xx,yy=np.meshgrid(np.arange(bounds[0]+pitch*.5,bounds[2],pitch),np.arange(bounds[1]+pitch*.5,bounds[3],pitch));anchors=np.c_[xx.ravel(),yy.ravel()];anchors+=rng.uniform(-.9,.9,anchors.shape);anchors=anchors[shapely.contains_xy(area,anchors[:,0],anchors[:,1])];depth=water_height(anchors)-bathy.sample(anchors);keep=depth>1.2;rejected=int((~keep).sum());anchors=anchors[keep];directions=.22+rng.normal(0,.35,len(anchors));lengths=rng.uniform(5.5,8.5,len(anchors));row={'source_id':source_id,'classification':label,'mapped_area_m2':area.area,'frond_anchors':len(anchors),'anchors_rejected_for_depth_at_most1_2m':rejected,'authored_anchor_pitch_m':pitch,'authored_frond_length_range_m':[5.5,8.5],'source_canopy_depth_known':False,'authored_surface_offset_m':.025 if label=='Kelp Canopy' else None,'authored_subsurface_depth_m':.60 if label!='Kelp Canopy' else None};rows.append(row)
 for start in range(0,len(anchors),160):
  a=anchors[start:start+160];theta=directions[start:start+160];L=lengths[start:start+160];u=np.c_[np.cos(theta),np.sin(theta)];v=np.c_[-u[:,1],u[:,0]];N=len(a);t=np.linspace(-.48,.48,32);p=a[:,None,:]+u[:,None,:]*(L[:,None,None]*t[None,:,None])+v[:,None,:]*(.28*np.sin(t[None,:,None]*9+theta[:,None,None]));tang=u[:,None,:]+v[:,None,:]*(2.52/L[:,None,None]*np.cos(t[None,:,None]*9+theta[:,None,None]));tang/=np.linalg.norm(tang,axis=2,keepdims=True);side=np.stack([-tang[:,:,1],tang[:,:,0]],axis=2);sign=np.where(np.arange(len(t))%2,1.,-1.);axes=.50*tang+.866*side*sign[None,:,None];axes/=np.linalg.norm(axes,axis=2,keepdims=True);p+=axes*.21;pp=p.reshape(-1,2);inside=shapely.contains_xy(area,pp[:,0],pp[:,1]);pp=pp[inside];axes=axes.reshape(-1,2)[inside];h=water_height(pp)+(.025 if label=='Kelp Canopy' else -.60);leafL=rng.uniform(.42,.72,len(pp));leafW=rng.uniform(.13,.22,len(pp));vv,ff=leaf_mesh(np.c_[pp,h],np.c_[axes,np.zeros(len(pp))],leafL,leafW,folded=True,rolls=rng.uniform(-.10,.10,len(pp)))
  # Drape the generated blade geometry on the same actual water height field.
  vv[:,2]=water_height(vv[:,:2])+(.025 if label=='Kelp Canopy' else -.60)+(vv[:,2]-np.repeat(h,5))
  parts.mesh(f'{label}_frond_blades_{start}',vv,ff,leaf,source_id,'Authored floating Macrocystis-like fronds within dated source-classified extent; positions/dimensions/optics are not individual observations',tint=1)
  estimated_leaf_area+=float(np.sum(leafL*leafW*.5));blade_count+=len(pp);frond_count+=N
  # Thin stipes connect successive supported blade stations. Skip source holes.
  q=p.reshape(-1,2);valid=shapely.contains_xy(area,q[:,0],q[:,1]).reshape(N,-1);mid=water_height(q).reshape(N,-1)+(.01 if label=='Kelp Canopy' else -.615);width=.009;sv=[];sf=[]
  for i in range(N):
   for k in range(len(t)-1):
    if not (valid[i,k] and valid[i,k+1]):continue
    aa=p[i,k];bb=p[i,k+1];dv=bb-aa;dv=np.array([-dv[1],dv[0]])/max(np.linalg.norm(dv),1e-9)*width*.5;j=len(sv);sv.extend([[*(aa-dv),mid[i,k]],[*(bb-dv),mid[i,k+1]],[*(bb+dv),mid[i,k+1]],[*(aa+dv),mid[i,k]]]);sf.extend([[j,j+1,j+2],[j,j+2,j+3]])
  if sf:parts.mesh(f'{label}_supported_stipes_{start}',sv,sf,stem,source_id,'Authored9mm stipes; connectivity respects sampled source holes')
 print('KELP',label,len(anchors),parts.writer.triangles,flush=True)
report=parts.close();report.update(material_offset=187,material_count=4,leaf_material=leaf,stem_material=stem,bottom_material=bottom,water_material=water,source_classes=rows,fronds=frond_count,blades=blade_count,projected_diamond_blade_area_m2=estimated_leaf_area,authored_leaf_length_range_m=[.42,.72],authored_leaf_width_range_m=[.13,.22],source_classification_interval='2016-09-03/2016-09-25',source_classification_grid_m=2,kelp_subset_sha256=hashlib.sha256((r/'data/coastal-kelp-2016/iv_kelp_2016_local.geojson').read_bytes()).hexdigest(),bathymetry_subset_sha256=hashlib.sha256((r/'data/coastal-coned-20261011/coned_native_1m_iv_subset.tif').read_bytes()).hexdigest(),limits='Dated geographic extents only. Individual fronds are procedural examples, not measured plant locations or reconstructed biomass. Subsurface depth0.6m and all optical parameters are authored; measured blade spectra were unavailable behind a human-verification check. No physical kelp dynamics or current-year canopy claim. Water optical absorption is an explicit estimated coastal state, not measured local IOPs.')
(out/'KELP_RECEIPT.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'triangles':report['triangles'],'fronds':frond_count,'blades':blade_count,'projected_blade_area_m2':estimated_leaf_area}),flush=True)
