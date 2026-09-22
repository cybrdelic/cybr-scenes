// Independent hemisphere integration versus matched VNDF-mixture importance sampling.
#define main obsidian_application_main
#include "../src/render.cpp"
#undef main
#include <cassert>
int main(){
 RNG rng(642712);constexpr int N=180000;int cases=0;
 for(double rough:{.28,.5,.82})for(double cosv:{.12,.5,1.}){
  Mat m;m.color=Vec3(.35);m.spec=.045;m.rough=rough;
  Vec3 n(0,1,0),wo(std::sqrt(1-cosv*cosv),cosv,0);double su=0,ss=0,qu=0,qs=0;
  for(int i=0;i<N;i++){
   double z=rng.uniform(),phi=2*pi*rng.uniform(),r=std::sqrt(1-z*z);Vec3 wi(r*std::cos(phi),z,r*std::sin(phi));
   double a=bsdf(m,m.color,n,wo,wi).f.x*z*2*pi;su+=a;qu+=a*a;
   wi=sample_bsdf(m,n,wo,rng);auto e=bsdf(m,m.color,n,wo,wi);double b=e.pdf>0?e.f.x*std::max(0.,dot(n,wi))/e.pdf:0;
   assert(std::isfinite(b)&&b>=0);ss+=b;qs+=b*b;
  }
  su/=N;ss/=N;double stderr=std::sqrt((qu/N-su*su+qs/N-ss*ss)/N);
  assert(std::abs(su-ss)<.015+6*stderr);assert(ss>=0&&ss<1.01);cases++;
  std::cout<<"rough="<<rough<<" cos_view="<<cosv<<" uniform="<<su<<" matched="<<ss<<" stderr="<<stderr<<" PASS\n";
 }
 std::cout<<"PASS "<<cases<<" grazing/roughness estimator consistency cases.\n";
}
