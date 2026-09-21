// CYBR Observatory IV. Native CPU spectral light transport.
// Uses the delivered CYBR GEO triangle/BVH kernel, not a third-party renderer.
// All appearance comes from intersected geometry, spectral BRDFs and lighting.
#include "spectral_geometry.h"
#include "wide_bvh.h"
#include <cstring>
#include <iomanip>
#include <stdexcept>
#include "texture_adapter.h"
#include "spectrum.h"

struct Frame {
    V t,b,n;
    Frame(V nn):n(nn){t=unit(cross(std::fabs(n.z)<.99f?V(0,0,1):V(0,1,0),n));b=cross(n,t);}
    Frame(V nn,V tangent):n(nn){t=unit(tangent-n*dot(tangent,n));if(len(t)<.5f)t=Frame(n).t;b=cross(n,t);}
    V local(V x)const{return V(dot(x,t),dot(x,b),dot(x,n));}
    V world(V x)const{return t*x.x+b*x.y+n*x.z;}
};
float fresnel(float c,float ei,float et){c=clamp(c);float ss=sqr(ei/et)*(1-c*c);if(ss>=1)return 1;float ct=std::sqrt(1-ss),rs=(ei*c-et*ct)/(ei*c+et*ct),rp=(et*c-ei*ct)/(et*c+ei*ct);return .5f*(rs*rs+rp*rp);}
V refract(V d,V n,float eta){float c=-dot(d,n),k=1-eta*eta*(1-c*c);return k<0?V():unit(d*eta+n*(eta*c-std::sqrt(k)));}
float quartzIndex(float wavelength){float l2=sqr(wavelength*.001f);return std::sqrt(1.28604141f+1.07044083f*l2/(l2-.0100585997f)+1.10202242f*l2/(l2-100.f));}
Spec quartzAbsorb(float metres){Spec a;for(int k=0;k<NBANDS;k++){float w=WL0+(k+.5f)*DL;a.v[k]=std::exp(-metres*(.009f+.018f*std::exp(-.5f*sqr((w-430)/90))));}return a;}
float power(float a,float b){return a*a/(a*a+b*b+1e-30f);}
V sampleSun(RNG&r){float c=1-r.uniform()*(1-SUN_COS),s=std::sqrt(std::max(0.f,1-c*c)),a=2*PI*r.uniform();return Frame(SUN).world(V(s*std::cos(a),s*std::sin(a),c));}
Spec sky(V d){float e=clamp(d.z),h=std::pow(1-e,3.f);return skyBlue*(.70f+.30f*e)+skyHorizon*(.34f*h);}

struct Portal{V c,u,v,n;float area;};
std::array<Portal,2> portals={Portal{V(1.35f,3.17f,2.195f),V(.85f,0,0),V(0,0,1.325f),V(0,1,0),4*.85f*1.325f},Portal{V(-1.78f,-3.81f,2.35f),V(.79f,0,0),V(0,0,1.27f),V(0,-1,0),4*.79f*1.27f}};
float portalWeight(V p){float w[2];for(int i=0;i<2;i++){V v=portals[i].c-p;float l=std::max(.15f,dot(v,v));w[i]=portals[i].area*std::max(.04f,std::fabs(dot(unit(v),portals[i].n)))/l;}return clamp(w[0]/(w[0]+w[1]),.07f,.93f);}
float portalPDF(V p,V d){float sum=0,w=portalWeight(p);for(int i=0;i<2;i++){auto&a=portals[i];float dn=dot(d,a.n);if(std::fabs(dn)<1e-9f)continue;float t=dot(a.c-p,a.n)/dn;if(t<=EPS)continue;V q=p+d*t-a.c;if(std::fabs(dot(q,a.u)/dot(a.u,a.u))>1||std::fabs(dot(q,a.v)/dot(a.v,a.v))>1)continue;sum+=(i?1-w:w)*t*t/(std::fabs(dn)*a.area);}return sum;}
V samplePortal(V p,RNG&r){auto&a=portals[r.uniform()<portalWeight(p)?0:1];return unit(a.c+a.u*(2*r.uniform()-1)+a.v*(2*r.uniform()-1)-p);}
bool closest(const Ray&r,Hit&h){return wideHit(r,h);}
bool shadow(const Ray&r,float far=INF){Hit h;h.t=far;return wideHit(r,h,true);}

const V FOG_LO(-3.6f,-3.60f,.0f),FOG_HI(3.6f,2.77f,5.0f);
float fogSigma=.006f;constexpr float HG_G=.36f;
bool fogInterval(const Ray&r,float far,float&a,float&b){a=0;b=far;for(int k=0;k<3;k++){if(std::fabs(r.d[k])<1e-10f){if(r.o[k]<FOG_LO[k]||r.o[k]>FOG_HI[k])return false;continue;}float x=(FOG_LO[k]-r.o[k])/r.d[k],y=(FOG_HI[k]-r.o[k])/r.d[k];if(x>y)std::swap(x,y);a=std::max(a,x);b=std::min(b,y);if(a>=b)return false;}return b>a;}
float transmittance(const Ray&r,float far=INF){float a,b;return fogInterval(r,far,a,b)?std::exp(-fogSigma*(b-a)):1.f;}
float sampleFog(const Ray&r,float far,RNG&rng){if(fogSigma<=0)return INF;float a,b;if(!fogInterval(r,far,a,b))return INF;float t=a-std::log(std::max(1e-8f,1-rng.uniform()))/fogSigma;return t<b?t:INF;}
float hg(float c){float v=1+HG_G*HG_G-2*HG_G*c;return (1-HG_G*HG_G)/(4*PI*v*std::sqrt(v));}
V sampleHG(V d,RNG&r){float u=r.uniform(),v=(1-HG_G*HG_G)/(1-HG_G+2*HG_G*u);float c=(1+HG_G*HG_G-v*v)/(2*HG_G),s=std::sqrt(std::max(0.f,1-c*c)),phi=2*PI*r.uniform();return unit(Frame(d).world(V(s*std::cos(phi),s*std::sin(phi),c)));}

struct Machining{V center,axis;float anisotropy;};std::vector<Machining> machining;
struct Surface{V color{.4f};float rough=.6f,metal=0,transmission=0,aniso=0;Frame frame{V(0,0,1)};int kind=0;};
Surface shade(V p,V n,V gn,int kind,float footprint,const Hit&hit){
    Surface m;m.kind=kind;m.frame=Frame(n);const auto&t=tris[hit.tri];const auto&a=attributes[hit.tri];
    V tint=a.col[0]*(1-hit.u-hit.v)+a.col[1]*hit.u+a.col[2]*hit.v;m.color=tint;
    if(kind==3||kind==4||kind==5){m.metal=1;m.rough=kind==3?.21f:.30f;m.aniso=kind==3?.48f:.22f;}
    if(kind==8){m.rough=0;m.color=V(.97f);}
    if(kind==12){m.transmission=.58f;m.rough=.86f;}
    if(kind==10){m.color=V(.022f,.017f,.009f);m.rough=.7f;}
    if(a.texture>=0&&a.texture<int(textures.size())){
        float u=a.uv[0].u*(1-hit.u-hit.v)+a.uv[1].u*hit.u+a.uv[2].u*hit.v;
        float v=a.uv[0].v*(1-hit.u-hit.v)+a.uv[1].v*hit.u+a.uv[2].v*hit.v;
        float du1=a.uv[1].u-a.uv[0].u,dv1=a.uv[1].v-a.uv[0].v,du2=a.uv[2].u-a.uv[0].u,dv2=a.uv[2].v-a.uv[0].v;
        float det=du1*dv2-du2*dv1,area=std::max(1e-14f,len(cross(t.e1,t.e2)));float rate=std::sqrt(std::fabs(det)/area);
        Texel tex=textures[a.texture].sample(u,v,std::max(.000001f,footprint*rate));m.color=tex.color*tint;m.rough=tex.rough;if(kind==3)m.color*=V(.91f,.93f,.97f);if(kind==3)m.rough=clamp(m.rough+.072f,.19f,.42f);
        if(std::fabs(det)>1e-9f){
            V tangent=unit((t.e1*dv2-t.e2*dv1)/det),bt=unit((t.e2*du1-t.e1*du2)/det);Frame f(n,tangent);
            float sign=dot(f.b,bt)<0?-1:1;V nn=unit(f.t*tex.normal.x+f.b*(tex.normal.y*sign)+n*std::max(.4f,tex.normal.z));
            // Shading normal stays on the geometric side and never points away
            // from the actual microgeometry at an extreme grazing angle.
            if(dot(nn,gn)<.30f)nn=n;m.frame=Frame(nn,tangent);
        }
    }
    if(m.metal>.5f&&t.group>=0&&t.group<int(machining.size())){const auto &g=machining[t.group];m.aniso=g.anisotropy;V tangent=cross(g.axis,p-g.center);if(len(tangent)>1e-7f)m.frame=Frame(m.frame.n,tangent);else m.aniso=0;}
    m.color=V(clamp(m.color.x,0,.94f),clamp(m.color.y,0,.94f),clamp(m.color.z,0,.94f));m.rough=clamp(m.rough,.11f,.93f);return m;
}
float pSpec(const Surface&m){return m.metal>.5f?1.f:(m.transmission>0?0.f:.23f);}
void alpha(const Surface&m,float&ax,float&ay){float a=std::max(.009f,m.rough*m.rough),aspect=std::sqrt(1-.80f*m.aniso);ax=a/aspect;ay=a*aspect;}
float D(V h,float ax,float ay){if(h.z<=0)return 0;float e=sqr(h.x/ax)+sqr(h.y/ay)+h.z*h.z;return 1/(PI*ax*ay*e*e);}
float G1(V v,float ax,float ay){if(v.z<=0)return 0;return 2/(1+std::sqrt(1+(sqr(ax*v.x)+sqr(ay*v.y))/(v.z*v.z)));}
Spec eval(const Surface&m,const Spec&base,V v,V l){
    v=m.frame.local(v);l=m.frame.local(l);if(v.z<=0)return Spec();
    if(l.z<0)return base*(m.transmission/PI);
    if(l.z<=0)return Spec();V h=unit(v+l);float ax,ay;alpha(m,ax,ay);float f=std::pow(1-clamp(dot(v,h)),5.f);
    Spec F=m.metal>.5f?base+(Spec(1)-base)*f:Spec(fresnel(dot(v,h),1,1.48f));
    Spec spec=F*(D(h,ax,ay)*G1(v,ax,ay)*G1(l,ax,ay)/(4*v.z*l.z));
    if(m.metal>.5f)return spec;
    if(m.transmission>0)return base*((1-m.transmission)/PI);
    float fv=fresnel(v.z,1,1.48f),fl=fresnel(l.z,1,1.48f);
    return base*((1-fv)*(1-fl)/PI)+spec;
}
float pdf(const Surface&m,V v,V l){v=m.frame.local(v);l=m.frame.local(l);if(v.z<=0)return 0;if(m.transmission>0)return std::fabs(l.z)*(l.z>0?1-m.transmission:m.transmission)/PI;if(l.z<=0)return 0;float ax,ay;alpha(m,ax,ay);V h=unit(v+l);float p=pSpec(m);return p*D(h,ax,ay)*G1(v,ax,ay)/(4*v.z)+(1-p)*l.z/PI;}
V sampleBSDF(const Surface&m,V v,RNG&r){
    V vv=m.frame.local(v);float p=pSpec(m);
    if(r.uniform()>p){float u=r.uniform(),phi=2*PI*r.uniform(),rr=std::sqrt(u),z=std::sqrt(1-u);if(m.transmission>0&&r.uniform()<m.transmission)z=-z;return m.frame.world(V(rr*std::cos(phi),rr*std::sin(phi),z));}
    float ax,ay;alpha(m,ax,ay);V vh=unit(V(ax*vv.x,ay*vv.y,std::max(.000001f,vv.z)));float ls=vh.x*vh.x+vh.y*vh.y;
    V t1=ls>0?V(-vh.y,vh.x,0)/std::sqrt(ls):V(1,0,0),t2=cross(vh,t1);float rr=std::sqrt(r.uniform()),phi=2*PI*r.uniform(),x=rr*std::cos(phi),y=rr*std::sin(phi),s=.5f*(1+vh.z);
    y=(1-s)*std::sqrt(std::max(0.f,1-x*x))+s*y;V nh=t1*x+t2*y+vh*std::sqrt(std::max(0.f,1-x*x-y*y));V h=unit(V(ax*nh.x,ay*nh.y,std::max(0.f,nh.z)));return m.frame.world(reflect(-vv,h));
}

struct Result{Spec direct,indirect;Spec total()const{return direct+indirect;}void add(Spec x,bool first){if(first)direct+=x;else indirect+=x;}Result operator*(Spec x)const{return {direct*x,indirect*x};}};
std::atomic<uint64_t> invalidPaths{0};bool dispersion=true;
Result trace(Ray ray,RNG&rng,int maxDepth,float cone,int band=-1,int quartzDepth=0,bool skipFirstFog=false,V prev=V(),float prevPdf=0,bool prevDelta=true,bool primary=true){
    Result out;Spec throughput(1);if(band>=0){throughput=Spec();throughput.v[band]=1;}float footprint=0;
    for(int depth=0;depth<maxDepth;depth++){
        Hit h;bool found=closest(ray,h);float far=found?h.t:INF;
        if(found&&tris[h.tri].mat==8&&band<0&&dispersion){
            Result sum;for(int k=0;k<NBANDS;k++){RNG r=rng;Result a=trace(ray,r,maxDepth-depth,cone,k,quartzDepth,skipFirstFog&&depth==0,prev,prevPdf,prevDelta,primary&&depth==0);sum.direct+=a.direct;sum.indirect+=a.indirect;}
            out.direct+=sum.direct*throughput;out.indirect+=sum.indirect*throughput;return out;
        }
        float ft=quartzDepth==0&&!(skipFirstFog&&depth==0)?sampleFog(ray,far,rng):INF;
        if(ft<far){
            V p=ray.o+ray.d*ft,l=sampleSun(rng);Spec add;
            if(!shadow(Ray(p,l)))add+=solar*(hg(dot(ray.d,l))*SUN_SOLID*transmittance(Ray(p,l)));
            l=samplePortal(p,rng);float lp=portalPDF(p,l),phase=hg(dot(ray.d,l));
            if(lp>1e-9f&&!shadow(Ray(p,l)))add+=sky(l)*(phase*transmittance(Ray(p,l))*power(lp,phase)/lp);
            out.indirect+=throughput*add*.98f;throughput*=.98f;V d=sampleHG(ray.d,rng);prev=p;prevPdf=hg(dot(ray.d,d));prevDelta=false;primary=false;ray=Ray(p,d);cone=std::max(cone,.025f);continue;
        }
        if(!found){
            float w=prevDelta?1:power(prevPdf,portalPDF(prev,ray.d));Spec add=sky(ray.d)*w;
            if(dot(ray.d,SUN)>=SUN_COS)add+=solar*(prevDelta?1:power(prevPdf,1/SUN_SOLID));
            out.add(throughput*add,primary&&depth<=1);break;
        }
        if(quartzDepth>0)throughput*=quartzAbsorb(h.t);
        auto &tr=tris[h.tri];V p=ray.o+ray.d*h.t,gn=unit(cross(tr.e1,tr.e2)),n=unit(tr.n0*(1-h.u-h.v)+tr.n1*h.u+tr.n2*h.v);footprint+=h.t*cone;
        if(tr.mat==8){
            bool enter=dot(ray.d,gn)<0;if(dot(n,gn)<0)n=-n;if(dot(n,ray.d)>0)n=-n;
            float index=quartzIndex(band>=0?WL0+(band+.5f)*DL:550.f),ei=enter?1:index,et=enter?index:1,F=fresnel(-dot(ray.d,n),ei,et);
            if(rng.uniform()<F){ray=Ray(p+n*EPS*8,unit(reflect(ray.d,n)));}
            else{V d=refract(ray.d,n,ei/et);if(dot(d,d)<.5f)ray=Ray(p+n*EPS*8,unit(reflect(ray.d,n)));else{throughput*=sqr(ei/et);quartzDepth=std::max(0,quartzDepth+(enter?1:-1));ray=Ray(p-n*EPS*8,d);}}
            prevDelta=true;continue;
        }
        if(dot(gn,ray.d)>0)gn=-gn;if(dot(n,gn)<0)n=-n;if(dot(n,-ray.d)<.08f)n=gn;
        Surface m=shade(p,n,gn,tr.mat,std::max(.000001f,footprint),h);if(dot(m.frame.n,-ray.d)<.05f)m.frame=Frame(gn,m.frame.t);
        Spec base=rgbAnchors(m.color);V v=-ray.d,l=sampleSun(rng);float cs=dot(m.frame.n,l);Spec illumination;
        auto direct=[&](V ld,bool sun){float cosine=dot(m.frame.n,ld);if(m.transmission<=0&&cosine<=0)return Spec();float ng=dot(gn,ld);if(m.transmission<=0&&ng<=0)return Spec();
            V origin=p+gn*(ng>0?EPS*8:-EPS*8);if(shadow(Ray(origin,ld)))return Spec();float lp=sun?1/SUN_SOLID:portalPDF(p,ld);if(lp<1e-9f)return Spec();float bp=pdf(m,v,ld);
            return eval(m,base,v,ld)*(sun?solar:sky(ld))*(std::fabs(cosine)*transmittance(Ray(origin,ld))*power(lp,bp)/lp);};
        illumination+=direct(l,true);illumination+=direct(samplePortal(p,rng),false);out.add(throughput*illumination,primary&&depth==0);
        V next=sampleBSDF(m,v,rng);float cosine=dot(m.frame.n,next),ng=dot(gn,next),bp=pdf(m,v,next);
        if(bp<1e-12f||(m.transmission<=0&&(cosine<=0||ng<=0)))break;
        throughput*=eval(m,base,v,next)*(std::fabs(cosine)/bp);
        float mx=throughput.maximum();if(!std::isfinite(mx)){invalidPaths++;break;}if(mx<1e-10f)break;
        if(depth>=3){float survive=clamp(mx,.10f,.96f);if(rng.uniform()>survive)break;throughput*=1/survive;}
        prev=p;prevPdf=bp;prevDelta=false;ray=Ray(p+gn*(ng>0?EPS*8:-EPS*8),unit(next));cone=std::max(cone,m.metal>.5f?cone*1.2f:.012f);
    }return out;
}
struct PrimaryResult{Spec direct,indirect,volume;Spec total()const{return direct+indirect+volume;}};
PrimaryResult cameraTrace(Ray ray,RNG&rng,int maxDepth,float cone){
    Hit h;bool found=closest(ray,h);float a,b,far=found?h.t:INF,T=1;
    if(fogSigma>0&&fogInterval(ray,far,a,b))T=std::exp(-fogSigma*(b-a));
    auto r=trace(ray,rng,maxDepth,cone,-1,0,true);PrimaryResult out{r.direct*T,r.indirect*T,Spec()};
    if(T<.999999f){
        float t=a-std::log(std::max(1e-8f,1-rng.uniform()*(1-T)))/fogSigma;V p=ray.o+ray.d*t;Spec light;
        V l=sampleSun(rng);if(!shadow(Ray(p,l)))light+=solar*(hg(dot(ray.d,l))*SUN_SOLID*transmittance(Ray(p,l)));
        l=samplePortal(p,rng);float lp=portalPDF(p,l),hp=hg(dot(ray.d,l));if(lp>1e-9f&&!shadow(Ray(p,l)))light+=sky(l)*(hp*transmittance(Ray(p,l))*power(lp,hp)/lp);
        V next=sampleHG(ray.d,rng);Spec continuation;if(rng.uniform()<.20f){auto cont=trace(Ray(p,next),rng,std::max(2,maxDepth-1),std::max(cone,.012f),-1,0,false,p,hg(dot(ray.d,next)),false,false);continuation=cont.total()*5.f;}
        out.volume=(light+continuation)*((1-T)*.98f);
    }return out;
}
struct Guide{V normal,color;float depth=0,variance=0,material=-1;};
Guide guide(Ray ray,float cone){Hit h;if(!closest(ray,h))return {V(),V(.5f),0,0,-1};auto&t=tris[h.tri];V gn=unit(cross(t.e1,t.e2)),n=unit(t.n0*(1-h.u-h.v)+t.n1*h.u+t.n2*h.v);if(dot(gn,ray.d)>0)gn=-gn;if(dot(n,gn)<0)n=-n;auto s=shade(ray.o+ray.d*h.t,n,gn,t.mat,h.t*cone,h);return {n,s.color,h.t,0,float(t.mat)};}

// Follow the dominant 550-nm dielectric path for reconstruction features.
// This is a geometry-only guide: it never changes the recorded light transport.
Guide transmittedGuide(Ray ray,float cone){
    Guide first=guide(ray,cone);if(int(first.material)!=8)return first;
    float travelled=0;
    for(int depth=0;depth<12;depth++){
        Hit h;if(!closest(ray,h)){first.normal=-ray.d;first.depth=travelled+1000.f;return first;}
        auto &t=tris[h.tri];V p=ray.o+ray.d*h.t,gn=unit(cross(t.e1,t.e2));
        V n=unit(t.n0*(1-h.u-h.v)+t.n1*h.u+t.n2*h.v);travelled+=h.t;
        if(t.mat!=8){if(dot(gn,ray.d)>0)gn=-gn;if(dot(n,gn)<0)n=-n;if(dot(n,-ray.d)<.08f)n=gn;first.normal=n;first.depth=travelled;return first;}
        bool enter=dot(ray.d,gn)<0;if(dot(n,gn)<0)n=-n;if(dot(n,ray.d)>0)n=-n;
        float index=quartzIndex(550.f),ei=enter?1.f:index,et=enter?index:1.f;
        float F=fresnel(-dot(ray.d,n),ei,et);V d=refract(ray.d,n,ei/et);
        if(F>.5f||dot(d,d)<.5f)ray=Ray(p+n*EPS*8,unit(reflect(ray.d,n)));
        else ray=Ray(p-n*EPS*8,d);
    }
    return first;
}

struct Options {std::string mesh,out="render",view="hero";int width=1200,height=800,spp=128,depth=10,threads=5,seed=71833;float exposure=1.7f,aperture=.003f;bool bands=false,adaptive=false,guidesOnly=false;};
Options parse(int argc,char**argv){Options o;for(int i=1;i<argc;i++){std::string s=argv[i];auto val=[&](){if(i+1>=argc)throw std::runtime_error("Missing argument "+s);return std::string(argv[++i]);};if(s=="--mesh")o.mesh=val();else if(s=="--out")o.out=val();else if(s=="--view")o.view=val();else if(s=="--width")o.width=stoi(val());else if(s=="--height")o.height=stoi(val());else if(s=="--spp")o.spp=stoi(val());else if(s=="--depth")o.depth=stoi(val());else if(s=="--threads")o.threads=stoi(val());else if(s=="--seed")o.seed=stoi(val());else if(s=="--exposure")o.exposure=stof(val());else if(s=="--aperture")o.aperture=stof(val());else if(s=="--fog")fogSigma=stof(val());else if(s=="--no-dispersion")dispersion=false;else if(s=="--bands")o.bands=true;else if(s=="--adaptive")o.adaptive=true;else if(s=="--guides-only")o.guidesOnly=true;else throw std::runtime_error("Unknown option "+s);}
if(o.mesh.empty()||o.width<1||o.height<1||o.width>8192||o.height>8192||o.spp<1||o.depth<1||o.threads<1||fogSigma<0)throw std::runtime_error("Invalid settings");return o;}
V display(V a,float exposure){a=V(a.x/whiteRGB.x,a.y/whiteRGB.y,a.z/whiteRGB.z)*exposure;for(int k=0;k<3;k++){float x=std::max(0.f,a[k]);x=clamp((x*(2.51f*x+.03f))/(x*(2.43f*x+.59f)+.14f));a[k]=x<=.0031308f?12.92f*x:1.055f*std::pow(x,1/2.4f)-.055f;}return a;}
int selftest(){initSpectra();float mx=0;for(int metal=0;metal<2;metal++)for(float rough:{.16f,.3f,.65f})for(float z:{.15f,.55f,1.f}){
    Surface m;m.color=V(.75f);m.metal=metal;m.rough=rough;m.aniso=.48f;Spec base(.75f);V v(std::sqrt(1-z*z),0,z);RNG rng(7183);double energy=0;int N=60000;
    for(int i=0;i<N;i++){V l=sampleBSDF(m,v,rng);float p=pdf(m,v,l);if(p>1e-12f){Spec f=eval(m,base,v,l);energy+=f.v[8]*std::max(0.f,l.z)/p;}}
    float e=float(energy/N);mx=std::max(mx,e);if(e>1.018f||e<0||!std::isfinite(e))throw std::runtime_error("White furnace failure "+std::to_string(e));}
    if(std::fabs(fresnel(1,1,1.5f)-.04f)>1e-6f)throw std::runtime_error("Fresnel failure");V r=refract(unit(V(.5,0,-.8660254f)),V(0,0,1),1/1.5f);if(std::fabs(r.x-1.f/3)>1e-5)throw std::runtime_error("Snell failure");
    if(!(quartzIndex(400)>quartzIndex(550)&&quartzIndex(550)>quartzIndex(700)))throw std::runtime_error("Quartz dispersion failure");
    double sum=0;V p(0,0,1.5);RNG rng(3821);int N=500000;for(int i=0;i<N;i++){float z=1-2*rng.uniform(),phi=2*PI*rng.uniform(),rr=std::sqrt(std::max(0.f,1-z*z));V d(rr*std::cos(phi),rr*std::sin(phi),z);sum+=portalPDF(p,d)*4*PI;}if(std::fabs(sum/N-1)>.025)throw std::runtime_error("Portal PDF normalization failure");
    std::cout<<std::setprecision(9)<<"{\"passed\":true,\"white_furnace_maximum\":"<<mx<<",\"portal_pdf_integral\":"<<sum/N<<",\"fresnel_normal\":"<<fresnel(1,1,1.5f)<<",\"quartz_ior_400\":"<<quartzIndex(400)<<",\"quartz_ior_700\":"<<quartzIndex(700)<<"}\n";return 0;}

int main(int argc,char**argv){try{
    if(argc==2&&std::string(argv[1])=="--self-test")return selftest();Options o=parse(argc,argv);omp_set_num_threads(o.threads);initSpectra();auto started=std::chrono::steady_clock::now();
    std::ifstream f(o.mesh,std::ios::binary);char magic[4];f.read(magic,4);uint32_t count;f.read((char*)&count,4);if(!f||memcmp(magic,"CVR2",4)||count>20000000)throw std::runtime_error("Invalid CVR2 geometry");
    tris.reserve(count);attributes.reserve(count);for(uint32_t i=0;i<count;i++){float a[36];f.read((char*)a,144);if(!f)throw std::runtime_error("Truncated mesh");for(float x:a)if(!std::isfinite(x))throw std::runtime_error("Nonfinite geometry");Tri t;t.p=V(a[0],a[1],a[2]);t.e1=V(a[3],a[4],a[5])-t.p;t.e2=V(a[6],a[7],a[8])-t.p;t.n0=V(a[9],a[10],a[11]);t.n1=V(a[12],a[13],a[14]);t.n2=V(a[15],a[16],a[17]);t.mat=int(a[18]);t.group=int(a[19]);if(t.mat<0||t.mat>12)throw std::runtime_error("Unknown material");Attribute at;for(int j=0;j<3;j++){at.uv[j]={a[20+j*2],a[21+j*2]};at.col[j]=V(a[26+j*3],a[27+j*3],a[28+j*3]);}at.texture=int(a[35]);if(dot(cross(t.e1,t.e2),cross(t.e1,t.e2))>1e-22f){tris.push_back(t);attributes.push_back(at);}}
    std::string root=o.mesh.substr(0,o.mesh.find_last_of("/\\"));textures.resize(11);for(int i=0;i<11;i++)textures[i].load(root+"/textures/"+std::to_string(i)+".cvtex");
    {std::string gp=o.mesh.substr(0,o.mesh.find_last_of("."))+".groups";std::ifstream input(gp,std::ios::binary);uint32_t ng=0;input.read((char*)&ng,4);if(!input||ng>100000)throw std::runtime_error("Missing/invalid machining groups");machining.resize(ng);input.read((char*)machining.data(),ng*sizeof(Machining));if(!input)throw std::runtime_error("Truncated machining groups");}
    order.resize(tris.size());std::iota(order.begin(),order.end(),0);nodes.reserve(tris.size()/2);build(0,int(order.size()));
    {std::vector<Tri> ts;std::vector<Attribute> as;ts.reserve(tris.size());as.reserve(tris.size());for(int i:order){ts.push_back(tris[i]);as.push_back(attributes[i]);}tris.swap(ts);attributes.swap(as);std::iota(order.begin(),order.end(),0);}buildWide();
    for(int i=0;i<3000;i++){RNG rng(i+4);Ray r(V(rng.uniform()*8-4,rng.uniform()*9-4,rng.uniform()*6),unit(V(rng.uniform()*2-1,rng.uniform()*2-1,rng.uniform()*2-1)));Hit a,b;bool aa=closest(r,a),bb=meshHitReference(r,b);if(aa!=bb||(aa&&std::fabs(a.t-b.t)>2e-4f))throw std::runtime_error("Wide BVH mismatch");}
    std::cerr<<"Loaded "<<tris.size()<<" triangles. 3000 BVH comparison rays passed.\n";
    V camera(-.95f,-3.28f,2.38f),target(-.20f,.43f,1.51f);float hfov=62;
    if(o.view=="instrument"){camera=V(-1.52f,-1.64f,1.98f);target=V(-.39f,.15f,1.52f);hfov=42;}
    else if(o.view=="workbench"){camera=V(1.86f,-1.79f,2.19f);target=V(-.29f,.06f,1.40f);hfov=55;}
    else if(o.view=="same_camera"){camera=V(-2.8f,-4.85f,2.45f);target=V(.15f,.6f,1.8f);hfov=57;}
    else if(o.view!="hero")throw std::runtime_error("Unknown view");
    V forward=unit(target-camera),right=unit(cross(forward,V(0,0,1))),up=cross(right,forward);float th=std::tan(hfov*PI/360),aspect=float(o.width)/o.height,focus=len(target-camera),cone=2*th/o.width;
    if(o.guidesOnly){
        std::vector<Guide> features(size_t(o.width)*o.height);
        #pragma omp parallel for schedule(dynamic,1)
        for(int y=0;y<o.height;y++)for(int x=0;x<o.width;x++){
            float gx=(2*(x+.5f)/o.width-1)*th,gy=(1-2*(y+.5f)/o.height)*th/aspect;
            features[size_t(y)*o.width+x]=transmittedGuide(Ray(camera,unit(forward+right*gx+up*gy)),cone);
        }
        std::ofstream fg(o.out+"_transmitted.guides",std::ios::binary);uint32_t sz[2]={(uint32_t)o.width,(uint32_t)o.height};fg.write((char*)sz,8);fg.write((char*)features.data(),features.size()*sizeof(Guide));
        if(!fg)throw std::runtime_error("Cannot write transmitted guides");
        std::cerr<<"WROTE dominant-path geometry guides in "<<std::chrono::duration<float>(std::chrono::steady_clock::now()-started).count()<<" s\n";return 0;
    }
    size_t np=size_t(o.width)*o.height;std::vector<Spec> film(np),directFilm(np),indirectFilm(np),volumeFilm(np);std::vector<Guide> guides(np);std::vector<uint32_t> sampleCounts(np);std::atomic<int> rows{0};
    #pragma omp parallel for schedule(dynamic,1)
    for(int y=0;y<o.height;y++){
        for(int x=0;x<o.width;x++){size_t id=size_t(y)*o.width+x;RNG rng(id*728172ULL+o.seed);Spec sum,ds,is,vs;double lum2=0;
            float gx=(2*(x+.5f)/o.width-1)*th,gy=(1-2*(y+.5f)/o.height)*th/aspect;Guide first=guide(Ray(camera,unit(forward+right*gx+up*gy)),cone);int spp=o.spp;if(o.adaptive){int mat=int(first.material);spp=(mat<0)?16:((mat==3||mat==4||mat==5)?o.spp*3:(mat==8?o.spp*8:std::max(32,o.spp*3/4)));}sampleCounts[id]=spp;
            for(int s=0;s<spp;s++){rng.beginSample(s,mix32(uint32_t(id)^uint32_t(o.seed)));float px=(2*(x+rng.uniform())/o.width-1)*th,py=(1-2*(y+rng.uniform())/o.height)*th/aspect;V d=unit(forward+right*px+up*py),origin=camera;
                if(o.aperture>0){float r=std::sqrt(rng.uniform())*o.aperture,phi=2*PI*rng.uniform();V offset=right*(r*std::cos(phi))+up*(r*std::sin(phi)),fp=camera+d*(focus/dot(d,forward));origin+=offset;d=unit(fp-origin);}
                PrimaryResult pr=cameraTrace(Ray(origin,d),rng,o.depth,cone);Spec val=pr.total();bool ok=true;for(float z:val.v)ok=ok&&std::isfinite(z);if(!ok){invalidPaths++;continue;}sum+=val;ds+=pr.direct;is+=pr.indirect;vs+=pr.volume;float l=xyz(val).y;lum2+=double(l)*l;
            }
            float inv=1.f/spp;film[id]=sum*inv;directFilm[id]=ds*inv;indirectFilm[id]=is*inv;volumeFilm[id]=vs*inv;float px=(2*(x+.5f)/o.width-1)*th,py=(1-2*(y+.5f)/o.height)*th/aspect;Guide g=guide(Ray(camera,unit(forward+right*px+up*py)),cone);double avg=xyz(film[id]).y;g.variance=std::max(0.,(lum2*inv-avg*avg)/std::max(1,spp-1));guides[id]=g;
        }
        int done=++rows;if(done%std::max(1,o.height/20)==0){float sec=std::chrono::duration<float>(std::chrono::steady_clock::now()-started).count();
            #pragma omp critical
            std::cerr<<100*done/o.height<<"% "<<sec<<" s\n";}
    }
    auto write=[&](std::string suffix,const std::vector<Spec>&buffer){std::ofstream f(o.out+suffix+".pfm",std::ios::binary);f<<"PF\n"<<o.width<<" "<<o.height<<"\n-1.0\n";for(int y=o.height-1;y>=0;y--)for(int x=0;x<o.width;x++){V rgb=toRGB(buffer[size_t(y)*o.width+x]);f.write((char*)&rgb,12);}if(!f)throw std::runtime_error("Cannot write film");};
    write("",film);write("_direct",directFilm);write("_indirect",indirectFilm);write("_volume",volumeFilm);
    std::ofstream pp(o.out+".ppm",std::ios::binary);pp<<"P6\n"<<o.width<<" "<<o.height<<"\n255\n";for(auto s:film){V c=display(toRGB(s),o.exposure);for(int k=0;k<3;k++){unsigned char b=(unsigned char)(clamp(c[k])*255+.5f);pp.write((char*)&b,1);}}
    std::ofstream gf(o.out+".guides",std::ios::binary);uint32_t dim[2]={(uint32_t)o.width,(uint32_t)o.height};gf.write((char*)dim,8);gf.write((char*)guides.data(),guides.size()*sizeof(Guide));
    {std::ofstream sc(o.out+".samples",std::ios::binary);sc.write((char*)dim,8);sc.write((char*)sampleCounts.data(),sampleCounts.size()*4);}
    if(o.bands){std::ofstream sp(o.out+".spectral",std::ios::binary);uint32_t h[]={0x36315053,(uint32_t)o.width,(uint32_t)o.height,16};sp.write((char*)h,16);sp.write((char*)film.data(),film.size()*sizeof(Spec));}
    float seconds=std::chrono::duration<float>(std::chrono::steady_clock::now()-started).count();
    std::ofstream meta(o.out+".json");meta<<std::setprecision(9)<<"{\n\"renderer\":\"CYBR Observatory IV native CPU spectral tracer\",\n\"width\":"<<o.width<<",\"height\":"<<o.height<<",\"spp\":"<<o.spp<<",\"max_depth\":"<<o.depth<<",\"threads\":"<<o.threads<<",\"seed\":"<<o.seed<<",\n\"view\":\""<<o.view<<"\",\"seconds\":"<<seconds<<",\"triangles\":"<<tris.size()<<",\"spectral_bands\":16,\"dispersion\":"<<(dispersion?"true":"false")<<",\"fog_density_m_inverse\":"<<fogSigma<<",\n\"camera\":["<<camera.x<<","<<camera.y<<","<<camera.z<<"],\"target\":["<<target.x<<","<<target.y<<","<<target.z<<"],\"horizontal_fov_degrees\":"<<hfov<<",\"aperture_radius_m\":"<<o.aperture<<",\n\"exposure\":"<<o.exposure<<",\"film_white_rgb\":["<<whiteRGB.x<<","<<whiteRGB.y<<","<<whiteRGB.z<<"],\n\"nonfinite_paths\":"<<invalidPaths.load()<<",\"clamped_path_contributions\":0,\"image_generation\":false,\"texture_synthesis\":\"deterministic mathematical material maps, no learned model\",\"spectral_method\":\"16 fixed midpoint bins; common-random-number splitting at first quartz interface\",\"polarization_and_birefringence\":false,\"raw_outputs_modified\":false,\"bvh_equivalence_rays_passed\":3000\n}\n";
    std::cerr<<"WROTE "<<o.out<<" in "<<seconds<<" s. Invalid paths "<<invalidPaths.load()<<"\n";return invalidPaths?2:0;
}catch(const std::exception&e){std::cerr<<"ERROR: "<<e.what()<<"\n";return 1;}}
