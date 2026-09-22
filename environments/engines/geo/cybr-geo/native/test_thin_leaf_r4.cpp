// SPDX-License-Identifier: GPL-2.0-only
#define main cybr_native_main
#include "spectral_scenes.cpp"
#undef main
int main(){
 try {
    Surface m;m.ior=1.46f;Spec white(1.f);V n(0,0,1);RNG rng(9213467);
    bool passed=true;double maxEnergy=0,maxReciprocity=0;int cases=0;long long total=0;
    std::cout<<std::setprecision(10)<<"{\n  \"scope\": \"Monte Carlo white-furnace and reciprocity checks of authored thin-leaf BSDF, not measured leaf optics\",\n  \"cases\": [";
    for(float rough:{.25f,.42f,.56f,.80f})for(float cosine:{1.f,.60f,.15f,.03f}){
        m.rough=rough;V view(std::sqrt(1-cosine*cosine),0,cosine);double sum=0,sum2=0;int nulls=0;constexpr int N=100000;
        for(int i=0;i<N;i++){
            V next=sampleLeafBSDF(m,n,view,rng);double weight=0;
            if(dot(next,next)<.5f)nulls++;
            else{
                float pdf=pdfLeafBSDF(m,n,view,next);if(!(pdf>0)||!std::isfinite(pdf))throw std::runtime_error("invalid leaf PDF");
                Spec f=evalLeafBSDF(m,white,n,view,next);
                weight=f.v[0]*std::fabs(dot(n,next))/pdf;
                Spec reciprocal=evalLeafBSDF(m,white,dot(n,next)>0?n:-n,next,view);
                maxReciprocity=std::max(maxReciprocity,double(std::fabs(f.v[0]-reciprocal.v[0])/(1.f+std::fabs(f.v[0]))));
                if(!std::isfinite(weight)||weight<0)throw std::runtime_error("invalid BSDF response");
            }
            sum+=weight;sum2+=weight*weight;
        }
        double mean=sum/N,se=std::sqrt(std::max(0.0,sum2/N-mean*mean)/N);
        maxEnergy=std::max(maxEnergy,mean);passed=passed&&(mean+5*se<=1.012);
        std::cout<<(cases++?",\n":"\n")<<"    {\"roughness\": "<<rough<<", \"view_cosine\": "<<cosine<<", \"samples\": "<<N<<", \"mean_white_furnace_response\": "<<mean<<", \"standard_error\": "<<se<<", \"null_samples\": "<<nulls<<"}";
        total+=N;
    }
    passed=passed&&maxReciprocity<2.e-5;
    std::cout<<"\n  ],\n  \"total_samples\": "<<total<<",\n  \"maximum_mean_white_furnace_response\": "<<maxEnergy<<",\n  \"maximum_relative_reciprocity_error\": "<<maxReciprocity<<",\n  \"passed\": "<<(passed?"true":"false")<<"\n}\n";
    return passed?0:1;
 } catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 2;}
}
