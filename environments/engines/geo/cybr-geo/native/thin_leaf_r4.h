// SPDX-License-Identifier: GPL-2.0-only
// R4 two-sided thin leaf: Fresnel GGX surface reflection plus attenuated
// diffuse reflection/transmission from an authored interior. This is not a
// measured botanical model and omits internal multiple reflections.
#pragma once
constexpr float LEAF_BODY_REFLECT=0.60f;
inline float leafCoatProbability(const Surface &m,V n,V view){
    return clamp(.12f+.60f*fresnelD(clamp(dot(n,view)),1.f,m.ior),.12f,.72f);
}
Spec evalLeafBSDF(const Surface&m,const Spec&base,V n,V view,V light){
    float nv=dot(n,view),nl=dot(n,light),al=std::fabs(nl);
    if(nv<=0.f||al<=0.f)return Spec();
    float fv=fresnelD(clamp(nv),1.f,m.ior),fl=fresnelD(clamp(al),1.f,m.ior);
    float side=nl>=0.f?LEAF_BODY_REFLECT:(1.f-LEAF_BODY_REFLECT);
    Spec result=base*(side*(1.f-fv)*(1.f-fl)/PI);
    if(nl>0.f){
        V half=unit(view+light);float alpha=std::max(.025f,m.rough*m.rough);
        // Symmetric half-angle evaluation avoids view/light-order roundoff.
        float vh=std::sqrt(clamp(.5f*(1.f+dot(view,light))));
        float f=fresnelD(vh,1.f,m.ior);
        result+=Spec(f*Dggx(clamp(dot(n,half)),alpha)*(G1(nv,alpha)*G1(nl,alpha))/(4.f*(nv*nl)));
    }
    return result;
}
float pdfLeafBSDF(const Surface&m,V n,V view,V light){
    float nv=dot(n,view),nl=dot(n,light);if(nv<=0.f)return 0.f;
    float p=leafCoatProbability(m,n,view);
    float pdf=(1.f-p)*(nl>=0.f?LEAF_BODY_REFLECT:(1.f-LEAF_BODY_REFLECT))*std::fabs(nl)/PI;
    if(nl>0.f){
        V half=unit(view+light);float alpha=std::max(.025f,m.rough*m.rough);
        pdf+=p*Dggx(clamp(dot(n,half)),alpha)*G1(nv,alpha)/(4.f*nv);
    }
    return pdf;
}
V sampleLeafBSDF(const Surface&m,V n,V view,RNG&rng){
    Frame frame(n);V v=frame.local(view);
    if(rng.uniform()>=leafCoatProbability(m,n,view)){
        float side=rng.uniform()<LEAF_BODY_REFLECT?1.f:-1.f;
        float u=rng.uniform(),phi=2.f*PI*rng.uniform(),r=std::sqrt(u);
        return frame.world(V(r*std::cos(phi),r*std::sin(phi),side*std::sqrt(1.f-u)));
    }
    float alpha=std::max(.025f,m.rough*m.rough);
    V vh=unit(V(alpha*v.x,alpha*v.y,std::max(0.f,v.z)));
    float lensq=vh.x*vh.x+vh.y*vh.y;
    V t1=lensq>0.f?V(-vh.y,vh.x,0.f)/std::sqrt(lensq):V(1,0,0),t2=cross(vh,t1);
    float r=std::sqrt(rng.uniform()),phi=2.f*PI*rng.uniform();
    float x=r*std::cos(phi),y=r*std::sin(phi),blend=.5f*(1.f+vh.z);
    y=(1.f-blend)*std::sqrt(std::max(0.f,1.f-x*x))+blend*y;
    V nh=t1*x+t2*y+vh*std::sqrt(std::max(0.f,1.f-x*x-y*y));
    V half=unit(V(alpha*nh.x,alpha*nh.y,std::max(0.f,nh.z)));
    V next=reflect(-v,half);
    // A reflected sample below the surface is a null event. It must NOT be
    // interpreted as a transmitted-body sample, whose PDF excludes this lobe.
    if(next.z<=0.f)return V(0);
    return unit(frame.world(next));
}
