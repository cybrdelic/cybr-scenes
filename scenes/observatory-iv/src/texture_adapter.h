// New CVR2 attribute and mipmap adapter for CYBR GEO's original SAH BVH.
struct UV {float u=0,v=0;};
struct Attribute {UV uv[3];V col[3];int texture=-1;};
std::vector<Attribute> attributes;
struct Texel {V color,normal;float rough;};
Texel blend(Texel a,Texel b,float f){return {a.color*(1-f)+b.color*f,a.normal*(1-f)+b.normal*f,a.rough*(1-f)+b.rough*f};}
struct Texture {
 std::vector<std::vector<Texel>> levels;std::vector<int> sizes;
 void load(const std::string &path){
  std::ifstream f(path,std::ios::binary);uint32_t h[3];f.read((char*)h,12);
  if(!f||h[0]!=h[1]||h[2]!=7||h[0]>8192)throw std::runtime_error("Invalid texture "+path);
  int n=h[0];sizes.push_back(n);levels.emplace_back(n*n);f.read((char*)levels[0].data(),n*n*sizeof(Texel));
  if(!f)throw std::runtime_error("Truncated texture "+path);
  while(n>1){int m=n/2;std::vector<Texel> a(m*m);auto &b=levels.back();
   for(int y=0;y<m;y++)for(int x=0;x<m;x++)a[y*m+x]=blend(blend(b[(2*y)*n+2*x],b[(2*y)*n+2*x+1],.5f),blend(b[(2*y+1)*n+2*x],b[(2*y+1)*n+2*x+1],.5f),.5f);
   levels.push_back(std::move(a));sizes.push_back(m);n=m;
  }
 }
 Texel sampleLevel(float u,float v,int level)const{
  int n=sizes[level];float xx=(u-std::floor(u))*n-.5f,yy=(v-std::floor(v))*n-.5f;
  int x=int(std::floor(xx)),y=int(std::floor(yy));float fx=xx-x,fy=yy-y;
  auto at=[&](int a,int b){return levels[level][((b+n)%n)*n+(a+n)%n];};
  return blend(blend(at(x,y),at(x+1,y),fx),blend(at(x,y+1),at(x+1,y+1),fx),fy);
 }
 Texel sample(float u,float v,float footprint)const{
  float lod=clamp(std::log2(std::max(1.f,footprint*sizes[0])),0,float(levels.size()-1));int l=int(lod);
  auto a=sampleLevel(u,v,l);return l+1<int(levels.size())?blend(a,sampleLevel(u,v,l+1),lod-l):a;
 }
};
std::vector<Texture> textures;
