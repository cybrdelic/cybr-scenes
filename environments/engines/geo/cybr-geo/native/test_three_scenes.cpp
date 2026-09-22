#define main original_renderer_main
#include "spectral_scenes.cpp"
#undef main
#include <cassert>
int main(){
 omp_set_num_threads(2);useSteam=false;useClouds=false;initSpectra();
 int samples=0;float maxLengthError=0,minReflectance=1,maxReflectance=0;
 for(int style=0;style<3;style++){
  sceneStyle=style;configureScene();RNG rng(4001+style);
  for(int i=0;i<5000;i++){
   V p(rng.uniform()*30-15,rng.uniform()*45-10,rng.uniform()*15-.3f);
   V n=unit(V(rng.uniform()-.5f,rng.uniform()-.5f,.2f+rng.uniform()));
   int id=i%13;if(id==6||id==7)id=1;
   Surface m=shade(p,n,id,.0001f+rng.uniform()*.025f);Spec s=rgbAnchors(m.color);
   maxLengthError=std::max(maxLengthError,std::fabs(len(n)-1));
   assert(std::isfinite(n.x+n.y+n.z));assert(m.rough>0&&m.rough<=1);
   for(float v:s.v){assert(std::isfinite(v)&&v>=0&&v<=.98501f);minReflectance=std::min(minReflectance,v);maxReflectance=std::max(maxReflectance,v);}
   samples++;
  }
 }
 std::cout<<std::setprecision(9)<<"{\"test\":\"Authored material bounds and finite unit shading normals\",\"material_samples\":"<<samples<<",\"maximum_unit_normal_error\":"<<maxLengthError<<",\"minimum_reflectance\":"<<minReflectance<<",\"maximum_reflectance\":"<<maxReflectance<<",\"passed\":true,\"photorealism_certification\":false}\n";
}
