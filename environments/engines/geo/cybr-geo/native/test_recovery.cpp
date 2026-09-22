// SPDX-License-Identifier: GPL-2.0-only
#define main renderer_entry_for_recovery_test
#include "spectral_scenes.cpp"
#undef main
#include <cassert>
// Independent scalar walk of the original binary SAH, skipping only water slots.
// This is a test reference; it is not part of the production renderer.
bool recoveryOpaqueReference(const Ray &ray,float limit){
 std::vector<int> stack{0};
 while(!stack.empty()){
  int index=stack.back();stack.pop_back();const auto &node=nodes[index];
  if(!node.b.hit(ray,limit))continue;
  if(node.count){for(int j=node.start;j<node.start+node.count;++j){
   const auto &triangle=tris[order[j]];if(triangle.mat==6||triangle.mat==7)continue;
   float distance,u,v;if(triangle.hit(ray,limit,distance,u,v))return true;
  }}else{stack.push_back(node.left);stack.push_back(node.right);}
 }
 return false;
}
int main(int argc,char **argv){try{
 if(argc<2)throw std::runtime_error("Usage: test_recovery ASSET_DIRECTORY [scene.meshbin]");
 omp_set_num_threads(2);useSteam=false;useClouds=false;initSpectra();
 std::string assets=argv[1];photographicGrain.load(assets+"/gravel_periodic.pgm");granularRelief.load(assets+"/granular_relief.bin");
 double grainChange[3]={},reliefChange[3]={};float maxNormalError=0;int samples=0;
 for(int style=0;style<3;++style){sceneStyle=style;configureScene();RNG rng(998+style);
  for(int i=0;i<8000;++i){V p(rng.uniform()*26-13,rng.uniform()*30-8,rng.uniform()*9-.2f);V n=unit(V(rng.uniform()-.5f,rng.uniform()-.5f,.3f+rng.uniform()));int id=i%17;if(id==6||id==7)id=1;
   auto m=shade(p,n,id,.0003f+.02f*rng.uniform());auto reflectance=rgbAnchors(m.color);assert(std::isfinite(n.x+n.y+n.z+m.rough));assert(m.rough>0&&m.rough<=1);
   for(float x:reflectance.v)assert(std::isfinite(x)&&x>=0&&x<=.98501f);maxNormalError=std::max(maxNormalError,std::fabs(len(n)-1));++samples;
  }
  for(int i=0;i<512;++i){V p(rng.uniform()*12-6,rng.uniform()*15-5,rng.uniform()*4);V geometric=unit(V(.2f+rng.uniform(),.1f+rng.uniform(),.5f+rng.uniform()));V n=geometric;
   Surface full=shade(p,n,i%2,.0004f);V normalFull=n;
   auto grain=std::move(photographicGrain.levels);photographicGrain.levels.clear();n=geometric;Surface noGrain=shade(p,n,i%2,.0004f);photographicGrain.levels=std::move(grain);
   auto relief=std::move(granularRelief.levels);granularRelief.levels.clear();n=geometric;shade(p,n,i%2,.0004f);granularRelief.levels=std::move(relief);
   grainChange[style]+=len(full.color-noGrain.color)/512.;reliefChange[style]+=len(normalFull-n)/512.;
  }
  assert(grainChange[style]>1.e-6&&reliefChange[style]>1.e-6);
 }
 bool actual=argc>2;RNG rng(4091);
 if(actual){std::ifstream file(argv[2],std::ios::binary);uint32_t count;file.read((char*)&count,4);if(!file||count>40000000)throw std::runtime_error("Invalid mesh");tris.reserve(count);
  for(uint32_t i=0;i<count;++i){float a[20];file.read((char*)a,80);if(!file)throw std::runtime_error("Truncated mesh");Tri t;t.p=V(a[0],a[1],a[2]);t.e1=V(a[3],a[4],a[5])-t.p;t.e2=V(a[6],a[7],a[8])-t.p;t.mat=int(a[18]);t.group=int(a[19]);
   if(dot(cross(t.e1,t.e2),cross(t.e1,t.e2))>1.e-20f)tris.push_back(t);
  }
 }else for(int i=0;i<4000;++i){Tri t;t.p=V(rng.uniform()*30-15,rng.uniform()*40-10,rng.uniform()*10);t.e1=V(rng.uniform()-.5f,rng.uniform()-.5f,rng.uniform()-.5f);t.e2=V(rng.uniform()-.5f,rng.uniform()-.5f,rng.uniform()-.5f);t.mat=i%17;tris.push_back(t);}
 order.resize(tris.size());std::iota(order.begin(),order.end(),0);nodes.reserve(tris.size()/2);build(0,int(order.size()));buildWideR3();
 const int rays=actual?16000:60000;int mismatches=0,anyMismatches=0,opaqueMismatches=0,bruteMismatches=0,bruteProbes=0;float maximumDistanceError=0;
 for(int i=0;i<rays;++i){V origin(rng.uniform()*24-12,rng.uniform()*40-12,rng.uniform()*9+.2f);const auto &tr=tris[rng.next()%tris.size()];V target=tr.centroid();V d=unit(target-origin);
  if(i%7==0){d=V(0);d[(i/7)%3]=(i%2)?1:-1;}
  Ray ray(origin,d);float limit=i%3==0 ? (EPS*10+rng.uniform()*40) : INF;Hit a,b;a.t=b.t=limit;bool ha=meshHit(ray,a),hb=meshHitWideR3(ray,b);
  float error=ha&&hb?std::fabs(a.t-b.t):0;maximumDistanceError=std::max(error,maximumDistanceError);
  if(ha!=hb||(ha&&error>1.e-5f*(1+std::fabs(a.t))))++mismatches;
  Hit c,e;c.t=e.t=limit;if(meshHit(ray,c,true)!=meshHitWideR3(ray,e,true))++anyMismatches;
  Hit opaque;opaque.t=limit;if(recoveryOpaqueReference(ray,limit)!=meshHitWideR3(ray,opaque,true,true))++opaqueMismatches;
  if(!actual&&i<1200){Hit w;w.t=limit;bool found=false;++bruteProbes;for(const auto&t:tris){if(t.mat==6||t.mat==7)continue;float distance,u,v;if(t.hit(ray,limit,distance,u,v)){found=true;break;}}
   if(found!=meshHitWideR3(ray,w,true,true))++bruteMismatches;
  }
 }
 bool pass=mismatches==0&&anyMismatches==0&&opaqueMismatches==0&&bruteMismatches==0&&maxNormalError<1.e-5f;
 std::cout<<std::setprecision(10)<<"{\"scope\":\"Restored inputs and original-SAH traversal parity, not photorealism\",\"material_samples\":"<<samples<<",\"material_bounds_passed\":true,\"maximum_normal_length_error\":"<<maxNormalError<<",\"grain_mean_color_change\":["<<grainChange[0]<<","<<grainChange[1]<<","<<grainChange[2]<<"],\"relief_mean_normal_change\":["<<reliefChange[0]<<","<<reliefChange[1]<<","<<reliefChange[2]<<"],\"rays\":"<<rays<<",\"actual_mesh\":"<<(actual?"true":"false")<<",\"triangles\":"<<tris.size()<<",\"nearest_hit_mismatches\":"<<mismatches<<",\"any_hit_mismatches\":"<<anyMismatches<<",\"opaque_any_hit_mismatches\":"<<opaqueMismatches<<",\"opaque_reference_probes\":"<<rays<<",\"brute_force_opaque_probes\":"<<bruteProbes<<",\"brute_force_opaque_mismatches\":"<<bruteMismatches<<",\"finite_ray_limits_tested\":true,\"maximum_hit_distance_error\":"<<maximumDistanceError<<",\"passed\":"<<(pass?"true":"false")<<"}\n";return pass?0:1;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 2;}}
