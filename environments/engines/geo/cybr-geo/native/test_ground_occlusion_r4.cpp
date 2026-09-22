// SPDX-License-Identifier: GPL-2.0-only
#define main cybr_native_main
#include "spectral_scenes.cpp"
#undef main
int main(int argc,char**argv){
 try{
  if(argc!=2)throw std::runtime_error("Usage: test_ground_occlusion_r4 ground_occlusion.bin");
  sceneStyle=2;configureScene();initRipples();groundOcclusion.load(argv[1]);
  std::ifstream input(argv[1],std::ios::binary);input.seekg(36);
  std::vector<float> minima(size_t(groundOcclusion.nx-1)*(groundOcclusion.ny-1));input.read(reinterpret_cast<char*>(minima.data()),minima.size()*4);if(!input)throw std::runtime_error("Cannot read independent cell bounds");
  V sun=unit(V(-.36f,.53f,.768f));Frame sf(sun);RNG rng(914771);uint64_t tested=0,rejected=0,invalid=0,underwaterRejects=0;
  for(int i=0;i<160000;i++){
   float x=groundOcclusion.x0+(groundOcclusion.x1-groundOcclusion.x0)*rng.uniform();
   float y=groundOcclusion.y0+(groundOcclusion.y1-groundOcclusion.y0)*rng.uniform();
   V q(x,y,waterHeight(x,y,0));V air=unit(sun+sf.t*((rng.uniform()-.5f)*.03f)+sf.b*((rng.uniform()-.5f)*.03f));
   V normal=waterNormal(x,y,0),out=reflect(-air,normal);
   if(out.z<=.04f)continue;
   float distance=.05f+18.f*rng.uniform();V p=q+out*distance;tested++;
   if(groundOcclusion.occludes(p,air)){
    rejected++;
    int ix=int(std::floor((q.x-groundOcclusion.x0)/groundOcclusion.dx)),iy=int(std::floor((q.y-groundOcclusion.y0)/groundOcclusion.dy));
    if(ix<0||iy<0||ix>=int(groundOcclusion.nx-1)||iy>=int(groundOcclusion.ny-1))invalid++;
    else if(!(minima[size_t(iy)*(groundOcclusion.nx-1)+ix]>q.z+.02f))invalid++;
    V above=q+air*((groundOcclusion.zhi+.10f-q.z)/air.z);
    if(above.x<=groundOcclusion.x0||above.x>=groundOcclusion.x1||above.y<=groundOcclusion.y0||above.y>=groundOcclusion.y1)invalid++;
   }
   if(groundOcclusion.occludes(V(x,y,float(-groundOcclusion.H)-.01f),air))underwaterRejects++;
  }
  bool passed=rejected>5000&&invalid==0&&underwaterRejects==0;
  std::cout<<std::setprecision(10)<<"{\n  \"scope\":\"Constructed actual-wave reflection paths verify conservative terrain and sun-domain rejection bounds; not all-scene unbiased transport proof\",\n  \"constructed_paths\":"<<tested<<",\n  \"rejected_paths_checked\":"<<rejected<<",\n  \"false_terrain_or_sun_domain_certificates\":"<<invalid<<",\n  \"underwater_rejections\":"<<underwaterRejects<<",\n  \"ripple_absolute_height_bound_m\":"<<groundOcclusion.H<<",\n  \"ripple_slope_bounds\":["<<groundOcclusion.Sx<<","<<groundOcclusion.Sy<<"],\n  \"passed\":"<<(passed?"true":"false")<<"\n}\n";
  return passed?0:1;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 2;}
}
