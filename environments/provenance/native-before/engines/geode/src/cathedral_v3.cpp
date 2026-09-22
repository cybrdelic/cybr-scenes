// CYBR GEO / GPL-2.0-only
// Native Drowned Geode extension. Reuses CYBR GEO's actual BVH and mesh
// intersections. Photographed material maps are inputs, not backgrounds.
// Sixteen spectral bands share paths until macro-quartz dispersion splits
// them. Water IOR is achromatic; its absorption remains wavelength dependent.
#include "spectral_geometry.h"
#include "wide_bvh.h"
#include <array>
#include <iomanip>
#include <stdexcept>
#include <cstring>
#include "texture_adapter.h"

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
V whiteRGB, SUN=unit(V(-.205f,.59f,.78f));
constexpr float SUN_RADIUS=.008f;
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
void initSpectra(){
    float y=0;
    for(int k=0;k<NBANDS;k++){matching[k]=cie1931(WL0+(k+.5f)*DL)*DL;y+=matching[k].y;}
    for(auto &c:matching)c=c/y;
    solar=blackbody(5650.f)*(6.8f/SUN_SOLID);
    skyBlue=blackbody(6500.f);
    for(int k=0;k<NBANDS;k++)skyBlue.v[k]*=std::pow(550.f/(WL0+(k+.5f)*DL),2.5f);
    skyBlue*=1.f/xyz(skyBlue).y;skyHorizon=blackbody(7600.f);
    whiteRGB=toRGB(blackbody(6500.f));
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
std::array<Pool,2> pools={Pool{.5f,18.5f,18.5f,36.5f,.075f,2.8f},Pool{.5f,18.5f,18.5f,36.5f,.075f,2.8f}};
float poolQ(V p,int i){
    auto a=pools[i];float x=(p.x-a.x)/a.rx,y=(p.y-a.y)/a.ry;
    float ang=std::atan2(y,x);
    float edge=1+.082f*std::sin(3*ang+.7f+i)+.044f*std::sin(7*ang-1.4f)+.019f*std::sin(13*ang+i)+.021f*noise(p.x*1.7f,p.y*1.7f);
    return std::sqrt(x*x+y*y)/edge;
}
float waterHeight(float x,float y,int){return .075f+.012f*std::sin(1.08f*x+1.48f*y)+.006f*std::sin(-2.31f*x+2.05f*y+1.2f)+.002f*std::sin(5.7f*x-3.2f*y+.4f);}
V waterNormal(float x,float y,int){float a=.012f*std::cos(1.08f*x+1.48f*y),b=.006f*std::cos(-2.31f*x+2.05f*y+1.2f),c=.002f*std::cos(5.7f*x-3.2f*y+.4f);return unit(V(-(1.08f*a-2.31f*b+5.7f*c),-(1.48f*a+2.05f*b-3.2f*c),1));}
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
    float elevation=clamp(d.z),h=std::pow(1-elevation,3.5f);
    Spec s=skyBlue*(.85f+.40f*elevation)+skyHorizon*(.40f*h);
    if(d.z<0)s=skyHorizon*.18f;
    if(solarVisible&&dot(d,SUN)>=SUN_COS)s+=solar;
    return s;
}

bool closest(const Ray&r,Hit&h){
    bool ok=wideHit(r,h);
    if(!useWater&&ok&&tris[h.tri].mat>=6&&tris[h.tri].mat<=7){
        V origin=r.o+r.d*(h.t+EPS*4);float travelled=h.t+EPS*4;Hit next;
        for(int i=0;i<8;i++){
            if(!wideHit(Ray(origin,r.d),next))return false;
            if(tris[next.tri].mat<6||tris[next.tri].mat>7){next.t+=travelled;h=next;return true;}
            float step=next.t+EPS*4;origin+=r.d*step;travelled+=step;next=Hit();
        }return false;
    }return ok;
}
bool opaqueShadow(Ray r,float distance){Hit h;h.t=distance;return wideHit(r,h,true,true);}

// Bounded, genuinely ray-integrated participating medium. This is a procedural
// density field, NOT a Navier-Stokes/thermal plume simulation or a 2-D overlay.
const V FOG_LO(-17,-19,.085f),FOG_HI(18,53,25.f);
constexpr float STEAM_SCALE=1.f,MAJORANT=.009f,PHASE_G=.49f,FOG_SIGMA=.0028f;
bool fogInterval(const Ray&r,float maximum,float &a,float &b){
    a=0;b=maximum;
    for(int k=0;k<3;k++){
        if(std::fabs(r.d[k])<1.e-9f){if(r.o[k]<FOG_LO[k]||r.o[k]>FOG_HI[k])return false;continue;}
        float x=(FOG_LO[k]-r.o[k])/r.d[k],y=(FOG_HI[k]-r.o[k])/r.d[k];if(x>y)std::swap(x,y);
        a=std::max(a,x);b=std::min(b,y);if(a>=b)return false;
    }return b>a;
}
float steamDensity(V){return useSteam?FOG_SIGMA:0.f;}
float sampleSteam(const Ray&r,float maxT,RNG&rng){
 if(!useSteam)return INF;float a,b;if(!fogInterval(r,maxT,a,b))return INF;
 float t=a-std::log(std::max(1.e-9f,1-rng.uniform()))/FOG_SIGMA;return t<b?t:INF;
}
float steamTransmittance(const Ray&r,float maxT,RNG&){
 if(!useSteam)return 1;float a,b;if(!fogInterval(r,maxT,a,b))return 1;
 return std::exp(-FOG_SIGMA*(b-a));
}
const V ATM_LO(-1250,48,-.4f),ATM_HI(1250,1300,210);
constexpr float ATM_SIGMA=.00000000001f;
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
Surface shade(V p,V &n,int material,float footprint,const Hit &hit){
 const auto &tr=tris[hit.tri];const auto &a=attributes[hit.tri];
 V tint=a.col[0]*(1-hit.u-hit.v)+a.col[1]*hit.u+a.col[2]*hit.v;
 Texel tex{V(.25f),V(0,0,1),.7f};Surface m;m.kind=material;
 if(a.texture>=0){
  float u=a.uv[0].u*(1-hit.u-hit.v)+a.uv[1].u*hit.u+a.uv[2].u*hit.v;
  float v=a.uv[0].v*(1-hit.u-hit.v)+a.uv[1].v*hit.u+a.uv[2].v*hit.v;
  float du1=a.uv[1].u-a.uv[0].u,dv1=a.uv[1].v-a.uv[0].v,du2=a.uv[2].u-a.uv[0].u,dv2=a.uv[2].v-a.uv[0].v;
  float area=std::max(1.e-10f,len(cross(tr.e1,tr.e2)));float rate=std::sqrt(std::fabs(du1*dv2-du2*dv1)/area);
  tex=textures[a.texture].sample(u,v,footprint*rate);
  float det=du1*dv2-du2*dv1;
  if(std::fabs(det)>1.e-8f){
   V t=unit((tr.e1*dv2-tr.e2*dv1)/det);t=unit(t-n*dot(t,n));V b=unit((tr.e2*du1-tr.e1*du2)/det);b=unit(b-n*dot(b,n)-t*dot(b,t));
   // Texture V is top-origin: tangent-space GL normals use the opposite B.
   V nn=unit(t*(tex.normal.x*.72f)-b*(tex.normal.y*.72f)+n*std::max(.2f,tex.normal.z));
   if(dot(nn,n)>.35f)n=nn;
  }
 }else if(a.texture<=-2){
  int id=a.texture==-3?3:4;
  float scale=a.texture==-3?.65f:.52f;
  V weights=V(std::pow(std::fabs(n.x),6.f),std::pow(std::fabs(n.y),6.f),std::pow(std::fabs(n.z),6.f));
  weights=weights/std::max(1.e-9f,weights.x+weights.y+weights.z);
  auto tx=textures[id].sample(p.y*scale,p.z*scale,footprint*scale);
  auto ty=textures[id].sample(p.x*scale,p.z*scale,footprint*scale);
  auto tz=textures[id].sample(p.x*scale,p.y*scale,footprint*scale);
  tex.color=tx.color*weights.x+ty.color*weights.y+tz.color*weights.z;
  tex.rough=tx.rough*weights.x+ty.rough*weights.y+tz.rough*weights.z;
  tex.normal=tx.normal*weights.x+ty.normal*weights.y+tz.normal*weights.z;
  // Triplanar tangent-space normals from the paired photographed height map.
  V perturb=V(0,tx.normal.x,-tx.normal.y)*weights.x+V(ty.normal.x,0,-ty.normal.y)*weights.y+V(tz.normal.x,-tz.normal.y,0)*weights.z;
  n=unit(n+(perturb-n*dot(perturb,n))*.68f);
  // Low-strength mesoscopic relief is evaluated in object space, bandwidth-limited.
  Frame frame(n);float f=29.f,filter=1/(1+sqr(footprint*f));
  V q=p*f;float dt=noise(q+frame.t*.025f)-noise(q-frame.t*.025f),db=noise(q+frame.b*.025f)-noise(q-frame.b*.025f);
  n=unit(n+(frame.t*dt+frame.b*db)*(1.7f*filter));
 }
 m.color=tex.color*tint;m.rough=clamp(tex.rough,.4f,.93f);
 if(material==0){
  float weather=noise(V(p.x*.29f,p.y*.29f,p.z*.36f));
  m.color*=.98f+.21f*weather;
  float z=p.z+.18f*fbm(V(p.x*.32f,p.y*.25f,p.z*.22f))+.07f*p.y;
  float mineral=std::exp(-sqr(std::sin(z*.85f+.35f*noise(p*.4f)))/.013f)*.12f;
  m.color=m.color*(1-mineral)+V(.34f,.30f,.24f)*mineral;
  // Green staining occurs only near the water. It is not an emissive material.
  float algae=std::exp(-sqr((p.z-.45f)/.70f))*clamp(.5f+noise(p*.78f))*.27f;
  m.color=m.color*(1-algae)+V(.066f,.092f,.026f)*algae;
 }
 bool submerged=p.z<.085f;
 float wet=submerged?1.f:clamp((.7f-p.z)*1.8f);
 if(material==0)wet=std::max(wet,.26f*clamp(.35f+noise(V(p.x*1.4f,p.y*.55f,p.z*.075f))*1.6f));
 m.color*=1-.2f*wet;m.rough=m.rough*(1-wet)+.31f*wet;
 if(submerged){m.ior=1.5f/WATER_IOR;
  if(material==1){float silt=.40f+.14f*noise(p*.7f);m.color=m.color*(1-silt)+V(.25f,.28f,.26f)*silt;m.rough=.78f;}
 }
 if(material==3){m.color=tint;m.rough=.48f;}
 if(material==4){m.color=tint;m.rough=.63f;}
 if(material==5){m.color=m.color*.6f+V(.26f,.24f,.19f)*.4f;m.rough=.61f;}

 m.color=vmin(vmax(m.color,V(.002f)),V(.93f));return m;
}

// A numerical Snell-law connection to the displaced water heightfield.
// The finite-difference solid-angle Jacobian includes local wave focusing.
// This owns one-interface floor -> water -> solar-disc paths; continuation
// paths of that class do not add the sun a second time.
struct Connection{V q,l,n;float jacobian=0;bool valid=false;};
Connection waterConnection(V p,V air,int pool,bool computeJac=true){
    Connection c;const auto& a=pools[pool];
    V w=-refractRay(-air,V(0,0,1),1/WATER_IOR);
    if(w.z<=0)return c;
    V q=p+w*((a.level-p.z)/w.z);
    for(int i=0;i<7;i++){
        V n=waterNormal(q.x,q.y,pool);w=-refractRay(-air,n,1/WATER_IOR);
        if(w.z<.1f)return c;
        q=p+w*((waterHeight(q.x,q.y,pool)-p.z)/w.z);
    }
    if(std::fabs(q.x-a.x)>a.rx*1.28f||std::fabs(q.y-a.y)>a.ry*1.28f)return c;
    c.q=q;c.l=unit(q-p);c.n=waterNormal(q.x,q.y,pool);c.valid=dot(c.l,c.n)>0&&q.z>p.z;
    if(computeJac&&c.valid){
        Frame frame(air);constexpr float e=.002f;
        auto u=waterConnection(p,unit(air+frame.t*e),pool,false);
        auto v=waterConnection(p,unit(air+frame.b*e),pool,false);
        if(!u.valid||!v.valid){c.valid=false;return c;}
        c.jacobian=std::fabs(dot(c.l,cross((u.l-c.l)/e,(v.l-c.l)/e)));
        if(!std::isfinite(c.jacobian)||c.jacobian>30)c.valid=false;
    }
    return c;
}

// Finite geometry-aware sky portals: no lighting cards are visible or emissive.
// Both merely importance-sample the actual sky through the real cave apertures.
struct Portal{V center,u,v,n;float area;};
std::array<Portal,3> portals={
 Portal{V(1.2f,12.8f,15.5f),V(7.1f,0,0),V(0,9.2f,0),V(0,0,1),261.28f},
 Portal{V(-4.8f,2.f,14.5f),V(3.f,0,0),V(0,4.7f,0),V(0,0,1),56.4f},
 Portal{V(-1.5f,-20.1f,4.2f),V(7.2f,0,0),V(0,0,7.5f),V(0,-1,0),216.f}};
float portalPDF(V p,V d){float sum=0;for(const auto&a:portals){
 float dn=dot(d,a.n);if(std::fabs(dn)<1e-8f)continue;float t=dot(a.center-p,a.n)/dn;if(t<=EPS)continue;
 V q=p+d*t-a.center;if(std::fabs(dot(q,a.u)/dot(a.u,a.u))>1||std::fabs(dot(q,a.v)/dot(a.v,a.v))>1)continue;
 sum+=(1.f/3.f)*t*t/(std::fabs(dn)*a.area);
 }return sum;}
V samplePortal(V p,RNG&rng){const auto&a=portals[std::min(2,int(rng.uniform()*3))];return unit(a.center+a.u*(2*rng.uniform()-1)+a.v*(2*rng.uniform()-1)-p);}
float misPower(float a,float b){return a*a/(a*a+b*b+1e-30f);}
float quartzIndex(float wavelength){float l2=sqr(wavelength*.001f);return std::sqrt(1.28604141f+1.07044083f*l2/(l2-.0100585997f)+1.10202242f*l2/(l2-100.f));}
Spec quartzAttenuation(float metres){Spec s;for(int k=0;k<NBANDS;k++){float w=WL0+(k+.5f)*DL;s.v[k]=std::exp(-metres*(.055f+.12f*std::exp(-.5f*sqr((w-420)/100))));}return s;}
constexpr float WATER_SCATTER_RATE=.033f;
struct WaterSkySample{V dir;Spec radiance;float pdf=1/(2*PI),branchProbability=0;bool valid=false;};
WaterSkySample sampleWaterSky(V p,RNG&rng){
 WaterSkySample o;float z=rng.uniform(),phi=2*PI*rng.uniform(),rr=std::sqrt(1-z*z);o.dir=V(rr*std::cos(phi),rr*std::sin(phi),z);
 Hit hit;if(!wideHit(Ray(p,o.dir),hit)||tris[hit.tri].mat!=6)return o;
 const auto &tr=tris[hit.tri];V n=unit(tr.n0*(1-hit.u-hit.v)+tr.n1*hit.u+tr.n2*hit.v);
 if(dot(n,o.dir)>0)n=-n;
 float f=fresnelD(-dot(o.dir,n),WATER_IOR,1);if(f>=1)return o;
 V air=refractRay(o.dir,n,WATER_IOR);if(dot(air,air)<.5f)return o;
 V q=p+o.dir*hit.t;Ray r(q-n*EPS*8,air);if(opaqueShadow(r,INF))return o;
 o.branchProbability=(1-f)*std::exp(-WATER_SCATTER_RATE*hit.t);
 o.radiance=environment(air,false)*attenuation(hit.t)*(sqr(WATER_IOR)*o.branchProbability*airTransmittance(r,INF,rng));o.valid=true;return o;
}
#include "rough_quartz_v3.h"
bool splitting=true,clay=false;
Spec trace(Ray ray,RNG&rng,int maxDepth,float pixelCone,int band=-1,int startWater=-1,int startQuartz=0,int previousScatter=-2,int previousDelta=0,V previousPoint=V(),float previousPDF=0,int primarySplit=0,bool skipFirstFog=false,float travelled=0,Spec *reflectionOut=nullptr){
 Spec L,throughput(1);if(band>=0){throughput=Spec();throughput.v[band]=1;}
 int waterPool=startWater,quartzDepth=startQuartz,scatterWater=previousScatter,deltaCount=previousDelta;
 V prev=previousPoint;float prevPdf=previousPDF,exitSkyMIS=1.f;uint32_t baseDimension=rng.dimension;
 for(int depth=0;depth<maxDepth;depth++){
  rng.dimension=baseDimension+uint32_t(depth)*32;
  Hit h;bool found=closest(ray,h);
  // Common-path deterministic wavelength splitting at the first dispersive
  // interface. Bands share random numbers; no rainbow-noise hero roulette.
  if(found&&tris[h.tri].mat==8&&band<0&&splitting&&!clay){
   Spec sum;RNG common=rng;
   for(int k=0;k<NBANDS;k++){RNG branch=common;sum+=trace(ray,branch,maxDepth-depth,pixelCone,k,waterPool,quartzDepth,scatterWater,deltaCount,prev,prevPdf,0,skipFirstFog&&depth==0,travelled);}
   return L+throughput*sum;
  }
  constexpr float waterScatterRate=WATER_SCATTER_RATE;
  if(waterPool>=0&&found&&!clay){
   float st=-std::log(std::max(1e-8f,1-rng.uniform()))/waterScatterRate;
   if(st<h.t){
    V p=ray.o+ray.d*st;throughput*=attenuation(st);V la=sampleSun(rng);auto c=waterConnection(p,la,0);
    if(c.valid){float dist=len(c.q-p),ca=dot(la,c.n);
     if(ca>0&&!opaqueShadow(Ray(p,c.l),std::max(EPS,dist-EPS*15))&&!opaqueShadow(Ray(c.q+c.n*EPS*12,la),INF)){
      float fr=fresnelD(ca,1,WATER_IOR),air=airTransmittance(Ray(c.q+c.n*EPS*12,la),INF,rng);
      L+=throughput*solar*attenuation(dist)*(phaseHG(dot(ray.d,c.l),.62f)*SUN_SOLID*(1-fr)*WATER_IOR*WATER_IOR*c.jacobian*air*std::exp(-dist*waterScatterRate));
     }
    }
    auto ws=sampleWaterSky(p,rng);if(ws.valid){float ph=phaseHG(dot(ray.d,ws.dir),.62f);L+=throughput*ws.radiance*(ph*misPower(ws.pdf,ph*ws.branchProbability)/ws.pdf);}
    exitSkyMIS=1.f;V next=sampleHG(ray.d,rng,.62f);prev=p;prevPdf=phaseHG(dot(ray.d,next),.62f);scatterWater=0;deltaCount=0;ray=Ray(p,next);continue;
   }
  }
  float scatterT=(waterPool<0&&quartzDepth==0&&!clay&&!(skipFirstFog&&depth==0))?sampleSteam(ray,found?h.t:INF,rng):INF;
  if(scatterT<(found?h.t:INF)){
   V p=ray.o+ray.d*scatterT,l=sampleSun(rng);
   if(!opaqueShadow(Ray(p,l),INF))L+=throughput*solar*(phaseHG(dot(ray.d,l))*SUN_SOLID*airTransmittance(Ray(p,l),INF,rng)*.995f);
   V sky=samplePortal(p,rng);float pdf=portalPDF(p,sky),phase=phaseHG(dot(ray.d,sky));
   if(pdf>0&&!opaqueShadow(Ray(p,sky),INF))L+=throughput*environment(sky,false)*(phase*airTransmittance(Ray(p,sky),INF,rng)*misPower(pdf,phase)/pdf);
   V next=sampleHG(ray.d,rng);prev=p;prevPdf=phaseHG(dot(ray.d,next));
   exitSkyMIS=1.f;throughput*=.995f;scatterWater=-1;deltaCount=0;ray=Ray(p,next);continue;
  }
  if(!found){
   bool sunVisible=!(scatterWater==-1&&deltaCount==0)&&!(scatterWater>=0&&deltaCount==1);
   float weight=(prevPdf>0&&deltaCount==0)?misPower(prevPdf,portalPDF(prev,ray.d)):1.f;
   L+=throughput*environment(ray.d,false)*(weight*exitSkyMIS);
   if(sunVisible&&dot(ray.d,SUN)>=SUN_COS)L+=throughput*solar;
   break;
  }
  if(waterPool>=0)throughput*=attenuation(h.t);
  if(quartzDepth>0)throughput*=quartzAttenuation(h.t);
  const auto &tri=tris[h.tri];V p=ray.o+ray.d*h.t,gn=unit(cross(tri.e1,tri.e2));
  V n=unit(tri.n0*(1-h.u-h.v)+tri.n1*h.u+tri.n2*h.v);int mat=tri.mat;
  if(!clay&&(mat==8||mat==9)){
   bool entering=dot(ray.d,gn)<0;
   // Intergrown crystals of the same ordinary-index material have no optical
   // discontinuity at an internal overlap boundary. Track occupancy rather
   // than inventing an air layer between intersecting quartz meshes.
   if((entering&&quartzDepth>0)||(!entering&&quartzDepth>1)){
    quartzDepth=std::max(0,quartzDepth+(entering?1:-1));
    travelled+=h.t;ray=Ray(p+ray.d*EPS*8,ray.d);continue;
   }
   if(dot(n,gn)<0)n=-n;if(dot(n,ray.d)>0)n=-n;
   V v=-ray.d;
   float index=quartzIndex(band>=0?WL0+(band+.5f)*DL:550.f);
   float ratio=entering?index:1.f/index;
   float alpha=(mat==8?.022f:.042f)*(1+.22f*noise(p*8.f));
   V light=sampleSun(rng);auto direct=roughGlass(n,v,light,ratio,alpha);
   V origin=p+gn*(dot(light,gn)>0?EPS*8:-EPS*8);
   if(direct.f>0&&!opaqueShadow(Ray(origin,light),INF))
    L+=throughput*solar*(direct.f*std::fabs(dot(n,light))*SUN_SOLID*airTransmittance(Ray(origin,light),INF,rng));
   V sky=samplePortal(p,rng);float spdf=portalPDF(p,sky);auto se=roughGlass(n,v,sky,ratio,alpha);
   origin=p+gn*(dot(sky,gn)>0?EPS*8:-EPS*8);
   if(se.f>0&&spdf>1e-12f&&!opaqueShadow(Ray(origin,sky),INF))
    L+=throughput*environment(sky,false)*(se.f*std::fabs(dot(n,sky))*airTransmittance(Ray(origin,sky),INF,rng)*misPower(spdf,se.pdf)/spdf);
   bool crossed=false;V next=sampleRoughGlass(n,v,ratio,alpha,rng,crossed);
   if(dot(next,next)<.5f)break;
   auto e=roughGlass(n,v,next,ratio,alpha);if(e.pdf<1e-18f||!std::isfinite(e.pdf)||!std::isfinite(e.f))break;
   if((dot(next,gn)*dot(v,gn)<0)!=crossed)break;
   throughput*=e.f*std::fabs(dot(n,next))/e.pdf;
   if(crossed)quartzDepth=std::max(0,quartzDepth+(entering?1:-1));
   travelled+=h.t;prev=p;prevPdf=e.pdf;deltaCount=0;scatterWater=-1;exitSkyMIS=1.f;
   ray=Ray(p+gn*(dot(next,gn)>0?EPS*8:-EPS*8),next);continue;
  }
  if(!clay&&mat==6){
   bool enter=dot(ray.d,gn)<0;if(dot(n,gn)<0)n=-n;if(dot(n,ray.d)>0)n=-n;
   if(mat==8||mat==9){Frame f(n);float q=std::sin(p.z*380.f+p.x*12.f)*.00016f;n=unit(n+f.t*q+f.b*(.00008f*std::sin(p.y*510.f+p.x*240.f)));}
   float index=mat==6?WATER_IOR:quartzIndex(band>=0?WL0+(band+.5f)*DL:550.f);
   float ei=enter?1.f:index,et=enter?index:1.f,fr=fresnelD(-dot(ray.d,n),ei,et);
   if(mat==6&&primarySplit&&depth==0&&band<0){
    RNG reflectedRng=rng,transmittedRng=rng;transmittedRng.dimension+=16;
    Spec lr=trace(Ray(p+n*EPS*6,unit(reflect(ray.d,n))),reflectedRng,maxDepth-depth-1,pixelCone,band,waterPool,quartzDepth,scatterWater,deltaCount+1,prev,prevPdf,0,false,travelled+h.t);
    V td=refractRay(ray.d,n,ei/et);Spec lt;
    if(dot(td,td)>.5f)lt=trace(Ray(p-n*EPS*6,td),transmittedRng,maxDepth-depth-1,pixelCone,band,enter?0:-1,quartzDepth,scatterWater,deltaCount+1,prev,prevPdf,0,false,travelled+h.t);
    Spec reflectContribution=throughput*lr*fr;if(reflectionOut)*reflectionOut=reflectContribution;
    return L+reflectContribution+throughput*lt*((1-fr)*sqr(ei/et));
   }
   exitSkyMIS=1.f;
   if(mat==6&&!enter&&scatterWater>=0&&deltaCount==0){float q=ray.d.z>0?1/(2*PI):0;
    exitSkyMIS=misPower(prevPdf*(1-fr)*std::exp(-h.t*waterScatterRate),q);}
   if(rng.uniform()<fr)ray=Ray(p+n*EPS*6,unit(reflect(ray.d,n)));
   else {V d=refractRay(ray.d,n,ei/et);if(dot(d,d)<.5f)ray=Ray(p+n*EPS*6,unit(reflect(ray.d,n)));
    else {throughput*=sqr(ei/et);if(mat==6)waterPool=enter?0:-1;else quartzDepth=std::max(0,quartzDepth+(enter?1:-1));ray=Ray(p-n*EPS*6,d);}}
   travelled+=h.t;deltaCount++;continue;
  }
  if(dot(gn,ray.d)>0)gn=-gn;if(dot(n,gn)<0)n=-n;
  Surface m=shade(p,n,mat,std::max(.00002f,(travelled+h.t)*pixelCone/std::max(.18f,std::fabs(dot(n,ray.d)))),h);
  if(dot(n,gn)<.25f||dot(n,-ray.d)<.06f)n=gn;
  if(clay){m.color=V(.38f);m.rough=.85f;}
  Spec base=rgbAnchors(m.color);V v=-ray.d,lAir=sampleSun(rng);
  if(waterPool<0){float cosine=dot(n,lAir);
   if(cosine>0&&dot(gn,lAir)>0&&!opaqueShadow(Ray(p+gn*EPS*6,lAir),INF))L+=throughput*evalBSDF(m,base,n,v,lAir)*solar*(cosine*SUN_SOLID*airTransmittance(Ray(p+gn*EPS*6,lAir),INF,rng));
   V sky=samplePortal(p,rng);float cs=dot(n,sky),pdf=portalPDF(p,sky);
   if(cs>0&&dot(gn,sky)>0&&pdf>1e-10f&&!opaqueShadow(Ray(p+gn*EPS*6,sky),INF)){
    float bsdfPdf=pdfBSDF(m,n,v,sky),tr=airTransmittance(Ray(p+gn*EPS*6,sky),INF,rng);
    L+=throughput*evalBSDF(m,base,n,v,sky)*environment(sky,false)*(cs*tr*misPower(pdf,bsdfPdf)/pdf);
   }
  }else {
   auto c=waterConnection(p,lAir,0);if(c.valid){float cosine=dot(n,c.l),dist=len(c.q-p),ca=dot(lAir,c.n),cw=dot(c.l,c.n);
    if(cosine>0&&dot(gn,c.l)>0&&ca>0&&cw>0&&!opaqueShadow(Ray(p+gn*EPS*6,c.l),std::max(EPS,dist-EPS*15))&&!opaqueShadow(Ray(c.q+c.n*EPS*12,lAir),INF)){
     float f=fresnelD(ca,1,WATER_IOR),tr=airTransmittance(Ray(c.q+c.n*EPS*12,lAir),INF,rng);
     L+=throughput*evalBSDF(m,base,n,v,c.l)*solar*attenuation(dist)*(cosine*SUN_SOLID*(1-f)*WATER_IOR*WATER_IOR*c.jacobian*tr*std::exp(-dist*waterScatterRate));
    }
   }
  }
  if(waterPool>=0){auto ws=sampleWaterSky(p+gn*EPS*6,rng);float cs=dot(n,ws.dir);
   if(ws.valid&&cs>0&&dot(gn,ws.dir)>0){float bp=pdfBSDF(m,n,v,ws.dir);
    L+=throughput*evalBSDF(m,base,n,v,ws.dir)*ws.radiance*(cs*misPower(ws.pdf,bp*ws.branchProbability)/ws.pdf);}}
  exitSkyMIS=1.f;V next=sampleBSDF(m,n,v,rng);float cs=dot(n,next),pdf=pdfBSDF(m,n,v,next);
  if(cs<=0||pdf<1e-12f||dot(gn,next)<=0)break;
  throughput*=evalBSDF(m,base,n,v,next)*(cs/pdf);
  if(!std::isfinite(throughput.maximum()))break;
  if(depth>=3){float survive=clamp(throughput.maximum(),.05f,.94f);if(rng.uniform()>survive)break;throughput*=1/survive;}
  travelled+=h.t;prev=p;prevPdf=pdf;scatterWater=waterPool;deltaCount=0;ray=Ray(p+gn*EPS*6,unit(next));
 }
 return L;
}

// V2: forced first collision in a bounded homogeneous atmosphere, followed by
// full multiple-scattering continuation. Every camera sample evaluates both
// the surface-survival and atmospheric-scatter terms, instead of roulette
// between a dark background and a rare bright haze contribution.
thread_local Spec sampleReflection, sampleVolume;

Spec tracePrimary(Ray ray,RNG &rng,int maxDepth,float cone) {
    sampleReflection=Spec(); sampleVolume=Spec();
    Hit h; bool found=closest(ray,h); float lo=0,hi=0;
    float T=1.f;
    bool fog=useSteam&&!clay&&fogInterval(ray,found?h.t:INF,lo,hi);
    if(fog) T=std::exp(-FOG_SIGMA*(hi-lo));
    Spec reflection;
    RNG surfaceRng=rng;
    Spec surface=trace(ray,surfaceRng,maxDepth,cone,-1,-1,0,-2,0,V(),0,1,true,0,&reflection);
    sampleReflection=reflection*T;
    if(!fog||T>=1.f) return surface;
    RNG volumeRng=rng; volumeRng.dimension=640;
    float t=lo-std::log(std::max(1.e-9f,1-volumeRng.uniform()*(1-T)))/FOG_SIGMA;
    V p=ray.o+ray.d*t;
    Spec scatter;
    V sun=sampleSun(volumeRng);
    if(!opaqueShadow(Ray(p,sun),INF))
        scatter+=solar*(phaseHG(dot(ray.d,sun))*SUN_SOLID*airTransmittance(Ray(p,sun),INF,volumeRng));
    V sky=samplePortal(p,volumeRng);
    float pdf=portalPDF(p,sky),phase=phaseHG(dot(ray.d,sky));
    if(pdf>0&&!opaqueShadow(Ray(p,sky),INF))
        scatter+=environment(sky,false)*(phase*airTransmittance(Ray(p,sky),INF,volumeRng)*misPower(pdf,phase)/pdf);
    V next=sampleHG(ray.d,volumeRng);
    scatter+=trace(Ray(p,next),volumeRng,maxDepth-1,cone,-1,-1,0,-1,0,p,phaseHG(dot(ray.d,next)),0,false,t);
    sampleVolume=scatter*((1-T)*.995f);
    return surface*T+sampleVolume;
}

struct Options{bool adaptive=false;
    std::string mesh,out,view="hero";int width=1600,height=1000,spp=128,depth=16,threads=5,seed=20260913;
    float exposure=1.0f;bool bands=true;float aperture=.00025f;
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
        else if(arg=="--adaptive")o.adaptive=true;else if(arg=="--no-split")splitting=false;else if(arg=="--clay")clay=true;else if(arg=="--no-bands")o.bands=false;else throw std::runtime_error("Unknown argument "+arg);
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
        if(t.mat==6&&!clay){V d=refractRay(ray.d,n,1/WATER_IOR);ray=Ray(p-n*EPS*5,d);continue;}
        V geometricGuide=n;auto m=shade(p,n,t.mat,travelled*cone,h);
        g.normal=geometricGuide;g.albedo=m.color;g.depth=travelled;g.material=t.mat;return g;
    }return g;
}

Guide primaryGuideRay(Ray ray,float cone,bool reflection){
 Guide g;Hit h;if(!closest(ray,h))return g;const auto&t=tris[h.tri];V p=ray.o+ray.d*h.t;
 V n=unit(t.n0*(1-h.u-h.v)+t.n1*h.u+t.n2*h.v);if(dot(n,ray.d)>0)n=-n;
 g.normal=n;g.depth=h.t;g.material=t.mat;g.albedo=V(1);
 if(reflection&&t.mat==6){g=guideRay(Ray(p+n*EPS*6,unit(reflect(ray.d,n))),cone);g.depth+=h.t;g.material=6;g.albedo=V(1);}
 return g;
}

int selftest(){
    initSpectra();float f=fresnelD(1,1,WATER_IOR),expected=sqr((WATER_IOR-1)/(WATER_IOR+1));
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
    auto o=parse(argc,argv);initSpectra();omp_set_num_threads(o.threads);
    auto started=std::chrono::steady_clock::now();
    std::ifstream input(o.mesh,std::ios::binary);if(!input)throw std::runtime_error("Cannot read CYBR GEO mesh "+o.mesh);
    char magic[4];input.read(magic,4);if(std::memcmp(magic,"CVR2",4))throw std::runtime_error("Not CVR2");uint32_t count;input.read(reinterpret_cast<char*>(&count),4);
    if(!input||count>40000000)throw std::runtime_error("Invalid mesh header");
    tris.reserve(count);
    for(uint32_t i=0;i<count;i++){
        float a[36];input.read(reinterpret_cast<char*>(a),144);if(!input)throw std::runtime_error("Truncated mesh");
        for(float v:a)if(!std::isfinite(v))throw std::runtime_error("Nonfinite mesh input");
        Tri t;t.p=V(a[0],a[1],a[2]);t.e1=V(a[3],a[4],a[5])-t.p;t.e2=V(a[6],a[7],a[8])-t.p;
        t.n0=V(a[9],a[10],a[11]);t.n1=V(a[12],a[13],a[14]);t.n2=V(a[15],a[16],a[17]);t.mat=int(a[18]);t.group=int(a[19]);
        if(t.mat<0||t.mat>9)throw std::runtime_error("Unknown landscape material");
        if(dot(cross(t.e1,t.e2),cross(t.e1,t.e2))>1e-20f){tris.push_back(t);Attribute at;for(int j=0;j<3;j++){at.uv[j]={a[20+j*2],a[21+j*2]};at.col[j]=V(a[26+j*3],a[27+j*3],a[28+j*3]);}at.texture=int(a[35]);attributes.push_back(at);}
    }
    if(tris.empty())throw std::runtime_error("No geometry");
    std::string root=o.mesh.substr(0,o.mesh.find_last_of("/\\"));textures.resize(5);for(int i=0;i<5;i++)textures[i].load(root+"/textures/"+std::to_string(i)+".cvtex");
    order.resize(tris.size());std::iota(order.begin(),order.end(),0);nodes.reserve(tris.size()/2);build(0,int(order.size()));
    {std::vector<Tri> sorted;std::vector<Attribute> sortedAttributes;sorted.reserve(tris.size());sortedAttributes.reserve(tris.size());
     for(int idx:order){sorted.push_back(tris[idx]);sortedAttributes.push_back(attributes[idx]);}
     tris.swap(sorted);attributes.swap(sortedAttributes);std::iota(order.begin(),order.end(),0);}
    buildWide();
    int traversalErrors=0;
    for(int i=0;i<5000;i++){RNG test(i+7293);Ray ray(V(test.uniform()*28-14,test.uniform()*58-16,test.uniform()*17-3),unit(V(test.uniform()*2-1,test.uniform()*2-1,test.uniform()*2-1)));
     Hit a,b;bool ha=wideHit(ray,a),hb=meshHitReference(ray,b);if(ha!=hb||(ha&&std::fabs(a.t-b.t)>1.e-4f)){if(traversalErrors<12)std::cerr<<"MISMATCH "<<i<<" "<<ha<<" "<<hb<<" "<<a.t<<" "<<b.t<<" tris "<<a.tri<<" "<<b.tri<<"\n";traversalErrors++;}}
    if(traversalErrors)throw std::runtime_error("BVH equivalence failure");
    std::cerr<<"BVH equivalence: 5000 rays passed\n";
    std::cerr<<"CYBR GEO BVH: "<<tris.size()<<" actual triangles; "<<nodes.size()<<" nodes\n";
    V camera(-3.8f,-10.3f,2.6f),target(.6f,12.8f,6.3f);float hfov=82;
    if(o.view=="detail"){camera=V(.4f,-4.2f,2.55f);target=V(3.3f,.25f,1.35f);hfov=49;}
    else if(o.view=="reverse"){camera=V(1.1f,12.f,2.0f);target=V(-1.6f,34.f,4.8f);hfov=76;}
    else if(o.view!="hero")throw std::runtime_error("Unknown camera view");
    V forward=unit(target-camera),right=unit(cross(forward,V(0,0,1))),up=cross(right,forward);
    float tanHalf=std::tan(hfov*PI/360.f),aspect=float(o.width)/o.height,focus=len(target-camera),cone=2*tanHalf/o.width;
    size_t pixels=size_t(o.width)*o.height;std::vector<uint32_t> sampleCounts(pixels);
    std::vector<Spec> film(pixels),reflectionFilm(pixels),volumeFilm(pixels);std::vector<Guide> guides(pixels),reflectionGuides(pixels),primaryGuides(pixels);std::atomic<int> rows{0};std::atomic<uint64_t> nonfinite{0};
    int strata=int(std::ceil(std::sqrt(float(o.spp))));
    #pragma omp parallel for schedule(dynamic,1)
    for(int y=0;y<o.height;y++){
        for(int x=0;x<o.width;x++){
            size_t index=size_t(y)*o.width+x;RNG rng(uint64_t(index)*0x9e3779b97f4a7c15ULL+o.seed);
            int pixelSpp=o.spp;
            float cx=(2*(x+.5f)/o.width-1)*tanHalf,cy=(1-2*(y+.5f)/o.height)*tanHalf/aspect;
            Guide first=primaryGuideRay(Ray(camera,unit(forward+right*cx+up*cy)),cone,false);
            if(o.adaptive){
             if(first.material<0)pixelSpp=std::max(8,o.spp/8);
             else if((first.material==0||first.material==3)&&first.depth>7)pixelSpp=std::max(16,o.spp/2);
             else if(first.material==8||first.material==9)pixelSpp=std::max(128,o.spp*2);
            }
            sampleCounts[index]=pixelSpp;Spec sum,reflectionSum,volumeSum;double lum2=0;
            for(int s=0;s<pixelSpp;s++){
                rng.beginSample(s,mix32(uint32_t(index)^uint32_t(o.seed)));float jx=rng.uniform(),jy=rng.uniform();
                float px=(2*(x+jx)/o.width-1)*tanHalf,py=(1-2*(y+jy)/o.height)*tanHalf/aspect;
                V direction=unit(forward+right*px+up*py),origin=camera;
                if(o.aperture>0){float r=std::sqrt(rng.uniform())*o.aperture,phi=2*PI*rng.uniform();V offset=right*(r*std::cos(phi))+up*(r*std::sin(phi));V fp=camera+direction*(focus/dot(direction,forward));origin+=offset;direction=unit(fp-origin);}
                Spec value=tracePrimary(Ray(origin,direction),rng,o.depth,cone);reflectionSum+=sampleReflection;volumeSum+=sampleVolume;
                bool finite=true;for(float v:value.v)finite=finite&&std::isfinite(v);
                if(!finite){nonfinite++;continue;}
                sum+=value;double lum=xyz(value).y;lum2+=lum*lum;
            }
            film[index]=sum*(1.f/pixelSpp);reflectionFilm[index]=reflectionSum*(1.f/pixelSpp);volumeFilm[index]=volumeSum*(1.f/pixelSpp);
            float px=(2*(x+.5f)/o.width-1)*tanHalf,py=(1-2*(y+.5f)/o.height)*tanHalf/aspect;
            Guide g=guideRay(Ray(camera,unit(forward+right*px+up*py)),cone);
            double avg=xyz(film[index]).y;g.variance=std::max(0.,(lum2/pixelSpp-avg*avg)/std::max(1,pixelSpp-1));guides[index]=g;
            Ray centerRay(camera,unit(forward+right*px+up*py));
            reflectionGuides[index]=primaryGuideRay(centerRay,cone,true);primaryGuides[index]=primaryGuideRay(centerRay,cone,false);
            reflectionGuides[index].variance=g.variance;primaryGuides[index].variance=g.variance;
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
    auto writeAOV=[&](const std::string &suffix,const std::vector<Spec>&buffer){std::ofstream out(o.out+suffix+".pfm",std::ios::binary);out<<"PF\n"<<o.width<<" "<<o.height<<"\n-1.0\n";
     for(int y=o.height-1;y>=0;y--)for(int x=0;x<o.width;x++){V rgb=toRGB(buffer[size_t(y)*o.width+x]);out.write((char*)&rgb,sizeof(V));}};
    writeAOV("_reflection",reflectionFilm);writeAOV("_volume",volumeFilm);
    std::ofstream ppm(o.out+".ppm",std::ios::binary);ppm<<"P6\n"<<o.width<<" "<<o.height<<"\n255\n";
    Spec means;
    for(auto s:film){means+=s*(1.f/float(pixels));V v=tonemap(toRGB(s),o.exposure);for(int k=0;k<3;k++){unsigned char b=static_cast<unsigned char>(clamp(v[k])*255+.5f);ppm.write(reinterpret_cast<char*>(&b),1);}}
    std::ofstream gf(o.out+".guides",std::ios::binary);uint32_t dim[2]={uint32_t(o.width),uint32_t(o.height)};gf.write(reinterpret_cast<char*>(dim),8);gf.write(reinterpret_cast<char*>(guides.data()),guides.size()*sizeof(Guide));
    auto writeGuide=[&](const std::string&suffix,const std::vector<Guide>&g){std::ofstream f(o.out+suffix+".guides",std::ios::binary);f.write((char*)dim,8);f.write((char*)g.data(),g.size()*sizeof(Guide));};
    writeGuide("_reflection",reflectionGuides);writeGuide("_primary",primaryGuides);
    {std::ofstream f(o.out+".samples",std::ios::binary);f.write((char*)dim,8);f.write((char*)sampleCounts.data(),sampleCounts.size()*sizeof(uint32_t));}
    if(o.bands){std::ofstream sp(o.out+".spectral",std::ios::binary);uint32_t header[]={0x36315053,uint32_t(o.width),uint32_t(o.height),NBANDS};sp.write(reinterpret_cast<char*>(header),16);sp.write(reinterpret_cast<char*>(film.data()),film.size()*sizeof(Spec));}
    float sec=std::chrono::duration<float>(std::chrono::steady_clock::now()-started).count();
    std::ofstream meta(o.out+".json");meta<<std::setprecision(9)<<"{\n  \"renderer\": \"CYBR GEO native cavern V3 - rough-quartz NEE spectral CPU\",\n  \"geometry_accelerator\": \"CYBR GEO native SAH BVH4 / AVX2 triangle packets\",\n  \"view\": \""<<o.view<<"\",\n  \"width\": "<<o.width<<", \"height\": "<<o.height<<", \"spp\": "<<o.spp<<",\n  \"max_depth\": "<<o.depth<<", \"seed\": "<<o.seed<<", \"threads\": "<<o.threads<<",\n  \"triangles\": "<<tris.size()<<", \"bvh_nodes\": "<<nodes.size()<<",\n  \"spectral_bands\": 16, \"wavelength_range_nm\": [380,780],\n  \"spectral_method\": \"Jointly transported fixed midpoint wavelength quadrature, 25 nm bins\",\n  \"water_ior\": "<<WATER_IOR<<", \"dispersion\": "<<((splitting&&!clay)?"true":"false")<<",\n  \"steam\": "<<(useSteam?"true":"false")<<", \"steam_model\": \"Bounded homogeneous haze; analytic transmittance; forced first collision; full continuation\",\n  \"water_absorption_scale\": "<<waterStrength<<",\n  \"finite_difference_water_connection_step_radians\": 0.002,\n  \"nonfinite_path_samples\": "<<nonfinite.load()<<",\n  \"exposure\": "<<o.exposure<<",\n  \"film_white_rgb\": ["<<whiteRGB.x<<","<<whiteRGB.y<<","<<whiteRGB.z<<"],\n  \"seconds\": "<<sec<<",\n  \"band_means\": [";
    for(int k=0;k<NBANDS;k++)meta<<(k?",":"")<<means.v[k];meta<<"]\n}\n";
    std::cerr<<"WROTE "<<o.out<<"; "<<sec<<" seconds; invalid paths "<<nonfinite<<"\n";
    return nonfinite?2:0;
}catch(const std::exception&e){std::cerr<<"ERROR: "<<e.what()<<"\n";return 1;}}
