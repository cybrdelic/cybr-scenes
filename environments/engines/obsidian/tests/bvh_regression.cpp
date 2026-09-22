#include "cybr/geometry.hpp"
#include <iostream>
#include <cassert>
using namespace cybr;
int main(){
 RNG rng(831621);std::vector<Primitive> p;
 for(int i=0;i<260;i++){Primitive q;q.shape=i%9==0?Shape::Sphere:Shape::Triangle;
 q.a=Vec3(rng.uniform()*20-10,rng.uniform()*20-10,rng.uniform()*20-10);
 q.b=q.a+uniform_sphere(rng)*rng.uniform()*2;q.c=q.a+uniform_sphere(rng)*rng.uniform()*2;q.radius=.2+rng.uniform();q.velocity=uniform_sphere(rng)*.5;p.push_back(q);}
 BVH b;b.build(p,0,1);
 for(int i=0;i<12000;i++){
 Ray r{uniform_sphere(rng)*14,uniform_sphere(rng),rng.uniform()};if(i%30==0)r.d=Vec3(0,1,0);if(i%31==0)r.d=Vec3(1,0,0);
 Hit a;bool yes=b.hit(r,a);Hit reference;bool truth=false;for(const auto&q:p)if(q.hit(r,1e-6,reference))truth=true;
 assert(yes==truth);if(truth)assert(std::abs(a.t-reference.t)<1e-9);
 double limit=rng.uniform()*22;bool blocked=b.occluded(r,limit),brute=false;Hit sh;sh.t=limit;for(const auto&q:p)if(q.hit(r,1e-6,sh)){brute=true;break;}
 assert(blocked==brute);
 }std::cout<<"PASS: 12000 accelerated closest-hit and shadow rays match brute-force intersections, including axis-parallel rays and moving primitives.\n";
}
