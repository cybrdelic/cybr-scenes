// GPL-2.0-only. Executable numerical checks, not a visual-realism certificate.
#define main cybr_desert_renderer_entry_for_test
#include "spectral_desert.cpp"
#undef main
int main(){
    omp_set_num_threads(5);initSpectra();initRipples();
    const float originalMajorant=MAJORANT;
    RNG rng(20260914);double squared=0;float maxAngle=0,maxResidual=0,maxHeight=0,maxSlope=0;
    int valid=0,invalid=0,total=8000;bool bounded=true,finite=true;
    for(int k=0;k<total;k++){
        V p(pools[0].x+(rng.uniform()-.5f)*3.5f,pools[0].y+(rng.uniform()-.5f)*2.5f,pools[0].level-(.09f+rng.uniform()*.93f));
        V air=sampleSun(rng);auto c=waterConnection(p,air,0);
        if(c.valid){
            ++valid;V actual=refractRay(c.l,-c.n,WATER_IOR);float e=len(actual-air);squared+=e*e;maxAngle=std::max(maxAngle,e);
            V ideal=-refractRay(-air,c.n,1/WATER_IOR);
            float t=(c.q.z-p.z)/ideal.z;float residual=len(c.q-(p+ideal*t));maxResidual=std::max(maxResidual,residual);
            finite=finite&&std::isfinite(c.jacobian)&&c.jacobian>=0;
        }else ++invalid;
        double x=p.x,y=p.y,h=0,dx=0,dy=0;
        for(const auto&m:RIPPLE_MODES){double phase=m[0]*x+m[1]*y+m[3],a=m[2]*RIPPLE_SCALE;h+=a*std::sin(phase);dx+=a*m[0]*std::cos(phase);dy+=a*m[1]*std::cos(phase);}
        auto lut=rippleFields[0].at(x,y);maxHeight=std::max(maxHeight,float(std::fabs(h-lut.x)));
        maxSlope=std::max(maxSlope,float(std::hypot(dx-lut.y,dy-lut.z)));
        for(int mat: {0,1,2,3,4,5,8,9}){
            V at((rng.uniform()-.5f)*15,(rng.uniform()-.5f)*15,rng.uniform()),normal=unit(V(rng.uniform()-.5f,rng.uniform()-.5f,1));
            auto m=shade(at,normal,mat,.001f);
            for(int i=0;i<3;i++)bounded=bounded&&m.color[i]>=.002f&&m.color[i]<=.88001f;
            bounded=bounded&&m.rough>=0&&m.rough<=1&&std::fabs(len(normal)-1)<1e-5;
        }
    }
    // Analytic flat-interface solid-angle Jacobian, evaluated independently.
    for(auto &field:rippleFields)for(auto &v:field.samples)v=V(0);
    float flatMaxRelative=0;
    for(int k=0;k<30;k++){
        float elevation=(15.f+k*2.f)*PI/180;V air=unit(V(std::cos(elevation),0,std::sin(elevation)));
        V p(.5,1,-.5);auto c=waterConnection(p,air,0);
        float expected=air.z/(WATER_IOR*WATER_IOR*c.l.z);
        flatMaxRelative=std::max(flatMaxRelative,std::fabs(c.jacobian-expected)/expected);
        finite=finite&&c.valid;
    }
    const double rms=std::sqrt(squared/std::max(1,valid));
    bool passed=finite&&bounded&&valid>7900&&maxResidual<.000201f&&maxAngle<.002f&&rms<.00010&&maxHeight<.00008f&&maxSlope<.005f&&flatMaxRelative<.025f;
    std::cout<<std::setprecision(10)<<"{\n"
      <<"  \"test\": \"CYBR GEO v9 water-connection and material regression\",\n"
      <<"  \"tested_water_connections\": "<<total<<",\n"
      <<"  \"accepted_water_connections\": "<<valid<<",\n"
      <<"  \"rejected_water_connections\": "<<invalid<<",\n"
      <<"  \"maximum_connection_residual_m\": "<<maxResidual<<",\n"
      <<"  \"maximum_snell_direction_error\": "<<maxAngle<<",\n"
      <<"  \"rms_snell_direction_error\": "<<rms<<",\n"
      <<"  \"maximum_ripple_lut_height_error_m\": "<<maxHeight<<",\n"
      <<"  \"maximum_ripple_lut_slope_error\": "<<maxSlope<<",\n"
      <<"  \"flat_interface_jacobian_maximum_relative_error\": "<<flatMaxRelative<<",\n"
      <<"  \"material_samples_tested\": "<<total*8<<",\n"
      <<"  \"reflectance_and_roughness_bounded\": "<<(bounded?"true":"false")<<",\n"
      <<"  \"finite_results\": "<<(finite?"true":"false")<<",\n"
      <<"  \"photorealism_certified_by_test\": false,\n"
      <<"  \"passed\": "<<(passed?"true":"false")<<"\n}\n";
    return passed?0:1;
}
