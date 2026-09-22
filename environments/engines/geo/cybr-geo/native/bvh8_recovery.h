// SPDX-License-Identifier: GPL-2.0-only
// Eight-child layout of the original CYBR GEO binned SAH hierarchy.
// Partitioning and triangle predicate remain unchanged.
#pragma once
#include <immintrin.h>
struct alignas(32) WideNodeR3 {float lo[3][8],hi[3][8];int reference[8],count[8],size;};
std::vector<WideNodeR3> wideNodesR3;
int flattenWideR3(int root){
 int out=int(wideNodesR3.size());wideNodesR3.emplace_back();std::vector<int> frontier{root};
 while(frontier.size()<8){
  int select=-1;float area=-1;
  for(size_t j=0;j<frontier.size();++j){const auto &n=nodes[frontier[j]];if(!n.count&&n.b.area()>area){select=int(j);area=n.b.area();}}
  if(select<0)break;int i=frontier[select];frontier[select]=nodes[i].left;frontier.push_back(nodes[i].right);
 }
 wideNodesR3[out].size=int(frontier.size());
 for(int j=0;j<8;++j){auto &w=wideNodesR3[out];w.count[j]=0;w.reference[j]=0;for(int a=0;a<3;++a){w.lo[a][j]=INF;w.hi[a][j]=-INF;}}
 for(int j=0;j<int(frontier.size());++j){const Node n=nodes[frontier[j]];
  for(int a=0;a<3;++a){wideNodesR3[out].lo[a][j]=std::nextafter(n.b.lo[a],-INFINITY);wideNodesR3[out].hi[a][j]=std::nextafter(n.b.hi[a],INFINITY);}
  if(n.count){wideNodesR3[out].reference[j]=n.start;wideNodesR3[out].count[j]=n.count;}
  else{int child=flattenWideR3(frontier[j]);wideNodesR3[out].reference[j]=-child-1;}
 }return out;
}
void buildWideR3(){wideNodesR3.clear();if(nodes.empty())return;wideNodesR3.reserve(nodes.size()/3+1);flattenWideR3(0);}
inline unsigned boxesWideR3(const WideNodeR3 &w,const Ray &r,float limit,float *entries){
#ifdef __AVX2__
 __m256 nearv=_mm256_set1_ps(EPS),farv=_mm256_set1_ps(limit),valid=_mm256_castsi256_ps(_mm256_set1_epi32(-1));
 for(int a=0;a<3;++a){
  const __m256 low=_mm256_load_ps(w.lo[a]),high=_mm256_load_ps(w.hi[a]),origin=_mm256_set1_ps(r.o[a]);
  if(r.d[a]==0.0f)valid=_mm256_and_ps(valid,_mm256_and_ps(_mm256_cmp_ps(origin,low,_CMP_GE_OQ),_mm256_cmp_ps(origin,high,_CMP_LE_OQ)));
  else{__m256 inv=_mm256_set1_ps(r.inv[a]),x=_mm256_mul_ps(_mm256_sub_ps(low,origin),inv),y=_mm256_mul_ps(_mm256_sub_ps(high,origin),inv);nearv=_mm256_max_ps(nearv,_mm256_min_ps(x,y));farv=_mm256_min_ps(farv,_mm256_max_ps(x,y));}
 }
 _mm256_storeu_ps(entries,nearv);return unsigned(_mm256_movemask_ps(_mm256_and_ps(valid,_mm256_cmp_ps(nearv,farv,_CMP_LE_OQ))))&((1u<<w.size)-1);
#else
 unsigned mask=0;for(int j=0;j<w.size;++j){float low=EPS,high=limit;bool valid=true;
  for(int a=0;a<3;++a){if(r.d[a]==0.0f){if(r.o[a]<w.lo[a][j]||r.o[a]>w.hi[a][j])valid=false;}else{float x=(w.lo[a][j]-r.o[a])*r.inv[a],y=(w.hi[a][j]-r.o[a])*r.inv[a];if(x>y)std::swap(x,y);low=std::max(low,x);high=std::min(high,y);}}
  entries[j]=low;if(valid&&low<=high)mask|=1u<<j;
 }return mask;
#endif
}
inline bool meshHitWideR3(const Ray &r,Hit &h,bool any=false,bool opaqueOnly=false){
 if(wideNodesR3.empty())return meshHit(r,h,any);
 struct Work{int ref,count;float entry;};Work stack[1024];int sp=0;stack[sp++]={-1,0,EPS};bool found=false;
 while(sp){Work work=stack[--sp];if(work.entry>h.t)continue;
  if(work.count){for(int j=work.ref;j<work.ref+work.count;++j){int id=order[j];const auto &t=tris[id];if(opaqueOnly&&(t.mat==6||t.mat==7))continue;float distance,u,v;
   if(t.hit(r,h.t,distance,u,v)){h.t=distance;h.u=u;h.v=v;h.tri=id;h.floor=false;h.light=-1;found=true;if(any)return true;}
  }}else{
   const auto &w=wideNodesR3[-work.ref-1];float entries[8];unsigned hits=boxesWideR3(w,r,h.t,entries);Work next[8];int nn=0;
   while(hits){unsigned j=unsigned(__builtin_ctz(hits));hits&=hits-1;Work a{w.reference[j],w.count[j],entries[j]};int k=nn++;while(k>0&&next[k-1].entry<a.entry){next[k]=next[k-1];--k;}next[k]=a;}
   if(sp+nn>=1024)throw std::runtime_error("CYBR wide BVH traversal stack overflow");for(int j=0;j<nn;++j)stack[sp++]=next[j];
  }
 }return found;
}
