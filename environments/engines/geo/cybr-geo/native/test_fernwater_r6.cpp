// SPDX-License-Identifier: GPL-2.0-only
#define main cybr_native_main
#include "spectral_scenes.cpp"
#undef main
struct Stats6 {double s=0,s2=0;int n=0;void add(double a){s+=a;s2+=a*a;n++;}double mean()const{return s/n;}double variance()const{return std::max(0.,s2/n-sqr(mean()));}double se()const{return std::sqrt(variance()/n);}};
float testEnv6(V l){return l.z>0&&std::sin(l.x*9)+std::cos(l.y*7)>.30f?(.4f+.9f*l.z):0.f;}
int main(){try{
    sceneStyle=2;configureScene();initSpectra();
    bool passed=true;int materialSamples=0;float maxNormalError=0,translationError=0;
    surfaceFrames6.push_back({});surfaceFrames6.push_back({V(0),V(1,0,0),V(0,1,0),V(0,0,1),.14f,.065f,3,52});
    RNG r(601271);
    for(int j=0;j<12000;j++){
        int id=j%17;V p(r.uniform()*8-4,r.uniform()*15,r.uniform()*6),n=unit(V(r.uniform()-.5f,r.uniform()-.5f,r.uniform()+.1f));
        auto s=shadeAt6(p,n,id,.0001f+.01f*r.uniform(),id==9?1:0);
        if(!std::isfinite(maxc(s.color))||maxc(s.color)>.88001f||std::min({s.color.x,s.color.y,s.color.z})<.00199f||s.rough<.10999f||s.rough>.98001f)passed=false;
        maxNormalError=std::max(maxNormalError,std::fabs(len(n)-1));materialSamples++;
    }
    for(int i=0;i<2000;i++){
        surfaceFrames6[1].origin=V(0);V p(r.uniform()*.14f,(r.uniform()-.5f)*.045f,.002f),n(0,0,1);
        auto first=shadeAt6(p,n,9,.0003f,1);V shift(2.7f,-1.5f,4.3f);surfaceFrames6[1].origin=shift;n=V(0,0,1);
        auto second=shadeAt6(p+shift,n,9,.0003f,1);translationError=std::max(translationError,len(first.color-second.color));
    }
    passed=passed&&maxNormalError<2e-5f&&translationError<2e-4f;
    std::cout<<std::setprecision(10)<<"{\n \"scope\": \"Executed material-frame, bounded-output and independent environment-MIS quadrature checks; not photorealism\",\n \"material_samples\": "<<materialSamples<<",\n \"max_normal_error\": "<<maxNormalError<<",\n \"leaf_translation_color_error\": "<<translationError<<",\n \"mis_cases\": [";
    for(int leaf=0;leaf<2;leaf++){
        V n=unit(V(.22f,.18f,.9f)),view=unit(V(.42f,-.05f,.91f));Surface m;m.ior=1.46;m.rough=.42f;Spec base(.38f);
        auto eval=[&](V l){return (leaf?evalLeafBSDF(m,base,n,view,l):evalBSDF(m,base,n,view,l)).v[0]*std::fabs(dot(n,l))*testEnv6(l);};
        auto pdf=[&](V l){return leaf?pdfLeafBSDF(m,n,view,l):pdfBSDF(m,n,view,l);};
        double reference=0;constexpr int NZ=512,NP=1024;
        for(int zi=0;zi<NZ;zi++)for(int pi=0;pi<NP;pi++){
            float z=(zi+.5f)/NZ,phi=2*PI*(pi+.5f)/NP,t=std::sqrt(1-z*z);reference+=eval(V(t*std::cos(phi),t*std::sin(phi),z));
        }reference*=2*PI/(NZ*NP);
        Stats6 bsdf,mis;
        for(int j=0;j<180000;j++){
            V l=leaf?sampleLeafBSDF(m,n,view,r):sampleBSDF(m,n,view,r);double c=0,mixed=0;
            if(dot(l,l)>.5f&&pdf(l)>1e-10f){c=eval(l)/pdf(l);mixed=c*(l.z>0?powerWeight(pdf(l),1/(2*PI)):1.f);}
            float z=r.uniform(),phi=2*PI*r.uniform(),t=std::sqrt(1-z*z);V sky(t*std::cos(phi),t*std::sin(phi),z);
            mixed+=eval(sky)*2*PI*powerWeight(1/(2*PI),pdf(sky));bsdf.add(c);mis.add(mixed);
        }
        bool ok=std::fabs(bsdf.mean()-reference)<6*bsdf.se()+.0003&&std::fabs(mis.mean()-reference)<6*mis.se()+.0003;passed=passed&&ok;
        std::cout<<(leaf?",":"")<<"\n  {\"leaf\": "<<(leaf?"true":"false")<<", \"reference_quadrature\": "<<reference<<", \"bsdf_mean\": "<<bsdf.mean()<<", \"mis_mean\": "<<mis.mean()<<", \"bsdf_standard_error\": "<<bsdf.se()<<", \"mis_standard_error\": "<<mis.se()<<", \"passed\": "<<(ok?"true":"false")<<"}";
    }
    std::cout<<"\n ],\n \"passed\": "<<(passed?"true":"false")<<"\n}\n";return passed?0:1;
}catch(const std::exception &e){std::cerr<<e.what()<<"\n";return 2;}}
