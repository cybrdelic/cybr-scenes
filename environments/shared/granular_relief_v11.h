// Authored microrelief reconstructed from an existing CC0 granular photograph.
// Scalar metres; no claim of measured displacement or calibrated photogrammetry.
#pragma once
struct GranularRelief {
 struct Level {int w,h;std::vector<float> data;};
 std::vector<Level> levels;
 void load(const std::string&path){
  std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("Cannot read granular relief: "+path);
  uint32_t h[3];f.read(reinterpret_cast<char*>(h),12);
  if(!f||h[0]!=0x31465247||h[1]<2||h[2]<2||h[1]>4096||h[2]>4096)throw std::runtime_error("Invalid granular relief header");
  Level base{int(h[1]),int(h[2]),std::vector<float>(size_t(h[1])*h[2])};f.read(reinterpret_cast<char*>(base.data.data()),base.data.size()*4);
  if(!f)throw std::runtime_error("Truncated relief map");
  for(float v:base.data)if(!std::isfinite(v)||std::fabs(v)>.05f)throw std::runtime_error("Invalid metre relief");
  levels.push_back(std::move(base));
  while(levels.back().w>1&&levels.back().h>1){auto&a=levels.back();Level l{a.w/2,a.h/2,{}};l.data.resize(size_t(l.w)*l.h);
   for(int y=0;y<l.h;y++)for(int x=0;x<l.w;x++)l.data[size_t(y)*l.w+x]=.25f*(a.data[size_t(y*2)*a.w+x*2]+a.data[size_t(y*2)*a.w+x*2+1]+a.data[size_t(y*2+1)*a.w+x*2]+a.data[size_t(y*2+1)*a.w+x*2+1]);
   levels.push_back(std::move(l));
  }
 }
 float bilinear(float u,float v,int l)const {
  auto&a=levels[l];u=(u-std::floor(u))*a.w;v=(v-std::floor(v))*a.h;
  int x=int(u),y=int(v);float dx=u-x,dy=v-y;int x1=(x+1)%a.w,y1=(y+1)%a.h;
  return (a.data[size_t(y)*a.w+x]*(1-dx)+a.data[size_t(y)*a.w+x1]*dx)*(1-dy)+(a.data[size_t(y1)*a.w+x]*(1-dx)+a.data[size_t(y1)*a.w+x1]*dx)*dy;
 }
 float sample(float x,float y,float footprint)const {
  if(levels.empty())return 0;
  float u=(x*.917f+y*.399f)/.68f,v=(y*.917f-x*.399f)/.68f;
  float lod=clamp(std::log2(std::max(1.f,footprint*levels[0].w/.68f)),0.f,float(levels.size()-1));int l=int(lod);float t=lod-l;
  return bilinear(u,v,l)*(1-t)+bilinear(u,v,std::min(l+1,int(levels.size()-1)))*t;
 }
 V gradient(float x,float y,float footprint)const {
  float e=std::max(.00065f,footprint*.5f);
  return V((sample(x+e,y,footprint)-sample(x-e,y,footprint))/(2*e),(sample(x,y+e,footprint)-sample(x,y-e,footprint))/(2*e),0);
 }
} granularRelief;
