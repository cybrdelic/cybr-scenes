#define main cybr_desert_renderer_test_entry
#include "spectral_desert.cpp"
#undef main
int main(){
    omp_set_num_threads(3);initSpectra();initRipples();
    Spec reference=blackbody(6500.f);V white=toRGB(reference);
    RNG rng(202609146);int cases=0,clipped=0;float maxError=0,maxBefore=0;bool bounded=true;
    for(int material:{0,1,2,3,4,5,8,9})for(int i=0;i<1600;i++){
        V p(-7+15*rng.uniform(),-5+20*rng.uniform(),0.04f+2*rng.uniform());
        if(material==5)p=V(-3000+6000*rng.uniform(),1000+5000*rng.uniform(),300+700*rng.uniform());
        V n=unit(V(.5f-rng.uniform(),.5f-rng.uniform(),1));
        Surface m=shade(p,n,material,.001f);
        V a(dot(RGB_TO_ANCHORS[0],m.color),dot(RGB_TO_ANCHORS[1],m.color),dot(RGB_TO_ANCHORS[2],m.color));
        if(std::min({a.x,a.y,a.z})<0||maxc(a)>.985f){clipped++;continue;}
        Spec spectrum=rgbAnchors(m.color);V achieved=toRGB(spectrum*reference);
        V before=toRGB(rawRGBAnchors(m.color)*reference);
        achieved=V(achieved.x/white.x,achieved.y/white.y,achieved.z/white.z);
        before=V(before.x/white.x,before.y/white.y,before.z/white.z);
        for(int k=0;k<3;k++){maxError=std::max(maxError,std::fabs(achieved[k]-m.color[k]));maxBefore=std::max(maxBefore,std::fabs(before[k]-m.color[k]));}
        for(float v:spectrum.v)bounded=bounded&&std::isfinite(v)&&v>=0&&v<=.985001f;
        cases++;
    }
    bool ok=bounded&&maxError<2e-6f&&cases>12000;
    std::cout<<std::setprecision(10)<<"{\n  \"scope\": \"Authored linear-RGB material round trip under 6500 K blackbody white; not measured material spectra\",\n  \"tested_material_samples\": "<<cases<<",\n  \"out_of_basis_gamut_samples\": "<<clipped<<",\n  \"legacy_maximum_channel_error\": "<<maxBefore<<",\n  \"calibrated_maximum_channel_error\": "<<maxError<<",\n  \"spectra_bounded\": "<<(bounded?"true":"false")<<",\n  \"passed\": "<<(ok?"true":"false")<<"\n}\n";
    return ok?0:1;
}
