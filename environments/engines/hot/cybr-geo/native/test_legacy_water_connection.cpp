// GPL-2.0-only. Matched-input comparison against the actual supplied v4 solver.
#define main cybr_renderer_entry_for_legacy_test
#include "spectral_desert.cpp"
#undef main
Connection legacyConnection(V p,V air,int pool,bool computeJac=true){
    Connection c;const auto& a=pools[pool];
    V w=-refractRay(-air,V(0,0,1),1/WATER_IOR);
    if(w.z<=0)return c;
    V q=p+w*((a.level-p.z)/w.z);
    for(int i=0;i<7;i++){
        V n=waterNormal(q.x,q.y,pool);w=-refractRay(-air,n,1/WATER_IOR);
        if(w.z<.1f)return c;
        q=p+w*((waterHeight(q.x,q.y,pool)-p.z)/w.z);
    }
    if(std::fabs(q.x-a.x)>a.rx*1.28f||std::fabs(q.y-a.y)>a.ry*1.28f)return c;
    c.q=q;c.l=unit(q-p);c.n=waterNormal(q.x,q.y,pool);c.valid=dot(c.l,c.n)>0&&q.z>p.z;
    if(computeJac&&c.valid){
        Frame frame(air);constexpr float e=.002f;
        auto u=legacyConnection(p,unit(air+frame.t*e),pool,false);
        auto v=legacyConnection(p,unit(air+frame.b*e),pool,false);
        if(!u.valid||!v.valid){c.valid=false;return c;}
        c.jacobian=std::fabs(dot(c.l,cross((u.l-c.l)/e,(v.l-c.l)/e)));
        if(!std::isfinite(c.jacobian)||c.jacobian>30)c.valid=false;
    }
    return c;
}


struct Metrics{int accepted=0,rejected=0,aboveTolerance=0;double squared=0;float maximum=0;};
void collect(Metrics &m,Connection c,V p,V air,int pool){
 if(!c.valid){m.rejected++;return;}
 m.accepted++;
 V n=waterNormal(c.q.x,c.q.y,pool);
 V dir=-refractRay(-air,n,1/WATER_IOR);
 float t=(waterHeight(c.q.x,c.q.y,pool)-p.z)/dir.z;
 float residual=len(V(c.q.x-p.x-dir.x*t,c.q.y-p.y-dir.y*t,0));
 m.squared+=double(residual)*residual;m.maximum=std::max(m.maximum,residual);
 if(residual>.0002f)m.aboveTolerance++;
}
void emit(const Metrics&m){
 std::cout<<"{\"accepted\":"<<m.accepted<<",\"rejected\":"<<m.rejected
 <<",\"accepted_above_0_2_mm_residual\":"<<m.aboveTolerance
 <<",\"max_residual_m\":"<<m.maximum<<",\"rms_residual_m\":"<<std::sqrt(m.squared/std::max(1,m.accepted))<<"}";
}
int main(){
 omp_set_num_threads(2);initSpectra();initRipples();
 bool pass=true;std::cout<<std::setprecision(10)<<"{\"scope\":\"Same-input comparison of the supplied seven-step solver with residual-checked Newton; no image-quality certificate\",\"samples_per_case\":8000,\"cases\":[";
 for(int scenario=0;scenario<3;scenario++){
  if(scenario==1){for(auto &field:rippleFields)for(auto&v:field.samples)v*=1/float(RIPPLE_SCALE);SUN=unit(V(-.85f,.10f,.43f));}
  else if(scenario==2){SUN=unit(V(-.72f,.57f,.28f));}
  RNG rng(20260914);Metrics legacy,checked;
  for(int j=0;j<8000;j++){
   V p(pools[0].x+(rng.uniform()-.5f)*3.5f,pools[0].y+(rng.uniform()-.5f)*2.5f,pools[0].level-.09f-rng.uniform()*.93f);
   V air=sampleSun(rng);collect(legacy,legacyConnection(p,air,0,false),p,air,0);collect(checked,waterConnection(p,air,0,false),p,air,0);
  }
  if(scenario)std::cout<<",";
  std::cout<<"{\"case\":\""<<(scenario==0?"current_v8_ripples_and_sun":(scenario==1?"unscaled_ripples_supplied_v4_sun":"unscaled_ripples_lower_sun_stress"))<<"\",\"legacy\":";emit(legacy);std::cout<<",\"checked_newton\":";emit(checked);std::cout<<"}";
  pass=pass&&checked.aboveTolerance==0&&checked.accepted>0;
 }
 std::cout<<"],\"passed\":"<<(pass?"true":"false")<<"}\n";return pass?0:1;
}
