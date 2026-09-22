#include "surface_detail.hpp"
#include <random>
#include <cassert>
#include <iostream>
struct V {float x,y,z;V(float a=0):x(a),y(a),z(a){} V(float a,float b,float c):x(a),y(b),z(c){} V operator+(V b)const{return {x+b.x,y+b.y,z+b.z};} V operator-(V b)const{return {x-b.x,y-b.y,z-b.z};} V operator*(float s)const{return {x*s,y*s,z*s};} V operator/(float s)const{return {x/s,y/s,z/s};}};
int main(int argc,char**argv){
 if(argc!=2)return 2;cybr_detail::atlas.load(argv[1]);auto& a=cybr_detail::atlas;
 std::mt19937 gen(735019);std::uniform_real_distribution<float> random(-40,40);double maxNormError=0,maxSeamError=0,minVariance=1;
 for(int k=0;k<10000;k++){
  V p(random(gen),random(gen),random(gen)),n(random(gen),random(gen),random(gen));n=n/std::sqrt(n.x*n.x+n.y*n.y+n.z*n.z);V base=n,c(.2f,.18f,.13f);float rough=.5f;
  float footprint=std::exp(-9.f+float(k%1000)*.009f);
  cybr_detail::apply(p,base,n,c,rough,footprint,.9f,.6f,.6f);
  double length=std::sqrt(n.x*n.x+n.y*n.y+n.z*n.z);maxNormError=std::max(maxNormError,std::abs(length-1));
  assert(std::isfinite(c.x+c.y+c.z+rough+length));assert(c.x>0&&c.y>0&&c.z>0);assert(rough>=.12f&&rough<=.971f);
  if(k<50){float u=float(k-25)/.45f,v=.712f;auto left=a.stochastic(u-.00002f,v,.01f),right=a.stochastic(u+.00002f,v,.01f);for(int j=0;j<3;j++)maxSeamError=std::max(maxSeamError,double(std::abs(left[j]-right[j])));}
 }
 for(const auto& l:a.levels)for(size_t k=0;k<l.pixels.size();k+=97){auto p=l.pixels[k];minVariance=std::min(minVariance,double(p[6]-p[4]*p[4]-p[5]*p[5]));}
 assert(maxNormError<2e-6);assert(maxSeamError<.02);assert(minVariance>-.0001);
 std::cout<<"{\"passed\":true,\"samples\":10000,\"normal_length_max_error\":"<<maxNormError<<",\"tile_boundary_max_delta\":"<<maxSeamError<<",\"minimum_slope_variance\":"<<minVariance<<"}\n";
}
