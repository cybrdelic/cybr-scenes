#define main cybr_desert_renderer_test_entry
#include "spectral_desert.cpp"
#undef main
int main(){
    omp_set_num_threads(3);initClouds();
    const auto maximumIt=std::max_element(cloudGrid.begin(),cloudGrid.end());
    const float maximum=*maximumIt;
    size_t at=maximumIt-cloudGrid.begin();
    int ix=at%CLOUD_NX,iy=(at/CLOUD_NX)%CLOUD_NY;
    float x=CLOUD_LO.x+(CLOUD_HI.x-CLOUD_LO.x)*ix/(CLOUD_NX-1);
    float y=CLOUD_LO.y+(CLOUD_HI.y-CLOUD_LO.y)*iy/(CLOUD_NY-1);
    V centre(x,y,(CLOUD_LO.z+CLOUD_HI.z)*.5f);
    std::array<V,6> directions={V(0,0,1),unit(V(.8f,.3f,1)),unit(V(-.7f,-.5f,-1)),unit(V(1,.8f,.12f)),unit(V(-.8f,1,.25f)),V(0,0,-1)};
    bool bounded=true;uint64_t checked=0;
    for(int ty=0;ty<CLOUD_MY;ty++)for(int tx=0;tx<CLOUD_MX;tx++){
        float majorant=cloudMajorants[ty*CLOUD_MX+tx];
        for(int k=0;k<CLOUD_NZ;k++)
          for(int j=ty*CLOUD_TILE;j<=std::min((ty+1)*CLOUD_TILE,CLOUD_NY-1);j++)
            for(int i=tx*CLOUD_TILE;i<=std::min((tx+1)*CLOUD_TILE,CLOUD_NX-1);i++){
              float rho=cloudGrid[(size_t(k)*CLOUD_NY+j)*CLOUD_NX+i];
              bounded=bounded&&rho<=majorant;checked++;
            }
    }
    bool ok=bounded&&maximum<=CLOUD_MAJORANT;
    std::cout<<std::setprecision(10)<<"{\n  \"scope\": \"Trilinear-column majorants and DDA null-collision tracking versus independent quadrature; not cloud morphology or weather validation\",\n  \"maximum_extinction_per_m\": "<<maximum<<",\n  \"conservative_column_bounds\": "<<(bounded?"true":"false")<<",\n  \"grid_corner_bound_checks\": "<<checked<<",\n  \"column_grid\": ["<<CLOUD_MX<<","<<CLOUD_MY<<"],\n  \"cases\": [\n";
    for(int index=0;index<6;index++){
        Ray r(centre-directions[index]*18000.f,directions[index]);float a,b;
        if(!cloudInterval(r,INF,a,b))return 2;
        constexpr int steps=32000,iterations=80000;
        double tau=0;
        for(int k=0;k<steps;k++)tau+=cloudDensity(r.o+r.d*float(a+(k+.5)*(b-a)/steps))*double(b-a)/steps;
        double truth=std::exp(-tau),sum=0,sum2=0;int misses=0;
        RNG rng(202609141+index*173);
        for(int i=0;i<iterations;i++){
            if(sampleCloud(r,INF,rng)==INF)misses++;
            float tr=cloudTransmittance(r,INF,rng);sum+=tr;sum2+=tr*tr;
        }
        double mean=sum/iterations,stderr=std::sqrt(std::max(0.,sum2/iterations-mean*mean)/iterations);
        double survival=double(misses)/iterations,binomialSE=std::sqrt(truth*(1-truth)/iterations);
        bool pass=std::fabs(mean-truth)<5*stderr+.0003&&std::fabs(survival-truth)<5*binomialSE+.0003;
        ok=ok&&pass;
        std::cout<<"    {\"index\": "<<index<<", \"reference_optical_depth\": "<<tau<<", \"reference_transmittance\": "<<truth<<", \"ratio_tracking_mean\": "<<mean<<", \"ratio_tracking_standard_error\": "<<stderr<<", \"delta_tracking_survival\": "<<survival<<", \"trials\": "<<iterations<<", \"passed\": "<<(pass?"true":"false")<<"}"<<(index<5?",":"")<<"\n";
    }
    std::cout<<"  ],\n  \"passed\": "<<(ok?"true":"false")<<"\n}\n";
    return ok?0:1;
}
