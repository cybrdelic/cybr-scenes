// GPL-2.0-only. CC0 grayscale albedo detail loader with footprint mipmapping.
// This map contains no calibrated height/roughness/spectral measurements.
#pragma once
struct GrainMap {
 struct Level {int w,h;std::vector<float> data;};
 std::vector<Level> levels;float mean=1;
 void load(const std::string& path){
  std::ifstream f(path,std::ios::binary);if(!f)throw std::runtime_error("Cannot read grayscale detail asset: "+path);
  std::string magic;int w,h,m;f>>magic>>w>>h>>m;
  if(magic!="P5"||w<2||h<2||w>8192||h>8192||m!=255)throw std::runtime_error("Expected 8-bit binary PGM");
  f.get();std::vector<unsigned char>b(size_t(w)*h);f.read(reinterpret_cast<char*>(b.data()),b.size());
  if(!f)throw std::runtime_error("Truncated grayscale detail asset");
  Level base{w,h,std::vector<float>(b.size())};double total=0;
  for(size_t i=0;i<b.size();i++){float s=b[i]/255.f;float linear=s<=.04045f?s/12.92f:std::pow((s+.055f)/1.055f,2.4f);base.data[i]=linear;total+=linear;}
  mean=float(total/b.size());if(mean<=0)throw std::runtime_error("Invalid empty texture");levels.push_back(std::move(base));
  while(levels.back().w>1&&levels.back().h>1){const auto&a=levels.back();Level next{a.w/2,a.h/2,{}};next.data.resize(size_t(next.w)*next.h);
   for(int y=0;y<next.h;y++)for(int x=0;x<next.w;x++)next.data[size_t(y)*next.w+x]=.25f*(a.data[size_t(y*2)*a.w+x*2]+a.data[size_t(y*2)*a.w+x*2+1]+a.data[size_t(y*2+1)*a.w+x*2]+a.data[size_t(y*2+1)*a.w+x*2+1]);
   levels.push_back(std::move(next));
  }
 }
 float bilinear(float u,float v,int l)const{
  const auto&a=levels[l];u=(u-std::floor(u))*a.w-.5f;v=(v-std::floor(v))*a.h-.5f;
  int ix=int(std::floor(u)),iy=int(std::floor(v));float fx=u-ix,fy=v-iy;
  int x0=(ix%a.w+a.w)%a.w,y0=(iy%a.h+a.h)%a.h,x1=(x0+1)%a.w,y1=(y0+1)%a.h;
  return (a.data[size_t(y0)*a.w+x0]*(1-fx)+a.data[size_t(y0)*a.w+x1]*fx)*(1-fy)+(a.data[size_t(y1)*a.w+x0]*(1-fx)+a.data[size_t(y1)*a.w+x1]*fx)*fy;
 }
 float sample(float u,float v,float footprint,float width)const{
  if(levels.empty())return 1.f;
  float lod=clamp(std::log2(std::max(1.f,footprint*levels[0].w/width)),0.f,float(levels.size()-1));
  int l=int(lod);float t=lod-l;
  return (bilinear(u/width,v/width,l)*(1-t)+bilinear(u/width,v/width,std::min(l+1,int(levels.size()-1)))*t)/mean;
 }
};
GrainMap photographicGrain;
