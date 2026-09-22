// GPL-2.0-only. Numerical integration, inversion and free-flight tests.
#define main cybr_desert_program_main
#include "spectral_desert.cpp"
#undef main
int main(){
    RNG rng(41907);double maxRel=0,maxTau=0;
    int tested=0;constexpr int N=2400;
    for(int j=0;j<N;j++){
        Ray ray{V((rng.uniform()-.5f)*9000,205+rng.uniform()*9000,2+rng.uniform()*1300),unit(V((rng.uniform()-.5f)*.8f,.8f,(rng.uniform()-.5f)*.8f))};
        float a,b;if(!atmosphereInterval(ray,8000,a,b))continue;
        double exact=atmosphereDepth(ray,a,b),quad=0,ds=(b-a)/1024.;
        for(int i=0;i<1024;i++)quad+=ATM_SIGMA*std::exp(-(ray.o.z+ray.d.z*(a+(i+.5)*ds))/ATM_SCALE_HEIGHT)*ds;
        maxRel=std::max(maxRel,std::fabs(exact-quad)/std::max(exact,1e-12));
        double tau=exact*(.05+.90*rng.uniform());float t=atmosphereFromOpticalDepth(ray,a,b,tau);
        maxTau=std::max(maxTau,std::fabs(atmosphereDepth(ray,a,t)-tau)/std::max(exact,1e-12));++tested;
    }
    Ray horizontal{V(0,201,15),V(0,1,0)};constexpr int M=300000;int survived=0;
    for(int j=0;j<M;j++)if(sampleAtmosphere(horizontal,4000,rng)>=4000)++survived;
    double observed=double(survived)/M,expected=std::exp(-atmosphereDepth(horizontal,0,4000));
    bool passed=tested==N&&maxRel<1e-6&&maxTau<1e-5&&std::fabs(observed-expected)<.004;
    std::cout<<std::setprecision(12)<<"{\"scope\":\"Analytic optical depth vs 1024-point quadrature, inverse CDF, horizontal free-flight survival; not weather or photographic validation\",\"segments\":"<<tested<<",\"scale_height_m\":"<<ATM_SCALE_HEIGHT<<",\"ground_extinction_per_m\":"<<ATM_SIGMA<<",\"maximum_depth_relative_error\":"<<maxRel<<",\"maximum_inversion_normalized_error\":"<<maxTau<<",\"free_flight_samples\":"<<M<<",\"observed_4km_survival\":"<<observed<<",\"expected_survival\":"<<expected<<",\"passed\":"<<(passed?"true":"false")<<"}\n";
    return passed?0:1;
}
