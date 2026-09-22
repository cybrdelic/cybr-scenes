#include "surface_detail.hpp"
#include <numeric>
#include <atomic>
#include <cstdint>
// CYBR GEO / GPL-2.0-only
// Native spectral landscape extension. Reuses CYBR GEO's actual BVH and mesh
// intersection implementation, with metre-native tolerances. CC0 grayscale albedo detail.
// 16 wavelength bands are transported jointly. Water IOR is deliberately
// achromatic: wavelength-dependent absorption is NOT called dispersion.
#include "spectral_geometry.h"
#include <stdexcept>
#include "bvh8_recovery.h"
#include <array>
#include <iomanip>
#include <stdexcept>
#include <cstring>
#include "photographic_grain.h"
#include "granular_relief_v11.h"

constexpr int NBANDS=16;
constexpr float WL0=380.f, DL=25.f, WATER_IOR=1.334f;
struct Spec {
    std::array<float,NBANDS> v{};
    Spec()=default;
    explicit Spec(float x){v.fill(x);}
    Spec operator+(const Spec&b)const{Spec r;for(int k=0;k<NBANDS;k++)r.v[k]=v[k]+b.v[k];return r;}
    Spec operator-(const Spec&b)const{Spec r;for(int k=0;k<NBANDS;k++)r.v[k]=v[k]-b.v[k];return r;}
    Spec operator*(const Spec&b)const{Spec r;for(int k=0;k<NBANDS;k++)r.v[k]=v[k]*b.v[k];return r;}
    Spec operator*(float b)const{Spec r;for(int k=0;k<NBANDS;k++)r.v[k]=v[k]*b;return r;}
    Spec& operator+=(const Spec&b){for(int k=0;k<NBANDS;k++)v[k]+=b.v[k];return *this;}
    Spec& operator*=(const Spec&b){for(int k=0;k<NBANDS;k++)v[k]*=b.v[k];return *this;}
    Spec& operator*=(float b){for(int k=0;k<NBANDS;k++)v[k]*=b;return *this;}
    float maximum()const{float m=0;for(float x:v)m=std::max(m,x);return m;}
};
std::array<V,NBANDS> matching;
Spec solar,skyBlue,skyHorizon,waterSigma;
V whiteRGB, SUN=unit(V(-.91f,.30f,.34f));
constexpr float SUN_RADIUS=.00465f;
const float SUN_COS=std::cos(SUN_RADIUS), SUN_SOLID=2*PI*(1-SUN_COS);
int sceneStyle=0;
bool skyNEE6=true;
bool useSteam=false,useWater=true;float waterStrength=1.f;
float sceneSunScale=1.f,sceneSkyScale=1.f;

// Analytic approximation to the CIE 1931 matching functions (Wyman et al.).
float gaussian(float wavelength,float mean,float left,float right){
    float t=(wavelength-mean)*(wavelength<mean?left:right);
    return std::exp(-.5f*t*t);
}
V cie1931(float w){
    return {1.056f*gaussian(w,599.8f,.0264f,.0323f)+.362f*gaussian(w,442.f,.0624f,.0374f)-.065f*gaussian(w,501.1f,.0490f,.0382f),
            .821f*gaussian(w,568.8f,.0213f,.0247f)+.286f*gaussian(w,530.9f,.0613f,.0322f),
            1.217f*gaussian(w,437.f,.0845f,.0278f)+.681f*gaussian(w,459.f,.0385f,.0725f)};
}
V xyz(const Spec&s){V out;for(int k=0;k<NBANDS;k++)out+=matching[k]*s.v[k];return out;}
V toRGB(const Spec&s){V t=xyz(s);return {3.2406f*t.x-1.5372f*t.y-.4986f*t.z,-.9689f*t.x+1.8758f*t.y+.0415f*t.z,.0557f*t.x-.2040f*t.y+1.0570f*t.z};}
Spec blackbody(float temperature){
    Spec s;
    for(int k=0;k<NBANDS;k++){
        double w=(WL0+(k+.5)*DL)*1.e-9;
        s.v[k]=float(1.e-28/(std::pow(w,5)*std::expm1(.01438776877/(w*temperature))));
    }
    return s*(1.f/xyz(s).y);
}
Spec rawRGBAnchors(V c){
    // Authored smooth reflectance spectrum, not a measured mineral spectrum.
    Spec s;
    for(int k=0;k<NBANDS;k++){
        float w=WL0+(k+.5f)*DL;
        float b=clamp((w-465.f)/90.f);b=b*b*(3-2*b);
        float r=clamp((w-550.f)/95.f);r=r*r*(3-2*r);
        s.v[k]=clamp(c.z*(1-b)+c.y*b*(1-r)+c.x*r,0,.985f);
    }
    return s;
}

// Calibrate the smooth anchor basis to the declared linear-RGB albedo under a
// 6500 K reference illuminant. This removes unintended hue shifts introduced by
// treating R/G/B channel values as spectral control points directly. Gamut
// clipping is explicit; the result is still authored, not a measured spectrum.
std::array<V,3> RGB_TO_ANCHORS={V(1,0,0),V(0,1,0),V(0,0,1)};
void initReflectanceCalibration(){
    Spec reference=blackbody(6500.f);V white=toRGB(reference);
    // Half-strength basis probes stay below the reflectance ceiling: clipping a
    // unit probe would bias the calibration matrix before its inversion.
    V r=toRGB(rawRGBAnchors(V(.5f,0,0))*reference)*2;
    V g=toRGB(rawRGBAnchors(V(0,.5f,0))*reference)*2;
    V b=toRGB(rawRGBAnchors(V(0,0,.5f))*reference)*2;
    r=V(r.x/white.x,r.y/white.y,r.z/white.z);
    g=V(g.x/white.x,g.y/white.y,g.z/white.z);
    b=V(b.x/white.x,b.y/white.y,b.z/white.z);
    float determinant=dot(r,cross(g,b));
    if(std::fabs(determinant)<1e-6f)throw std::runtime_error("Singular spectral albedo basis");
    RGB_TO_ANCHORS={cross(g,b)/determinant,cross(b,r)/determinant,cross(r,g)/determinant};
}
Spec rgbAnchors(V color){
    V a(dot(RGB_TO_ANCHORS[0],color),dot(RGB_TO_ANCHORS[1],color),dot(RGB_TO_ANCHORS[2],color));
    return rawRGBAnchors(vmin(vmax(a,V(0)),V(.985f)));
}

#include "single_scatter_sky.h"
void initSpectra(){
    float y=0;
    for(int k=0;k<NBANDS;k++){matching[k]=cie1931(WL0+(k+.5f)*DL)*DL;y+=matching[k].y;}
    for(auto &c:matching)c=c/y;
    solar=blackbody(4350.f)*(4.1f/SUN_SOLID);
    skyBlue=blackbody(6500.f);
    for(int k=0;k<NBANDS;k++)skyBlue.v[k]*=std::pow(550.f/(WL0+(k+.5f)*DL),3.7f);
    skyBlue*=1.f/xyz(skyBlue).y;skyHorizon=blackbody(7600.f);
    whiteRGB=toRGB(blackbody(6500.f));
    initReflectanceCalibration();
    buildPhysicalSky();
    solar*=sceneSunScale; for(auto &entry:skyLUT)entry*=sceneSkyScale;
    // Representative absorption controls [1/metre], not certified measurements.
    const float wl[]={380,400,425,450,475,500,525,550,575,600,625,650,675,700,725,750,780};
    const float a[]={.016,.0066,.0048,.0092,.0121,.0204,.040,.0565,.084,.222,.280,.340,.448,.624,1.06,2.47,2.6};
    for(int k=0;k<NBANDS;k++){
        float w=WL0+(k+.5f)*DL;int i=0;while(i<15&&wl[i+1]<w)i++;
        float t=(w-wl[i])/(wl[i+1]-wl[i]);
        waterSigma.v[k]=a[i]*(1-t)+a[i+1]*t+.015f;
    }
}
Spec attenuation(float metres){Spec s;for(int k=0;k<NBANDS;k++)s.v[k]=std::exp(-waterSigma.v[k]*metres*waterStrength);return s;}

uint32_t hash3(int x,int y,int z){
    uint32_t h=uint32_t(x)*374761393u+uint32_t(y)*668265263u+uint32_t(z)*2147483647u+1274126177u;
    h=(h^(h>>13))*1274126177u;return h^(h>>16);
}
float noise(V p){
    int ix=int(std::floor(p.x)),iy=int(std::floor(p.y)),iz=int(std::floor(p.z));
    float x=p.x-ix,y=p.y-iy,z=p.z-iz;x=x*x*(3-2*x);y=y*y*(3-2*y);z=z*z*(3-2*z);
    float value=0;
    for(int a=0;a<2;a++)for(int b=0;b<2;b++)for(int c=0;c<2;c++)
        value+=(float(hash3(ix+a,iy+b,iz+c))*(2.f/4294967295.f)-1)*(a?x:1-x)*(b?y:1-y)*(c?z:1-z);
    return value;
}
float noise(float x,float y){return noise(V(x,y,0));}
float fbm(V p){return noise(p)+.5f*noise(p*2.07f+V(11,-7,.31f))+.25f*noise(p*4.2849f+V(22,-14,.62f));}
struct Pool{float x,y,rx,ry,level,depth;};
std::array<Pool,2> pools={Pool{.5f,1.f,4.1f,4.05f,.055f,1.48f},Pool{-3.5f,10.f,2.2f,1.65f,.245f,.73f}};
float poolQ(V p,int i){
    const auto &k=pools[i];
    return std::max(std::fabs((p.x-k.x)/k.rx),std::fabs((p.y-k.y)/k.ry));
}
void configureScene(){
    // The second water enclosure is deliberately outside all three scenes.
    pools[1]=Pool{10000,10000,1,1,0,1};
    if(sceneStyle==0){useWater=false;pools[0]=Pool{0,0,1,1,0,1};}
    if(sceneStyle==1)pools[0]=Pool{10,40,100,160,0,8};
    if(sceneStyle==2)pools[0]=Pool{0,20,18,55,0,1};
}
#include "scene_ripples.h"

float fresnelD(float cosine,float ei,float et){
    cosine=clamp(cosine);float sin2=ei*ei/(et*et)*(1-cosine*cosine);if(sin2>=1)return 1;
    float ct=std::sqrt(1-sin2),rs=(ei*cosine-et*ct)/(ei*cosine+et*ct),rp=(et*cosine-ei*ct)/(et*cosine+ei*ct);
    return .5f*(rs*rs+rp*rp);
}
V refractRay(V d,V n,float eta){
    float c=-dot(d,n),k=1-eta*eta*(1-c*c);if(k<0)return V(0);
    return unit(d*eta+n*(eta*c-std::sqrt(k)));
}
struct Frame{
    V t,b,n;
    explicit Frame(V normal):n(normal){t=unit(cross(std::fabs(n.z)<.99f?V(0,0,1):V(0,1,0),n));b=cross(n,t);}
    V local(V a)const{return {dot(a,t),dot(a,b),dot(a,n)};}
    V world(V a)const{return t*a.x+b*a.y+n*a.z;}
};
V sampleSun(RNG&rng){Frame f(SUN);float c=1-rng.uniform()*(1-SUN_COS),s=std::sqrt(std::max(0.f,1-c*c)),a=2*PI*rng.uniform();return unit(f.world(V(s*std::cos(a),s*std::sin(a),c)));}
Spec environment(V d,bool solarVisible){
    Spec s=physicalSky(d);
    if(solarVisible&&dot(d,SUN)>=SUN_COS)s+=solar;
    return s;
}


bool closest(const Ray&r,Hit&h){
    bool ok=meshHitWideR3(r,h);
    if(!useWater&&ok&&tris[h.tri].mat>=6&&tris[h.tri].mat<=7){
        V origin=r.o+r.d*(h.t+EPS*4);float travelled=h.t+EPS*4;Hit next;
        for(int i=0;i<8;i++){
            if(!meshHitWideR3(Ray(origin,r.d),next))return false;
            if(tris[next.tri].mat<6||tris[next.tri].mat>7){next.t+=travelled;h=next;return true;}
            float step=next.t+EPS*4;origin+=r.d*step;travelled+=step;next=Hit();
        }return false;
    }return ok;
}
bool opaqueShadow(Ray r,float distance){
    Hit h;h.t=distance;return meshHitWideR3(r,h,true,true);
}

// Bounded, genuinely ray-integrated participating medium. This is a procedural
// density field, NOT a Navier-Stokes/thermal plume simulation or a 2-D overlay.
const V FOG_LO(-8,-4.8f,.055f),FOG_HI(8.4f,13.4f,3.6f);
constexpr float STEAM_SCALE=.95f,MAJORANT=.85f,PHASE_G=.63f;
bool fogInterval(const Ray&r,float maximum,float &a,float &b){
    a=0;b=maximum;
    for(int k=0;k<3;k++){
        if(std::fabs(r.d[k])<1.e-9f){if(r.o[k]<FOG_LO[k]||r.o[k]>FOG_HI[k])return false;continue;}
        float x=(FOG_LO[k]-r.o[k])/r.d[k],y=(FOG_HI[k]-r.o[k])/r.d[k];if(x>y)std::swap(x,y);
        a=std::max(a,x);b=std::min(b,y);if(a>=b)return false;
    }return b>a;
}
float steamAnalytic(V p){
    if(!useSteam)return 0;
    float density=0;
    for(int i=0;i<2;i++){
        const auto&pool=pools[i];float h=p.z-pool.level;
        if(h<.018f||h>3.15f)continue;
        float xx=(p.x-pool.x-.28f*h)/pool.rx,yy=(p.y-pool.y-.14f*h)/pool.ry;
        float str=clamp(.44f+.40f*fbm(V(p.x*2.f+h*.7f,p.y*2.f,h*2.6f)));
        density+=.028f*std::exp(-2*(xx*xx+yy*yy)-h*1.8f)*str;
        for(int plume=0;plume<3;plume++){
            float offsetx=plume==0?-.9f:(plume==1?.9f:.1f);
            float offsety=plume==0?.45f:(plume==1?.20f:1.f);
            float ax=p.x-pool.x-offsetx-.35f*h-.12f*std::sin(h*4+plume);
            float ay=p.y-pool.y-offsety-.12f*h;
            float width=.40f+h*.19f;
            float shape=std::exp(-(ax*ax+ay*ay)/(width*width)-h*.95f);
            density+=.46f*shape*(.15f+.85f*str*str);
        }
    }return density*STEAM_SCALE;
}
#include "steam_volume_v11.h"

float sampleSteam(const Ray&r,float maxT,RNG&rng){
    if(!useSteam)return INF;float a,b;if(!fogInterval(r,maxT,a,b))return INF;
    float t=a;const float majorant=trackingSteamMajorant();if(majorant<=0)return INF;
    for(int k=0;k<1024;k++){
        t+=-std::log(std::max(1e-8f,1-rng.uniform()))/majorant;
        if(t>=b)return INF;
        if(rng.uniform()<steamDensity(r.o+r.d*t)/majorant)return t;
    }return INF;
}
float steamTransmittance(const Ray&r,float maxT,RNG&rng){
    if(!useSteam)return 1;float a,b;if(!fogInterval(r,maxT,a,b))return 1;
    float t=a,tr=1;const float majorant=trackingSteamMajorant();if(majorant<=0)return 1;
    for(int k=0;k<1024;k++){
        t+=-std::log(std::max(1e-8f,1-rng.uniform()))/majorant;if(t>=b)return tr;
        tr*=std::max(0.f,1-steamDensity(r.o+r.d*t)/majorant);
        if(tr<1.e-5f)return 0;
    }return tr;
}

#include "cloud_volume_v9.h"
#include "scene_haze.h"
float airTransmittance(const Ray&r,float maxT,RNG&rng){
    float a,b,tr=steamTransmittance(r,maxT,rng)*cloudTransmittance(r,maxT,rng);
    if(atmosphereInterval(r,maxT,a,b))tr*=float(std::exp(-atmosphereDepth(r,a,b)));
    return tr;
}
float phaseHG(float c,float g=PHASE_G){float v=1+g*g-2*g*c;return (1-g*g)/(4*PI*v*std::sqrt(v));}
V sampleHG(V d,RNG&rng,float g=PHASE_G){
    float u=rng.uniform(),v=(1-g*g)/(1-g+2*g*u);
    float c=(1+g*g-v*v)/(2*g),ss=std::sqrt(std::max(0.f,1-c*c)),a=2*PI*rng.uniform();
    return unit(Frame(d).world(V(ss*std::cos(a),ss*std::sin(a),c)));
}


struct Surface{V color;float rough=.65f;float ior=1.5f;int kind=0;};
float G1(float cosine,float alpha){return cosine>0?2*cosine/(cosine+std::sqrt(alpha*alpha+(1-alpha*alpha)*cosine*cosine)):0;}
float Dggx(float nh,float alpha){float a=alpha*alpha;return a/(PI*sqr(nh*nh*(a-1)+1));}
float specProbability(const Surface&m){return m.rough<.35f?.44f:.19f;}
Spec evalBSDF(const Surface&m,const Spec&base,V n,V v,V l){
    float nv=dot(n,v),nl=dot(n,l);if(nv<=0||nl<=0)return Spec();
    V h=unit(v+l);float a=std::max(.018f,m.rough*m.rough);
    float fr=fresnelD(clamp(dot(v,h)),1,m.ior);
    float sigma=m.rough*.52f,s2=sigma*sigma;
    float A=1-s2/(2*(s2+.33f)),B=.45f*s2/(s2+.09f);
    float vi=std::sqrt(std::max(0.f,1-nv*nv)),li=std::sqrt(std::max(0.f,1-nl*nl));
    float cosPhi=vi*li>1e-8f?std::max(0.f,(dot(v,l)-nv*nl)/(vi*li)):0.f;
    float sinAlpha=std::max(vi,li),tanBeta=std::min(vi/std::max(nv,1e-5f),li/std::max(nl,1e-5f));
    float oren=A+B*cosPhi*sinAlpha*tanBeta;
    return base*((1-fr)*oren/PI)+Spec(fr*Dggx(clamp(dot(n,h)),a)*G1(nv,a)*G1(nl,a)/(4*nv*nl));
}
float pdfBSDF(const Surface&m,V n,V v,V l){
    float nv=dot(n,v),nl=dot(n,l);if(nv<=0||nl<=0)return 0;
    V h=unit(v+l);float a=std::max(.018f,m.rough*m.rough),p=specProbability(m);
    return p*Dggx(clamp(dot(n,h)),a)*G1(nv,a)/(4*nv)+(1-p)*nl/PI;
}
V sampleBSDF(const Surface&m,V n,V v,RNG&rng){
    Frame frame(n);V vv=frame.local(v);
    if(rng.uniform()>specProbability(m)){
        float u=rng.uniform(),phi=2*PI*rng.uniform(),r=std::sqrt(u);
        return frame.world(V(r*std::cos(phi),r*std::sin(phi),std::sqrt(1-u)));
    }
    float alpha=std::max(.018f,m.rough*m.rough);
    V vh=unit(V(alpha*vv.x,alpha*vv.y,std::max(0.f,vv.z)));
    float lensq=vh.x*vh.x+vh.y*vh.y;
    V t1=lensq>0?V(-vh.y,vh.x,0)/std::sqrt(lensq):V(1,0,0),t2=cross(vh,t1);
    float r=std::sqrt(rng.uniform()),phi=2*PI*rng.uniform(),x=r*std::cos(phi),y=r*std::sin(phi),s=.5f*(1+vh.z);
    y=(1-s)*std::sqrt(std::max(0.f,1-x*x))+s*y;
    V nh=t1*x+t2*y+vh*std::sqrt(std::max(0.f,1-x*x-y*y));
    V h=unit(V(alpha*nh.x,alpha*nh.y,std::max(0.f,nh.z)));
    return frame.world(reflect(-vv,h));
}
float smooth(float a,float b,float x){float t=clamp((x-a)/(b-a));return t*t*(3-2*t);}
// Correlated sediment deposition, mineral staining and mesoscopic grain.
// All coordinates are metres; tiny grains are footprint filtered.
// Correlated position/elevation driven mixtures. The retained CC0 grayscale
// photograph is only a weak albedo modulation, never a backdrop or a render.
#define shade shadeLegacyR5
#include "formation_materials_r4.h"
#undef shade
#include "fernwater_materials_r6.h"

// A numerical Snell-law connection to the displaced water heightfield.
// The finite-difference solid-angle Jacobian includes local wave focusing.
// This owns one-interface floor -> water -> solar-disc paths; continuation
// paths of that class do not add the sun a second time.
struct Connection{V q,l,n;float jacobian=0;bool valid=false;};
// Damped Newton solve, with a measured residual. The old fixed-point update
// admitted unconverged connections, producing false bright/folded caustics.
Connection waterConnection(V p,V air,int pool,bool computeJac=true){
    Connection c;const auto&a=pools[pool];
    V w=-refractRay(-air,V(0,0,1),1/WATER_IOR);if(w.z<=.04f)return c;
    V q=p+w*((a.level-p.z)/w.z);
    auto residual=[&](V at){
        V n=waterNormal(at.x,at.y,pool),dir=-refractRay(-air,n,1/WATER_IOR);
        if(dir.z<=.03f)return V(INF,INF,0);
        float h=waterHeight(at.x,at.y,pool)-p.z;
        return V(at.x-p.x-dir.x*h/dir.z,at.y-p.y-dir.y*h/dir.z,0);
    };
    V res=residual(q);
    for(int iter=0;iter<12&&dot(res,res)>1.e-10f;iter++){
        constexpr float e=.0008f;
        V dx=(residual(q+V(e,0,0))-residual(q-V(e,0,0)))/(2*e);
        V dy=(residual(q+V(0,e,0))-residual(q-V(0,e,0)))/(2*e);
        float det=dx.x*dy.y-dy.x*dx.y;if(std::fabs(det)<1.e-5f)return c;
        V step((dy.y*res.x-dy.x*res.y)/det,(-dx.y*res.x+dx.x*res.y)/det,0);
        float size=len(step);if(size>.30f)step*=.30f/size;
        bool accepted=false;
        for(int ls=0;ls<6;ls++){
            V trial=q-step,r=residual(trial);
            if(dot(r,r)<dot(res,res)){q=trial;res=r;accepted=true;break;}
            step*=.5f;
        }
        if(!accepted)break;
    }
    if(!std::isfinite(res.x)||dot(res,res)>4.e-8f)return c;
    q.z=waterHeight(q.x,q.y,pool);
    if(std::fabs(q.x-a.x)>a.rx*1.4f||std::fabs(q.y-a.y)>a.ry*1.4f)return c;
    c.q=q;c.l=unit(q-p);c.n=waterNormal(q.x,q.y,pool);c.valid=dot(c.l,c.n)>0&&q.z>p.z;
    if(computeJac&&c.valid){
        Frame f(air);constexpr float e=.0001f;
        auto u1=waterConnection(p,unit(air+f.t*e),pool,false),u0=waterConnection(p,unit(air-f.t*e),pool,false);
        auto v1=waterConnection(p,unit(air+f.b*e),pool,false),v0=waterConnection(p,unit(air-f.b*e),pool,false);
        if(!u1.valid||!u0.valid||!v1.valid||!v0.valid){c.valid=false;return c;}
        c.jacobian=std::fabs(dot(c.l,cross((u1.l-u0.l)/(2*e),(v1.l-v0.l)/(2*e))));
        if(!std::isfinite(c.jacobian)||c.jacobian>30)c.valid=false;
    }
    return c;
}

#include "scene_reflection_connection.h"

// GGX visible-normal sampling for unresolved capillary roughness. Explicit
// solar-disc NEE and MIS avoid relying on rare, extremely bright reflected
// sun hits. Macro ripples remain actual geometry. Direct floor-to-sun
// manifold connections still approximate this microscopic transmitted lobe.
constexpr float WATER_MICRO_ALPHA=.0050f;
float powerWeight(float a,float b){return a*a/(a*a+b*b);}
V sampleWaterMicroNormal(V n,V view,RNG &rng){
    Frame frame(n);V vv=frame.local(view);
    V vh=unit(V(WATER_MICRO_ALPHA*vv.x,WATER_MICRO_ALPHA*vv.y,std::max(.000001f,vv.z)));
    float ls=vh.x*vh.x+vh.y*vh.y;
    V t1=ls>0?V(-vh.y,vh.x,0)/std::sqrt(ls):V(1,0,0),t2=cross(vh,t1);
    float rr=std::sqrt(rng.uniform()),phi=2*PI*rng.uniform();
    float x=rr*std::cos(phi),y=rr*std::sin(phi),blend=.5f*(1+vh.z);
    y=(1-blend)*std::sqrt(std::max(0.f,1-x*x))+blend*y;
    V nh=t1*x+t2*y+vh*std::sqrt(std::max(0.f,1-x*x-y*y));
    return unit(frame.world(unit(V(WATER_MICRO_ALPHA*nh.x,WATER_MICRO_ALPHA*nh.y,std::max(.0000001f,nh.z)))));
}
float waterReflection(V n,V view,V light,float ei,float et){
    float nv=dot(n,view),nl=dot(n,light);if(nv<=0||nl<=0)return 0;
    V half=unit(view+light);
    return fresnelD(clamp(dot(view,half)),ei,et)*Dggx(clamp(dot(n,half)),WATER_MICRO_ALPHA)
        *G1(nv,WATER_MICRO_ALPHA)*G1(nl,WATER_MICRO_ALPHA)/(4*nv*nl);
}
float waterReflectionPDF(V n,V view,V light,float ei,float et){
    float nv=dot(n,view),nl=dot(n,light);if(nv<=0||nl<=0)return 0;
    V half=unit(view+light);
    return fresnelD(clamp(dot(view,half)),ei,et)*Dggx(clamp(dot(n,half)),WATER_MICRO_ALPHA)
        *G1(nv,WATER_MICRO_ALPHA)/(4*nv);
}

// Authored, homogeneous suspended-mineral scattering. Units: inverse metres.
// Scattering free flights are sampled explicitly; absorption remains spectral.
constexpr float WATER_SIGMA_S=.025f;
constexpr float WATER_PHASE_G=.74f;
float indirectClamp=12.f;
std::atomic<uint64_t> clampedIndirectContributions{0};
void recordRadiance(Spec& target,Spec value,bool indirect){
    float luminance=xyz(value).y;
    if(indirect&&indirectClamp>0&&luminance>indirectClamp){
        value*=indirectClamp/luminance;clampedIndirectContributions++;
    }
    target+=value;
}
#include "thin_leaf_r4.h"

Spec trace(Ray ray,RNG&rng,int maxDepth,float pixelCone){
    Spec L,throughput(1);int waterPool=-1,scatterWater=-2,deltaCount=0;
    bool indirect=false;bool lastWaterReflection=false;bool waterReflectionNEE=false;float previousReflectionPDF=0;float totalPathLength=0;
    float previousSkyPDF6=0; bool previousSkyNEE6=false;
    for(int depth=0;depth<maxDepth;depth++){
        Hit h;bool found=closest(ray,h);
        if(waterPool>=0){
            float t=-std::log(std::max(1.e-8f,1-rng.uniform()))/WATER_SIGMA_S;
            if(t<(found?h.t:INF)){
                throughput*=attenuation(t);
                V p=ray.o+ray.d*t,lAir=sampleSun(rng);
                auto c=waterConnection(p,lAir,waterPool);
                if(c.valid){
                    float dist=len(c.q-p),ca=dot(lAir,c.n);
                    if(ca>0&&!opaqueShadow(Ray(p,c.l),std::max(EPS,dist-EPS*15))&&
                       !opaqueShadow(Ray(c.q+c.n*EPS*12,lAir),INF)){
                        float fr=fresnelD(ca,1,WATER_IOR);
                        float tr=airTransmittance(Ray(c.q+c.n*EPS*12,lAir),INF,rng)*std::exp(-WATER_SIGMA_S*dist);
                        float factor=phaseHG(dot(ray.d,c.l),WATER_PHASE_G)*SUN_SOLID*(1-fr)*WATER_IOR*WATER_IOR*c.jacobian*tr;
                        recordRadiance(L,throughput*solar*attenuation(dist)*factor,indirect);
                    }
                }
                previousSkyNEE6=false;scatterWater=waterPool;deltaCount=0;waterReflectionNEE=false;indirect=true;
                ray=Ray(p,sampleHG(ray.d,rng,WATER_PHASE_G));
                continue;
            }
        }
        float steamT=waterPool<0?sampleSteam(ray,found?h.t:INF,rng):INF;
        float atmosphereT=waterPool<0?sampleAtmosphere(ray,found?h.t:INF,rng):INF;
        float cloudT=waterPool<0?sampleCloud(ray,found?h.t:INF,rng):INF;
        float scatterT=std::min(cloudT,std::min(steamT,atmosphereT)),g=cloudT<steamT&&cloudT<atmosphereT?CLOUD_G:(steamT<atmosphereT?PHASE_G:.38f);
        if(scatterT< (found?h.t:INF)){
            V p=ray.o+ray.d*scatterT,l=sampleSun(rng);
            if(!opaqueShadow(Ray(p,l),INF)){
                float tr=airTransmittance(Ray(p,l),INF,rng);
                recordRadiance(L,throughput*solar*(phaseHG(dot(ray.d,l),g)*SUN_SOLID*tr*.995f),indirect);
            }
            if(useWater){
                for(int pool=0;pool<1;pool++){
                    auto c=reflectedWaterConnection(p,l,pool);
                    float factor=reflectedSolarFactor(p,l,c,rng);
                    if(factor>0)recordRadiance(L,throughput*solar*(phaseHG(dot(ray.d,c.l),g)*factor*.995f),indirect);
                }
            }
            throughput*=.995f;
            previousSkyNEE6=false;scatterWater=-1;deltaCount=0;waterReflectionNEE=false;indirect=true;
            ray=Ray(p,sampleHG(ray.d,rng,g));
            continue;
        }
        if(!found){
            bool sunVisible=!(scatterWater==-1&&deltaCount==0)&&!(scatterWater>=0&&deltaCount==1)
                &&!(scatterWater==-1&&deltaCount==1&&lastWaterReflection);
            Spec incoming=physicalSky(ray.d);
            if(previousSkyNEE6&&ray.d.z>0)incoming*=powerWeight(previousSkyPDF6,1/(2*PI));
            if(sunVisible&&dot(ray.d,SUN)>=SUN_COS){
                float weight=waterReflectionNEE?powerWeight(previousReflectionPDF,1/SUN_SOLID):1.f;
                incoming+=solar*weight;
            }
            recordRadiance(L,throughput*incoming,indirect);break;
        }
        if(waterPool>=0)throughput*=attenuation(h.t);
        totalPathLength+=h.t;
        const Tri &tri=tris[h.tri];V p=ray.o+ray.d*h.t;
        V gn=unit(cross(tri.e1,tri.e2)),n=unit(tri.n0*(1-h.u-h.v)+tri.n1*h.u+tri.n2*h.v);
        int material=tri.mat;waterReflectionNEE=false;
        if(useWater&&(material==6||material==7)){
            previousSkyNEE6=false;
            bool enter=dot(ray.d,gn)<0;
            // Only top normals are smoothed. The closed buried side/bottom
            // geometry still supplies the actual boundary orientations.
            if(dot(n,gn)<0)n=-n;if(dot(n,ray.d)>0)n=-n;
            float ei=enter?1:WATER_IOR,et=enter?WATER_IOR:1;
            V view=-ray.d;
            if(enter&&!indirect){
                V light=sampleSun(rng);float nl=dot(n,light);
                if(nl>0&&dot(gn,light)>0&&!opaqueShadow(Ray(p+gn*EPS*7,light),INF)){
                    float reflection=waterReflection(n,view,light,ei,et);
                    float reflectionPDF=waterReflectionPDF(n,view,light,ei,et);
                    float tr=airTransmittance(Ray(p+gn*EPS*7,light),INF,rng);
                    recordRadiance(L,throughput*solar*(reflection*nl*SUN_SOLID*tr*powerWeight(1/SUN_SOLID,reflectionPDF)),indirect);
                }
            }
            V micro=indirect?n:sampleWaterMicroNormal(n,view,rng);
            float fr=fresnelD(clamp(dot(view,micro)),ei,et);
            if(rng.uniform()<fr){
                V direction=unit(reflect(ray.d,micro));float nl=dot(n,direction);
                if(nl<=0||dot(enter?gn:-gn,direction)<=0)break;
                throughput*=indirect?1.f:G1(nl,WATER_MICRO_ALPHA);
                previousReflectionPDF=waterReflectionPDF(n,view,direction,ei,et);
                waterReflectionNEE=enter&&!indirect;lastWaterReflection=true;
                ray=Ray(p+n*EPS*7,direction);
            }else{
                V direction=refractRay(ray.d,micro,ei/et);float nl=-dot(n,direction);
                if(dot(direction,direction)<.5f||nl<=0||dot(enter?-gn:gn,direction)<=0)break;
                throughput*=sqr(ei/et)*(indirect?1.f:G1(nl,WATER_MICRO_ALPHA));
                lastWaterReflection=false;waterPool=enter?material-6:-1;ray=Ray(p-n*EPS*7,direction);
            }
            deltaCount++;continue;
        }
        if(dot(gn,ray.d)>0)gn=-gn;if(dot(n,gn)<0)n=-n;
        if(dot(n,-ray.d)<.04f)n=unit(n+gn*(.041f-dot(n,-ray.d)));
        Surface m=shadeAt6(p,n,material,std::max(.00004f,totalPathLength*pixelCone/std::max(.18f,std::fabs(dot(n,ray.d)))),tri.group);
        if(dot(n,gn)<.1f)n=gn;
        if(dot(n,-ray.d)<.01f)n=gn;
        Spec base=rgbAnchors(m.color);V v=-ray.d,lAir=sampleSun(rng);
        const bool sampleSkyHere6=skyNEE6&&waterPool<0;
        if(sampleSkyHere6){
            float z=rng.uniform(),phi=2*PI*rng.uniform(),rr=std::sqrt(std::max(0.f,1-z*z));
            V light(rr*std::cos(phi),rr*std::sin(phi),z);
            bool leaf=material==3||material==9;float nc=dot(n,light),gc=dot(gn,light);
            if((leaf?nc*gc>0.f:(nc>0&&gc>0))){
                V offset=gn*(gc>0?EPS*5:-EPS*5);Ray shadow(p+offset,light);Hit blocker;
                // A direct environment connection cannot silently cross a water
                // boundary. Water/foliage are actual occluders for this path class.
                if(!meshHitWideR3(shadow,blocker,true,false)){
                    const float lightPdf=1/(2*PI);
                    float bsdfPdf=leaf?pdfLeafBSDF(m,n,v,light):pdfBSDF(m,n,v,light);
                    Spec f=leaf?evalLeafBSDF(m,base,n,v,light):evalBSDF(m,base,n,v,light);
                    float tr=airTransmittance(shadow,INF,rng);
                    recordRadiance(L,throughput*f*physicalSky(light)*(std::fabs(nc)*tr*powerWeight(lightPdf,bsdfPdf)/lightPdf),indirect);
                }
            }
        }
        if(useWater&&waterPool<0){
            for(int pool=0;pool<1;pool++){
                auto c=reflectedWaterConnection(p,lAir,pool);
                if(!c.valid)continue;
                float cosine=dot(n,c.l);bool foliage=(material==3||material==9);
                if(!foliage&&(cosine<=0||dot(gn,c.l)<=0))continue;
                V offset=gn*(dot(gn,c.l)>0?EPS*5:-EPS*5);
                float factor=reflectedSolarFactor(p+offset,lAir,c,rng);
                if(factor<=0)continue;
                Spec bsdf=foliage?evalLeafBSDF(m,base,n,v,c.l):evalBSDF(m,base,n,v,c.l);
                recordRadiance(L,throughput*bsdf*solar*(std::fabs(cosine)*factor),indirect);
            }
        }
        if((material==3||material==9)&&waterPool<0){
            float cosine=std::fabs(dot(n,lAir));V offset=gn*(dot(gn,lAir)>0?1.f:-1.f);
            if(cosine>0&&!opaqueShadow(Ray(p+offset*EPS*5,lAir),INF)){
                float tr=airTransmittance(Ray(p+offset*EPS*5,lAir),INF,rng);
                recordRadiance(L,throughput*evalLeafBSDF(m,base,n,v,lAir)*solar*(cosine*SUN_SOLID*tr),indirect);
            }
            V next=sampleLeafBSDF(m,n,v,rng);
            if(dot(next,next)<.5f)break;
            float nc=dot(n,next),gc=dot(gn,next),pdf=pdfLeafBSDF(m,n,v,next);
            if(pdf<1.e-12f||nc*gc<=0.f)break;
            throughput*=evalLeafBSDF(m,base,n,v,next)*(std::fabs(nc)/pdf);
            if(!std::isfinite(throughput.maximum()))break;
            if(depth>=3){float survive=clamp(throughput.maximum(),.05f,.94f);if(rng.uniform()>survive)break;throughput*=1/survive;}
            previousSkyNEE6=sampleSkyHere6;previousSkyPDF6=pdf;
            scatterWater=-1;deltaCount=0;indirect=true;
            ray=Ray(p+gn*(gc>0?EPS*5:-EPS*5),next);continue;
        }
        if(waterPool<0){
            float cosine=dot(n,lAir);
            if(cosine>0&&dot(gn,lAir)>0&&!opaqueShadow(Ray(p+gn*EPS*5,lAir),INF)){
                float tr=airTransmittance(Ray(p+gn*EPS*5,lAir),INF,rng);
                recordRadiance(L,throughput*evalBSDF(m,base,n,v,lAir)*solar*(cosine*SUN_SOLID*tr),indirect);
            }
        }else{
            auto connection=waterConnection(p,lAir,waterPool);
            if(connection.valid){
                float cosine=dot(n,connection.l),dist=len(connection.q-p);
                float ca=dot(lAir,connection.n),cw=dot(connection.l,connection.n);
                if(cosine>0&&dot(gn,connection.l)>0&&ca>0&&cw>0&&
                   !opaqueShadow(Ray(p+gn*EPS*5,connection.l),std::max(EPS,dist-EPS*15))&&
                   !opaqueShadow(Ray(connection.q+connection.n*EPS*12,lAir),INF)){
                    float f=fresnelD(ca,1,WATER_IOR);
                    float tr=airTransmittance(Ray(connection.q+connection.n*EPS*12,lAir),INF,rng);
                    float factor=cosine*SUN_SOLID*(1-f)*WATER_IOR*WATER_IOR*connection.jacobian*tr*std::exp(-WATER_SIGMA_S*dist);
                    recordRadiance(L,throughput*evalBSDF(m,base,n,v,connection.l)*solar*attenuation(dist)*factor,indirect);
                }
            }
        }
        V next=sampleBSDF(m,n,v,rng);float cosine=dot(n,next),pdf=pdfBSDF(m,n,v,next);
        if(cosine<=0||pdf<1.e-12f||dot(gn,next)<=0)break;
        throughput*=evalBSDF(m,base,n,v,next)*(cosine/pdf);
        if(!std::isfinite(throughput.maximum()))break;
        if(depth>=3){float survive=clamp(throughput.maximum(),.05f,.94f);if(rng.uniform()>survive)break;throughput*=1/survive;}
        previousSkyNEE6=sampleSkyHere6;previousSkyPDF6=pdf;
        scatterWater=waterPool;deltaCount=0;indirect=true;
        ray=Ray(p+gn*EPS*5,unit(next));
    }
    return L;
}

struct Options{
    V camera=V(0,-5,1.5f),target=V(0,5,1); float hfov=70; bool customCamera=false;
    std::string scene="canyon";
    std::string mesh,out,grain,relief,groundCertificate,view="hero";int width=1200,height=800,spp=128,depth=12,threads=5,seed=20260913;
    int waterSpp=0;float exposure=1.3f;bool bands=true;float aperture=.00025f;
    int guideSpp=16;bool guidesOnly=false;
};
Options parse(int argc,char**argv){
    if(argc<3)throw std::runtime_error("usage: spectral_desert scene.meshbin output_stem [--w N --h N --spp N --view hero|detail]");
    Options o;o.mesh=argv[1];o.out=argv[2];
    for(int i=3;i<argc;i++){
        std::string arg=argv[i];auto get=[&](){if(i+1>=argc)throw std::runtime_error("Missing argument for "+arg);return std::string(argv[++i]);};
        if(arg=="--scene"){
            o.scene=get(); if(o.scene=="canyon")sceneStyle=0;else if(o.scene=="coast")sceneStyle=1;else if(o.scene=="forest")sceneStyle=2;else throw std::runtime_error("Unknown scene");
        }else if(arg=="--camera"||arg=="--target"){
            auto value=get();float x,y,z;if(std::sscanf(value.c_str(),"%f,%f,%f",&x,&y,&z)!=3||!std::isfinite(x+y+z))throw std::runtime_error("Expected x,y,z");
            if(arg=="--camera"){o.camera=V(x,y,z);o.customCamera=true;}else o.target=V(x,y,z);
        }else if(arg=="--fov")o.hfov=std::stof(get());
        else if(arg=="--sun-scale")sceneSunScale=std::stof(get());
        else if(arg=="--sky-scale")sceneSkyScale=std::stof(get());
        else if(arg=="--guide-spp")o.guideSpp=std::stoi(get());
        else if(arg=="--guides-only")o.guidesOnly=true;
        else if(arg=="--no-sky-nee")skyNEE6=false;
        else if(arg=="--water-spp")o.waterSpp=std::stoi(get());else if(arg=="--indirect-clamp")indirectClamp=std::stof(get());else if(arg=="--w")o.width=std::stoi(get());else if(arg=="--h")o.height=std::stoi(get());else if(arg=="--spp")o.spp=std::stoi(get());
        else if(arg=="--depth")o.depth=std::stoi(get());else if(arg=="--threads")o.threads=std::stoi(get());else if(arg=="--seed")o.seed=std::stoi(get());
        else if(arg=="--view")o.view=get();else if(arg=="--exposure")o.exposure=std::stof(get());else if(arg=="--aperture")o.aperture=std::stof(get());
        else if(arg=="--sun"){
            std::string value=get();float x,y,z;
            if(std::sscanf(value.c_str(),"%f,%f,%f",&x,&y,&z)!=3||z<=0||!std::isfinite(x+y+z))
                throw std::runtime_error("--sun expects finite x,y,z with z>0");
            SUN=unit(V(x,y,z));
        }
        else if(arg=="--no-clouds")useClouds=false;else if(arg=="--no-steam")useSteam=false;else if(arg=="--no-water")useWater=false;else if(arg=="--water-absorption")waterStrength=std::stof(get());
        else if(arg=="--ground-occlusion")o.groundCertificate=get();else if(arg=="--relief")o.relief=get();else if(arg=="--grain")o.grain=get();else if(arg=="--no-bands")o.bands=false;else throw std::runtime_error("Unknown argument "+arg);
    }
    if(o.guideSpp<1||o.guideSpp>256||o.width<1||o.height<1||o.spp<1||o.depth<1||o.threads<1||o.aperture<0||waterStrength<0||o.waterSpp<0||o.waterSpp>65535||o.spp>65535||indirectClamp<0)throw std::runtime_error("Invalid render setting");
    return o;
}

V tonemap(V rgb,float exposure){
    rgb=V(rgb.x/whiteRGB.x,rgb.y/whiteRGB.y,rgb.z/whiteRGB.z)*exposure;
    float peak=std::max(.000001f,maxc(rgb));
    // One scalar shoulder preserves hue through bright mineral highlights.
    rgb*=(-std::expm1(-peak))/peak;
    for(int k=0;k<3;k++){float v=clamp(rgb[k]);rgb[k]=v<=.0031308f?12.92f*v:1.055f*std::pow(v,1/2.4f)-.055f;}
    return rgb;
}
struct Guide{V normal,albedo;float depth=0,variance=0,material=-1;};
Guide guideRay(Ray ray,float cone){
    Guide g;float travelled=0;
    for(int k=0;k<5;k++){
        Hit h;if(!closest(ray,h))return g;
        const auto&t=tris[h.tri];V p=ray.o+ray.d*h.t;
        V n=unit(t.n0*(1-h.u-h.v)+t.n1*h.u+t.n2*h.v);if(dot(n,ray.d)>0)n=-n;
        travelled+=h.t;
        if(t.mat==6||t.mat==7){V d=refractRay(ray.d,n,1/WATER_IOR);ray=Ray(p-n*EPS*5,d);continue;}
        auto m=shadeAt6(p,n,t.mat,travelled*cone,t.group);
        g.normal=n;g.albedo=m.color;g.depth=travelled;g.material=t.mat;return g;
    }return g;
}

// First-visible-surface features for denoising. Water is a water guide, not
// an arbitrarily refracted bottom guide. Normal features use unperturbed mesh
// normals; full surface detail is retained in the independently sampled albedo.
// This only affects auxiliary data, never transport or material evaluation.
Guide primaryFeature(Ray ray,float cone){
    Guide g;Hit h;if(!closest(ray,h))return g;
    const Tri&t=tris[h.tri];V p=ray.o+ray.d*h.t;
    V gn=unit(cross(t.e1,t.e2)),n=unit(t.n0*(1-h.u-h.v)+t.n1*h.u+t.n2*h.v);
    if(dot(gn,ray.d)>0)gn=-gn;if(dot(n,gn)<0)n=-n;
    if(dot(n,-ray.d)<.01f)n=gn;
    g.normal=n;g.material=float(t.mat);g.depth=h.t;
    if(t.mat==6||t.mat==7){g.albedo=V(1);return g;}
    float footprint=std::max(.00004f,h.t*cone/std::max(.18f,std::fabs(dot(n,ray.d))));
    g.albedo=shadeAt6(p,n,t.mat,footprint,t.group).color;return g;
}
struct GuideSupport{float coverage=1,normalVariance=0,depthSigma=0,skyCoverage=0;};
Guide supersampledFeature(V camera,V forward,V right,V up,float tangent,float aspect,
                         int width,int height,int x,int y,int spp,float cone,
                         uint64_t seed,GuideSupport&support){
    struct Acc{V n,a;double z=0,z2=0;int count=0;};std::array<Acc,18> acc{};
    // Independent stream: auxiliary sample counts cannot perturb beauty rays.
    RNG random(seed^0x84d12ac765db98efULL);int side=int(std::ceil(std::sqrt(float(spp))));
    for(int i=0;i<spp;i++){
        // Rectangular strata for square counts; independent uniform fallback for
        // non-square counts avoids missing strata or a biased partial grid.
        float jx=side*side==spp?((i%side)+random.uniform())/side:random.uniform();
        float jy=side*side==spp?((i/side)+random.uniform())/side:random.uniform();
        float px=(2*(x+jx)/width-1)*tangent,py=(1-2*(y+jy)/height)*tangent/aspect;
        Guide q=primaryFeature(Ray(camera,unit(forward+right*px+up*py)),cone);
        int id=std::max(0,std::min(17,int(q.material)+1));Acc& a=acc[id];
        a.n+=q.normal;a.a+=q.albedo;a.z+=q.depth;a.z2+=double(q.depth)*q.depth;a.count++;
    }
    int selected=0;for(int j=1;j<18;j++)if(acc[j].count>acc[selected].count)selected=j;
    const Acc&a=acc[selected];Guide g;g.material=float(selected-1);
    g.albedo=a.a/float(a.count);g.normal=unit(a.n);g.depth=float(a.z/a.count);
    support.coverage=float(a.count)/spp;support.skyCoverage=float(acc[0].count)/spp;
    support.normalVariance=selected==0?0.f:clamp(1.f-len(a.n)/a.count);
    support.depthSigma=float(std::sqrt(std::max(0.,a.z2/a.count-sqr(g.depth))));
    return g;
}

int selftest(){
    initSpectra();initRipples();float f=fresnelD(1,1,WATER_IOR),expected=sqr((WATER_IOR-1)/(WATER_IOR+1));
    auto a=attenuation(.7f),b=attenuation(1.4f);float err=0;
    for(int k=0;k<NBANDS;k++)err=std::max(err,std::fabs(a.v[k]*a.v[k]-b.v[k]));
    float maxDensity=0;
    for(int i=0;i<60000;i++){RNG r(i+41);V p(FOG_LO.x+(FOG_HI.x-FOG_LO.x)*r.uniform(),FOG_LO.y+(FOG_HI.y-FOG_LO.y)*r.uniform(),FOG_LO.z+(FOG_HI.z-FOG_LO.z)*r.uniform());maxDensity=std::max(maxDensity,steamDensity(p));}
    V d=unit(V(.4f,0,-1));V transmitted=refractRay(d,V(0,0,1),1/WATER_IOR);float snell=std::fabs(std::sqrt(1-d.z*d.z)-WATER_IOR*std::sqrt(1-transmitted.z*transmitted.z));
    bool passed=std::fabs(f-expected)<1e-6f&&err<2e-6f&&maxDensity<MAJORANT&&snell<2e-6f;
    std::cout<<std::setprecision(10)<<"{\n  \"spectral_bands\": "<<NBANDS<<",\n  \"wavelength_range_nm\": [380,780],\n  \"fresnel_normal\": "<<f<<",\n  \"fresnel_error\": "<<std::fabs(f-expected)<<",\n  \"beer_lambert_composition_error\": "<<err<<",\n  \"snell_error\": "<<snell<<",\n  \"sampled_max_steam_density\": "<<maxDensity<<",\n  \"steam_majorant\": "<<MAJORANT<<",\n  \"passed\": "<<(passed?"true":"false")<<"\n}\n";
    return passed?0:1;
}
int main(int argc,char**argv){try{
    if(argc==2&&std::string(argv[1])=="--self-test")return selftest();
    auto o=parse(argc,argv);cybr_detail::load_from_environment();if(!o.grain.empty())photographicGrain.load(o.grain);if(!o.relief.empty())granularRelief.load(o.relief);omp_set_num_threads(o.threads);configureScene();initSpectra();initRipples();initClouds();initSteam();if(!o.groundCertificate.empty())groundOcclusion.load(o.groundCertificate);
    auto started=std::chrono::steady_clock::now();
    loadSurfaceFrames6(o.mesh);
    std::ifstream input(o.mesh,std::ios::binary);if(!input)throw std::runtime_error("Cannot read CYBR GEO mesh "+o.mesh);
    uint32_t count;input.read(reinterpret_cast<char*>(&count),4);
    if(!input||count>40000000)throw std::runtime_error("Invalid mesh header");
    tris.reserve(count);
    for(uint32_t i=0;i<count;i++){
        float a[20];input.read(reinterpret_cast<char*>(a),80);if(!input)throw std::runtime_error("Truncated mesh");
        for(float v:a)if(!std::isfinite(v))throw std::runtime_error("Nonfinite mesh input");
        Tri t;t.p=V(a[0],a[1],a[2]);t.e1=V(a[3],a[4],a[5])-t.p;t.e2=V(a[6],a[7],a[8])-t.p;
        t.n0=V(a[9],a[10],a[11]);t.n1=V(a[12],a[13],a[14]);t.n2=V(a[15],a[16],a[17]);t.mat=int(a[18]);t.group=int(a[19]);
        if(t.mat<0||t.mat>16)throw std::runtime_error("Unknown landscape material");
        if(dot(cross(t.e1,t.e2),cross(t.e1,t.e2))>1e-20f)tris.push_back(t);
    }
    if(tris.empty())throw std::runtime_error("No geometry");
    if(!surfaceFrames6.empty())for(const auto &t:tris)if(t.group<0||size_t(t.group)>=surfaceFrames6.size())throw std::runtime_error("Mesh group/frame mismatch");
    order.resize(tris.size());std::iota(order.begin(),order.end(),0);nodes.reserve(tris.size()/2);build(0,int(order.size()));buildWideR3();
    std::cerr<<"CYBR GEO BVH: "<<tris.size()<<" actual triangles; "<<nodes.size()<<" nodes\n";
    V camera(2.10f,-5.65f,1.52f),target(-.15f,3.15f,.15f);float hfov=72;
    if(o.view=="low"){camera=V(1.90f,-5.1f,1.03f);target=V(-.15f,3.8f,.18f);hfov=69;}
    else if(o.view=="detail"){camera=V(1.95f,-4.65f,.67f);target=V(.81f,-2.95f,.09f);hfov=55;}
    else if(o.view=="overhead"){camera=V(.3f,-7.6f,12.3f);target=V(-.5f,3.f,0);hfov=62;}
    else if(o.view!="hero")throw std::runtime_error("Unknown camera view");
    if(o.customCamera){camera=o.camera;target=o.target;hfov=o.hfov;}
    if(hfov<5||hfov>150||len(target-camera)<.0001f)throw std::runtime_error("Invalid camera");
    V forward=unit(target-camera),right=unit(cross(forward,V(0,0,1))),up=cross(right,forward);
    float tanHalf=std::tan(hfov*PI/360.f),aspect=float(o.width)/o.height,focus=len(target-camera),cone=2*tanHalf/o.width;
    size_t pixels=size_t(o.width)*o.height;
    std::vector<GuideSupport> support(pixels);
    std::vector<uint16_t> sampleCounts(pixels);std::vector<Spec> film(pixels);std::vector<Guide> guides(pixels);std::atomic<int> rows{0};std::atomic<uint64_t> nonfinite{0};
    int strata=int(std::ceil(std::sqrt(float(o.spp))));
    #pragma omp parallel for schedule(dynamic,1)
    for(int y=0;y<o.height;y++){
        for(int x=0;x<o.width;x++){
            size_t index=size_t(y)*o.width+x;RNG rng(uint64_t(index)*0x9e3779b97f4a7c15ULL+o.seed);
            Spec sum;double lum2=0;float jitterShift=rng.uniform();
            float cx=(2*(x+.5f)/o.width-1)*tanHalf,cy=(1-2*(y+.5f)/o.height)*tanHalf/aspect;
            Hit centerHit;bool waterPixel=closest(Ray(camera,unit(forward+right*cx+up*cy)),centerHit)
                &&(tris[centerHit.tri].mat==6||tris[centerHit.tri].mat==7);
            int pixelSpp=waterPixel&&o.waterSpp>0?std::max(o.waterSpp,o.spp):o.spp;
            sampleCounts[index]=uint16_t(o.guidesOnly?0:pixelSpp);
            for(int s=0;s<(o.guidesOnly?0:pixelSpp);s++){
                float jx=(s+rng.uniform())/pixelSpp,jy=std::fmod((s+.5f)*.61803398875f+jitterShift,1.f);
                float px=(2*(x+jx)/o.width-1)*tanHalf,py=(1-2*(y+jy)/o.height)*tanHalf/aspect;
                V direction=unit(forward+right*px+up*py),origin=camera;
                if(o.aperture>0){float r=std::sqrt(rng.uniform())*o.aperture,phi=2*PI*rng.uniform();V offset=right*(r*std::cos(phi))+up*(r*std::sin(phi));V fp=camera+direction*(focus/dot(direction,forward));origin+=offset;direction=unit(fp-origin);}
                Spec value=trace(Ray(origin,direction),rng,o.depth,cone);
                bool finite=true;for(float v:value.v)finite=finite&&std::isfinite(v);
                if(!finite){nonfinite++;continue;}
                sum+=value;double lum=xyz(value).y;lum2+=lum*lum;
            }
            film[index]=sum*(1.f/pixelSpp);
            float px=(2*(x+.5f)/o.width-1)*tanHalf,py=(1-2*(y+.5f)/o.height)*tanHalf/aspect;
            Guide g=supersampledFeature(camera,forward,right,up,tanHalf,aspect,o.width,o.height,x,y,
                o.guideSpp,cone,uint64_t(index)*0x9e3779b97f4a7c15ULL+o.seed,support[index]);
            double avg=xyz(film[index]).y;g.variance=std::max(0.,(lum2/pixelSpp-avg*avg)/std::max(1,pixelSpp-1));guides[index]=g;
        }
        int done=++rows;
        if(done%std::max(1,o.height/20)==0){
            float sec=std::chrono::duration<float>(std::chrono::steady_clock::now()-started).count();
            #pragma omp critical
            std::cerr<<100*done/o.height<<"% "<<sec<<" s\n";
        }
    }
    if(o.guidesOnly){
        uint32_t dims[2]={uint32_t(o.width),uint32_t(o.height)};
        std::ofstream gf(o.out+".guides",std::ios::binary);gf.write(reinterpret_cast<char*>(dims),8);gf.write(reinterpret_cast<char*>(guides.data()),guides.size()*sizeof(Guide));
        std::ofstream sf(o.out+".support",std::ios::binary);sf.write(reinterpret_cast<char*>(dims),8);sf.write(reinterpret_cast<char*>(support.data()),support.size()*sizeof(GuideSupport));
        std::ofstream mf(o.out+".json");mf<<"{\"guides_only\":true,\"beauty_rendered\":false,\"guide_spp\":"<<o.guideSpp<<",\"width\":"<<o.width<<",\"height\":"<<o.height<<",\"primary_surface_guides\":true,\"seconds\":"<<std::chrono::duration<double>(std::chrono::steady_clock::now()-started).count()<<"}\n";
        std::cerr<<"GUIDES COMPLETE "<<o.out<<"\n";return 0;
    }
    std::ofstream pf(o.out+".pfm",std::ios::binary);pf<<"PF\n"<<o.width<<" "<<o.height<<"\n-1.0\n";
    for(int y=o.height-1;y>=0;y--)for(int x=0;x<o.width;x++){V rgb=toRGB(film[size_t(y)*o.width+x]);pf.write(reinterpret_cast<char*>(&rgb),sizeof(V));}
    std::ofstream ppm(o.out+".ppm",std::ios::binary);ppm<<"P6\n"<<o.width<<" "<<o.height<<"\n255\n";
    Spec means;
    for(auto s:film){means+=s*(1.f/float(pixels));V v=tonemap(toRGB(s),o.exposure);for(int k=0;k<3;k++){unsigned char b=static_cast<unsigned char>(clamp(v[k])*255+.5f);ppm.write(reinterpret_cast<char*>(&b),1);}}
    std::ofstream gf(o.out+".guides",std::ios::binary);uint32_t dim[2]={uint32_t(o.width),uint32_t(o.height)};gf.write(reinterpret_cast<char*>(dim),8);gf.write(reinterpret_cast<char*>(guides.data()),guides.size()*sizeof(Guide));
    if(o.bands){std::ofstream sp(o.out+".spectral",std::ios::binary);uint32_t header[]={0x36315053,uint32_t(o.width),uint32_t(o.height),NBANDS};sp.write(reinterpret_cast<char*>(header),16);sp.write(reinterpret_cast<char*>(film.data()),film.size()*sizeof(Spec));}
    {std::ofstream samples(o.out+".samples",std::ios::binary);samples.write(reinterpret_cast<char*>(dim),8);samples.write(reinterpret_cast<char*>(sampleCounts.data()),sampleCounts.size()*sizeof(uint16_t));}
    {std::ofstream sf(o.out+".support",std::ios::binary);sf.write(reinterpret_cast<char*>(dim),8);sf.write(reinterpret_cast<char*>(support.data()),support.size()*sizeof(GuideSupport));}
    uint64_t totalCameraSamples=std::accumulate(sampleCounts.begin(),sampleCounts.end(),uint64_t(0));
    float sec=std::chrono::duration<float>(std::chrono::steady_clock::now()-started).count();
    std::ofstream meta(o.out+".json");meta<<std::setprecision(9)<<"{\n  \"renderer\": \"CYBR SCENES R2 / GEO: stochastic photographic minerals, slope moments, global sky MIS\",\n  \"guide_spp\": "<<o.guideSpp<<",\n  \"primary_surface_guides\": true,\n  \"geometry_accelerator\": \"CYBR GEO native SAH BVH\",\n  \"view\": \""<<o.view<<"\",\n  \"width\": "<<o.width<<", \"height\": "<<o.height<<", \"spp\": "<<o.spp<<",\n  \"max_depth\": "<<o.depth<<", \"seed\": "<<o.seed<<", \"threads\": "<<o.threads<<",\n  \"triangles\": "<<tris.size()<<", \"bvh_nodes\": "<<nodes.size()<<",\n  \"spectral_bands\": 16, \"wavelength_range_nm\": [380,780],\n  \"spectral_method\": \"Jointly transported fixed midpoint wavelength quadrature, 25 nm bins\",\n  \"water_ior\": "<<WATER_IOR<<", \"dispersion\": false,\n  \"steam\": "<<(useSteam?"true":"false")<<", \"steam_model\": \"Authored heterogeneous trilinear density grid; grid-bounded delta and ratio tracking; HG phase\",\n  \"water_absorption_scale\": "<<waterStrength<<",\n  \"finite_difference_water_connection_step_radians\": 0.0001,\n  \"nonfinite_path_samples\": "<<nonfinite.load()<<",\n  \"exposure\": "<<o.exposure<<",\n  \"film_white_rgb\": ["<<whiteRGB.x<<","<<whiteRGB.y<<","<<whiteRGB.z<<"],\n  \"seconds\": "<<sec<<",\n  \"band_means\": [";
    for(int k=0;k<NBANDS;k++)meta<<(k?",":"")<<means.v[k];
    meta<<"],\n  \"r6_surface_coordinate_frames\": "<<surfaceFrames6.size()<<",\n  \"sky_next_event_sampling\": "<<(skyNEE6?"true":"false")<<",\n  \"water_scattering_coefficient_per_m\": "<<WATER_SIGMA_S<<",\n  \"water_scattering_HG_g\": "<<WATER_PHASE_G<<",\n  \"ripple_modes\": "<<RIPPLE_COUNT<<",\n  \"camera_origin_m\": ["<<camera.x<<","<<camera.y<<","<<camera.z<<"],\n  \"camera_target_m\": ["<<target.x<<","<<target.y<<","<<target.z<<"],\n  \"horizontal_fov_degrees\": "<<hfov<<",\n  \"aperture_radius_m\": "<<o.aperture<<",\n  \"sun_direction\": ["<<SUN.x<<","<<SUN.y<<","<<SUN.z<<"],\n  \"photographic_grayscale_albedo_detail\": "<<(!photographicGrain.levels.empty()?"true":"false")<<",\n  \"granular_relief_enabled\": "<<(!granularRelief.levels.empty()?"true":"false")<<",\n  \"photographic_backplate\": false,\n  \"image_generation\": false,\n  \"sky_model\": \"Single-scattering spherical Rayleigh/aerosol spectral LUT, not reference-validated\",\n  \"material_spectra\": \"Reference-illuminant-calibrated RGB-anchor reflectance, not measured mineral spectra\",\n  \"clouds\": "<<(useClouds?"true":"false")<<",\n  \"cloud_model\": \"Bounded 3D extinction grid; conservative column-majorant DDA; delta-tracked scattering and ratio-tracked shadows\",\n  \"cloud_grid\": ["<<CLOUD_NX<<","<<CLOUD_NY<<","<<CLOUD_NZ<<"],\n  \"water_spp\": "<<o.waterSpp<<",\n  \"total_camera_samples\": "<<totalCameraSamples<<",\n  \"indirect_contribution_clamp_Y\": "<<indirectClamp<<",\n  \"clamped_indirect_contributions\": "<<clampedIndirectContributions.load()<<",\n  \"leaf_surface_model\": \"Reciprocal Fresnel-GGX coat with two-sided attenuated diffuse body; authored, not measured\",\n  \"leaf_body_reflection_share\": 0.6,\n  \"leaf_surface_r4\": true,\n  \"ground_occlusion_enabled\": "<<(groundOcclusion.active?"true":"false")<<",\n  \"ground_occlusion_queries\": "<<groundOcclusion.queries.load()<<",\n  \"ground_occlusion_rejections\": "<<groundOcclusion.rejections.load()<<",\n  \"water_microfacet_alpha\": "<<WATER_MICRO_ALPHA<<",\n  \"water_reflection_estimator\": \"Primary: GGX VNDF and solar-disc MIS; indirect: one-root macro reflection manifold with exclusive path ownership\",\n  \"underwater_direct_light_approximation\": \"One-root macro-surface manifolds approximate indirect reflected and transmitted caustics; primary reflection uses GGX\"\n}\n";
    std::cerr<<"WROTE "<<o.out<<"; "<<sec<<" seconds; invalid paths "<<nonfinite<<"\n";
    return nonfinite?2:0;
}catch(const std::exception&e){std::cerr<<"ERROR: "<<e.what()<<"\n";return 1;}}
