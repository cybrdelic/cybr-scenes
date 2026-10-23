// CYBR GEO native BVH and triangle intersection, reused from native/pathtrace.cpp.
// GPL-2.0-only. Original source SHA256: f1b3eb112b48137645c28c931be4162a76d21dc98ca02f5f99790b4e18183b38
// The only geometric unit change is EPS: scene transport uses metres, not millimetres.
#pragma once
// Offline triangle-geometry path tracer for the reference reconstruction.
// C++17 / OpenMP. No neural images, image billboards, raster shadow tricks,
// screen-space occlusion, or generative textures. All visibility is ray traced.
// Includes a binned SAH BVH, smooth normals, GGX visible-normal sampling,
// diffuse/GGX mixture PDFs, area-light next-event estimation and MIS,
// camera jitter, Russian roulette, and procedural micromachining.
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iostream>
#include <limits>
#include <numeric>
#include <sstream>
#include <string>
#include <vector>
#include <omp.h>

constexpr float PI=3.14159265358979323846f, EPS=.00002f, INF=1.e30f;
struct V {
 float x=0,y=0,z=0;
 V(){} V(float a):x(a),y(a),z(a){} V(float a,float b,float c):x(a),y(b),z(c){}
 float &operator[](int i){return (&x)[i];} float operator[](int i)const{return (&x)[i];}
 V operator+(V b)const{return {x+b.x,y+b.y,z+b.z};}
 V operator-(V b)const{return {x-b.x,y-b.y,z-b.z};}
 V operator-()const{return {-x,-y,-z};}
 V operator*(float b)const{return {x*b,y*b,z*b};}
 V operator/(float b)const{return *this*(1.f/b);}
 V operator*(V b)const{return {x*b.x,y*b.y,z*b.z};}
 V &operator+=(V b){x+=b.x;y+=b.y;z+=b.z;return *this;}
 V &operator*=(V b){x*=b.x;y*=b.y;z*=b.z;return *this;}
 V &operator*=(float b){x*=b;y*=b;z*=b;return *this;}
};
inline V operator*(float a,V b){return b*a;}
inline float dot(V a,V b){return a.x*b.x+a.y*b.y+a.z*b.z;}
inline V cross(V a,V b){return {a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x};}
inline float len(V a){return std::sqrt(dot(a,a));}
inline V unit(V a){return a/std::sqrt(std::max(1e-30f,dot(a,a)));}
inline V vmin(V a,V b){return {std::min(a.x,b.x),std::min(a.y,b.y),std::min(a.z,b.z)};}
inline V vmax(V a,V b){return {std::max(a.x,b.x),std::max(a.y,b.y),std::max(a.z,b.z)};}
inline float maxc(V a){return std::max(a.x,std::max(a.y,a.z));}
inline float clamp(float a,float lo=0.f,float hi=1.f){return std::max(lo,std::min(hi,a));}
inline V reflect(V i,V n){return i-2*dot(i,n)*n;}
inline float sqr(float x){return x*x;}
struct RNG{
 uint64_t state;
 RNG(uint64_t seed):state(seed+0x9e3779b97f4a7c15ULL){for(int i=0;i<4;i++)next();}
 uint32_t next(){state^=state>>12;state^=state<<25;state^=state>>27;return uint32_t((state*2685821657736338717ULL)>>32);}
 float uniform(){return (next()>>8)*(1.f/16777216.f);}
};
struct Ray {V o,d,inv; Ray(V a,V b):o(a),d(b),inv(1.f/b.x,1.f/b.y,1.f/b.z){} };
struct Box{
 V lo{INF},hi{-INF};
 void grow(V v){lo=vmin(lo,v);hi=vmax(hi,v);}
 void grow(const Box& b){lo=vmin(lo,b.lo);hi=vmax(hi,b.hi);}
 float area()const{V d=vmax(hi-lo,V(0));return 2*(d.x*d.y+d.x*d.z+d.y*d.z);}
 bool hit(const Ray&r,float maxT,float *entry=nullptr)const {
  float t0=EPS,t1=maxT;
  for(int k=0;k<3;k++){
   float a=(lo[k]-r.o[k])*r.inv[k],b=(hi[k]-r.o[k])*r.inv[k];
   if(a>b)std::swap(a,b);t0=std::max(t0,a);t1=std::min(t1,b);
   if(t0>t1)return false;
  }
  if(entry)*entry=t0;return true;
 }
};
struct Tri{
 V p,e1,e2,n0,n1,n2; int mat=0,group=0;
 V centroid()const{return p+(e1+e2)*(1.f/3);}
 Box bounds()const{Box b;b.grow(p);b.grow(p+e1);b.grow(p+e2);return b;}
 bool hit(const Ray&r,float maxT,float &t,float &u,float &v)const{
  V pvec=cross(r.d,e2);float det=dot(e1,pvec);
  if(std::fabs(det)<1e-10f)return false;
  float inv=1.f/det;V tv=r.o-p;u=dot(tv,pvec)*inv;
  if(u<0||u>1)return false;
  V q=cross(tv,e1);v=dot(r.d,q)*inv;if(v<0||u+v>1)return false;
  t=dot(e2,q)*inv;return t>EPS&&t<maxT;
 }
};
struct Node {Box b;int left=-1,right=-1,start=0,count=0;};
struct Hit {float t=INF,u=0,v=0;int tri=-1,light=-1;bool floor=false;};
std::vector<Tri> tris;std::vector<int> order;std::vector<Node> nodes;
int build(int start,int count){
 int ni=nodes.size();nodes.emplace_back();Box bounds,cb;
 for(int j=start;j<start+count;j++){bounds.grow(tris[order[j]].bounds());cb.grow(tris[order[j]].centroid());}
 nodes[ni].b=bounds;
 if(count<=5){nodes[ni].start=start;nodes[ni].count=count;return ni;}
 constexpr int NB=12;
 float best=INF;int ba=-1,bb=-1;
 for(int ax=0;ax<3;ax++){
  float extent=cb.hi[ax]-cb.lo[ax];if(extent<1e-5f)continue;
  Box bins[NB];int cnt[NB]={};
  for(int j=start;j<start+count;j++){
   const auto &tr=tris[order[j]];int b=std::min(NB-1,int(NB*(tr.centroid()[ax]-cb.lo[ax])/extent));
   bins[b].grow(tr.bounds());cnt[b]++;
  }
  Box left[NB-1],right[NB-1];int lc[NB-1],rc[NB-1];Box cur;int n=0;
  for(int k=0;k<NB-1;k++){cur.grow(bins[k]);n+=cnt[k];left[k]=cur;lc[k]=n;}
  cur=Box();n=0;
  for(int k=NB-1;k>0;k--){cur.grow(bins[k]);n+=cnt[k];right[k-1]=cur;rc[k-1]=n;}
  for(int k=0;k<NB-1;k++)if(lc[k]&&rc[k]){
   float c=left[k].area()*lc[k]+right[k].area()*rc[k];
   if(c<best){best=c;ba=ax;bb=k;}
  }
 }
 if(ba<0){nodes[ni].start=start;nodes[ni].count=count;return ni;}
 float split=cb.lo[ba]+(cb.hi[ba]-cb.lo[ba])*(float(bb+1)/NB);
 auto it=std::partition(order.begin()+start,order.begin()+start+count,[&](int id){return tris[id].centroid()[ba]<split;});
 int mid=int(it-order.begin());
 if(mid==start||mid==start+count)mid=start+count/2;
 int l=build(start,mid-start),r=build(mid,start+count-mid);
 nodes[ni].left=l;nodes[ni].right=r;return ni;
}
bool meshHit(const Ray&r,Hit &h,bool any=false){
 int stack[96],sp=0;stack[sp++]=0;bool found=false;
 while(sp){
  int ni=stack[--sp];const auto&nd=nodes[ni];
  if(!nd.b.hit(r,h.t))continue;
  if(nd.count){
   for(int i=nd.start;i<nd.start+nd.count;i++){
    int id=order[i];float t,u,v;
    if(tris[id].hit(r,h.t,t,u,v)){h.t=t;h.u=u;h.v=v;h.tri=id;h.floor=false;h.light=-1;found=true;if(any)return true;}
   }
  }else{
   float a,b;bool ha=nodes[nd.left].b.hit(r,h.t,&a),hb=nodes[nd.right].b.hit(r,h.t,&b);
   if(ha&&hb){if(a<b){stack[sp++]=nd.right;stack[sp++]=nd.left;}else{stack[sp++]=nd.left;stack[sp++]=nd.right;}}
   else if(ha)stack[sp++]=nd.left;else if(hb)stack[sp++]=nd.right;
  }
 }
 return found;
}
