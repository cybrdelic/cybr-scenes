#pragma once
#include <immintrin.h>
// BVH4/AVX2 traversal built from the same deterministic native SAH hierarchy.
// No geometry simplification: all triangle positions and UVs stay unchanged.
struct alignas(32) TrianglePacket {
 __m256 p[3],e1[3],e2[3];uint32_t valid=0,opaque=0;int first=0;
};
struct PacketLeaf {int first,count;};
struct alignas(64) WideNode {
 float low[3][4],high[3][4];int child[4];
};
std::vector<TrianglePacket> packets;
std::vector<PacketLeaf> packetLeaves;
std::vector<WideNode> wideNodes;
int wideRoot=0;
int buildWideNode(int ni){
 const Node nd=nodes[ni];
 if(nd.count){
  PacketLeaf leaf{int(packets.size()),0};
  for(int off=0;off<nd.count;off+=8){
   TrianglePacket p;alignas(32) float v[9][8]{};p.first=nd.start+off;
   for(int lane=0;lane<std::min(8,nd.count-off);lane++){
    const Tri&t=tris[order[p.first+lane]];p.valid|=1u<<lane;p.opaque|=1u<<lane;
    for(int axis=0;axis<3;axis++){v[axis][lane]=t.p[axis];v[3+axis][lane]=t.e1[axis];v[6+axis][lane]=t.e2[axis];}
   }
   for(int axis=0;axis<3;axis++){p.p[axis]=_mm256_load_ps(v[axis]);p.e1[axis]=_mm256_load_ps(v[3+axis]);p.e2[axis]=_mm256_load_ps(v[6+axis]);}
   packets.push_back(p);leaf.count++;
  }
  int id=int(packetLeaves.size());packetLeaves.push_back(leaf);return -id-1;
 }
 std::vector<int> frontier{nd.left,nd.right};
 while(frontier.size()<4){int split=-1;float area=-1;
  for(int i=0;i<int(frontier.size());i++)if(!nodes[frontier[i]].count&&nodes[frontier[i]].b.area()>area){split=i;area=nodes[frontier[i]].b.area();}
  if(split<0)break;int id=frontier[split];frontier[split]=nodes[id].left;frontier.push_back(nodes[id].right);
 }
 int id=int(wideNodes.size());wideNodes.emplace_back();WideNode out{};
 for(int lane=0;lane<4;lane++){
  if(lane<int(frontier.size())){const Box b=nodes[frontier[lane]].b;for(int a=0;a<3;a++){out.low[a][lane]=b.lo[a];out.high[a][lane]=b.hi[a];}out.child[lane]=buildWideNode(frontier[lane]);}
  else{for(int a=0;a<3;a++){out.low[a][lane]=INF;out.high[a][lane]=-INF;}out.child[lane]=INT32_MAX;}
 }
 wideNodes[id]=out;return id;
}
void buildWide(){packets.reserve(tris.size()/3);packetLeaves.reserve(tris.size()/3);wideNodes.reserve(nodes.size()/3);wideRoot=buildWideNode(0);}

bool packetHit(const TrianglePacket&p,const Ray&r,Hit&h,bool any,bool opaqueOnly){
 __m256 d[3],o[3],tv[3],pv[3],qv[3];for(int a=0;a<3;a++){d[a]=_mm256_set1_ps(r.d[a]);o[a]=_mm256_set1_ps(r.o[a]);tv[a]=_mm256_sub_ps(o[a],p.p[a]);}
 auto crossComp=[](__m256 a,__m256 b,__m256 c,__m256 d){return _mm256_sub_ps(_mm256_mul_ps(a,b),_mm256_mul_ps(c,d));};
 pv[0]=crossComp(d[1],p.e2[2],d[2],p.e2[1]);pv[1]=crossComp(d[2],p.e2[0],d[0],p.e2[2]);pv[2]=crossComp(d[0],p.e2[1],d[1],p.e2[0]);
 auto dot3=[](const __m256*a,const __m256*b){return _mm256_add_ps(_mm256_add_ps(_mm256_mul_ps(a[0],b[0]),_mm256_mul_ps(a[1],b[1])),_mm256_mul_ps(a[2],b[2]));};
 __m256 det=dot3(p.e1,pv),inv=_mm256_div_ps(_mm256_set1_ps(1),det),u=_mm256_mul_ps(dot3(tv,pv),inv);
 qv[0]=crossComp(tv[1],p.e1[2],tv[2],p.e1[1]);qv[1]=crossComp(tv[2],p.e1[0],tv[0],p.e1[2]);qv[2]=crossComp(tv[0],p.e1[1],tv[1],p.e1[0]);
 __m256 v=_mm256_mul_ps(dot3(d,qv),inv),t=_mm256_mul_ps(dot3(p.e2,qv),inv),zero=_mm256_setzero_ps(),one=_mm256_set1_ps(1);
 __m256 mask=_mm256_cmp_ps(_mm256_andnot_ps(_mm256_set1_ps(-0.f),det),_mm256_set1_ps(1e-10f),_CMP_GE_OQ);
 mask=_mm256_and_ps(mask,_mm256_cmp_ps(u,zero,_CMP_GE_OQ));mask=_mm256_and_ps(mask,_mm256_cmp_ps(v,zero,_CMP_GE_OQ));
 mask=_mm256_and_ps(mask,_mm256_cmp_ps(_mm256_add_ps(u,v),one,_CMP_LE_OQ));
 mask=_mm256_and_ps(mask,_mm256_cmp_ps(t,_mm256_set1_ps(EPS),_CMP_GT_OQ));mask=_mm256_and_ps(mask,_mm256_cmp_ps(t,_mm256_set1_ps(h.t),_CMP_LT_OQ));
 uint32_t bits=uint32_t(_mm256_movemask_ps(mask))&(opaqueOnly?p.opaque:p.valid);if(!bits)return false;
 if(any)return true;
 alignas(32) float tt[8],uu[8],vv[8];_mm256_store_ps(tt,t);_mm256_store_ps(uu,u);_mm256_store_ps(vv,v);
 while(bits){int lane=__builtin_ctz(bits);bits&=bits-1;if(tt[lane]<h.t){h.t=tt[lane];h.u=uu[lane];h.v=vv[lane];h.tri=order[p.first+lane];h.floor=false;h.light=-1;}}
 return true;
}
bool wideHit(const Ray&r,Hit&h,bool any=false,bool opaqueOnly=false){
 struct Entry{int id;float t;};Entry stack[160];int sp=0;stack[sp++]={wideRoot,EPS};bool found=false;
 __m128 origin[3],inv[3];for(int a=0;a<3;a++){origin[a]=_mm_set1_ps(r.o[a]);inv[a]=_mm_set1_ps(r.inv[a]);}
 while(sp){Entry e=stack[--sp];if(e.t>h.t)continue;
  if(e.id<0){const auto&leaf=packetLeaves[-e.id-1];for(int p=0;p<leaf.count;p++)if(packetHit(packets[leaf.first+p],r,h,any,opaqueOnly)){found=true;if(any)return true;}continue;}
  const auto&node=wideNodes[e.id];__m128 lo=_mm_set1_ps(EPS),hi=_mm_set1_ps(h.t);
  for(int a=0;a<3;a++){
   __m128 t0=_mm_mul_ps(_mm_sub_ps(_mm_loadu_ps(node.low[a]),origin[a]),inv[a]);
   __m128 t1=_mm_mul_ps(_mm_sub_ps(_mm_loadu_ps(node.high[a]),origin[a]),inv[a]);
   lo=_mm_max_ps(lo,_mm_min_ps(t0,t1));hi=_mm_min_ps(hi,_mm_max_ps(t0,t1));
  }
  unsigned mask=unsigned(_mm_movemask_ps(_mm_cmple_ps(lo,hi)));alignas(16) float near[4];_mm_store_ps(near,lo);
  Entry hit[4];int count=0;
  for(int lane=0;lane<4;lane++)if((mask&(1u<<lane))&&node.child[lane]!=INT32_MAX){Entry v{node.child[lane],near[lane]};int j=count++;while(j>0&&hit[j-1].t<v.t){hit[j]=hit[j-1];j--;}hit[j]=v;}
  for(int i=0;i<count;i++)stack[sp++]=hit[i];
 }
 return found;
}
