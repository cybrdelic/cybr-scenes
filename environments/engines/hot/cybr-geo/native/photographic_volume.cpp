// AERIS / native, deterministic single-scattering CFD volume renderer.
// Reuses CYBR GEO's actual scene BVH, photographic studio, materials and camera.
// Static surfaces are a cached high-SPP native path trace. Every volume frame is
// integrated from a different saved CFD scalar field. This is a HYBRID renderer,
// not a multiple-scattering path-traced film. No procedural smoke or image noise.
#define MECHANISM_PHOTO_LIBRARY
#include "photoreal.cpp"
#include <filesystem>
#include <stdexcept>

struct Grid {
 int nx=0,ny=0,nz=0;V origin;float h=0;std::vector<float> c;
 size_t index(int i,int j,int k)const{return (size_t(i)*ny+j)*nz+k;}
 V point(size_t id)const{int k=id%nz;id/=nz;int j=id%ny;int i=id/ny;return origin+V(i*h,j*h,k*h);}
 Box bounds()const{Box b;b.lo=origin-V(.5f*h);b.hi=origin+V((nx-.5f)*h,(ny-.5f)*h,(nz-.5f)*h);return b;}
 void load(const std::string&path){
  std::ifstream in(path,std::ios::binary);if(!in)throw std::runtime_error("Cannot read grid "+path);
  uint32_t dims[3];float geo[4];in.read((char*)dims,12);in.read((char*)geo,16);
  nx=dims[0];ny=dims[1];nz=dims[2];origin=V(geo[0],geo[1],geo[2]);h=geo[3];
  if(nx<2||ny<2||nz<2||nx>1000||ny>1000||nz>1000||h<=0)throw std::runtime_error("Invalid grid header");
  c.resize(size_t(nx)*ny*nz);in.read((char*)c.data(),c.size()*4);
  if(!in)throw std::runtime_error("Truncated density array");
  for(float d:c)if(!std::isfinite(d)||d<0)throw std::runtime_error("Invalid tracer; not silently clipped");
 }
 struct Weights{int i,j,k;float a,b,c;bool valid;};
 Weights weights(V p)const{
  V q=(p-origin)/h;
  if(q.x<-.5f||q.y<-.5f||q.z<-.5f||q.x>nx-.5f||q.y>ny-.5f||q.z>nz-.5f)return{0,0,0,0,0,0,false};
  q.x=clamp(q.x,0.f,nx-1.00001f);q.y=clamp(q.y,0.f,ny-1.00001f);q.z=clamp(q.z,0.f,nz-1.00001f);
  int i=int(q.x),j=int(q.y),k=int(q.z);return{i,j,k,q.x-i,q.y-j,q.z-k,true};
 }
 template<class T> T interp(const std::vector<T>&a,const Weights&w)const{
  if(!w.valid)return T(0);
  size_t z=index(w.i,w.j,w.k),dx=size_t(ny)*nz,dy=nz;
  return ((a[z]*(1-w.a)+a[z+dx]*w.a)*(1-w.b)+(a[z+dy]*(1-w.a)+a[z+dx+dy]*w.a)*w.b)*(1-w.c)
       + ((a[z+1]*(1-w.a)+a[z+dx+1]*w.a)*(1-w.b)+(a[z+dy+1]*(1-w.a)+a[z+dx+dy+1]*w.a)*w.b)*w.c;
 }
 float sample(V p)const{return interp(c,weights(p));}
};

bool segment(const Box&b,V origin,V direction,float limit,float&nearT,float&farT){
 nearT=0;farT=limit;
 for(int k=0;k<3;k++){
  if(std::abs(direction[k])<1e-10f){if(origin[k]<b.lo[k]||origin[k]>b.hi[k])return false;continue;}
  float x=(b.lo[k]-origin[k])/direction[k],y=(b.hi[k]-origin[k])/direction[k];
  if(x>y)std::swap(x,y);nearT=std::max(nearT,x);farT=std::min(farT,y);
  if(farT<=nearT)return false;
 }
 return true;
}
float phaseHG(float cosTravel,float g){return (1-g*g)/(4*PI*std::pow(std::max(.00001f,1+g*g-2*g*cosTravel),1.5f));}
float opticalDepth(const Grid&g,const Box&active,V p,V to,float extinction){
 V delta=to-p;float dist=len(delta);V d=delta/dist;float a,b;
 if(!segment(active,p,d,dist,a,b))return 0;
 const float step=g.h*.5f;int n=std::max(1,int(std::ceil((b-a)/step)));float ds=(b-a)/n;
 double sum=0;for(int k=0;k<n;k++)sum+=g.sample(p+d*(a+(k+.5f)*ds));
 return float(sum)*ds*extinction;
}
struct Beam{V position,emission;float area;V normal;};
struct Opt {std::string base,list,out;float extinction=3e-7f,albedo=.9f,g=.45f,step=.9f;int ss=2,limit=0;};

std::vector<V> loadPFM(const std::string&path,int W,int H){
 std::ifstream f(path,std::ios::binary);std::string magic;int w,h;float scale;
 f>>magic>>w>>h>>scale;f.get();if(!f||magic!="PF"||w!=W||h!=H||scale!=-1.f)throw std::runtime_error("Unexpected PFM format/size/endian");
 std::vector<V> a(size_t(w)*h);for(int y=h-1;y>=0;y--)f.read((char*)(&a[size_t(y)*w]),sizeof(V)*w);
 if(!f)throw std::runtime_error("Truncated base radiance");return a;
}
void savePPM(const std::string&path,const std::vector<V>&a,int w,int h,float exposure){
 std::ofstream f(path,std::ios::binary);if(!f)throw std::runtime_error("Cannot write frame");f<<"P6\n"<<w<<" "<<h<<"\n255\n";
 std::vector<unsigned char> rgb(a.size()*3);
 #pragma omp parallel for
 for(size_t i=0;i<a.size();i++)for(int k=0;k<3;k++){
  float t=aces(a[i][k]*exposure);t=t<=.0031308f?12.92f*t:1.055f*std::pow(t,1/2.4f)-.055f;
  rgb[i*3+k]=(unsigned char)(clamp(t)*255+.5f);
 }
 f.write((char*)rgb.data(),rgb.size());
}

#ifndef MECHANISM_VOLUME_LIBRARY
int main(int argc,char**argv){try{
 if(argc<3)throw std::runtime_error("Usage: photographic_volume SCENE.meshbin unused.ppm [photo args] --base-radiance PFM --density-list TXT --frames-dir DIR");
 std::vector<char*> args{argv[0],argv[1],argv[2]};Opt op;
 for(int i=3;i<argc;i++){
  std::string s=argv[i];auto next=[&](){if(i+1>=argc)throw std::runtime_error("Missing volume option value");return std::string(argv[++i]);};
  if(s=="--base-radiance")op.base=next();else if(s=="--density-list")op.list=next();else if(s=="--frames-dir")op.out=next();
  else if(s=="--extinction")op.extinction=std::stof(next());else if(s=="--albedo")op.albedo=std::stof(next());
  else if(s=="--phase-g")op.g=std::stof(next());else if(s=="--ray-step-mm")op.step=std::stof(next());
  else if(s=="--volume-ss")op.ss=std::stoi(next());else if(s=="--limit")op.limit=std::stoi(next());
  else args.push_back(argv[i]);
 }
 auto opt=parsePhoto(args.size(),args.data());
 if(op.base.empty()||op.list.empty()||op.out.empty()||op.extinction<0||op.albedo<0||op.albedo>1||std::abs(op.g)>=1||op.step<=0||op.ss<1||op.ss>4)
  throw std::runtime_error("Invalid single-scattering configuration");
 if(opt.ortho||opt.fstop<10000)throw std::runtime_error("Static cache requires matching pinhole perspective; DOF is not silently mismatched");
 auto start=std::chrono::steady_clock::now();auto cam=photoSetup(opt);auto base=loadPFM(op.base,opt.w,opt.h);
 std::ifstream f(op.list);std::vector<std::string> files;std::string path;
 while(std::getline(f,path))if(!path.empty())files.push_back(path);
 if(files.empty())throw std::runtime_error("Empty density sequence");if(op.limit>0&&op.limit<int(files.size()))files.resize(op.limit);
 std::filesystem::create_directories(op.out);
 Grid grid;grid.load(files.front());const size_t cells=grid.c.size();std::vector<float> maxC=grid.c;
 for(size_t n=1;n<files.size();n++){
  Grid a;a.load(files[n]);if(a.nx!=grid.nx||a.ny!=grid.ny||a.nz!=grid.nz||a.h!=grid.h||len(a.origin-grid.origin)>1e-6f)throw std::runtime_error("Inconsistent sequence grid");
  for(size_t j=0;j<cells;j++)maxC[j]=std::max(maxC[j],a.c[j]);
 }
 // Finite, fixed quadrature on the same four studio softboxes. The coefficient
 // includes phase, solid angle, emitted radiance and actual mesh visibility.
 std::vector<Beam> beams;
 for(const auto&l:lights)for(int i=0;i<2;i++)for(int j=0;j<2;j++)
  beams.push_back({l.c+l.u*(i-.5f)+l.v*(j-.5f),l.emission,l.area*.25f,l.n});
 const int B=beams.size();std::vector<V> lightCoeff(cells*B,V(0)),ambient(cells,V(0));std::vector<size_t> ids;
 // Values below 0.5 are omitted in RENDERING only. Over 400 mm, the
 // omitted optical depth is bounded by 200*op.extinction (0.00012 at 6e-7).
 for(size_t i=0;i<cells;i++)if(maxC[i]>.5f)ids.push_back(i);
 #pragma omp parallel for schedule(dynamic,64)
 for(size_t q=0;q<ids.size();q++){
  size_t id=ids[q];V p=grid.point(id),wo=unit(cam.camera-p);
  for(int b=0;b<B;b++){
   V delta=beams[b].position-p;float dist=len(delta);V wi=delta/dist;
   float cosine=std::max(0.f,dot(beams[b].normal,-wi));if(cosine<=0)continue;
   if(occluded(Ray(p+wi*EPS*4,wi),dist-EPS*8))continue;
   float phase=phaseHG(dot(-wi,wo),op.g);
   lightCoeff[id*B+b]=beams[b].emission*(beams[b].area*cosine/(dist*dist)*phase);
  }
  // Deterministic sphere quadrature of the photographic environment. This
  // incoming environment term neglects attenuation by the dilute volume.
  V e(0);const int N=32;
  for(int j=0;j<N;j++){
   float z=1-2*(j+.5f)/N,phi=j*2.39996323f,r=std::sqrt(1-z*z);V wi(r*std::cos(phi),r*std::sin(phi),z);
   if(!occluded(Ray(p+wi*EPS*4,wi),100000.f))e+=photoEnvironment(wi,false)*(phaseHG(dot(-wi,wo),op.g)*(4*PI/N));
  }
  ambient[id]=e;
 }
 std::cerr<<"Precomputed lighting for "<<ids.size()<<" active cells / "<<B<<" softbox quadrature samples\n";
 // Pixel footprint rays and true geometric stopping depths are shared by all
 // frames: fixed camera, fixed solid geometry, no stochastic temporal jitter.
 const int S=op.ss*op.ss;const size_t pixels=size_t(opt.w)*opt.h;
 std::vector<V> dirs(pixels*S);std::vector<float> depth(pixels*S,INF);
 float sensorH=opt.sensorWidth*float(opt.h)/opt.w;
 #pragma omp parallel for schedule(dynamic,128)
 for(size_t id=0;id<pixels;id++){
  int x=id%opt.w,y=id/opt.w;
  for(int j=0;j<op.ss;j++)for(int i=0;i<op.ss;i++){
   int sample=j*op.ss+i;float xx=2*(x+(i+.5f)/op.ss)/opt.w-1,yy=1-2*(y+(j+.5f)/op.ss)/opt.h;
   V d=unit(cam.fwd*opt.focal+cam.right*(xx*opt.sensorWidth*.5f)+cam.up*(yy*sensorH*.5f));
   dirs[id*S+sample]=d;Hit hit;if(sceneHit(Ray(cam.camera,d),hit,false))depth[id*S+sample]=hit.t;
  }
 }
 std::vector<V> scatter(cells),image(pixels);
 for(size_t frame=0;frame<files.size();frame++){
  grid.load(files[frame]);Box active;
  for(size_t id:ids)if(grid.c[id]>.5f)active.grow(grid.point(id));
  bool empty=active.lo.x==INF;
  if(!empty){active.lo=active.lo-V(grid.h);active.hi=active.hi+V(grid.h);}
  std::fill(scatter.begin(),scatter.end(),V(0));
  #pragma omp parallel for schedule(dynamic,32)
  for(size_t q=0;q<ids.size();q++){
   size_t id=ids[q];if(grid.c[id]<=.5f)continue;
   V p=grid.point(id),illum=ambient[id];
   for(int b=0;b<B;b++){
    V l=lightCoeff[id*B+b];if(maxc(l)<=0)continue;
    float tau=opticalDepth(grid,active,p,beams[b].position,op.extinction);
    illum+=l*std::exp(-tau);
   }
   scatter[id]=illum*(grid.c[id]*op.albedo);
  }
  #pragma omp parallel for schedule(dynamic,128)
  for(size_t id=0;id<pixels;id++){
   V sum(0);
   for(int sample=0;sample<S;sample++){
    V d=dirs[id*S+sample];float a,b,Tr=1;V L(0);
    if(!empty&&segment(active,cam.camera,d,depth[id*S+sample],a,b)){
     int steps=std::max(1,int(std::ceil((b-a)/op.step)));float ds=(b-a)/steps;
     for(int k=0;k<steps&&Tr>1e-5f;k++){
      V p=cam.camera+d*(a+(k+.5f)*ds);auto weights=grid.weights(p);float c=grid.interp(grid.c,weights);
      if(c<=.5f)continue;
      float alpha=-std::expm1(-c*op.extinction*ds);V source=grid.interp(scatter,weights)/c;
      L+=source*(Tr*alpha);Tr*=1-alpha;
     }
    }
    sum+=L+base[id]*Tr;
   }
   image[id]=sum/float(S);
  }
  char name[64];std::snprintf(name,sizeof(name),"/%04zu.ppm",frame);savePPM(op.out+name,image,opt.w,opt.h,opt.exposure);
  if(frame%10==0||frame+1==files.size())std::cerr<<"FRAME "<<frame+1<<"/"<<files.size()<<" elapsed "<<std::chrono::duration<float>(std::chrono::steady_clock::now()-start).count()<<" s\n";
 }
 std::ofstream record(op.out+"/native_record.json");
 record<<"{\n  \"frames\":"<<files.size()<<",\n  \"width\":"<<opt.w<<",\n  \"height\":"<<opt.h<<",\n  \"volume_samples_per_pixel\":"<<S<<",\n  \"step_mm\":"<<op.step<<",\n  \"extinction_per_mm_per_unit\":"<<op.extinction<<",\n  \"single_scattering_albedo\":"<<op.albedo<<",\n  \"phase_g\":"<<op.g<<",\n  \"area_light_samples\":"<<B<<",\n  \"active_voxels\":"<<ids.size()<<",\n  \"elapsed_seconds\":"<<std::chrono::duration<float>(std::chrono::steady_clock::now()-start).count()<<",\n  \"classification\":\"Native path-traced static surfaces + deterministic single-scattering CFD volume\",\n  \"limits\":[\"No multiple scattering\",\"Cached surfaces omit dynamic volume shadows and reflections\",\"Environment scattering neglects volume attenuation\",\"Optical parameters are illustrative, not measured soot\",\"Fixed pinhole camera; no fake DOF\"]\n}\n";
 return 0;
 }catch(const std::exception&e){std::cerr<<"VOLUME ERROR: "<<e.what()<<"\n";return 2;}}

#endif // MECHANISM_VOLUME_LIBRARY
