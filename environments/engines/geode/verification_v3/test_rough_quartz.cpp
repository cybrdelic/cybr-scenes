#define main renderer_main
#include "../src/cathedral_v3.cpp"
#undef main
int main(){
 initSpectra();RNG rng(17613);V n(0,0,1),wo=unit(V(.3f,.2f,1));
 int finiteErrors=0,valid=0,refracted=0;double energy=0,recipMax=0,reflectEnergy=0;
 const int N=200000;float eta=quartzIndex(550),alpha=.022f;
 for(int i=0;i<N;i++){
  bool crossed;V wi=sampleRoughGlass(n,wo,eta,alpha,rng,crossed);
  if(dot(wi,wi)<.5f)continue;auto e=roughGlass(n,wo,wi,eta,alpha);
  if(!std::isfinite(e.f)||!std::isfinite(e.pdf)||e.f<0||e.pdf<=0){finiteErrors++;continue;}
  valid++;double weight=e.f*std::fabs(dot(n,wi))/e.pdf;energy+=weight;
  if(crossed){
   refracted++;auto reverse=roughGlass(-n,wi,wo,1/eta,alpha);
   if(e.f>1e-4&&reverse.f>1e-4)recipMax=std::max(recipMax,double(std::fabs(reverse.f/(e.f*eta*eta)-1)));
  }else reflectEnergy+=weight;
 }
 // Smooth-boundary energy and radiance eta convention sanity check.
 RNG r2(77131);double smoothEnergy=0;V z(0,0,1);
 for(int i=0;i<N;i++){bool cross;V wi=sampleRoughGlass(z,z,eta,.0015f,r2,cross);auto e=roughGlass(z,z,wi,eta,.0015f);if(e.pdf>0)smoothEnergy+=e.f*std::fabs(wi.z)/e.pdf;}
 double F=fresnelD(1,1,eta),expected=F+(1-F)/(eta*eta);
 bool passed=!finiteErrors&&recipMax<.015&&std::fabs(smoothEnergy/N-expected)<.004;
 std::cout<<std::setprecision(10)<<"{\n \"samples\": "<<N<<",\n \"valid\": "<<valid<<",\n \"finite_errors\": "<<finiteErrors<<",\n \"transmitted_samples\": "<<refracted<<",\n \"radiance_integral\": "<<energy/N<<",\n \"reflection_integral\": "<<reflectEnergy/N<<",\n \"transmission_reciprocity_relative_max\": "<<recipMax<<",\n \"smooth_limit_integral\": "<<smoothEnergy/N<<",\n \"smooth_limit_expected\": "<<expected<<",\n \"passed\": "<<(passed?"true":"false")<<"\n}\n";
 return passed?0:1;
}
