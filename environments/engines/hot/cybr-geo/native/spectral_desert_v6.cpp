// CYBR GEO / GPL-2.0-only
// Native spectral landscape extension. Reuses CYBR GEO's actual BVH and mesh
// intersection implementation, with metre-native tolerances. CC0 grayscale albedo detail.
// 16 wavelength bands are transported jointly. Water IOR is deliberately
// achromatic: wavelength-dependent absorption is NOT called dispersion.
#include "spectral_geometry.h"
#include <array>
#include <iomanip>
#include <stdexcept>
#include <cstring>
#include "photographic_grain.h"

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
V whiteRGB, SUN=unit(V(-.70f,.26f,.56f));
constexpr float SUN_RADIUS=.00465f;
const float SUN_COS=std::cos(SUN_RADIUS), SUN_SOLID=2*PI*(1-SUN_COS);
bool useSteam=true,useWater=true;float waterStrength=1.f;

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
Spec rgbAnchors(V c){
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
    buildPhysicalSky();
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
std::array<Pool,2> pools={Pool{.5f,1.f,4.1f,3.2f,.055f,1.30f},Pool{-3.5f,10.f,2.2f,1.65f,.245f,.75f}};
float poolQ(V p,int i){
    const auto &a=pools[i];float x=(p.x-a.x)/a.rx,y=(p.y-a.y)/a.ry;
    float ang=std::atan2(y,x);
    float edge=1+.16f*std::sin(2*ang+.55f)+.050f*std::sin(5*ang-1.3f)+.027f*std::sin(9*ang+.9f*i)
       +.09f*noise(p.x*.55f,p.y*.55f)+.025f*noise(p.x*2.7f,p.y*2.7f);
    return std::sqrt(x*x+y*y)/edge;
}
#include "broadband_ripples.h"

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
    bool ok=meshHit(r,h);
    if(!useWater&&ok&&tris[h.tri].mat>=6&&tris[h.tri].mat<=7){
        V origin=r.o+r.d*(h.t+EPS*4);float travelled=h.t+EPS*4;Hit next;
        for(int i=0;i<8;i++){
            if(!meshHit(Ray(origin,r.d),next))return false;
            if(tris[next.tri].mat<6||tris[next.tri].mat>7){next.t+=travelled;h=next;return true;}
            float step=next.t+EPS*4;origin+=r.d*step;travelled+=step;next=Hit();
        }return false;
    }return ok;
}
bool opaqueShadow(Ray r,float distance){
    for(int k=0;k<8;k++){
        Hit h;h.t=distance;if(!meshHit(r,h,true))return false;
        if(tris[h.tri].mat!=6 && tris[h.tri].mat!=7)return true;
        // meshHit(any=true) is only safe when ALL hits block. With transmissive
        // water, obtain the true closest hit before skipping its interface.
        h=Hit();h.t=distance;if(!meshHit(r,h))return false;
        int m=tris[h.tri].mat;
        if(m!=6&&m!=7)return true;
        float step=h.t+EPS*8;distance-=step;
        if(distance<=EPS)return false;
        r=Ray(r.o+r.d*step,r.d);
    }return true;
}

// Bounded, genuinely ray-integrated participating medium. This is a procedural
// density field, NOT a Navier-Stokes/thermal plume simulation or a 2-D overlay.
const V FOG_LO(-8,-4.8f,.055f),FOG_HI(8.4f,13.4f,3.6f);
constexpr float STEAM_SCALE=.36f,MAJORANT=.85f,PHASE_G=.63f;
bool fogInterval(const Ray&r,float maximum,float &a,float &b){
    a=0;b=maximum;
    for(int k=0;k<3;k++){
        if(std::fabs(r.d[k])<1.e-9f){if(r.o[k]<FOG_LO[k]||r.o[k]>FOG_HI[k])return false;continue;}
        float x=(FOG_LO[k]-r.o[k])/r.d[k],y=(FOG_HI[k]-r.o[k])/r.d[k];if(x>y)std::swap(x,y);
        a=std::max(a,x);b=std::min(b,y);if(a>=b)return false;
    }return b>a;
}
float steamDensity(V p){
    if(!useSteam)return 0;
    float density=0;
    for(int i=0;i<2;i++){
        const auto &pool=pools[i];float h=p.z-pool.level;
        if(h<.018f||h>3.15f)continue;
        float xx=(p.x-pool.x-.32f*h-.22f*std::sin(h*2.2f))/pool.rx;
        float yy=(p.y-pool.y-.16f*h)/pool.ry;
        float spread=std::exp(-1.5f*(xx*xx+yy*yy));
        float structure=clamp(.50f+.43f*fbm(V(p.x*1.4f+h*.2f,p.y*1.5f,h*2.2f)));
        density+=.17f*spread*std::exp(-h*1.35f)*(.22f+.78f*structure*structure);
        float xx2=(p.x-pool.x-.85f-.40f*h-.20f*std::sin(h*3))/1.0f;
        float yy2=(p.y-pool.y-.1f)/.9f;
        density+=.06f*std::exp(-(xx2*xx2+yy2*yy2)-h*.8f)*structure;
    }
    return density*STEAM_SCALE;
}
float sampleSteam(const Ray&r,float maxT,RNG&rng){
    if(!useSteam)return INF;float a,b;if(!fogInterval(r,maxT,a,b))return INF;
    float t=a;
    for(int k=0;k<1024;k++){
        t+=-std::log(std::max(1e-8f,1-rng.uniform()))/MAJORANT;
        if(t>=b)return INF;
        if(rng.uniform()<steamDensity(r.o+r.d*t)/MAJORANT)return t;
    }return INF;
}
float steamTransmittance(const Ray&r,float maxT,RNG&rng){
    if(!useSteam)return 1;float a,b;if(!fogInterval(r,maxT,a,b))return 1;
    float t=a,tr=1;
    for(int k=0;k<1024;k++){
        t+=-std::log(std::max(1e-8f,1-rng.uniform()))/MAJORANT;if(t>=b)return tr;
        tr*=std::max(0.f,1-steamDensity(r.o+r.d*t)/MAJORANT);
        if(tr<1.e-5f)return 0;
    }return tr;
}
const V ATM_LO(-2500,330,-.4f),ATM_HI(2500,2300,420);
constexpr float ATM_SIGMA=.00014f;
bool atmosphereInterval(const Ray&r,float maximum,float&a,float&b){
    a=0;b=maximum;
    for(int k=0;k<3;k++){
        if(std::fabs(r.d[k])<1e-9f){if(r.o[k]<ATM_LO[k]||r.o[k]>ATM_HI[k])return false;continue;}
        float x=(ATM_LO[k]-r.o[k])/r.d[k],y=(ATM_HI[k]-r.o[k])/r.d[k];if(x>y)std::swap(x,y);
        a=std::max(a,x);b=std::min(b,y);if(a>=b)return false;
    }return true;
}
float sampleAtmosphere(const Ray&r,float maxT,RNG&rng){
    float a,b;if(!atmosphereInterval(r,maxT,a,b))return INF;
    float t=a-std::log(std::max(1e-8f,1-rng.uniform()))/ATM_SIGMA;return t<b?t:INF;
}
float airTransmittance(const Ray&r,float maxT,RNG&rng){
    float a,b,tr=steamTransmittance(r,maxT,rng);
    if(atmosphereInterval(r,maxT,a,b))tr*=std::exp(-(b-a)*ATM_SIGMA);
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
    return base*((1-fr)/PI)+Spec(fr*Dggx(clamp(dot(n,h)),a)*G1(nv,a)*G1(nl,a)/(4*nv*nl));
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
Surface shade(V p,V &n,int material,float footprint){
    Surface m;m.kind=material;
    float macro=fbm(p*.59f),meso=fbm(p*10.4f),grain=noise(p*231.7f);
    float q0=poolQ(p,0),q1=poolQ(p,1);int pool=q0<q1?0:1;float q=std::min(q0,q1);
    float d=(q-1)*pools[pool].rx,level=pools[pool].level;
    float patch=fbm(V(p.x*.94f,p.y*1.15f,p.z*3.4f));
    float wet=(1-smooth(level+.01f,level+.16f+.018f*noise(p*7),p.z))*(1-smooth(1.17f,1.5f,q));
    float mineral=std::exp(-sqr(d/.63f));
    float ff=1/(1+sqr(footprint*200));
    if(material==0||material==4){
        V sand(.32f,.291f,.251f),carbonate(.75f,.725f,.663f);
        float coating=clamp(mineral*(.92f+.65f*patch)+.11f*noise(p*7));
        m.color=sand*(1-coating)+carbonate*coating;
        if(q<.96f)m.color=V(.21f,.205f,.174f)*(1+.25f*meso+.14f*macro);
        float iron=std::exp(-sqr((q-1.02f)/.15f))*smooth(-.18f,.51f,fbm(V(p.x*.92f,p.y*3.1f,p.z*5.8f)));
        m.color=m.color*(1-iron*.60f)+V(.33f,.145f,.049f)*(iron*.60f);
        if(material==4)m.color=V(.72f,.69f,.62f)*(1+.17f*meso+.08f*macro)*(1-.22f*iron);
        m.color*=1+.13f*macro+.06f*meso+.04f*grain*ff;
        m.rough=.85f*(1-wet)+.20f*wet;
        if(!photographicGrain.levels.empty()){
            float u=p.x*.917f+p.y*.399f,v=p.y*.917f-p.x*.399f;
            float g=photographicGrain.sample(u,v,footprint,.45f);
            float amount=(material==4?.36f:.82f)*(q<1?.40f:1.f);
            m.color*=1-amount+amount*clamp(g,.24f,2.3f);
        }
    }else if(material==1||material==2){
        m.color=material==1?V(.48f,.455f,.398f):V(.265f,.231f,.185f);
        float quartz=smooth(.08f,.48f,noise(p*155.1f))*ff;
        float feldspar=smooth(.02f,.44f,noise(p*76.3f+V(3,8,11)));
        m.color*=1+.30f*macro+.15f*meso+.10f*grain*ff;
        m.color=m.color*(1-.24f*quartz)+V(.62f,.592f,.536f)*(.24f*quartz);
        m.color=m.color*(1-.13f*feldspar)+V(.32f,.172f,.084f)*(.13f*feldspar);
        float bedding=std::fabs(std::sin(p.z*37+p.x*8+.7f*fbm(p*5)));
        m.color*=.92f+.08f*smooth(.025f,.17f,bedding);
        float crust=mineral*smooth(-.25f,.47f,patch)*smooth(-.05f,.65f,n.z)*.57f;
        m.color=m.color*(1-crust)+V(.70f,.674f,.60f)*crust;
        if(!photographicGrain.levels.empty()){
            V wn(n.x*n.x,n.y*n.y,n.z*n.z);
            float g=wn.x*photographicGrain.sample(p.y,p.z,footprint,.19f)+wn.y*photographicGrain.sample(p.x,p.z,footprint,.19f)+wn.z*photographicGrain.sample(p.x,p.y,footprint,.19f);
            m.color*=.56f+.44f*clamp(g,.24f,2.8f);
        }
        m.rough=.83f*(1-wet)+.25f*wet;
    }else if(material==3){m.color=V(.38f,.253f,.106f)*(1+.23f*macro+.17f*noise(p*47));m.rough=.91f;}
    else if(material==5){
        float strata=std::sin(p.z*.47f+p.x*.011f+fbm(p*.025f)*1.7f);
        float exposure=smooth(.055f,.34f,1-n.z);
        float geology=smooth(-.20f,.33f,fbm(V(p.x*.021f,p.y*.019f,p.z*.052f)));
        V talus(.31f,.277f,.235f),rock(.138f,.145f,.143f);
        float exposed=clamp(exposure*.85f+.25f*geology);
        m.color=(talus*(1-exposed)+rock*exposed);
        m.color*=1+.24f*fbm(p*.47f)+.13f*noise(p*1.6f)+.11f*strata;
        m.rough=.91f;
    }else if(material==8){m.color=V(.18f,.119f,.063f)*(1+.28f*macro);m.rough=.94f;}
    else if(material==9){m.color=V(.25f,.263f,.149f)*(1+.29f*macro);m.rough=.90f;}
    else{m.color=V(.3f);}
    m.color*=1-.30f*wet;
    m.ior=(p.z<level&&q<1.1f)?1.48f/WATER_IOR:1.48f;
    m.color=vmin(vmax(m.color,V(.002f)),V(.88f));
    if(material==0||material==1||material==2||material==4||material==5){
        Frame frame(n);float f=material==5?.24f:73.f,filter=1/(1+sqr(footprint*f));
        V u=frame.t*.015f,b=frame.b*.015f,pf=p*f;
        float dt=(noise(pf+u)-noise(pf-u))/.03f,db=(noise(pf+b)-noise(pf-b))/.03f;
        float strength=material==5?.11f:((material==0||material==4)?.036f:.085f);
        n=unit(n-(frame.t*dt+frame.b*db)*(strength*filter));
        float f2=510,filter2=1/(1+sqr(footprint*f2));
        n=unit(n+(frame.t*noise(p*f2)+frame.b*noise(p*f2+V(5,8,2)))*(.037f*filter2));
    }
    return m;
}

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

// Authored, homogeneous suspended-mineral scattering. Units: inverse metres.
// Scattering free flights are sampled explicitly; absorption remains spectral.
constexpr float WATER_SIGMA_S=.065f;
constexpr float WATER_PHASE_G=.74f;
Spec trace(Ray ray,RNG&rng,int maxDepth,float pixelCone){
    Spec L,throughput(1);int waterPool=-1,scatterWater=-2,deltaCount=0;
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
                        L+=throughput*solar*attenuation(dist)*factor;
                    }
                }
                scatterWater=waterPool;deltaCount=0;
                ray=Ray(p,sampleHG(ray.d,rng,WATER_PHASE_G));
                continue;
            }
        }
        float steamT=waterPool<0?sampleSteam(ray,found?h.t:INF,rng):INF;
        float atmosphereT=waterPool<0?sampleAtmosphere(ray,found?h.t:INF,rng):INF;
        float scatterT=std::min(steamT,atmosphereT),g=steamT<atmosphereT?PHASE_G:.38f;
        if(scatterT< (found?h.t:INF)){
            V p=ray.o+ray.d*scatterT,l=sampleSun(rng);
            if(!opaqueShadow(Ray(p,l),INF)){
                float tr=airTransmittance(Ray(p,l),INF,rng);
                L+=throughput*solar*(phaseHG(dot(ray.d,l),g)*SUN_SOLID*tr*.995f);
            }
            throughput*=.995f;
            scatterWater=-1;deltaCount=0;
            ray=Ray(p,sampleHG(ray.d,rng,g));
            continue;
        }
        if(!found){
            bool sunVisible=!(scatterWater==-1&&deltaCount==0)&&!(scatterWater>=0&&deltaCount==1);
            L+=throughput*environment(ray.d,sunVisible);break;
        }
        if(waterPool>=0)throughput*=attenuation(h.t);
        const Tri &tri=tris[h.tri];V p=ray.o+ray.d*h.t;
        V gn=unit(cross(tri.e1,tri.e2)),n=unit(tri.n0*(1-h.u-h.v)+tri.n1*h.u+tri.n2*h.v);
        int material=tri.mat;
        if(useWater&&(material==6||material==7)){
            bool enter=dot(ray.d,gn)<0;
            // Only top normals are smoothed. The closed buried side/bottom
            // geometry still supplies the actual boundary orientations.
            if(dot(n,gn)<0)n=-n;if(dot(n,ray.d)>0)n=-n;
            float ei=enter?1:WATER_IOR,et=enter?WATER_IOR:1;
            float fr=fresnelD(-dot(ray.d,n),ei,et);
            if(rng.uniform()<fr){ray=Ray(p+n*EPS*5,unit(reflect(ray.d,n)));}
            else{
                V d=refractRay(ray.d,n,ei/et);
                if(dot(d,d)<.5f){ray=Ray(p+n*EPS*5,unit(reflect(ray.d,n)));}
                else{throughput*=sqr(ei/et);waterPool=enter?material-6:-1;ray=Ray(p-n*EPS*5,d);}
            }
            deltaCount++;continue;
        }
        if(dot(gn,ray.d)>0)gn=-gn;if(dot(n,gn)<0)n=-n;
        if(dot(n,-ray.d)<.04f)n=unit(n+gn*(.041f-dot(n,-ray.d)));
        Surface m=shade(p,n,material,std::max(.00004f,h.t*pixelCone));
        if(dot(n,gn)<.1f)n=gn;
        if(dot(n,-ray.d)<.01f)n=gn;
        Spec base=rgbAnchors(m.color);V v=-ray.d,lAir=sampleSun(rng);
        if((material==3||material==9)&&waterPool<0){
            float side=dot(n,lAir)>=0?1.f:-1.f,prob=side>0?.60f:.40f;
            float cosine=std::fabs(dot(n,lAir));V offset=gn*(dot(gn,lAir)>0?1.f:-1.f);
            if(cosine>0&&!opaqueShadow(Ray(p+offset*EPS*5,lAir),INF)){
                float tr=airTransmittance(Ray(p+offset*EPS*5,lAir),INF,rng);
                L+=throughput*base*solar*(prob*cosine*SUN_SOLID*tr/PI);
            }
            float flip=rng.uniform()<.60f?1.f:-1.f;
            float u=rng.uniform(),phi=2*PI*rng.uniform(),rr=std::sqrt(u);
            Frame frame(n*flip);V next=frame.world(V(rr*std::cos(phi),rr*std::sin(phi),std::sqrt(1-u)));
            throughput*=base;
            if(depth>=3){float survive=clamp(throughput.maximum(),.05f,.94f);if(rng.uniform()>survive)break;throughput*=1/survive;}
            scatterWater=-1;deltaCount=0;
            ray=Ray(p+gn*(dot(gn,next)>0?EPS*5:-EPS*5),unit(next));continue;
        }
        if(waterPool<0){
            float cosine=dot(n,lAir);
            if(cosine>0&&dot(gn,lAir)>0&&!opaqueShadow(Ray(p+gn*EPS*5,lAir),INF)){
                float tr=airTransmittance(Ray(p+gn*EPS*5,lAir),INF,rng);
                L+=throughput*evalBSDF(m,base,n,v,lAir)*solar*(cosine*SUN_SOLID*tr);
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
                    L+=throughput*evalBSDF(m,base,n,v,connection.l)*solar*attenuation(dist)*factor;
                }
            }
        }
        V next=sampleBSDF(m,n,v,rng);float cosine=dot(n,next),pdf=pdfBSDF(m,n,v,next);
        if(cosine<=0||pdf<1.e-12f||dot(gn,next)<=0)break;
        throughput*=evalBSDF(m,base,n,v,next)*(cosine/pdf);
        if(!std::isfinite(throughput.maximum()))break;
        if(depth>=3){float survive=clamp(throughput.maximum(),.05f,.94f);if(rng.uniform()>survive)break;throughput*=1/survive;}
        scatterWater=waterPool;deltaCount=0;
        ray=Ray(p+gn*EPS*5,unit(next));
    }
    return L;
}

struct Options{
    std::string mesh,out,grain,view="hero";int width=1200,height=800,spp=128,depth=12,threads=5,seed=20260913;
    float exposure=1.3f;bool bands=true;float aperture=.00025f;
};
Options parse(int argc,char**argv){
    if(argc<3)throw std::runtime_error("usage: spectral_desert scene.meshbin output_stem [--w N --h N --spp N --view hero|detail]");
    Options o;o.mesh=argv[1];o.out=argv[2];
    for(int i=3;i<argc;i++){
        std::string arg=argv[i];auto get=[&](){if(i+1>=argc)throw std::runtime_error("Missing argument for "+arg);return std::string(argv[++i]);};
        if(arg=="--w")o.width=std::stoi(get());else if(arg=="--h")o.height=std::stoi(get());else if(arg=="--spp")o.spp=std::stoi(get());
        else if(arg=="--depth")o.depth=std::stoi(get());else if(arg=="--threads")o.threads=std::stoi(get());else if(arg=="--seed")o.seed=std::stoi(get());
        else if(arg=="--view")o.view=get();else if(arg=="--exposure")o.exposure=std::stof(get());else if(arg=="--aperture")o.aperture=std::stof(get());
        else if(arg=="--no-steam")useSteam=false;else if(arg=="--no-water")useWater=false;else if(arg=="--water-absorption")waterStrength=std::stof(get());
        else if(arg=="--grain")o.grain=get();else if(arg=="--no-bands")o.bands=false;else throw std::runtime_error("Unknown argument "+arg);
    }
    if(o.width<1||o.height<1||o.spp<1||o.depth<1||o.threads<1||o.aperture<0||waterStrength<0)throw std::runtime_error("Invalid render setting");
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
        auto m=shade(p,n,t.mat,travelled*cone);
        g.normal=n;g.albedo=m.color;g.depth=travelled;g.material=t.mat;return g;
    }return g;
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
    auto o=parse(argc,argv);if(!o.grain.empty())photographicGrain.load(o.grain);omp_set_num_threads(o.threads);initSpectra();initRipples();
    auto started=std::chrono::steady_clock::now();
    std::ifstream input(o.mesh,std::ios::binary);if(!input)throw std::runtime_error("Cannot read CYBR GEO mesh "+o.mesh);
    uint32_t count;input.read(reinterpret_cast<char*>(&count),4);
    if(!input||count>40000000)throw std::runtime_error("Invalid mesh header");
    tris.reserve(count);
    for(uint32_t i=0;i<count;i++){
        float a[20];input.read(reinterpret_cast<char*>(a),80);if(!input)throw std::runtime_error("Truncated mesh");
        for(float v:a)if(!std::isfinite(v))throw std::runtime_error("Nonfinite mesh input");
        Tri t;t.p=V(a[0],a[1],a[2]);t.e1=V(a[3],a[4],a[5])-t.p;t.e2=V(a[6],a[7],a[8])-t.p;
        t.n0=V(a[9],a[10],a[11]);t.n1=V(a[12],a[13],a[14]);t.n2=V(a[15],a[16],a[17]);t.mat=int(a[18]);t.group=int(a[19]);
        if(t.mat<0||t.mat>9)throw std::runtime_error("Unknown landscape material");
        if(dot(cross(t.e1,t.e2),cross(t.e1,t.e2))>1e-20f)tris.push_back(t);
    }
    if(tris.empty())throw std::runtime_error("No geometry");
    order.resize(tris.size());std::iota(order.begin(),order.end(),0);nodes.reserve(tris.size()/2);build(0,int(order.size()));
    std::cerr<<"CYBR GEO BVH: "<<tris.size()<<" actual triangles; "<<nodes.size()<<" nodes\n";
    V camera(1.6f,-4.2f,1.50f),target(-.30f,4.9f,.02f);float hfov=70;
    if(o.view=="detail"){camera=V(4.55f,-4.4f,1.15f);target=V(1.9f,.1f,.045f);hfov=65;}
    else if(o.view=="overhead"){camera=V(.3f,-7.6f,12.3f);target=V(-.5f,3.f,0);hfov=62;}
    else if(o.view!="hero")throw std::runtime_error("Unknown camera view");
    V forward=unit(target-camera),right=unit(cross(forward,V(0,0,1))),up=cross(right,forward);
    float tanHalf=std::tan(hfov*PI/360.f),aspect=float(o.width)/o.height,focus=len(target-camera),cone=2*tanHalf/o.width;
    size_t pixels=size_t(o.width)*o.height;
    std::vector<Spec> film(pixels);std::vector<Guide> guides(pixels);std::atomic<int> rows{0};std::atomic<uint64_t> nonfinite{0};
    int strata=int(std::ceil(std::sqrt(float(o.spp))));
    #pragma omp parallel for schedule(dynamic,1)
    for(int y=0;y<o.height;y++){
        for(int x=0;x<o.width;x++){
            size_t index=size_t(y)*o.width+x;RNG rng(uint64_t(index)*0x9e3779b97f4a7c15ULL+o.seed);
            Spec sum;double lum2=0;float jitterShift=rng.uniform();
            for(int s=0;s<o.spp;s++){
                float jx=(s+rng.uniform())/o.spp,jy=std::fmod((s+.5f)*.61803398875f+jitterShift,1.f);
                float px=(2*(x+jx)/o.width-1)*tanHalf,py=(1-2*(y+jy)/o.height)*tanHalf/aspect;
                V direction=unit(forward+right*px+up*py),origin=camera;
                if(o.aperture>0){float r=std::sqrt(rng.uniform())*o.aperture,phi=2*PI*rng.uniform();V offset=right*(r*std::cos(phi))+up*(r*std::sin(phi));V fp=camera+direction*(focus/dot(direction,forward));origin+=offset;direction=unit(fp-origin);}
                Spec value=trace(Ray(origin,direction),rng,o.depth,cone);
                bool finite=true;for(float v:value.v)finite=finite&&std::isfinite(v);
                if(!finite){nonfinite++;continue;}
                sum+=value;double lum=xyz(value).y;lum2+=lum*lum;
            }
            film[index]=sum*(1.f/o.spp);
            float px=(2*(x+.5f)/o.width-1)*tanHalf,py=(1-2*(y+.5f)/o.height)*tanHalf/aspect;
            Guide g=guideRay(Ray(camera,unit(forward+right*px+up*py)),cone);
            double avg=xyz(film[index]).y;g.variance=std::max(0.,(lum2/o.spp-avg*avg)/std::max(1,o.spp-1));guides[index]=g;
        }
        int done=++rows;
        if(done%std::max(1,o.height/20)==0){
            float sec=std::chrono::duration<float>(std::chrono::steady_clock::now()-started).count();
            #pragma omp critical
            std::cerr<<100*done/o.height<<"% "<<sec<<" s\n";
        }
    }
    std::ofstream pf(o.out+".pfm",std::ios::binary);pf<<"PF\n"<<o.width<<" "<<o.height<<"\n-1.0\n";
    for(int y=o.height-1;y>=0;y--)for(int x=0;x<o.width;x++){V rgb=toRGB(film[size_t(y)*o.width+x]);pf.write(reinterpret_cast<char*>(&rgb),sizeof(V));}
    std::ofstream ppm(o.out+".ppm",std::ios::binary);ppm<<"P6\n"<<o.width<<" "<<o.height<<"\n255\n";
    Spec means;
    for(auto s:film){means+=s*(1.f/float(pixels));V v=tonemap(toRGB(s),o.exposure);for(int k=0;k<3;k++){unsigned char b=static_cast<unsigned char>(clamp(v[k])*255+.5f);ppm.write(reinterpret_cast<char*>(&b),1);}}
    std::ofstream gf(o.out+".guides",std::ios::binary);uint32_t dim[2]={uint32_t(o.width),uint32_t(o.height)};gf.write(reinterpret_cast<char*>(dim),8);gf.write(reinterpret_cast<char*>(guides.data()),guides.size()*sizeof(Guide));
    if(o.bands){std::ofstream sp(o.out+".spectral",std::ios::binary);uint32_t header[]={0x36315053,uint32_t(o.width),uint32_t(o.height),NBANDS};sp.write(reinterpret_cast<char*>(header),16);sp.write(reinterpret_cast<char*>(film.data()),film.size()*sizeof(Spec));}
    float sec=std::chrono::duration<float>(std::chrono::steady_clock::now()-started).count();
    std::ofstream meta(o.out+".json");meta<<std::setprecision(9)<<"{\n  \"renderer\": \"CYBR GEO native v6 joint-plane geology and residual-checked water\",\n  \"geometry_accelerator\": \"CYBR GEO native SAH BVH\",\n  \"view\": \""<<o.view<<"\",\n  \"width\": "<<o.width<<", \"height\": "<<o.height<<", \"spp\": "<<o.spp<<",\n  \"max_depth\": "<<o.depth<<", \"seed\": "<<o.seed<<", \"threads\": "<<o.threads<<",\n  \"triangles\": "<<tris.size()<<", \"bvh_nodes\": "<<nodes.size()<<",\n  \"spectral_bands\": 16, \"wavelength_range_nm\": [380,780],\n  \"spectral_method\": \"Jointly transported fixed midpoint wavelength quadrature, 25 nm bins\",\n  \"water_ior\": "<<WATER_IOR<<", \"dispersion\": false,\n  \"steam\": "<<(useSteam?"true":"false")<<", \"steam_model\": \"Authored heterogeneous density; delta and ratio tracking; HG phase\",\n  \"water_absorption_scale\": "<<waterStrength<<",\n  \"finite_difference_water_connection_step_radians\": 0.0001,\n  \"nonfinite_path_samples\": "<<nonfinite.load()<<",\n  \"exposure\": "<<o.exposure<<",\n  \"film_white_rgb\": ["<<whiteRGB.x<<","<<whiteRGB.y<<","<<whiteRGB.z<<"],\n  \"seconds\": "<<sec<<",\n  \"band_means\": [";
    for(int k=0;k<NBANDS;k++)meta<<(k?",":"")<<means.v[k];
    meta<<"],\n  \"water_scattering_coefficient_per_m\": "<<WATER_SIGMA_S<<",\n  \"water_scattering_HG_g\": "<<WATER_PHASE_G<<",\n  \"ripple_modes\": "<<RIPPLE_COUNT<<",\n  \"camera_origin_m\": ["<<camera.x<<","<<camera.y<<","<<camera.z<<"],\n  \"camera_target_m\": ["<<target.x<<","<<target.y<<","<<target.z<<"],\n  \"horizontal_fov_degrees\": "<<hfov<<",\n  \"aperture_radius_m\": "<<o.aperture<<",\n  \"sun_direction\": ["<<SUN.x<<","<<SUN.y<<","<<SUN.z<<"],\n  \"photographic_grayscale_albedo_detail\": "<<(!photographicGrain.levels.empty()?"true":"false")<<",\n  \"photographic_backplate\": false,\n  \"image_generation\": false,\n  \"sky_model\": \"Single-scattering spherical Rayleigh/aerosol spectral LUT, not reference-validated\",\n  \"material_spectra\": \"Authored RGB-anchor reflectance reconstruction, not measured mineral spectra\"\n}\n";
    std::cerr<<"WROTE "<<o.out<<"; "<<sec<<" seconds; invalid paths "<<nonfinite<<"\n";
    return nonfinite?2:0;
}catch(const std::exception&e){std::cerr<<"ERROR: "<<e.what()<<"\n";return 1;}}
