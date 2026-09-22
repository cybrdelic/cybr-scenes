// GPL-2.0-only. Limited sampler/phase checks, not complete transport validation.
#define main cybr_desert_program_main
#include "spectral_desert.cpp"
#undef main
int main(){
    constexpr int N=400000;
    RNG rng(9142026);double sum=0;int beyond=0;
    for(int i=0;i<N;i++){
        double t=-std::log(std::max(1.e-8f,1-rng.uniform()))/WATER_SIGMA_S;
        sum+=t;if(t>1.4)++beyond;
    }
    double mean=sum/N,expectedMean=1./WATER_SIGMA_S;
    double fraction=double(beyond)/N,expectedFraction=std::exp(-1.4*WATER_SIGMA_S);
    constexpr int M=65536;double integral=0;
    for(int i=0;i<M;i++)integral+=phaseHG(-1.f+(i+.5f)*(2.f/M),WATER_PHASE_G);
    integral*=4*PI/M;
    bool pass=std::fabs(mean/expectedMean-1)<.01&&std::fabs(fraction-expectedFraction)<.004&&std::fabs(integral-1)<.0002;
    std::cout<<std::setprecision(12)<<"{\"scope\":\"Free-flight distribution and HG normalization only\",\"sample_count\":"<<N<<",\"mean_free_path_m\":"<<mean<<",\"expected_mean_free_path_m\":"<<expectedMean<<",\"survival_at_1_4_m\":"<<fraction<<",\"expected_survival\":"<<expectedFraction<<",\"HG_sphere_integral\":"<<integral<<",\"passed\":"<<(pass?"true":"false")<<"}\n";
    return pass?0:1;
}
