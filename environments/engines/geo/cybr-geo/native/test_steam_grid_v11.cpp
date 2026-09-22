#define main spectral_desert_entrypoint
#include "spectral_desert.cpp"
#undef main
int main(){try{
 omp_set_num_threads(2);initSteam();RNG random(1935813);
 double mae=0,squared=0;float maxError=0,maxValue=0;bool finite=true,bounded=true;
 const int count=50000;
 for(int i=0;i<count;i++){
  V p(FOG_LO.x+(FOG_HI.x-FOG_LO.x)*random.uniform(),FOG_LO.y+(FOG_HI.y-FOG_LO.y)*random.uniform(),FOG_LO.z+(FOG_HI.z-FOG_LO.z)*random.uniform());
  float exact=steamAnalytic(p),approx=steamDensity(p),error=std::fabs(exact-approx);
  finite&=std::isfinite(approx);bounded&=approx>=0&&approx<=steamGridMajorant;
  maxError=std::max(maxError,error);maxValue=std::max(maxValue,approx);mae+=error;squared+=double(error)*error;
 }
 float maximumTransmissionError=0,maximumStandardError=0;
 for(float z:{.18f,.44f,1.0f}){
  Ray r(V(-6,1,z),V(1,0,0));constexpr float distance=12;double tau=0;
  constexpr int steps=16384;
  for(int i=0;i<steps;i++)tau+=steamDensity(r.o+r.d*((i+.5f)*distance/steps))*distance/steps;
  double expected=std::exp(-tau),sum=0,sum2=0;const int N=70000;
  for(int i=0;i<N;i++){float tr=steamTransmittance(r,distance,random);sum+=tr;sum2+=tr*tr;}
  double mean=sum/N,se=std::sqrt(std::max(0.,sum2/N-mean*mean)/N);
  maximumTransmissionError=std::max(maximumTransmissionError,float(std::fabs(mean-expected)));
  maximumStandardError=std::max(maximumStandardError,float(se));
 }
 bool passed=finite&&bounded&&mae/count<.00025&&maximumTransmissionError<.0075;
 std::cout<<std::setprecision(10)<<"{\n  \"scope\": \"Conservative trilinear-grid density bound, representation error against authored field, and sampled transmittance; not CFD or measured steam\",\n  \"grid\": ["<<STEAM_NX<<","<<STEAM_NY<<","<<STEAM_NZ<<"],\n  \"tracking_majorant_per_m\": "<<steamGridMajorant<<",\n  \"random_samples\": "<<count<<",\n  \"sampled_maximum_density\": "<<maxValue<<",\n  \"maximum_absolute_density_error\": "<<maxError<<",\n  \"mean_absolute_density_error\": "<<mae/count<<",\n  \"rms_density_error\": "<<std::sqrt(squared/count)<<",\n  \"finite\": "<<(finite?"true":"false")<<",\n  \"sampled_densities_within_majorant\": "<<(bounded?"true":"false")<<",\n  \"maximum_transmittance_absolute_error\": "<<maximumTransmissionError<<",\n  \"maximum_transmittance_standard_error\": "<<maximumStandardError<<",\n  \"passed\": "<<(passed?"true":"false")<<"\n}\n";
 return passed?0:1;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 2;}}
