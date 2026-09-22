#define main cybr_obsidian_application_main
#include "../engines/obsidian/src/render.cpp"
#undef main
#include <cassert>
int main(){
 prepare_sky();prepare_environment_sampler();RNG r(8173);double integral=0,maxPdfError=0,meanX=0,meanX2=0;constexpr int N=200000;
 double mass=0;for(double v:env_mass){assert(v>0&&std::isfinite(v));mass+=v;}
 for(int i=0;i<N;i++){
  double y=2*r.uniform()-1,phi=2*pi*r.uniform(),rr=std::sqrt(1-y*y);Vec3 u(rr*std::cos(phi),y,rr*std::sin(phi));integral+=environment_pdf(u)*4*pi/N;
  double p;Vec3 v=sample_environment(r,p);maxPdfError=std::max(maxPdfError,std::abs(p-environment_pdf(v))/p);
  double x=lum(sky(v))/p;meanX+=x/N;meanX2+=x*x/N;
 }
 assert(std::abs(mass-1)<1e-10);assert(std::abs(integral-1)<.04);assert(maxPdfError<1e-8);assert(std::isfinite(meanX)&&meanX>0);
 std::cout<<"{\"passed\":true,\"samples\":"<<N<<",\"mass_sum\":"<<mass<<",\"uniform_sphere_pdf_integral\":"<<integral<<",\"maximum_sample_pdf_relative_error\":"<<maxPdfError<<",\"mean_environment_radiance_integral\":"<<meanX<<"}\n";
}
