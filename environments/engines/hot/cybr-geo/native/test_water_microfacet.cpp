// Numerical consistency checks; not a certification of scene photorealism.
#define main original_scene_main
#include "spectral_desert.cpp"
#undef main
int main(){
    RNG rng(728091);double worstRecip=0,worstWeight=0,worstSnell=0;
    bool finite=true;int reflection=0,transmission=0,masked=0;
    V n(0,0,1);
    for(float elevation:{.08f,.3f,.8f,1.f})for(bool enter:{true,false}){
        V view=unit(V(std::sqrt(1-elevation*elevation),0,elevation));
        float ei=enter?1:WATER_IOR,et=enter?WATER_IOR:1;
        for(int k=0;k<40000;k++){
            V h=sampleWaterMicroNormal(n,view,rng);
            float fr=fresnelD(dot(view,h),ei,et);
            finite=finite&&std::isfinite(fr)&&std::fabs(len(h)-1)<2e-6&&dot(view,h)>0;
            if(rng.uniform()<fr){
                V l=unit(reflect(-view,h));if(dot(n,l)<=0){masked++;continue;}
                float f=waterReflection(n,view,l,ei,et),pdf=waterReflectionPDF(n,view,l,ei,et);
                float reverse=waterReflection(n,l,view,ei,et);
                worstRecip=std::max(worstRecip,double(std::fabs(f-reverse)/(1+f)));
                worstWeight=std::max(worstWeight,double(std::fabs(f*dot(n,l)/pdf-G1(dot(n,l),WATER_MICRO_ALPHA))));
                reflection++;
            }else{
                V l=refractRay(-view,h,ei/et);if(dot(n,l)>=0){masked++;continue;}
                double lhs=ei*std::sqrt(std::max(0.f,1-sqr(dot(view,h))));
                double rhs=et*std::sqrt(std::max(0.f,1-sqr(dot(l,h))));
                worstSnell=std::max(worstSnell,std::fabs(lhs-rhs));transmission++;
                finite=finite&&std::fabs(len(l)-1)<2e-6;
            }
        }
    }
    bool pass=finite&&worstRecip<.001&&worstWeight<.0001&&worstSnell<.001;
    std::cout<<std::setprecision(10)<<"{\"scope\":\"GGX VNDF reflection reciprocity, sampling weight and microfacet Snell consistency; not complete manifold-transport accuracy\",\"samples\":320000,\"reflection_samples\":"<<reflection<<",\"transmission_samples\":"<<transmission<<",\"masked_samples\":"<<masked<<",\"roughness_alpha\":"<<WATER_MICRO_ALPHA<<",\"max_reflection_reciprocity_normalized_error\":"<<worstRecip<<",\"max_reflection_throughput_identity_error\":"<<worstWeight<<",\"max_snell_error\":"<<worstSnell<<",\"finite\":"<<(finite?"true":"false")<<",\"passed\":"<<(pass?"true":"false")<<"}\n";
    return pass?0:1;
}
