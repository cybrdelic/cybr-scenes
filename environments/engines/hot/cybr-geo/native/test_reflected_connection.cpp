// GPL-2.0-only. Macro reflection constraints, not complete caustic accuracy.
#define main cybr_native_main_for_reflection_test
#include "spectral_desert.cpp"
#undef main
int main(){
    omp_set_num_threads(5);initSpectra();initRipples();RNG rng(841171);
    int tested=0,accepted=0,rejected=0;float maximumResidual=0,maximumDirectionError=0,maximumJacobian=0;
    for(int i=0;i<6000;i++){
        V q(.5f+(rng.uniform()-.5f)*4.2f,1+(rng.uniform()-.5f)*3.f,0);
        q.z=waterHeight(q.x,q.y,0);V n=waterNormal(q.x,q.y,0),air=sampleSun(rng),outgoing=reflect(-air,n);
        if(outgoing.z<.07f)continue;
        V p=q+outgoing*(.18f+1.12f*rng.uniform());tested++;
        auto c=reflectedWaterConnection(p,air,0);
        if(!c.valid){rejected++;continue;}accepted++;
        V actual=reflect(c.l,c.n);
        float directionError=len(actual-air);
        V reflected=reflect(-air,c.n);
        float t=(p.z-c.q.z)/reflected.z;
        float residual=len(c.q+reflected*t-p);
        maximumResidual=std::max(maximumResidual,residual);
        maximumDirectionError=std::max(maximumDirectionError,directionError);
        maximumJacobian=std::max(maximumJacobian,c.jacobian);
    }
    for(auto &field:rippleFields)for(auto &v:field.samples)v=V(0);
    float maximumFlatJacobianError=0;bool flatValid=true;
    for(int i=0;i<60;i++){
        float e=(10+i)*PI/180;V air=unit(V(std::cos(e),0,std::sin(e)));
        V q(.5f,1.f,pools[0].level),p=q+reflect(-air,V(0,0,1))*.65f;
        auto c=reflectedWaterConnection(p,air,0);flatValid=flatValid&&c.valid;
        maximumFlatJacobianError=std::max(maximumFlatJacobianError,std::fabs(c.jacobian-1.f));
    }
    bool passed=accepted>int(tested*.70)&&maximumResidual<.00021f&&maximumDirectionError<.002f&&flatValid&&maximumFlatJacobianError<.012f;
    std::cout<<std::setprecision(10)<<"{\n  \"scope\": \"One-root macro reflection law and finite-difference solid-angle Jacobian; not all-root or rough-caustic validation\",\n"
        <<"  \"tested_receivers\": "<<tested<<",\n  \"accepted_connections\": "<<accepted<<",\n  \"rejected_connections\": "<<rejected<<",\n"
        <<"  \"maximum_connection_residual_m\": "<<maximumResidual<<",\n  \"maximum_reflection_direction_error\": "<<maximumDirectionError<<",\n"
        <<"  \"maximum_accepted_jacobian\": "<<maximumJacobian<<",\n  \"flat_mirror_jacobian_max_abs_error\": "<<maximumFlatJacobianError<<",\n"
        <<"  \"all_flat_connections_valid\": "<<(flatValid?"true":"false")<<",\n  \"passed\": "<<(passed?"true":"false")<<"\n}\n";
    return passed?0:1;
}
