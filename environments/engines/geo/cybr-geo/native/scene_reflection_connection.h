// GPL-2.0-only. One-root macro-interface reflection manifold.
// Complements the existing one-root transmitted solar connection. This
// approximates rough microscopic caustics; it is NOT an unbiased all-root
// solution. It replaces, rather than double-counts, the corresponding
// air-non-delta -> water reflection -> solar-disc continuation path class.
#pragma once
#include "ground_occlusion_r4.h"
Connection reflectedWaterConnection(V p,V air,int pool,bool computeJac=true){
    Connection c;const auto &a=pools[pool];
    if(computeJac&&pool==0&&groundOcclusion.occludes(p,air))return c;
    if(p.z<=a.level+.002f||air.z<.05f)return c;
    V outgoing=reflect(-air,V(0,0,1));
    V q=p-outgoing*((p.z-a.level)/outgoing.z);
    if(std::fabs(q.x-a.x)>a.rx*1.6f||std::fabs(q.y-a.y)>a.ry*1.6f)return c;
    auto residual=[&](V at){
        V n=waterNormal(at.x,at.y,pool),r=reflect(-air,n);
        float z=waterHeight(at.x,at.y,pool),height=p.z-z;
        if(r.z<=.035f||height<=.0001f)return V(INF,INF,0);
        return V(at.x+r.x*height/r.z-p.x,at.y+r.y*height/r.z-p.y,0);
    };
    V res=residual(q);
    for(int iter=0;iter<14&&dot(res,res)>1.e-10f;iter++){
        constexpr float e=.0008f;
        V dx=(residual(q+V(e,0,0))-residual(q-V(e,0,0)))/(2*e);
        V dy=(residual(q+V(0,e,0))-residual(q-V(0,e,0)))/(2*e);
        float det=dx.x*dy.y-dy.x*dx.y;
        if(!std::isfinite(det)||std::fabs(det)<1.e-6f)return c;
        V step((dy.y*res.x-dy.x*res.y)/det,(-dx.y*res.x+dx.x*res.y)/det,0);
        float size=len(step);if(size>.35f)step*=.35f/size;
        bool accepted=false;
        for(int ls=0;ls<7;ls++){
            V trial=q-step,r=residual(trial);
            if(dot(r,r)<dot(res,res)){q=trial;res=r;accepted=true;break;}
            step*=.5f;
        }
        if(!accepted)break;
    }
    if(!std::isfinite(res.x)||!std::isfinite(res.y)||dot(res,res)>4.e-8f)return c;
    q.z=waterHeight(q.x,q.y,pool);
    if(poolQ(q,pool)>1.13f)return c;
    c.q=q;c.l=unit(q-p);c.n=waterNormal(q.x,q.y,pool);
    c.valid=dot(-c.l,c.n)>.01f&&dot(air,c.n)>.01f&&p.z>q.z;
    // R4: reject the exact same buried/non-water interface that the light
    // factor rejects, but BEFORE the four costly finite-difference root solves.
    // No samples, visibility thresholds, or light contributions are approximated.
    if(computeJac&&c.valid&&!tris.empty()){
        Hit interfaceHit;
        if(!meshHit(Ray(c.q+V(0,0,.015f),V(0,0,-1)),interfaceHit)||
           (tris[interfaceHit.tri].mat!=6&&tris[interfaceHit.tri].mat!=7)||
           interfaceHit.t>.030f){c.valid=false;return c;}
    }
    if(computeJac&&c.valid){
        Frame f(air);constexpr float e=.0001f;
        auto u1=reflectedWaterConnection(p,unit(air+f.t*e),pool,false);
        auto u0=reflectedWaterConnection(p,unit(air-f.t*e),pool,false);
        auto v1=reflectedWaterConnection(p,unit(air+f.b*e),pool,false);
        auto v0=reflectedWaterConnection(p,unit(air-f.b*e),pool,false);
        if(!u1.valid||!u0.valid||!v1.valid||!v0.valid){c.valid=false;return c;}
        c.jacobian=std::fabs(dot(c.l,cross((u1.l-u0.l)/(2*e),(v1.l-v0.l)/(2*e))));
        if(!std::isfinite(c.jacobian)||c.jacobian>30)c.valid=false;
    }
    return c;
}
float reflectedSolarFactor(V p,V air,const Connection &c,RNG &rng){
    if(!c.valid)return 0;
    Hit interfaceHit;
    if(!meshHit(Ray(c.q+V(0,0,.015f),V(0,0,-1)),interfaceHit)||
       (tris[interfaceHit.tri].mat!=6&&tris[interfaceHit.tri].mat!=7)||interfaceHit.t>.030f)return 0;
    float distance=len(c.q-p);
    if(opaqueShadow(Ray(p,c.l),std::max(EPS,distance-EPS*15))||
       opaqueShadow(Ray(c.q+c.n*EPS*12,air),INF))return 0;
    float visibility=airTransmittance(Ray(p,c.l),std::max(EPS,distance-EPS*15),rng)
        *airTransmittance(Ray(c.q+c.n*EPS*12,air),INF,rng);
    return fresnelD(clamp(dot(air,c.n)),1,WATER_IOR)*SUN_SOLID*c.jacobian*visibility;
}
