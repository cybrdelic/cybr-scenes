precision highp float;
precision highp int;
uniform vec3 uEye;
uniform vec3 uSun;
uniform vec3 uSolar;
uniform vec3 uWhite;
uniform float uExposure;
uniform int uMode;
uniform mat3 uRGBToAnchors;
uniform mat3 uSolarResponse;
in vec3 vWorld;
in vec3 vNormal;
in vec3 vGiR;
in vec3 vGiG;
in vec3 vGiB;
in vec2 vSurface;
out vec4 outColor;
const float PI=3.141592653589793;
// SPDX-License-Identifier: GPL-2.0-only
// Shared GLSL / C++ material field. P is in metres, N is a GEOMETRIC normal.
// All stochastic coordinates are isotropic 3D. No UVs, chart indices, normal-
// dependent projection or camera-space coordinates enter color/height.
// Footprint controls bandwidth only; it never changes the feature locations.
struct SWNoise { float value; vec3 gradient; };
struct SWMaterial { vec3 color; vec3 normal; float rough; };
uint swHash(int x, int y, int z) {
    uint h = uint(x)*0x8da6b343u ^ uint(y)*0xd8163841u ^ uint(z)*0xcb1ab31fu ^ 0x9e3779b9u;
    h ^= h >> 16; h *= 0x7feb352du; h ^= h >> 15; h *= 0x846ca68bu; h ^= h >> 16;
    return h;
}
float swSaturate(float x) { return min(1.0,max(0.0,x)); }
float swSmooth(float a,float b,float x) { float t=swSaturate((x-a)/(b-a)); return t*t*(3.0-2.0*t); }
SWNoise swNoise(vec3 p) {
    int ix=int(floor(p.x)), iy=int(floor(p.y)), iz=int(floor(p.z));
    vec3 f=p-vec3(float(ix),float(iy),float(iz));
    vec3 t=f*f*f*(f*(f*6.0-vec3(15.0))+vec3(10.0));
    vec3 dt=30.0*f*f*(f-vec3(1.0))*(f-vec3(1.0));
    SWNoise n; n.value=0.0; n.gradient=vec3(0.0);
    for(int a=0;a<2;a++) for(int b=0;b<2;b++) for(int c=0;c<2;c++) {
        float v=float(swHash(ix+a,iy+b,iz+c)>>8)*(1.0/8388608.0)-1.0;
        float x=a==1?t.x:1.0-t.x, y=b==1?t.y:1.0-t.y, z=c==1?t.z:1.0-t.z;
        float dx=a==1?dt.x:-dt.x, dy=b==1?dt.y:-dt.y, dz=c==1?dt.z:-dt.z;
        n.value+=v*x*y*z;
        n.gradient+=v*vec3(dx*y*z,x*dy*z,x*y*dz);
    }
    return n;
}
// Fade unresolved octaves to their analytic zero mean. The conservative largest
// singular screen footprint is provided by the fragment shader. The path tracer
// supplies its native ray footprint. Derivatives are never evaluated in branches.
SWNoise swBand(vec3 p, float frequency, float footprint, vec3 offset) {
    float weight=1.0-swSmooth(0.20,0.65,frequency*footprint);
    SWNoise n; n.value=0.0; n.gradient=vec3(0.0);
    if(weight>0.00001) {
        // A fixed orthonormal rotation avoids aligning the value-noise lattice
        // with horizontal/vertical rock faces. It changes no metric scale.
        vec3 q=vec3(.8*p.y+.6*p.z,-.8*p.x+.36*p.y-.48*p.z,-.6*p.x-.48*p.y+.64*p.z);
        n=swNoise(q*frequency+offset);
        vec3 gradient=n.gradient;
        n.gradient=vec3(-.8*gradient.y-.6*gradient.z,
            .8*gradient.x+.36*gradient.y-.48*gradient.z,
            .6*gradient.x-.48*gradient.y+.64*gradient.z);
        n.value*=weight; n.gradient*=weight*frequency;
    }
    return n;
}
SWMaterial swMaterial(vec3 p,vec3 geometric,int family,float footprint) {
    vec3 n=normalize(geometric);
    SWNoise broad=swBand(p,.37,footprint,vec3(13.1,-8.4,2.3));
    SWNoise mottled=swBand(p,1.65,footprint,vec3(-17.2,3.8,29.1));
    SWNoise broken=swBand(p,5.8,footprint,vec3(4.9,27.7,-11.8));
    SWNoise pore=swBand(p,23.0,footprint,vec3(-5.7,-14.2,35.6));
    SWNoise grain=swBand(p,92.0,footprint,vec3(31.2,-3.1,7.6));
    SWNoise fine=swBand(p,368.0,footprint,vec3(-12.7,51.2,16.5));
    float macro=.65*broad.value+.25*mottled.value+.10*broken.value;
    float oxidation=swSmooth(-.04,.28,.55*broad.value+.35*mottled.value+.22*broken.value);
    float abrasion=swSmooth(-.04,.42,broken.value*.7+pore.value*.22);
    SWMaterial m;
    if(family==0 || family==4) {
        // Alluvial sediment: the same metre scale on level and inclined ground.
        m.color=mix(vec3(.282,.200,.132),vec3(.417,.314,.216),.56+.30*macro);
        m.color*=1.0+.10*broken.value+.12*pore.value+.20*grain.value+.10*fine.value;
        m.rough=.92+.025*broken.value;
    } else {
        m.color=mix(vec3(.245,.134,.063),vec3(.475,.305,.167),.61+.45*macro);
        float varnish=oxidation*(1.0-.70*abrasion);
        // Mottled, finite patches; no p.z*.12 vertical smearing or per-wall axes.
        m.color=mix(m.color,vec3(.108,.073,.045),.58*varnish);
        m.color*=1.0+.16*broken.value+.12*pore.value+.21*grain.value+.07*fine.value;
        if(family==2 || family==14) m.color=mix(m.color,vec3(.362,.243,.143),.20);
        m.rough=.84-.075*varnish+.020*pore.value;
    }
    vec3 slope=broken.gradient*.0035+pore.gradient*.0025+grain.gradient*.00085+fine.gradient*.00012;
    if(family==0 || family==4) slope*=1.12;
    // True scalar-height gradient projected into the tangent plane. This avoids
    // tangent handedness/projection seams and cannot rotate with the camera.
    slope=slope-n*dot(n,slope);
    float magnitude=length(slope);
    slope*=min(1.0,.22/max(magnitude,.000001));
    m.normal=normalize(n-slope);
    m.color=clamp(m.color,vec3(.008),vec3(.82));
    m.rough=clamp(m.rough,.65,.98);
    return m;
}

float fresnel(float c){
 const float eta=1.49;
 float st2=(1.0-c*c)/(eta*eta),ct=sqrt(max(0.0,1.0-st2));
 float rs=(c-eta*ct)/(c+eta*ct),rp=(eta*c-ct)/(eta*c+ct);
 return .5*(rs*rs+rp*rp);
}
float ggxD(float nh,float a){float a2=a*a;float d=nh*nh*(a2-1.0)+1.0;return a2/(PI*d*d);}
float smithG1(float c,float a){return c>0.0?2.0*c/(c+sqrt(a*a+(1.0-a*a)*c*c)):0.0;}
vec3 encodeNative(vec3 rgb){
 vec3 a=max(rgb/uWhite*uExposure,vec3(0.0));
 a=a*a/(a+vec3(.035));float peak=max(max(a.r,a.g),max(a.b,.0000001));
 a*=(1.0-exp(-peak))/peak;
 a=clamp(a,0.0,1.0);
 return mix(12.92*a,1.055*pow(a,vec3(1.0/2.4))-.055,step(vec3(.0031308),a));
}
float screenFootprint(vec3 dx,vec3 dy){
 float a=dot(dx,dx),b=dot(dx,dy),c=dot(dy,dy);
 return sqrt(max(.5*(a+c+sqrt(max(0.0,(a-c)*(a-c)+4.0*b*b))),1e-12));
}
vec3 encodeAlbedo(vec3 a){return mix(12.92*a,1.055*pow(max(a,0.0),vec3(1.0/2.4))-.055,step(vec3(.0031308),a));}
void main(){
 vec3 dx=dFdx(vWorld),dy=dFdy(vWorld);
 float footprint=screenFootprint(dx,dy);
 vec3 geometric=normalize(vNormal),V=normalize(uEye-vWorld),L=uSun;
 vec3 Ng=normalize(cross(dx,dy));
 if(dot(Ng,V)<0.0)Ng=-Ng;
 if(dot(geometric,Ng)<0.0)geometric=-geometric;
 if(dot(geometric,Ng)<.1||dot(geometric,V)<.01)geometric=Ng;
 int family=int(floor(vSurface.y*255.0+.5));
 SWMaterial material=swMaterial(vWorld,geometric,family,footprint);
 vec3 N=material.normal;
 if(dot(N,Ng)<.1||dot(N,V)<.01)N=geometric;
 float nv=max(dot(N,V),.0001),nl=max(dot(N,L),0.0);
 float rough=material.rough,visibility=clamp(vSurface.x,0.0,1.0);
 vec3 anchors=clamp(uRGBToAnchors*material.color,vec3(0.0),vec3(.985));
 vec3 H=normalize(V+L);float fr=fresnel(clamp(dot(V,H),0.0,1.0));
 float s2=pow(rough*.52,2.0),A=1.0-s2/(2.0*(s2+.33)),B=.45*s2/(s2+.09);
 float vi=sqrt(max(0.0,1.0-nv*nv)),li=sqrt(max(0.0,1.0-nl*nl));
 float cosPhi=vi*li>.00000001?max(0.0,(dot(V,L)-nv*nl)/(vi*li)):0.0;
 float oren=A+B*cosPhi*max(vi,li)*min(vi/max(nv,.00001),li/max(nl,.00001));
 float alpha=max(.018,rough*rough);
 vec3 direct=(uSolarResponse*anchors)*(1.0-fr)*oren*nl*visibility;
 if(nl>0.0)direct+=uSolar*(visibility*fr*ggxD(max(dot(N,H),0.0),alpha)*smithG1(nv,alpha)*smithG1(nl,alpha)/(4.0*nv));
 const float F0=(.49*.49)/(2.49*2.49);
 vec3 indirect=max((vGiR*anchors.x+vGiG*anchors.y+vGiB*anchors.z)*((1.0-F0)*A),0.0);
 vec3 radiance=direct+indirect;
 if(uMode==1)radiance=direct;
 else if(uMode==2)radiance=indirect;
 else if(uMode==3){outColor=vec4(N*.5+.5,1.0);return;}
 else if(uMode==4){outColor=vec4(vec3(visibility),1.0);return;}
 else if(uMode==5){outColor=vec4(encodeAlbedo(material.color),1.0);return;}
 else if(uMode==6){
  // 25-cm volumetric checker: no UVs or chart-dependent coordinates.
  vec3 q=vWorld*4.0,w=max(fwidth(q),vec3(.0001));
  vec3 integral=2.0*(abs(fract((q-.5*w)*.5)-.5)-abs(fract((q+.5*w)*.5)-.5))/w;
  float pattern=.5-.5*integral.x*integral.y*integral.z;
  outColor=vec4(mix(vec3(.15),vec3(.85),pattern),1.0);return;
 }
 else if(uMode==7){outColor=vec4(vec3(rough),1.0);return;}
 else if(uMode==8){outColor=vec4(geometric*.5+.5,1.0);return;}
 outColor=vec4(encodeNative(radiance),1.0);
}
