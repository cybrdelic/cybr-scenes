#define main spectral_desert_entrypoint
#include "spectral_desert.cpp"
#undef main
int main(int argc,char**argv){
 try{
  if(argc!=3)throw std::runtime_error("usage: test_materials_v11 relief.bin gravel.pgm");
  omp_set_num_threads(2);initSpectra();initRipples();granularRelief.load(argv[1]);photographicGrain.load(argv[2]);
  RNG r(987656321);bool finite=true,bounded=true;float maxNormalError=0,maxSlope=0,periodicError=0;
  for(int k=0;k<15000;k++){
   V p(-7+15*r.uniform(),-5+17*r.uniform(),-.4f+2*r.uniform());
   int material=k%10;if(material==6||material==7)material=0;
   V n=unit(V(r.uniform()-.5f,r.uniform()-.5f,.6f));float footprint=std::pow(10.f,-4+3.5f*r.uniform());
   Surface s=shade(p,n,material,footprint);
   for(int c=0;c<3;c++){finite&=std::isfinite(n[c])&&std::isfinite(s.color[c]);bounded&=s.color[c]>=.0029f&&s.color[c]<=.91001f;}
   bounded&=s.rough>=0&&s.rough<=1&&s.ior>=1;
   maxNormalError=std::max(maxNormalError,std::fabs(len(n)-1));
   maxSlope=std::max(maxSlope,len(granularRelief.gradient(p.x,p.y,footprint)));
   // Shift by one exact texture-space u period transformed into world XY.
   const float norm=.917f*.917f+.399f*.399f;
   float x=p.x+.68f*.917f/norm,y=p.y+.68f*.399f/norm;
   periodicError=std::max(periodicError,std::fabs(granularRelief.sample(p.x,p.y,footprint)-granularRelief.sample(x,y,footprint)));
  }
  float maximumEnergy=0;
  for(float rough:{.3f,.6f,.94f})for(float cosine:{.2f,.6f,1.f}){
   Surface s;s.color=V(.75f);s.rough=rough;s.ior=1.48f;Spec base(.75f);V n(0,0,1),v(std::sqrt(1-cosine*cosine),0,cosine);
   double sum=0;const int N=180000;
   for(int i=0;i<N;i++){
    float z=(i+.5f)/N,phi=2*PI*std::fmod(i*.61803398875f,.999999999f),rad=std::sqrt(1-z*z);
    V l(rad*std::cos(phi),rad*std::sin(phi),z);
    sum+=evalBSDF(s,base,n,v,l).v[5]*z*2*PI;
   }
   maximumEnergy=std::max(maximumEnergy,float(sum/N));
  }
  bool passed=finite&&bounded&&maxNormalError<1e-5f&&periodicError<2e-5f&&maximumEnergy<=1.02f;
  std::cout<<std::setprecision(10)<<"{\n  \"scope\": \"Finite materials, normalized normals, periodic relief and bounded rough diffuse energy at sampled angles; not perceptual validation\",\n  \"material_samples\": 15000,\n  \"finite\": "<<(finite?"true":"false")<<",\n  \"bounded\": "<<(bounded?"true":"false")<<",\n  \"maximum_normal_length_error\": "<<maxNormalError<<",\n  \"maximum_relief_gradient\": "<<maxSlope<<",\n  \"maximum_periodic_height_error_m\": "<<periodicError<<",\n  \"maximum_directional_hemispherical_reflectance\": "<<maximumEnergy<<",\n  \"passed\": "<<(passed?"true":"false")<<"\n}\n";
  return passed?0:1;
 }catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 2;}
}
