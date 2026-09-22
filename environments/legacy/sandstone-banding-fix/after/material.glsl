// SPDX-License-Identifier: GPL-2.0-only
// Photographic receiving material. Does not change source positions or indices.
// Uses a metric triplanar projection of the same 4K maps on every surface.
// Parallax changes material intersections, NOT the terrain silhouette.
uniform highp sampler2D uRockColorRough;
uniform highp sampler2D uRockNormalHeightAO;
uniform highp sampler2D uSandColorRough;
uniform highp sampler2D uSandNormalHeightAO;
uniform vec3 uRockMean;
uniform vec3 uSandMean;
uniform float uRockScale,uSandScale,uRockRelief,uSandRelief;
uniform float uDetail;
uniform int uParallax;
uniform int uMicroShadows;
uniform int uLinearOutput;
uniform int uGeometricSun;
uniform highp sampler2D uSunDepth;
uniform mat4 uSunVP;
uniform vec3 uSunExtent;
uniform float uSunTexel;
uniform mat3 uSunViewRotation;
uniform highp sampler2D uNearSunDepth;
uniform mat4 uNearSunVP;
uniform vec3 uNearSunExtent;
// Depth must be sampled at high precision independently of float arithmetic.
// Compare at the actual texel centres, THEN interpolate comparison outcomes.
// Interpolating raw depths across occluder edges is not percentage-closer filtering.
vec4 swReceiverGaps(highp sampler2D depthMap,vec2 uv,vec3 receiver,vec2 slope,out vec2 f){
 ivec2 size=textureSize(depthMap,0);
 vec2 p=uv*vec2(size)-0.5;
 ivec2 b=ivec2(floor(p)); f=fract(p);
 ivec2 hi=size-ivec2(1);
 ivec2 c0=clamp(b,ivec2(0),hi),c1=clamp(b+ivec2(1,0),ivec2(0),hi);
 ivec2 c2=clamp(b+ivec2(0,1),ivec2(0),hi),c3=clamp(b+ivec2(1),ivec2(0),hi);
 vec4 z=vec4(texelFetch(depthMap,c0,0).r,texelFetch(depthMap,c1,0).r,
              texelFetch(depthMap,c2,0).r,texelFetch(depthMap,c3,0).r);
 vec4 r=receiver.zzzz+vec4(
   dot(slope,(vec2(c0)+0.5)/vec2(size)-receiver.xy),
   dot(slope,(vec2(c1)+0.5)/vec2(size)-receiver.xy),
   dot(slope,(vec2(c2)+0.5)/vec2(size)-receiver.xy),
   dot(slope,(vec2(c3)+0.5)/vec2(size)-receiver.xy));
 return r-z; // positive: actual occluder in front of the receiving plane
}
float swBilinear(vec4 v,vec2 f){return mix(mix(v.x,v.y,f.x),mix(v.z,v.w,f.x),f.y);}
float swShadow(highp sampler2D depthMap,mat4 sunVP,vec3 extent,vec3 P,vec3 Ng,float fallback){
 vec3 planeNormal=uSunViewRotation*Ng;
 // Faces turned away from the emitter cannot receive direct sunlight.
 if(planeNormal.z<=0.0)return 0.0;
 float cosSun=clamp(planeNormal.z,0.0,1.0);
 float texelMetres=max(extent.x,extent.y)*uSunTexel;
 // Offset by the depth footprint, not a display-space amount. This covers the
 // receiver's finite shadow texel without inflating bias with camera distance.
 float normalOffset=0.0015+min(0.010,0.5*texelMetres)*sqrt(max(0.0,1.0-cosSun*cosSun));
 vec4 projected=sunVP*vec4(P+Ng*normalOffset,1.0);
 vec3 q=projected.xyz/projected.w*0.5+0.5;
 if(any(lessThan(q,vec3(0)))||any(greaterThan(q,vec3(1))))return fallback;
 // Ng is the raster triangle's plane normal, not the smooth shading normal.
 // The latter gives a false depth slope and produces periodic self-shadow stripes.
 float z=(planeNormal.z<0.0?-1.0:1.0)*max(abs(planeNormal.z),0.06);
 vec2 slope=planeNormal.xy*extent.xy/(z*extent.z);
 q.z-=0.0015/extent.z+4.0/16777216.0;
 float weight=0.0,separationSum=0.0;
 for(int i=0;i<8;i++){
  float a=float(i)*2.39996323,r=sqrt((float(i)+0.5)/8.0);
  vec2 offset=vec2(cos(a),sin(a))*r*(0.10/extent.xy),f;
  vec4 gap=swReceiverGaps(depthMap,q.xy+offset,q,slope,f)*extent.z;
  // Continuous weighted blocker search avoids penumbra-size jumps when a
  // blocker enters a nearest-sampled texel or an eight-point search stencil.
  vec4 blocked=smoothstep(vec4(0.0001),vec4(0.004),gap);
  weight+=swBilinear(blocked,f);
  separationSum+=swBilinear(max(gap,vec4(0.0))*blocked,f);
 }
 float separation=weight>1e-5?separationSum/weight:0.0;
 vec2 radius=clamp(vec2(separation*0.00465)/extent.xy,vec2(uSunTexel*0.9),vec2(0.085)/extent.xy);
 float visible=0.0;
 for(int i=0;i<16;i++){
  float a=float(i)*2.39996323,r=sqrt((float(i)+0.5)/16.0);
  vec2 offset=vec2(cos(a),sin(a))*r*radius,f;
  vec4 gap=swReceiverGaps(depthMap,q.xy+offset,q,slope,f);
  visible+=swBilinear(step(gap,vec4(0.0)),f);
 }
 // Not restricted to 17 visibility values: each sample has fractional coverage.
 return visible/16.0;
}
float swSunVisibility(vec3 P,vec3 N,float fallback){
 if(uGeometricSun==0)return fallback;
 vec4 projected=uNearSunVP*vec4(P,1);
 vec3 q=projected.xyz/projected.w*.5+.5;
 float border=min(min(q.x,1.0-q.x),min(q.y,1.0-q.y));
 float blend=smoothstep(.01,.06,border)*step(0.,q.z)*step(q.z,1.);
 if(blend>.999)return swShadow(uNearSunDepth,uNearSunVP,uNearSunExtent,P,N,fallback);
 float broad=swShadow(uSunDepth,uSunVP,uSunExtent,P,N,fallback);
 if(blend<.001)return broad;
 return mix(broad,swShadow(uNearSunDepth,uNearSunVP,uNearSunExtent,P,N,fallback),blend);
}

struct SWScan {vec3 color; vec3 gradient; float rough; float ao; float shadow;};

SWScan swScanPlane(highp sampler2D colorMap, highp sampler2D dataMap, vec2 uv, vec2 du, vec2 dv,
                  vec3 viewTS, vec3 lightTS, vec3 tangent, vec3 bitangent,
                  float relativeDepth, float normalStrength, bool allowParallax) {
    vec2 hit=uv;
    float h=textureGrad(dataMap,hit,du,dv).b;
    if (allowParallax && viewTS.z>0.18) {
        // A bounded, centred, 12-layer linear search with a bracketed refinement.
        // Explicit unperturbed derivatives keep mip choice stable through steps.
        vec2 ray=viewTS.xy/max(viewTS.z,0.18)*relativeDepth;
        vec2 top=uv+0.5*ray;
        float previousDepth=0.0,depth=0.0;
        vec2 previousUV=top;
        float previousH=textureGrad(dataMap,top,du,dv).b;
        hit=top; h=previousH;
        for(int i=0;i<12;i++) {
            if(depth>=1.0-h)break;
            previousDepth=depth;previousUV=hit;previousH=h;
            depth+=1.0/12.0;
            hit=top-ray*depth;
            h=textureGrad(dataMap,hit,du,dv).b;
        }
        float a=previousDepth-(1.0-previousH),b=depth-(1.0-h);
        float t=clamp(b/max(b-a,0.00001),0.0,1.0);
        hit=mix(hit,previousUV,t);
        h=textureGrad(dataMap,hit,du,dv).b;
    }
    vec4 color=textureGrad(colorMap,hit,du,dv);
    vec4 data=textureGrad(dataMap,hit,du,dv);
    vec2 xy=data.rg*2.0-1.0;
    float nz=sqrt(max(0.045,1.0-dot(xy,xy)));
    SWScan s;
    s.color=color.rgb;
    s.gradient=-(tangent*xy.x+bitangent*xy.y)*(normalStrength/nz);
    s.rough=color.a; s.ao=data.a; s.shadow=1.0;
    if(uMicroShadows==1 && allowParallax && lightTS.z>0.18) {
        float obstruction=0.0;
        for(int i=0;i<4;i++) {
            float stepZ=(float(i)+1.0)*(float(i)+1.0)*0.041;
            vec2 at=hit+lightTS.xy/max(lightTS.z,0.18)*relativeDepth*stepZ;
            float other=textureGrad(dataMap,at,du,dv).b;
            float blocked=smoothstep(0.022,0.095,other-h-stepZ);
            obstruction=max(obstruction,blocked);
        }
        s.shadow=1.0-0.82*obstruction;
    }
    return s;
}

SWScan swScanMaterial(highp sampler2D colorMap, highp sampler2D dataMap, vec3 P, vec3 n,
                     vec3 V, vec3 L, vec3 dx, vec3 dy,
                     float scaleMetres, float heightMetres,float normalStrength) {
    vec3 w=pow(abs(n),vec3(6.0)); w/=max(dot(w,vec3(1.0)),0.00001);
    vec3 signs=vec3(n.x<0.0?-1.0:1.0,n.y<0.0?-1.0:1.0,n.z<0.0?-1.0:1.0);
    vec3 q=P/scaleMetres,ddx=dx/scaleMetres,ddy=dy/scaleMetres;
    float reliefFade=1.0-smoothstep(5.0,10.0,length(uEye-P));
    heightMetres*=reliefFade;
    bool relief=uParallax==1 && reliefFade>0.001;
    SWScan s; s.color=vec3(0);s.gradient=vec3(0);s.rough=0.0;s.ao=0.0;s.shadow=0.0;
    // Near-zero lobes are omitted below; their total weight is at most 0.00003.
    // Each projection has a positive handedness matching OpenGL tangent normals.
    if(w.x>0.00001){
        vec3 T=vec3(0,signs.x,0),B=vec3(0,0,1),W=vec3(signs.x,0,0);
        SWScan a=swScanPlane(colorMap,dataMap,vec2(q.y*signs.x,q.z),vec2(ddx.y*signs.x,ddx.z),vec2(ddy.y*signs.x,ddy.z),
            vec3(dot(V,T),dot(V,B),dot(V,W)),vec3(dot(L,T),dot(L,B),dot(L,W)),T,B,heightMetres/scaleMetres,normalStrength,relief);
        s.color+=w.x*a.color;s.gradient+=w.x*a.gradient;s.rough+=w.x*a.rough;s.ao+=w.x*a.ao;s.shadow+=w.x*a.shadow;
    }
    if(w.y>0.00001){
        vec3 T=vec3(-signs.y,0,0),B=vec3(0,0,1),W=vec3(0,signs.y,0);
        SWScan a=swScanPlane(colorMap,dataMap,vec2(-q.x*signs.y,q.z),vec2(-ddx.x*signs.y,ddx.z),vec2(-ddy.x*signs.y,ddy.z),
            vec3(dot(V,T),dot(V,B),dot(V,W)),vec3(dot(L,T),dot(L,B),dot(L,W)),T,B,heightMetres/scaleMetres,normalStrength,relief);
        s.color+=w.y*a.color;s.gradient+=w.y*a.gradient;s.rough+=w.y*a.rough;s.ao+=w.y*a.ao;s.shadow+=w.y*a.shadow;
    }
    if(w.z>0.00001){
        vec3 T=vec3(signs.z,0,0),B=vec3(0,1,0),W=vec3(0,0,signs.z);
        SWScan a=swScanPlane(colorMap,dataMap,vec2(q.x*signs.z,q.y),vec2(ddx.x*signs.z,ddx.y),vec2(ddy.x*signs.z,ddy.y),
            vec3(dot(V,T),dot(V,B),dot(V,W)),vec3(dot(L,T),dot(L,B),dot(L,W)),T,B,heightMetres/scaleMetres,normalStrength,relief);
        s.color+=w.z*a.color;s.gradient+=w.z*a.gradient;s.rough+=w.z*a.rough;s.ao+=w.z*a.ao;s.shadow+=w.z*a.shadow;
    }
    return s;
}

SWMaterial swPhotographicMaterial(vec3 P,vec3 n,int family,float footprint,vec3 dx,vec3 dy,vec3 V,
                                  out float cavity,out float microVisibility) {
    if(uDetail<0.001){cavity=1.0;microVisibility=1.0;return swMaterial(P,n,family,footprint);}
    bool sand=family==0||family==4;
    SWScan scan;
    if(sand)scan=swScanMaterial(uSandColorRough,uSandNormalHeightAO,P,n,V,uSun,dx,dy,uSandScale,uSandRelief,0.52);
    else scan=swScanMaterial(uRockColorRough,uRockNormalHeightAO,P,n,V,uSun,dx,dy,uRockScale,uRockRelief,0.70);
    // Retain coarse reflectance near the original bake, with real photographic
    // within-material variation. There is no burned-in scene illumination here.
    SWNoise broad=swBand(P,0.37,footprint,vec3(13.1,-8.4,2.3));
    SWNoise mottled=swBand(P,1.65,footprint,vec3(-17.2,3.8,29.1));
    float macro=.72*broad.value+.28*mottled.value;
    vec3 base=sand?mix(vec3(.282,.200,.132),vec3(.417,.314,.216),.56+.30*macro):
                   mix(vec3(.245,.134,.063),vec3(.475,.305,.167),.61+.45*macro);
    vec3 mean=sand?uSandMean:uRockMean;
    vec3 relative=clamp(scan.color/max(mean,vec3(.015)),vec3(.22),vec3(2.5));
    // Color differences remain registered with the scanned height and normal.
    SWMaterial m;
    m.color=clamp(base*relative,vec3(.012),vec3(.82));
    m.rough=clamp(mix(sand?.91:.82,scan.rough,.68),.56,.97);
    vec3 gradient=scan.gradient-n*dot(scan.gradient,n);
    gradient*=min(1.0,0.85/max(length(gradient),0.00001));
    m.normal=normalize(n-gradient);
    cavity=mix(0.56,1.0,scan.ao);microVisibility=scan.shadow;
    if(uDetail<.999){
        SWMaterial old=swMaterial(P,n,family,footprint);
        m.color=mix(old.color,m.color,uDetail);m.rough=mix(old.rough,m.rough,uDetail);m.normal=normalize(mix(old.normal,m.normal,uDetail));
        cavity=mix(1.0,cavity,uDetail);microVisibility=mix(1.0,microVisibility,uDetail);
    }
    return m;
}
