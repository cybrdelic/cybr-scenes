#define MECHANISM_VOLUME_LIBRARY
#include "photographic_volume.cpp"
#define CHECK(expr) do { if (!(expr)) throw std::runtime_error("Check failed: " #expr); } while (false)
int main(){
 Grid g;g.nx=g.ny=g.nz=8;g.origin=V(.5f);g.h=1;g.c.assign(512,2.f);
 Box b=g.bounds();float a,z;
 CHECK(segment(b,V(-2,4,4),V(1,0,0),100,a,z));CHECK(std::abs(a-2)<1e-6&&std::abs(z-10)<1e-6);
 CHECK(!segment(b,V(-2,9,4),V(1,0,0),100,a,z));
 float tau=opticalDepth(g,b,V(-2,4,4),V(12,4,4),.1f);
 CHECK(std::abs(tau-1.6f)<1e-5f);CHECK(std::abs(std::exp(-tau)-std::exp(-1.6f))<1e-6f);
 CHECK(opticalDepth(g,b,V(-2,9,4),V(12,9,4),.1f)==0);
 for(size_t i=0;i<g.c.size();i++){V p=g.point(i);g.c[i]=p.x+2*p.y+3*p.z;}
 CHECK(std::abs(g.sample(V(2.2f,3.1f,4.7f))-(2.2f+6.2f+14.1f))<1e-5f);
 CHECK(g.sample(V(-3,0,0))==0);
 double integral=0,mean=0;int N=200000;float phase=.45f;
 for(int i=0;i<N;i++){double c=-1.+(i+.5)*2./N;double p=phaseHG(c,phase);integral+=p*4*PI/N;mean+=c*p*4*PI/N;}
 CHECK(std::abs(integral-1)<1e-5);CHECK(std::abs(mean-phase)<1e-5);
 CHECK(std::abs(phaseHG(1,0)-1.f/(4*PI))<1e-7f);
 std::cout<<"Native checks passed: axis-aligned bounds, outside-ray rejection, Beer transmittance, vacuum ray, trilinear reconstruction, zero exterior, HG normalization/mean, isotropic limit.\n";
 std::cout<<"{\"checks\":8,\"all_passed\":true,\"homogeneous_optical_depth\":"<<tau<<",\"phase_integral\":"<<integral<<",\"phase_mean_cosine\":"<<mean<<"}\n";
}
