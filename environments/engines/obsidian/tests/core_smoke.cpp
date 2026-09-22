#include "cybr/geometry.hpp"
#include "cybr/spectrum.hpp"
#include <cassert>
#include <iostream>
using namespace cybr;
int main() {
 Primitive p; p.shape=Shape::Triangle;
 p.a={-1,0,-1}; p.b={0,0,1}; p.c={1,0,-1};
 p.material=0; p.object=0;
 std::vector<Primitive> prims{p}; BVH bvh; bvh.build(prims);
 Ray ray{{0,2,0},{0,-1,0}};Hit h;
 assert(bvh.hit(ray,h)); assert(std::abs(h.t-2)<1e-9);
 assert(h.front); assert(h.n.y>.99999);
 assert(bvh.occluded(ray,2.1)); assert(!bvh.occluded(ray,1.9));
 assert(!bvh.occluded({{4,2,0},{0,-1,0}},10));
 assert(blackbody(650,1600)>blackbody(650,1300));
 assert(std::isfinite(Observer::analytic(550).y));
 Vec3 n=normalize(Vec3(1,2,3));assert(std::abs(norm(n)-1)<1e-12);
 Camera c;c.origin={0,2,0};c.target={0,0,0};c.up={0,0,1};RNG r(3);
 auto camera_ray=c.generate(50,50,100,100,r);
 assert(dot(camera_ray.d,Vec3(0,-1,0))>.9999);
 std::cout<<"PASS: intersections, BVH visibility, camera, spectral source monotonicity\n";
}
