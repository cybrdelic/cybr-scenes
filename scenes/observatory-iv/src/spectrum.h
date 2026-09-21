#pragma once
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
V whiteRGB, SUN=unit(V(.52f,.81f,.335f));
constexpr float SUN_RADIUS=.043f;
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
    solar=blackbody(4900.f)*(2.0f/SUN_SOLID);
    skyBlue=blackbody(7200.f);
    for(int k=0;k<NBANDS;k++)skyBlue.v[k]*=std::pow(550.f/(WL0+(k+.5f)*DL),.25f);
    skyBlue*=1.f/xyz(skyBlue).y;skyHorizon=blackbody(6300.f);
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

