#define main obsidian_application_main
#include "../src/render.cpp"
#undef main
#include <cassert>
int main(){
 SceneMap tex;SceneMap::Level l;l.w=4;l.h=4;l.p.resize(16);double avg=0;
 for(int i=0;i<16;i++){double e=(i+1)*.1;avg+=e/16;l.p[i]=SceneMap::pack({Vec3(.3),Vec3(0,1,0),Vec3(e,2*e,0),.6,1});}
 tex.levels.push_back(l);tex.mip();auto a=tex.sample(.5,.5,2);
 assert(std::abs(a.e.x-avg)<1e-6);assert(std::abs(a.e.y-2*avg)<1e-6);assert(std::abs(a.rough-.6)<1e-6);
 assert(norm(a.n-Vec3(0,1,0))<1e-8);
 materials.clear();Mat m;m.emission=Vec3(1);materials.push_back(m);
 Primitive p;p.shape=Shape::Triangle;p.a={-1,0,-1};p.b={0,0,1};p.c={1,0,-1};p.material=0;
 primitives={p,p};primitives[1].a.x+=7;primitives[1].b.x+=7;primitives[1].c.x+=7;
 prepare_lights();Vec3 point(0,4,-4);double sum=0;for(int i=0;i<2;i++)sum+=area_pdf(point,i)*primitives[i].area();assert(std::abs(sum-1)<1e-8);
 RNG rng(512);for(int k=0;k<1000;k++){int i=choose_light(point,rng);assert(i==0||i==1);assert(area_pdf(point,i)>0);}
 Mat matte;matte.color=Vec3(.5);matte.rough=.65;Vec3 integral;
 for(int k=0;k<50000;k++){double z=rng.uniform(),phi=2*pi*rng.uniform(),r=std::sqrt(1-z*z);Vec3 wi(r*std::cos(phi),z,r*std::sin(phi));auto e=bsdf(matte,matte.color,Vec3(0,1,0),Vec3(0,1,0),wi);assert(e.pdf>=0&&std::isfinite(e.pdf));integral+=e.f*(z*2*pi/50000.);}
 assert(integral.x>.4&&integral.x<.7);assert(source_spectrum(1400).x>source_spectrum(1200).x);
 std::cout<<"PASS: radiance mip average, auxiliary normal preservation, light PDFs normalized/full-support, finite BSDF and hemisphere integral, Planck monotonicity\n";
}
