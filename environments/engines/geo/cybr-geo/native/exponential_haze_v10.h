// GPL-2.0-only. Exact segment optical depth and inverse-CDF free flights
// for an authored exponential-height aerosol layer inside a finite scene box.
// This is a reduced atmosphere, not a measured atmosphere or weather solver.
#pragma once
const V ATM_LO(-9000,200,-.4f),ATM_HI(9000,14000,1800);
constexpr double ATM_SIGMA=0.000034,ATM_SCALE_HEIGHT=500.0;
bool atmosphereInterval(const Ray&r,float maximum,float&a,float&b){
    a=0;b=maximum;
    for(int k=0;k<3;k++){
        if(std::fabs(r.d[k])<1e-9f){if(r.o[k]<ATM_LO[k]||r.o[k]>ATM_HI[k])return false;continue;}
        float x=(ATM_LO[k]-r.o[k])/r.d[k],y=(ATM_HI[k]-r.o[k])/r.d[k];if(x>y)std::swap(x,y);
        a=std::max(a,x);b=std::min(b,y);if(a>=b)return false;
    }return true;
}
double atmosphereDepth(const Ray&r,double a,double b){
    if(b<=a)return 0;
    const double sigma=ATM_SIGMA*std::exp(-(double(r.o.z)+double(r.d.z)*a)/ATM_SCALE_HEIGHT);
    const double k=-double(r.d.z)/ATM_SCALE_HEIGHT,L=b-a;
    if(std::fabs(k)<1e-12)return sigma*L;
    return sigma*std::expm1(k*L)/k;
}
float atmosphereFromOpticalDepth(const Ray&r,float a,float b,double tau){
    if(tau>=atmosphereDepth(r,a,b))return INF;
    const double sigma=ATM_SIGMA*std::exp(-(double(r.o.z)+double(r.d.z)*a)/ATM_SCALE_HEIGHT);
    const double k=-double(r.d.z)/ATM_SCALE_HEIGHT;
    const double d=std::fabs(k)<1e-12?tau/sigma:std::log1p(k*tau/sigma)/k;
    return float(std::max(double(a),std::min(double(b),double(a)+d)));
}
float sampleAtmosphere(const Ray&r,float maxT,RNG&rng){
    float a,b;if(!atmosphereInterval(r,maxT,a,b))return INF;
    const double tau=-std::log(std::max(1e-8,1.-double(rng.uniform())));
    return atmosphereFromOpticalDepth(r,a,b,tau);
}
