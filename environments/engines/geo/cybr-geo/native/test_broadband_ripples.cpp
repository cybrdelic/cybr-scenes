// GPL-2.0-only. Numerical lookup-error test, not a CFD validation.
#include "spectral_geometry.h"
#include <array>
#include <iomanip>
#include <stdexcept>
struct Pool{float x,y,rx,ry,level;};
const std::array<Pool,2> pools={Pool{.5f,1.0f,4.1f,4.05f,.055f},Pool{-3.5f,10.0f,2.2f,1.65f,.245f}};
#include "broadband_ripples.h"
int main(){
 omp_set_num_threads(2);initRipples();
 double heightMax=0,normalMax=0,heightSum=0;constexpr int N=10000;
 for(int i=0;i<2;i++)for(int j=0;j<N;j++){
  const auto&p=pools[i];double u=std::fmod((j+.5)*.6180339887498949,1.),v=std::fmod((j+.5)*.4142135623730951,1.);
  float x=p.x+(2*u-1)*p.rx*1.2,y=p.y+(2*v-1)*p.ry*1.2;double h=0,dx=0,dy=0;
  for(const auto&m:RIPPLE_MODES){double a=m[0]*x+m[1]*y+m[3]+.37*i;h+=m[2]*RIPPLE_SCALE*std::sin(a);dx+=m[0]*m[2]*RIPPLE_SCALE*std::cos(a);dy+=m[1]*m[2]*RIPPLE_SCALE*std::cos(a);}
  double e=std::fabs(waterHeight(x,y,i)-p.level-h);heightMax=std::max(heightMax,e);heightSum+=e;
  V exact=unit(V(-dx,-dy,1)),sample=waterNormal(x,y,i);normalMax=std::max(normalMax,double(len(exact-sample)));
 }
 bool good=heightMax<.0002&&normalMax<.01;
 std::cout<<std::setprecision(12)<<"{\"scope\":\"LUT vs analytic authored mode table; not physical wave validation\",\"modes\":"<<RIPPLE_COUNT<<",\"tested_points\":"<<N*2<<",\"height_max_error_m\":"<<heightMax<<",\"height_mean_absolute_error_m\":"<<heightSum/(N*2)<<",\"unit_normal_max_difference\":"<<normalMax<<",\"passed\":"<<(good?"true":"false")<<"}\n";
 return good?0:1;
}
