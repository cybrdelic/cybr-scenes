// OBSIDIAN / cinematic CPU bridge. Uses CYBR LIGHT's ray intersections, SAH BVH,
// camera, sampling, Fresnel and spectral observer; integrates CYBR ELEMENTS
// Planck emission before neutral-surface transport. This is NOT the untouched
// stock CYBR LIGHT executable. No image synthesis models are used.
#include "cybr/geometry.hpp"
#include "cybr/spectrum.hpp"
#include <fstream>
#include <iostream>
#include <chrono>
#include <atomic>
#include <cstring>
#include <iomanip>
#include <omp.h>
#include <cstdlib>
using namespace cybr;
#ifndef CYBR_SEQUENCE_BASE
#define CYBR_SEQUENCE_BASE 933719
#endif
struct Mat {Vec3 color{.07},emission;double rough=.6,spec=.04;int kind=0;};
Vec3 source_spectrum(double T){Vec3 xyz;for(int w=360;w<=830;w++){double e=blackbody(w,T)*(2*6.62607015e-34*299792458.*299792458.)*1e-9;xyz+=Observer::analytic(w)*(e/106.856895);}return vmax(Vec3(0),xyz_to_rgb(xyz));}
struct Group {std::vector<int> ids;std::vector<double> cdf;Vec3 center;double total=0,area=0;};
std::vector<Primitive> primitives;std::vector<Mat> materials;BVH bvh;std::vector<float> uv_density,uv_sign;
std::vector<Group> groups;std::vector<int> gid;std::vector<double> power;
std::vector<double> light_cdf;constexpr int GX=32,GY=12,GZ=54;int NG=0;
Vec3 sun=normalize(Vec3(-.62,.44,.65)),sunColor(.72,.60,.48);double globalExposure=1;
inline double lum(Vec3 v){return .2126*v.x+.7152*v.y+.0722*v.z;}
inline double frac(double x){return x-std::floor(x);}
inline double hash3(int x,int y,int z){return double(mix64(uint64_t(x)*73856093ull^uint64_t(y)*19349663ull^uint64_t(z)*83492791ull)>>11)/9007199254740992.;}
double noise(Vec3 p){int x=int(std::floor(p.x)),y=int(std::floor(p.y)),z=int(std::floor(p.z));double u=frac(p.x),v=frac(p.y),w=frac(p.z);u=u*u*(3-2*u);v=v*v*(3-2*v);w=w*w*(3-2*w);double a=0;for(int i=0;i<2;i++)for(int j=0;j<2;j++)for(int k=0;k<2;k++)a+=hash3(x+i,y+j,z+k)*(i?u:1-u)*(j?v:1-v)*(k?w:1-w);return a;}
constexpr int SW=1024,SH=512;
std::vector<Vec3> skyLUT;
Vec3 clear_sky(Vec3 d){double t=std::pow(clamp(d.y*.8+.18),.6);Vec3 low(.055,.087,.14),high(.012,.030,.069);Vec3 s=low*(1-t)+high*t;double glow=std::exp((dot(d,sun)-1)*16);return s+Vec3(.075,.035,.011)*glow;}
void prepare_sky(){
 std::ifstream f("assets/sky.bin",std::ios::binary);int w=0,h=0;
 f.read((char*)&w,4);f.read((char*)&h,4);
 if(!f||w!=SW||h!=SH)throw std::runtime_error("Invalid CYBR GEO sky panorama");
 skyLUT.resize(SW*SH);
 for(auto&c:skyLUT){float v[3];f.read((char*)v,12);c={v[0],v[1],v[2]};}
 if(!f)throw std::runtime_error("Truncated sky panorama");
}

Vec3 sky(Vec3 d){if(skyLUT.empty())return clear_sky(d);double x=(std::atan2(d.z,d.x)/(2*pi))*SW-.5;if(x<0)x+=SW;double y=std::acos(clamp(d.y,-1.,1.))/pi*SH-.5;int x0=int(std::floor(x)),y0=std::clamp(int(std::floor(y)),0,SH-1);double u=frac(x),v=frac(y);int x1=(x0+1)%SW,y1=std::min(SH-1,y0+1);Vec3 c=skyLUT[y0*SW+x0]*(1-u)*(1-v)+skyLUT[y0*SW+x1]*u*(1-v)+skyLUT[y1*SW+x0]*(1-u)*v+skyLUT[y1*SW+x1]*u*v;return (c*.96+Vec3(lum(c))*.04  )*.84;}

#include "environment_sampler.hpp"
#include "scene_maps.hpp"
Vec3 emitted(const Mat&m,Vec3 p){return m.kind==10000?skin_at(p).e:m.emission;}

int cell(Vec3 p){int x=int(std::floor((p.x+80)/5)),y=int(std::floor((p.y+10)/5)),z=int(std::floor((p.z+40)/5));x=std::clamp(x,0,GX-1);y=std::clamp(y,0,GY-1);z=std::clamp(z,0,GZ-1);return (z*GY+y)*GX+x;}
void prepare_lights(){
 gid.assign(primitives.size(),-1);power.assign(primitives.size(),0);groups.resize(52);
 for(int i=0;i<int(primitives.size());i++){auto&p=primitives[i];const auto&m=materials[p.material];if(m.kind!=10000&&lum(m.emission)<=0)continue;Vec3 c=(p.a+p.b+p.c)/3;double L=(m.kind==10000?lum(skin_at(c,std::sqrt(p.area())*.90).e):lum(m.emission))+.002;int g=std::clamp(int((c.z+40)/5),0,51);gid[i]=g;double a=p.area(),w=a*L;auto&q=groups[g];q.ids.push_back(i);q.total+=w;q.area+=a;q.cdf.push_back(q.total);q.center+=c*w;power[i]=w;}
 for(auto&g:groups)if(g.total>0){g.center=g.center/g.total;for(auto&c:g.cdf)c/=g.total;}
 NG=groups.size();light_cdf.resize(size_t(GX)*GY*GZ*NG);
 #pragma omp parallel for
 for(int idx=0;idx<GX*GY*GZ;idx++){int x=idx%GX,y=(idx/GX)%GY,z=idx/(GX*GY);Vec3 p(-77.5+x*5,-7.5+y*5,-37.5+z*5);double total=0;std::array<double,52>w{};for(int g=0;g<NG;g++){w[g]=groups[g].total/(norm2(groups[g].center-p)+12);total+=w[g];}double c=0;for(int g=0;g<NG;g++){c+=w[g]/std::max(total,1e-30);light_cdf[size_t(idx)*NG+g]=c;}light_cdf[size_t(idx)*NG+NG-1]=1;}
}
double area_pdf(Vec3 p,int id){int g=gid[id];if(g<0)return 0;const double*c=&light_cdf[size_t(cell(p))*NG];double pg=c[g]-(g?c[g-1]:0);return pg*power[id]/(primitives[id].area()*groups[g].total);}
int choose_light(Vec3 p,RNG&r){const double*c=&light_cdf[size_t(cell(p))*NG];int g=std::min(NG-1,int(std::upper_bound(c,c+NG,r.uniform())-c));auto&q=groups[g];if(q.ids.empty())return -1;size_t i=std::min(q.ids.size()-1,size_t(std::upper_bound(q.cdf.begin(),q.cdf.end(),r.uniform())-q.cdf.begin()));return q.ids[i];}
struct Texel{double albedo=1,height=.5,rough=.6;Vec3 grad;};
struct RockLevel{int w,h;std::vector<std::array<float,6>> p;};
std::vector<RockLevel> rocklevels;thread_local double rock_lod=0;
void load_texture(const char*name){
 std::ifstream f(name,std::ios::binary);RockLevel a;f.read((char*)&a.w,4);f.read((char*)&a.h,4);
 if(!f||a.w<4||a.h<4||a.w>4096||a.h>4096)throw std::runtime_error("Invalid rock texture");
 a.p.resize(size_t(a.w)*a.h);
 for(auto&p:a.p){float q[4];f.read((char*)q,16);p={q[0],q[1],q[2],q[3],0,0};}
 if(!f)throw std::runtime_error("Truncated rock texture");
 for(int y=0;y<a.h;y++)for(int x=0;x<a.w;x++){
   a.p[y*a.w+x][4]=(a.p[y*a.w+(x+1)%a.w][1]-a.p[y*a.w+(x+a.w-1)%a.w][1])*(a.w*.5f);
   a.p[y*a.w+x][5]=(a.p[((y+1)%a.h)*a.w+x][1]-a.p[((y+a.h-1)%a.h)*a.w+x][1])*(a.h*.5f);
 }
 rocklevels.push_back(std::move(a));
 while(rocklevels.back().w>1||rocklevels.back().h>1){const auto&t=rocklevels.back();RockLevel b;b.w=std::max(1,t.w/2);b.h=std::max(1,t.h/2);b.p.resize(size_t(b.w)*b.h);
 for(int y=0;y<b.h;y++)for(int x=0;x<b.w;x++)for(int c=0;c<6;c++){float v=0;for(int j=0;j<2;j++)for(int i=0;i<2;i++)v+=t.p[std::min(t.h-1,y*2+j)*t.w+std::min(t.w-1,x*2+i)][c]*.25f;b.p[y*b.w+x][c]=v;}rocklevels.push_back(std::move(b));}
}
Texel texuv_level(double u,double v,int l){
 const auto&t=rocklevels[l];u=frac(u)*t.w;v=frac(v)*t.h;int x=int(u),y=int(v),x1=(x+1)%t.w,y1=(y+1)%t.h;double a=frac(u),b=frac(v);Texel r{0,0,0,{}};double w[4]={(1-a)*(1-b),a*(1-b),(1-a)*b,a*b};int ids[4]={y*t.w+x,y*t.w+x1,y1*t.w+x,y1*t.w+x1};for(int k=0;k<4;k++){const auto&p=t.p[ids[k]];r.albedo+=p[0]*w[k];r.height+=p[1]*w[k];r.rough+=p[2]*w[k];r.grad.x+=p[4]*w[k];r.grad.y+=p[5]*w[k];}return r;
}
Texel texuv(double u,double v){double lod=clamp(rock_lod,0,rocklevels.size()-1);int l=int(lod);double f=lod-l;auto a=texuv_level(u,v,l),b=texuv_level(u,v,std::min(l+1,int(rocklevels.size()-1)));return {a.albedo*(1-f)+b.albedo*f,a.height*(1-f)+b.height*f,a.rough*(1-f)+b.rough*f,a.grad*(1-f)+b.grad*f};}
Texel triplanar(Vec3 p,Vec3 n){Vec3 a(std::pow(std::abs(n.x),5),std::pow(std::abs(n.y),5),std::pow(std::abs(n.z),5));a=a/(a.x+a.y+a.z+1e-20);Texel x=texuv(p.z*.23,p.y*.23),y=texuv(p.x*.23,p.z*.23),z=texuv(p.x*.23,p.y*.23);
 Vec3 g=(Vec3(0,x.grad.y,x.grad.x)*a.x+Vec3(y.grad.x,0,y.grad.y)*a.y+Vec3(z.grad.x,z.grad.y,0)*a.z)*.23;
 return {x.albedo*a.x+y.albedo*a.y+z.albedo*a.z,x.height*a.x+y.height*a.y+z.height*a.z,x.rough*a.x+y.rough*a.y+z.rough*a.z,g};}

struct Surface {Mat m;Vec3 albedo,n,emission;};
Surface surface(const Mat&input,const Hit&h,Vec3 wo,double footprint){
 Surface o;o.m=input;o.n=h.n;o.emission=input.emission;rock_lod=std::log2(std::max(1.,footprint*.725*1024/std::max(.10,std::abs(dot(h.n,wo)))));
 if(input.kind==10000){
  double co=std::abs(dot(h.n,wo));double major=footprint/std::max(.09,co);
  Vec3 projected=wo-h.n*dot(h.n,wo);projected=normalize(projected);
  MapValue t{};int taps=std::clamp(int(std::ceil(1/std::max(.09,co))),1,8);
  double minor=std::max(footprint,major/taps);
  for(int k=0;k<taps;k++){double q=(double(k)+.5)/taps-.5;t=t+skin_at(h.p+projected*(q*major),minor)*(1./taps);}
  o.albedo=t.c;o.emission=t.e;
  // Normal-map mip variance becomes unresolved roughness rather than sparkle.
  o.m.rough=clamp(std::sqrt(t.rough*t.rough+.5*std::max(0.,1-norm(t.n))),.15,.90);
  o.n=normalize(Vec3(t.n.x,t.n.y,t.n.z-t.n.x*river_center_derivative(h.p.z)-(.02+.17*.052*std::cos(h.p.z*.052))*t.n.y));
  // Photographed mineral-scale relief supplements the resolved pressure folds.
  // It changes reflected skin only, not the temperature field or visible emission.
  // The height is in metres; ray-footprint mip filtering suppresses subpixel grain.
  double cold=1-clamp(lum(t.e)*.25);
  rock_lod=std::log2(std::max(1.,footprint*1.35*1024/std::max(.12,co)));
  Texel micro=texuv(h.p.x*1.35,h.p.z*1.35);
  o.albedo=o.albedo*(1-cold*.65+cold*.65*clamp(micro.albedo,.40,1.85));
  o.m.rough=clamp(o.m.rough*(.74+.48*micro.rough),.24,.86);
  Vec3 microgradient(micro.grad.x*1.35,0,micro.grad.y*1.35);microgradient=microgradient-o.n*dot(microgradient,o.n);
  o.n=normalize(o.n-microgradient*(.0025*cold));
 }else if(input.kind==6){
  // Geometry carries the resolved folded skin. Fine mineral relief changes only
  // sub-centimetre shading; never replace the body normal with a flat top map.
  double co=std::abs(dot(h.n,wo));
  rock_lod=std::log2(std::max(1.,footprint*1.1*1024/std::max(.16,co)));
  auto tex=triplanar(h.p*4.8,h.n);
  double f=.62+.65*std::clamp(tex.albedo,.3,1.8);
  o.albedo=input.color*f;
  o.m.rough=std::clamp(input.rough*(.72+.45*tex.rough),.28,.72);
  Vec3 gradient=tex.grad*4.8;gradient=gradient-h.n*dot(gradient,h.n);o.n=normalize(h.n-gradient*.0022);
 }else if(input.kind==3){
  // Triplanar scan albedo / normal / roughness evaluated at a metre scale.
  double co=std::max(.15,std::abs(dot(h.n,wo))),scale=.65;
  double lod=std::log2(std::max(1.,footprint*scale*2048/std::sqrt(co)));
  Vec3 p=h.p*scale;
  MapValue a=scan_maps[0].sample(frac(p.z),frac(p.y),lod),b=scan_maps[0].sample(frac(p.x),frac(p.z),lod),c=scan_maps[0].sample(frac(p.x),frac(p.y),lod);
  Vec3 w(std::pow(std::abs(h.n.x),6),std::pow(std::abs(h.n.y),6),std::pow(std::abs(h.n.z),6));w=w/(w.x+w.y+w.z+1e-12);
  Vec3 col=a.c*w.x+b.c*w.y+c.c*w.z;double gray=lum(col);
  o.albedo=(col*.22+Vec3(gray)*.78)*.46;
  o.m.rough=clamp((a.rough*w.x+b.rough*w.y+c.rough*w.z)*.9,.45,.90);
  Vec3 g=Vec3(0,a.n.y,a.n.x)*w.x+Vec3(b.n.x,0,b.n.y)*w.y+Vec3(c.n.x,c.n.y,0)*w.z;
  g=g-h.n*dot(g,h.n);o.n=normalize(h.n+g*.72);
 }else if(input.kind<0){
  auto t=scan_at(input,h,footprint/std::sqrt(std::max(.12,std::abs(dot(h.n,wo)))));
  double gray=lum(t.c);Vec3 color=t.c*.32+Vec3(gray)*.68;
  o.albedo=color*input.color*(.94+.06*t.ao);o.m.rough=std::clamp(t.rough*.86,.28,.9);
  Vec3 tangent=normalize(h.tangent-h.n*dot(h.tangent,h.n)),bitangent=normalize(cross(h.n,tangent))*uv_sign[h.primitive];
  o.n=normalize(tangent*t.n.x+bitangent*t.n.y+h.n*std::max(.15,t.n.z));
 }else{
  double spatial=input.kind==3?3.143:2.1;auto tex=triplanar(h.p*spatial,h.n);double mult=std::clamp(tex.albedo,.28,2.5);
  double stain=.79+.32*noise(Vec3(h.p.x*.7,h.p.y*.09,h.p.z*.7));
  o.albedo=input.color*(mult*stain);o.m.rough=std::clamp(input.rough*(.55+.6*tex.rough),.24,.96);
  Vec3 g=tex.grad*spatial;g=g-h.n*dot(g,h.n);o.n=normalize(h.n-g*(input.kind==3?.012:.010));
 }
 if(dot(o.n,h.gn)<.15||dot(o.n,wo)<=.03)o.n=h.n;
 o.albedo=vmin(Vec3(.85),vmax(Vec3(.001),o.albedo));return o;
}

struct Eval{Vec3 f;double pdf;};
double ggx_alpha(const Mat&m){return std::max(.045,m.rough*m.rough);}
double smithG1(double c,double a2){return c>0?2*c/(c+std::sqrt(a2+(1-a2)*c*c)):0;}
double spec_probability(const Mat&m){return m.kind==10000?.50:.28;}
Eval bsdf(const Mat&m,Vec3 albedo,Vec3 n,Vec3 wo,Vec3 wi){
 double co=dot(n,wo),ci=dot(n,wi);if(co<=0||ci<=0)return {{},0};
 Vec3 h=normalize(wi+wo);double ch=std::max(0.,dot(n,h)),oh=std::max(0.,dot(wo,h));
 double a=ggx_alpha(m),a2=a*a,D=a2/(pi*sqr(ch*ch*(a2-1)+1));
 double Fo=m.spec+(1-m.spec)*std::pow(1-oh,5);
 double Fv=m.spec+(1-m.spec)*std::pow(1-co,5),Fl=m.spec+(1-m.spec)*std::pow(1-ci,5);
 double spec=D*smithG1(ci,a2)*smithG1(co,a2)*Fo/(4*ci*co);
 double mix=spec_probability(m),pdf=(1-mix)*ci/pi+mix*D*smithG1(co,a2)/(4*co);
 return {albedo*((1-Fv)*(1-Fl)/pi)+Vec3(spec),pdf};
}
Vec3 sample_bsdf(const Mat&m,Vec3 n,Vec3 wo,RNG&r){
 if(r.uniform()>=spec_probability(m))return Frame(n).world(cosine_hemisphere(r));
 Frame f(n);Vec3 v=f.local(wo);double alpha=ggx_alpha(m);Vec3 vh=normalize(Vec3(alpha*v.x,alpha*v.y,v.z));
 double l=vh.x*vh.x+vh.y*vh.y;Vec3 t1=l>1e-15?Vec3(-vh.y,vh.x,0)/std::sqrt(l):Vec3(1,0,0),t2=cross(vh,t1);
 double rad=std::sqrt(r.uniform()),phi=2*pi*r.uniform(),p1=rad*std::cos(phi),p2=rad*std::sin(phi);
 double s=.5*(1+vh.z);p2=(1-s)*std::sqrt(std::max(0.,1-p1*p1))+s*p2;
 Vec3 nh=t1*p1+t2*p2+vh*std::sqrt(std::max(0.,1-p1*p1-p2*p2));
 Vec3 h=f.world(normalize(Vec3(alpha*nh.x,alpha*nh.y,std::max(0.,nh.z))));return reflect(-wo,h);
}

struct Sample {Vec3 color,albedo,normal,emission;double distance=30000;};
Sample trace(Ray ray,RNG&r,int maxdepth){Sample out;Vec3 result,throughput(1),prev;double lastpdf=0;bool first=true;double traveled=0;
 for(int depth=0;depth<maxdepth;depth++){
  Hit h;if(!bvh.hit(ray,h)){double mis=first?1.:power_heuristic(lastpdf,environment_pdf(ray.d));result+=throughput*sky(ray.d)*mis;break;}
  traveled+=h.t;double footprint=traveled*pixel_angle;
  auto surf=surface(materials[h.material],h,-ray.d,footprint);const Mat&m=surf.m;Vec3 albedo=surf.albedo,n=surf.n,wo=-ray.d;
  if(first){out.albedo=albedo;out.normal=n;out.emission=surf.emission;out.distance=h.t;}
  if(m.kind==10000||lum(m.emission)>0){double w=1;if(!first){double cs=std::abs(dot(h.gn,-ray.d));double pdf=area_pdf(prev,h.primitive)*h.t*h.t/std::max(cs,1e-10);w=power_heuristic(lastpdf,pdf);}result+=throughput*surf.emission*w;}
  int id=choose_light(h.p,r);if(id>=0){Vec3 p,ln;primitives[id].sample(r,ray.time,p,ln);Vec3 d=p-h.p;double dist=norm(d);d=d/dist;double cosine=std::abs(dot(ln,-d)),pdf=area_pdf(h.p,id)*dist*dist/std::max(cosine,1e-10);auto e=bsdf(m,albedo,n,wo,d);if(e.pdf>0&&pdf>0&&!bvh.occluded({offset(h.p,h.gn,d),d},dist-3e-4)){result+=throughput*e.f*emitted(materials[primitives[id].material],p)*(std::max(0.,dot(n,d))*power_heuristic(pdf,e.pdf)/pdf);}}
  auto disk=concentric_disk(r.uniform(),r.uniform());Frame sf(sun);Vec3 sd=normalize(sun+(sf.x*disk[0]+sf.y*disk[1] )*.024);auto se=bsdf(m,albedo,n,wo,sd);if(dot(n,sd)>0&&!bvh.occluded({offset(h.p,h.gn,sd),sd},1000))result+=throughput*se.f*sunColor*dot(n,sd);
  // R2: explicit HDR-environment next-event sampling; the escape path uses
  // the matching PDF above. No screen-space ambient term replaces transport.
  double epdf=0;Vec3 ed=sample_environment(r,epdf);auto ee=bsdf(m,albedo,n,wo,ed);
  if(epdf>0&&dot(h.gn,ed)>0&&dot(n,ed)>0&&ee.pdf>0&&!bvh.occluded({offset(h.p,h.gn,ed),ed},1e8))
      result+=throughput*ee.f*sky(ed)*(dot(n,ed)*power_heuristic(epdf,ee.pdf)/epdf);
  Vec3 wi=sample_bsdf(m,n,wo,r);auto e=bsdf(m,albedo,n,wo,wi);if(e.pdf<=0||dot(wi,h.gn)<=0)break;
  throughput=throughput*e.f*(std::max(0.,dot(n,wi))/e.pdf);prev=h.p;lastpdf=e.pdf;first=false;ray={offset(h.p,h.gn,wi),wi};
  if(depth>=2){double survive=std::clamp(std::max({throughput.x,throughput.y,throughput.z}),.1,.85);if(r.uniform()>survive)break;throughput=throughput/survive;}
 }
 out.color=result;return out;
}
// Authored height-dependent haze. Beer-Lambert integration with an approximate
// sky source. This is not a forward-simulated gas plume or full volume transport.

double atmosphere(Sample&sample,const Ray&r){
 double total=sample.distance;double d=std::min(total,650.),T=1;Vec3 scatter;constexpr int steps=96;
 Vec3 ambient=sky(r.d)*.80+Vec3(.0012,.0018,.0030);double last=0;
 for(int i=0;i<steps;i++){
  double next=d*std::pow(double(i+1)/steps,1.4),ds=next-last;Vec3 p=r.at((last+next)*.5);last=next;
  double density=.0015*std::exp(-std::max(0.,p.y)*.028);
  double level=.55+.035*(p.z+22)+.55*(1+std::tanh((p.z-11)/2.4))+.85*(1+std::tanh((p.z-39)/3.1));double above=p.y-level;
  double plume=0;
  if(above>0&&above<42&&p.z>15&&p.z<160){
   double dr=p.x-river_center(p.z)-above*.40;
   Vec3 warp(1.9*std::sin(p.y*.57+p.z*.10),0,1.5*std::sin(p.y*.24+p.x*.27));
   double cloud=.57*noise((p+warp)*Vec3(.39,.49,.24))+.29*noise((p+warp)*Vec3(.89,1.1,.69))+.14*noise(p*Vec3(2.2,2.1,1.8));
   double sourceMod=.34+1.4*std::exp(-sqr((p.z-34)/8.0))+.9*std::exp(-sqr((p.z-67)/11.0));
   plume=.18*sourceMod*std::exp(-dr*dr/(7+above*1.8))*std::exp(-above/11.0)*std::max(0.,cloud-.34)*3.1;
  }
  density+=plume;double tr=std::exp(-density*ds);Vec3 source=ambient;
  if(plume>0){auto heat=skin_at(Vec3(river_center(p.z),level,p.z),2.4).e;source+=heat*(.075*std::exp(-std::max(0.,above)/3.0));}
  scatter+=source*(T*(1-tr));T*=tr;
 }
 if(total>650){double farT=std::exp(-.000020*(std::min(total,30000.)-650));
  // Far-distance aerial perspective behind the finite near-field plume integration.
  sample.color=sample.color*farT+(sky(r.d)*.95)*(1-farT);
 }
 sample.color=sample.color*T+scatter;sample.emission=sample.emission*T;return T;
}

void pfm(const std::string&f,const std::vector<Vec3>&data,int w,int h){std::ofstream out(f,std::ios::binary);if(!out)throw std::runtime_error("Cannot write "+f);out<<"PF\n"<<w<<" "<<h<<"\n-1.0\n";for(int y=h-1;y>=0;y--)for(int x=0;x<w;x++){auto a=data[size_t(y)*w+x];float v[]={float(a.x),float(a.y),float(a.z)};out.write((char*)v,12);}}
template<class T>T read(std::ifstream&f){T x{};f.read((char*)&x,sizeof(x));if(!f)throw std::runtime_error("Truncated scene");return x;}
Vec3 readv(std::ifstream&f){double x=read<float>(f),y=read<float>(f),z=read<float>(f);return {x,y,z};}
int main(int argc,char**argv){try{
 if(argc<7){std::cerr<<"usage: render scene.bin output_prefix width height spp camera[0/1] [maxdepth]\n";return 2;}
 int W=std::stoi(argv[3]),H=std::stoi(argv[4]),SPP=std::stoi(argv[5]),cam=std::stoi(argv[6]),depth=argc>7?std::stoi(argv[7]):4;
 if(W<16||H<16||SPP<1)throw std::runtime_error("Invalid image settings");const char* threads=std::getenv("OMP_NUM_THREADS");omp_set_num_threads(threads?std::max(1,std::atoi(threads)):4);
 std::ifstream f(argv[1],std::ios::binary);if(!f)throw std::runtime_error("Cannot open scene");uint32_t magic=read<uint32_t>(f);if(magic!=0x3253424f)throw std::runtime_error("Not an OBS2 scene stream");uint32_t nm=read<uint32_t>(f),np=read<uint32_t>(f),stride=read<uint32_t>(f);if(stride!=104)throw std::runtime_error("Invalid triangle stride");if(nm>10000||np>12000000)throw std::runtime_error("Invalid scene counts");
 materials.resize(nm);for(auto&m:materials){m.color=readv(f);m.emission=readv(f);m.rough=read<float>(f);m.spec=read<float>(f);m.kind=read<int32_t>(f);}
 uv_density.resize(np,240);uv_sign.resize(np,1);primitives.resize(np);int prim_id=0;for(auto&p:primitives){p.shape=Shape::Triangle;p.a=readv(f);p.b=readv(f);p.c=readv(f);p.na=readv(f);p.nb=readv(f);p.nc=readv(f);p.ta={read<float>(f),read<float>(f),0};p.tb={read<float>(f),read<float>(f),0};p.tc={read<float>(f),read<float>(f),0};p.material=read<int32_t>(f);p.object=read<int32_t>(f);p.smooth=true;if(p.material<0||p.material>=int(nm))throw std::runtime_error("Bad material");p.has_uv=materials[p.material].kind<0||materials[p.material].kind==10000;if(p.has_uv){Vec3 d1=p.tb-p.ta,d2=p.tc-p.ta;double det=d1.x*d2.y-d1.y*d2.x;uv_density[prim_id]=2048*std::sqrt(std::abs(det)*.5/std::max(p.area(),1e-15));uv_sign[prim_id]=det>0?1:-1;}prim_id++;}
 auto start=std::chrono::steady_clock::now();std::cerr<<"Building "<<np<<" CYBR LIGHT primitives\n";load_texture("assets/rock_texture.bin");prepare_maps();bvh.build(primitives);prepare_lights();prepare_sky();prepare_environment_sampler();std::cerr<<"BVH "<<bvh.node_count()<<" nodes; rendering "<<W<<"x"<<H<<" @ "<<SPP<<" spp\n";
 Camera camera;camera.origin=cam==0?Vec3(-2.8,7.0,-15):Vec3(.3,9.0,-21);camera.target=cam==0?Vec3(.5,1.8,12):Vec3(1.0,2.3,16);camera.fov=cam==0?41:38;pixel_angle=2*std::tan(camera.fov*pi/360)/H;
 std::vector<Vec3>film(size_t(W)*H),normal(film.size()),alb(film.size()),dist(film.size()),variance(film.size()),emission(film.size());std::atomic<int>done{0};std::atomic<uint64_t> nonfinite_samples{0};std::atomic<uint64_t> total_camera_paths{0};
 std::vector<uint16_t> budget;
 if(argc>8){std::ifstream bf(argv[8],std::ios::binary);uint32_t bw=read<uint32_t>(bf),bh=read<uint32_t>(bf);if(bw!=uint32_t(W)||bh!=uint32_t(H))throw std::runtime_error("Sample-budget dimensions do not match film");budget.resize(size_t(W)*H);bf.read((char*)budget.data(),budget.size()*sizeof(uint16_t));if(!bf)throw std::runtime_error("Truncated sample budget");for(auto n:budget)if(n<1||n>SPP)throw std::runtime_error("Sample budget outside 1..SPP");}
 #pragma omp parallel for schedule(dynamic,1)

 for(int y=0;y<H;y++){for(int x=0;x<W;x++){
  size_t idx=size_t(y)*W+x;Vec3 sum,sqsum,ns,as,es;double ds=0;int samples=budget.empty()?SPP:int(budget[idx]);total_camera_paths+=samples;RNG r(mix64(idx+CYBR_SEQUENCE_BASE));
  for(int s=0;s<samples;s++){
   r.configure(s,mix64(idx+CYBR_SEQUENCE_BASE),1);Ray ray=camera.generate(x+r.uniform(),y+r.uniform(),W,H,r);auto sample=trace(ray,r,depth);Vec3 c=sample.color;
   if(std::isfinite(c.x)&&std::isfinite(c.y)&&std::isfinite(c.z)){sum+=c;sqsum+=c*c;ns+=sample.normal;as+=sample.albedo;es+=sample.emission;ds+=std::min(sample.distance,30000.);}else{nonfinite_samples++;}
  }
  film[idx]=sum/samples;variance[idx]=vmax(Vec3(0),sqsum/samples-film[idx]*film[idx])/samples;
  // The authored haze model is integrated once per pixel at mean primary depth.
  // Surface light transport and all auxiliary features remain sample-averaged.
  RNG ar(1);Ray center_ray=camera.generate(x+.5,y+.5,W,H,ar);Sample avg;avg.color=film[idx];avg.emission=es/samples;avg.distance=ds/samples;double trans=atmosphere(avg,center_ray);
  film[idx]=avg.color;variance[idx]=variance[idx]*(trans*trans);normal[idx]=ns/samples;alb[idx]=as/samples;emission[idx]=avg.emission;dist[idx]=Vec3(ds/samples);
 }
 int n=++done;if(n%40==0)std::cerr<<n<<"/"<<H<<" rows\n";
 }

 std::string prefix=argv[2];pfm(prefix+".pfm",film,W,H);pfm(prefix+"_normal.pfm",normal,W,H);pfm(prefix+"_albedo.pfm",alb,W,H);pfm(prefix+"_depth.pfm",dist,W,H);pfm(prefix+"_variance.pfm",variance,W,H);pfm(prefix+"_emission.pfm",emission,W,H);
 double elapsed=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();std::ofstream meta(prefix+"_render.json");meta<<"{\"renderer\":\"CYBR SCENES R2 / CYBR LIGHT CPU bridge, explicit HDR MIS\",\"width\":"<<W<<",\"height\":"<<H<<",\"spp\":"<<SPP<<",\"triangles\":"<<np<<",\"seconds\":"<<elapsed<<",\"path_depth\":"<<depth<<",\"gpu\":false,\"image_generation\":false,\"nonfinite_path_samples\":"<<nonfinite_samples.load()<<",\"temperature_spectrum_preintegrated\":true,\"fluid_simulation\":false}";std::ofstream sr(prefix+"_sampling.json");sr<<"{\"total_camera_paths\":"<<total_camera_paths.load()<<",\"mean_spp\":"<<double(total_camera_paths.load())/(W*H)<<",\"guided_budget\":"<<(budget.empty()?"false":"true")<<"}";std::cerr<<"NONFINITE_SAMPLES "<<nonfinite_samples.load()<<"\n";std::cerr<<"DONE "<<elapsed<<" seconds\n";return 0;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
