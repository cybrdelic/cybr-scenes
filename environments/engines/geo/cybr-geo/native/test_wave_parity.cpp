#define main original_renderer_main
#include "spectral_scenes.cpp"
#undef main
int main(int argc,char **argv){
 if(argc!=2)return 1;omp_set_num_threads(2);std::ofstream out(argv[1],std::ios::binary);
 for(int style=1;style<=2;style++){
  sceneStyle=style;configureScene();initRipples();RNG rng(31000+style);
  for(int i=0;i<2048;i++){
   const auto &p=pools[0];float x=p.x+(rng.uniform()*2-1)*p.rx,y=p.y+(rng.uniform()*2-1)*p.ry;
   V n=waterNormal(x,y,0);float v[]={float(style),x,y,waterHeight(x,y,0),n.x,n.y,n.z};
   out.write(reinterpret_cast<char*>(v),sizeof(v));
  }
 }
 return out?0:2;
}
