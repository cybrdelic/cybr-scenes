#pragma once
// Geometry-aligned reflectance / normal / roughness maps with radiance mip levels.
// Mip levels average emitted radiance, NOT temperature, preserving distant seams.
struct MapValue {Vec3 c,n,e;double rough=0,ao=0;};
inline MapValue operator+(MapValue a,MapValue b){return {a.c+b.c,a.n+b.n,a.e+b.e,a.rough+b.rough,a.ao+b.ao};}
inline MapValue operator*(MapValue a,double s){return {a.c*s,a.n*s,a.e*s,a.rough*s,a.ao*s};}
struct SceneMap {
 struct Level{int w=0,h=0;std::vector<std::array<float,11>> p;};
 std::vector<Level> levels;
 static MapValue unpack(const std::array<float,11>&p){return {{p[0],p[1],p[2]},{p[3],p[4],p[5]},{p[7],p[8],p[9]},p[6],p[10]};}
 static std::array<float,11> pack(MapValue a){return {float(a.c.x),float(a.c.y),float(a.c.z),float(a.n.x),float(a.n.y),float(a.n.z),float(a.rough),float(a.e.x),float(a.e.y),float(a.e.z),float(a.ao)};}
 void mip(){
  while(levels.back().w>1||levels.back().h>1){const auto&a=levels.back();Level b;b.w=std::max(1,a.w/2);b.h=std::max(1,a.h/2);b.p.resize(size_t(b.w)*b.h);
   for(int y=0;y<b.h;y++)for(int x=0;x<b.w;x++){MapValue v;for(int j=0;j<2;j++)for(int i=0;i<2;i++)v=v+unpack(a.p[std::min(y*2+j,a.h-1)*a.w+std::min(x*2+i,a.w-1)])*.25;b.p[y*b.w+x]=pack(v);}levels.push_back(std::move(b));
  }
 }
 MapValue sample_level(double u,double v,int l)const{
  const auto&a=levels[l];u=clamp(u)*double(a.w-1);v=clamp(v)*double(a.h-1);int x=std::min(a.w-1,int(u)),y=std::min(a.h-1,int(v)),xx=std::min(a.w-1,x+1),yy=std::min(a.h-1,y+1);double fu=u-x,fv=v-y;
  return unpack(a.p[y*a.w+x])*((1-fu)*(1-fv))+unpack(a.p[y*a.w+xx])*(fu*(1-fv))+unpack(a.p[yy*a.w+x])*((1-fu)*fv)+unpack(a.p[yy*a.w+xx])*(fu*fv);
 }
 MapValue sample(double u,double v,double lod=0)const{lod=clamp(lod,0,levels.size()-1);int l=int(lod);return sample_level(u,v,l)*(1-(lod-l))+sample_level(u,v,std::min(l+1,int(levels.size()-1)))*(lod-l);}
};
SceneMap lava_map;std::array<SceneMap,2> scan_maps;
std::vector<Vec3> thermal_table;
float skin_bounds[4];double pixel_angle=.001;
constexpr double emission_gain=19.0;
double river_center(double z){return 3.7*std::sin(z*.090)+1.10*std::sin(z*.153+.7);}
double river_center_derivative(double z){return 3.7*.090*std::cos(z*.090)+1.10*.153*std::cos(z*.153+.7);}
Vec3 thermal(double T){double t=clamp(T-500,0,1499.);int i=int(t);return thermal_table[i]*(1-(t-i))+thermal_table[i+1]*(t-i);}
void prepare_maps(){
 thermal_table.resize(1501);for(int i=0;i<=1500;i++)thermal_table[i]=source_spectrum(500+i);
 for(int k=0;k<2;k++){
  std::ifstream f("assets/scan_texture_"+std::to_string(k)+".bin",std::ios::binary);SceneMap::Level a;f.read((char*)&a.w,4);f.read((char*)&a.h,4);if(!f||a.w<1||a.h<1||a.w>4096||a.h>4096)throw std::runtime_error("Invalid scan map");a.p.resize(size_t(a.w)*a.h);
  for(auto&p:a.p){float v[8];f.read((char*)v,32);p={v[0],v[1],v[2],v[3],v[4],v[5],v[6],0,0,0,v[7]};}
  if(!f)throw std::runtime_error("Truncated scan map");scan_maps[k].levels.push_back(std::move(a));scan_maps[k].mip();
 }
 std::ifstream f("assets/lava_skin.bin",std::ios::binary);SceneMap::Level a;f.read((char*)&a.w,4);f.read((char*)&a.h,4);f.read((char*)skin_bounds,16);
 if(!f||a.w<1||a.h<1||a.w>8192||a.h>8192)throw std::runtime_error("Invalid thermal map");a.p.resize(size_t(a.w)*a.h);
 for(auto&p:a.p){float v[8];f.read((char*)v,32);Vec3 e=thermal(v[2])*emission_gain;p={v[0],v[0]*1.04f,v[0]*1.1f,v[4],v[5],v[6],v[3],float(e.x),float(e.y),float(e.z),1};}
 if(!f)throw std::runtime_error("Truncated thermal map");lava_map.levels.push_back(std::move(a));lava_map.mip();
}
MapValue skin_at(Vec3 p,double footprint=0){
 double u=(p.x-river_center(p.z)-skin_bounds[0])/(skin_bounds[1]-skin_bounds[0]);double v=(p.z-skin_bounds[2])/(skin_bounds[3]-skin_bounds[2]);
 double texel=std::max(lava_map.levels[0].w/(skin_bounds[1]-skin_bounds[0]),lava_map.levels[0].h/(skin_bounds[3]-skin_bounds[2]));
 double lod=std::log2(std::max(1.,footprint*texel));return lava_map.sample(u,v,lod);
}
MapValue scan_at(const Mat&m,const Hit&h,double footprint){
 int k=-m.kind-1;double lod=std::log2(std::max(1.,footprint*uv_density[h.primitive]));return scan_maps[k].sample(h.u,1-h.v,lod);
}
