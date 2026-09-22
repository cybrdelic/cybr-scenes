#include "spectral_geometry.h"
#include <stdexcept>
#include <iomanip>
#include "photographic_grain.h"
int main(int argc,char**argv){try{
 if(argc!=2)throw std::runtime_error("Usage: test_photographic_grain texture.pgm");
 GrainMap g;g.load(argv[1]);float periodic=0;
 for(int i=0;i<80;i++){
  float u=.01273f*i-.39f,v=.08371f*i+.23f;
  periodic=std::max(periodic,std::fabs(g.sample(u,v,.004f,1.3f)-g.sample(u+1.3f,v-1.3f,.004f,1.3f)));
 }
 float coarsest=std::fabs(g.sample(.12f,.42f,1000.f,1.3f)-1.f);
 bool good=periodic<.001f&&coarsest<.00001f&&g.levels.size()==10;
 std::cout<<std::setprecision(10)<<"{\"periodic_max_error\":"<<periodic<<",\"coarsest_mean_error\":"<<coarsest<<",\"mip_levels\":"<<g.levels.size()<<",\"passed\":"<<(good?"true":"false")<<"}\n";
 return good?0:1;
}catch(const std::exception&e){std::cerr<<e.what()<<"\n";return 1;}}
