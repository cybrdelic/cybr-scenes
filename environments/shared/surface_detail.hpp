// SPDX-License-Identifier: GPL-2.0-only
// CYBR SCENES R2: photograph-derived, metre-scale stochastic triplanar detail.
// No beauty images are sampled. Input channels are linear reflectance ratios,
// roughness, physical height gradients and their second moments. Mips average
// moments, not normalised normals; lost slope variance broadens the rough lobe.
#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>
namespace cybr_detail {
constexpr int CHANNELS=8;
using Pixel=std::array<float,CHANNELS>;
inline uint32_t hash(uint32_t v){v^=v>>16;v*=0x7feb352du;v^=v>>15;v*=0x846ca68bu;return v^(v>>16);}
inline float fraction(float x){return x-std::floor(x);}
inline float smooth(float t){return t*t*(3.f-2.f*t);}
struct Level{int size=0;std::vector<Pixel> pixels;};
struct Atlas {
 std::vector<Level> levels;
 void load(const std::string& name){
  levels.clear();std::ifstream f(name,std::ios::binary);char tag[4];uint32_t n=0,c=0;
  f.read(tag,4);f.read(reinterpret_cast<char*>(&n),4);f.read(reinterpret_cast<char*>(&c),4);
  if(!f||std::string(tag,4)!="CDT2"||n<4||n>4096||(n&(n-1))||c!=CHANNELS)throw std::runtime_error("Invalid R2 mineral atlas header");
  Level a;a.size=int(n);a.pixels.resize(size_t(n)*n);f.read(reinterpret_cast<char*>(a.pixels.data()),a.pixels.size()*sizeof(Pixel));
  if(!f||f.peek()!=std::char_traits<char>::eof())throw std::runtime_error("Truncated or overlong R2 mineral atlas");
  for(const auto& p:a.pixels)for(float x:p)if(!std::isfinite(x))throw std::runtime_error("Nonfinite atlas texel");
  levels.push_back(std::move(a));
  while(levels.back().size>1){const auto& src=levels.back();Level dst;dst.size=src.size/2;dst.pixels.resize(size_t(dst.size)*dst.size);
   for(int y=0;y<dst.size;++y)for(int x=0;x<dst.size;++x)for(int k=0;k<CHANNELS;++k){float s=0;for(int j=0;j<2;++j)for(int i=0;i<2;++i)s+=src.pixels[(2*y+j)*src.size+2*x+i][k]*.25f;dst.pixels[y*dst.size+x][k]=s;}
   levels.push_back(std::move(dst));
  }
  std::cerr<<"CYBR R2 photographic surface atlas: "<<n<<" square; "<<levels.size()<<" moment mip levels\n";
 }
 Pixel bilinear(float u,float v,int level)const{
  const auto& a=levels[level];float x=fraction(u)*a.size-.5f,y=fraction(v)*a.size-.5f;int ix=int(std::floor(x)),iy=int(std::floor(y));float fx=x-ix,fy=y-iy;Pixel p{};
  for(int j=0;j<2;++j)for(int i=0;i<2;++i){float w=(i?fx:1-fx)*(j?fy:1-fy);const auto& q=a.pixels[((iy+j)&(a.size-1))*a.size+((ix+i)&(a.size-1))];for(int k=0;k<CHANNELS;++k)p[k]+=w*q[k];}return p;
 }
 Pixel sample(float u,float v,float footprint)const{
  if(levels.empty())return Pixel{1,1,1,.7f,0,0,0,.5f};
  float lod=std::clamp(std::log2(std::max(1.f,footprint*levels[0].size)),0.f,float(levels.size()-1));int l=int(lod);float t=lod-l;auto a=bilinear(u,v,l),b=bilinear(u,v,std::min(l+1,int(levels.size()-1)));for(int k=0;k<CHANNELS;++k)a[k]=a[k]*(1-t)+b[k]*t;return a;
 }
 Pixel stochastic(float u,float v,float footprint)const{
  // Four overlapping, independently transformed tile instances. Smooth weights
  // are continuous across cells. Normals use the inverse texture rotation.
  float cx=u*.45f,cy=v*.45f;int ix=int(std::floor(cx)),iy=int(std::floor(cy));float tx=smooth(cx-ix),ty=smooth(cy-iy);Pixel result{};
  for(int j=0;j<2;++j)for(int i=0;i<2;++i){float weight=(i?tx:1-tx)*(j?ty:1-ty);if(weight<.00001f)continue;
   uint32_t h=hash(uint32_t(ix+i)*73856093u^uint32_t(iy+j)*19349663u^0x5da6b173u);int rot=int(h&3u);
   float ru=u,rv=v;if(rot==1){ru=-v;rv=u;}else if(rot==2){ru=-u;rv=-v;}else if(rot==3){ru=v;rv=-u;}
   auto s=sample(ru+float((h>>2)&1023u)/1024.f,rv+float((h>>12)&1023u)/1024.f,footprint);
   float gx=s[4],gy=s[5];if(rot==1){s[4]=gy;s[5]=-gx;}else if(rot==2){s[4]=-gx;s[5]=-gy;}else if(rot==3){s[4]=-gy;s[5]=gx;}
   for(int k=0;k<CHANNELS;++k)result[k]+=weight*s[k];
  }return result;
 }
};
inline Atlas atlas;
inline void load_from_environment(){const char* name=std::getenv("CYBR_SURFACE_ATLAS");if(!name||!*name)throw std::runtime_error("CYBR_SURFACE_ATLAS is required for the R2 renderer; use the project launcher");atlas.load(name);}
// V only requires x/y/z, arithmetic, and a three-scalar constructor.
template<class V> void apply(V p,V baseNormal,V& normal,V& color,float& rough,float footprint,float scale,float strength,float relief){
 if(atlas.levels.empty()||strength<=0)return;
 float w[3]={std::pow(std::abs(baseNormal.x),6.f),std::pow(std::abs(baseNormal.y),6.f),std::pow(std::abs(baseNormal.z),6.f)};float sum=w[0]+w[1]+w[2]+1e-10f;for(float& x:w)x/=sum;
 Pixel mix{};V gradient(0);float variance=0;
 for(int a=0;a<3;++a){if(w[a]<.015f)continue;float u=a==0?p.y:p.x,v=a==2?p.y:p.z;
  auto s=atlas.stochastic(u*scale,v*scale,std::max(1e-6f,footprint*scale));for(int k=0;k<CHANNELS;++k)mix[k]+=w[a]*s[k];
  V g=a==0?V(0,s[4],s[5]):a==1?V(s[4],0,s[5]):V(s[4],s[5],0);gradient=gradient+g*(w[a]*scale);
  variance+=w[a]*std::max(0.f,s[6]-s[4]*s[4]-s[5]*s[5])*scale*scale;
 }
 color=V(color.x*(1+strength*(mix[0]-1)),color.y*(1+strength*(mix[1]-1)),color.z*(1+strength*(mix[2]-1)));
 float d=gradient.x*baseNormal.x+gradient.y*baseNormal.y+gradient.z*baseNormal.z;gradient=gradient-baseNormal*d;
 // Separate existing resolved mesostructure from the new fine-scale relief.
 V n=normal-gradient*relief;float len=std::sqrt(n.x*n.x+n.y*n.y+n.z*n.z);if(len>1e-6f)normal=n/len;
 rough=std::clamp(rough*(.90f+.17f*mix[3]),.12f,.96f);
 rough=std::min(.97f,std::pow(std::pow(rough,4.f)+variance*relief*relief,.25f));
}
} // namespace cybr_detail
