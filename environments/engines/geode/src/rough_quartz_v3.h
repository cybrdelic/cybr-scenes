// Rough spectral dielectric extension for the CYBR native transport loop.
// Isotropic GGX VNDF sampling with Fresnel reflection/transmission, matching
// evaluators and densities. Theory: PBRT 4, section 9.7 (see docs_v3).
struct GlassEval { float f=0, pdf=0; };
V sampleVisibleNormal(V n,V outgoing,float alpha,RNG&rng){
    Frame frame(n);V v=frame.local(outgoing);
    V stretched=unit(V(alpha*v.x,alpha*v.y,std::max(1e-7f,v.z)));
    float q=stretched.x*stretched.x+stretched.y*stretched.y;
    V a=q>1e-12f?V(-stretched.y,stretched.x,0)/std::sqrt(q):V(1,0,0);
    V b=cross(stretched,a);
    float radius=std::sqrt(rng.uniform()),angle=2*PI*rng.uniform();
    float x=radius*std::cos(angle),y=radius*std::sin(angle),mix=.5f*(1+stretched.z);
    y=(1-mix)*std::sqrt(std::max(0.f,1-x*x))+mix*y;
    V h=a*x+b*y+stretched*std::sqrt(std::max(0.f,1-x*x-y*y));
    return unit(frame.world(unit(V(alpha*h.x,alpha*h.y,std::max(0.f,h.z)))));
}
GlassEval roughGlass(V n,V outgoing,V incoming,float ratio,float alpha){
    GlassEval result;
    float co=dot(n,outgoing),ci=dot(n,incoming);
    if(co<=1e-7f||std::fabs(ci)<1e-7f)return result;
    bool reflection=ci>0;float eta=reflection?1.f:ratio;
    V sum=outgoing+incoming*eta;if(dot(sum,sum)<1e-15f)return result;
    V h=unit(sum);if(dot(h,n)<0)h=-h;
    float oh=dot(outgoing,h),ih=dot(incoming,h);
    if(oh<=0||ih*ci<=0)return result;
    float F=fresnelD(oh,1.f,ratio),D=Dggx(clamp(dot(n,h)),alpha);
    float masking=G1(co,alpha)*G1(std::fabs(ci),alpha);
    float normalPDF=D*G1(co,alpha)*oh/co;
    if(reflection){
        result.f=F*D*masking/(4*co*ci);
        result.pdf=normalPDF*F/(4*oh);
    }else{
        float jacDen=sqr(ih+oh/ratio);if(jacDen<1e-18f)return result;
        result.f=(1-F)*D*masking*std::fabs(ih*oh/(jacDen*ci*co))/sqr(ratio);
        result.pdf=normalPDF*(1-F)*std::fabs(ih)/jacDen;
    }
    return result;
}
V sampleRoughGlass(V n,V outgoing,float ratio,float alpha,RNG&rng,bool &crossed){
    V h=sampleVisibleNormal(n,outgoing,alpha,rng);
    float F=fresnelD(dot(outgoing,h),1.f,ratio);
    crossed=rng.uniform()>=F;
    V incoming=crossed?refractRay(-outgoing,h,1.f/ratio):unit(reflect(-outgoing,h));
    if(dot(incoming,incoming)<.5f)return V();
    if((dot(n,incoming)<0)!=crossed)return V();
    return incoming;
}
