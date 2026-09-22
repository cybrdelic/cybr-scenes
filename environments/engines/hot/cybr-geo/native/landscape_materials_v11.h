// World-scale material hierarchy. All spectra are authored reconstructed RGB.
// No screen-space overlays, depth tint, external beauty images or generated images.
#pragma once
V mixc(V a,V b,float t){return a*(1-t)+b*t;}
float gap2(float x,float y){
 int ix=int(std::floor(x)),iy=int(std::floor(y));float a=INF,b=INF;
 for(int j=-1;j<=1;j++)for(int i=-1;i<=1;i++){
  uint32_t h=hash3(ix+i,iy+j,0),q=h*1664525u+1013904223u;
  float dx=ix+i+.18f+.64f*(float(h)/4294967295.f)-x,dy=iy+j+.18f+.64f*(float(q)/4294967295.f)-y;
  float r=dx*dx+dy*dy;if(r<a){b=a;a=r;}else if(r<b)b=r;
 }return std::sqrt(b)-std::sqrt(a);
}
V filteredNoiseSlope(V p,V n,float frequency,float amplitude,float footprint){
 Frame frame(n);float filter=1/(1+sqr(footprint*frequency));float e=.021f;
 V at=p*frequency;
 float dx=(noise(at+frame.t*e)-noise(at-frame.t*e))/(2*e);
 float dy=(noise(at+frame.b*e)-noise(at-frame.b*e))/(2*e);
 return (frame.t*dx+frame.b*dy)*(amplitude*filter);
}
Surface shade(V p,V &n,int material,float footprint){
 Surface m;m.kind=material;V originalNormal=n;
 float q0=poolQ(p,0),q1=poolQ(p,1);int pi=q0<q1?0:1;
 float q=std::min(q0,q1),d=(q-1)*pools[pi].rx,level=pools[pi].level;
 float macro=fbm(p*.53f),meso=fbm(p*17.1f);
 float patch=smooth(-.27f,.26f,fbm(V(p.x*.92f+8,p.y*.81f+4,p.z*.71f)));
 float wet=(1-smooth(level+.015f,level+.105f+.014f*noise(p*4),p.z))*(1-smooth(1.14f,1.5f,q));
 float line=p.x-(3.28f+.27f*std::sin(p.y*.94f)+.13f*noise(p.y*3.7f,0));
 float drain=std::exp(-sqr(line/.32f))*std::exp(-std::pow((p.y+1.65f)/2.8f,4));
 wet=clamp(wet+.84f*drain);
 if(material==0||material==4){
  // A broad broken sinter apron, not an evenly colored pool collar.
  float fresh=std::exp(-sqr((d-.09f)/(.19f+.18f*patch)))*(.23f+.77f*patch);
  float apron=std::exp(-sqr((d-.62f)/1.25f))*smooth(-.18f,.32f,fbm(V(p.x*.78f-4,p.y*.71f+2,p.z)));
  float mineral=clamp(fresh+.85f*apron);
  float gravel=smooth(-.4f,.44f,fbm(V(p.x*.53f+3,p.y*.57f-9,0)));
  float clay=smooth(-.12f,.36f,fbm(p*.95f));
  V sand(.265f,.211f,.152f),fines(.165f,.143f,.115f),sinter(.64f,.628f,.565f);
  m.color=mixc(mixc(sand,fines,clay*.58f),sinter,mineral*.91f);
  float iron=std::exp(-sqr((d-.033f)/.15f))*(.09f+.59f*(1-patch));
  iron=clamp(iron+drain*.90f);
  m.color=mixc(m.color,V(.31f,.125f,.035f),iron*.85f);
  if(q<.99f){
   float bed=smooth(-.2f,.45f,fbm(V(p.x*1.5f,p.y*1.31f,p.z*2.3f)));
   m.color=mixc(V(.39f,.393f,.325f),V(.205f,.230f,.199f),bed*.55f);
   float oxide=smooth(.69f,.97f,q)*smooth(-.28f,.4f,fbm(p*3.4f));
   m.color=mixc(m.color,V(.26f,.158f,.066f),oxide*.50f);
   wet=0;
  }
  if(material==4)m.color=V(.66f,.651f,.58f)*(1+.14f*meso);
  float tiny=1/(1+sqr(footprint*350));
  m.color*=1+.055f*macro+.13f*meso+.11f*noise(p*311)*tiny;
  if(!photographicGrain.levels.empty()){
   float u=p.x*.917f+p.y*.399f,v=p.y*.917f-p.x*.399f;
   float grit=photographicGrain.sample(u,v,footprint,.68f);
   // Most brightness comes from the actual geometric relief, not baked shadow.
   m.color*=.71f+.29f*clamp(grit,.26f,1.90f);
  }
  float crackMask=smooth(1.07f,1.28f,q)*(1-smooth(1.75f,2.4f,q))*smooth(-.26f,.27f,noise(p.x*.47f,p.y*.51f));
  if(crackMask>.001f){
   float gap=gap2(p.x*6.3f+.26f*noise(p.x*3.1f,p.y*3.1f),p.y*6.3f+.26f*noise(p.x*3.1f+9,p.y*3.1f));
   m.color*=1-.31f*crackMask*std::exp(-sqr(gap/std::max(.045f,footprint*9)));
  }
  // Only unresolved height frequencies affect the shading normal. The coarser
  // support field is already geometry; subtract it to avoid double displacement.
  if(footprint<.026f){
   V delta=granularRelief.gradient(p.x,p.y,std::max(.0006f,footprint))-
           granularRelief.gradient(p.x,p.y,std::max(.017f,footprint));
   delta*=.26f+.74f*gravel;
   n=unit(n-V(delta.x,delta.y,0)*.74f);
  }
  n=unit(n-filteredNoiseSlope(p,n,163,.12f,footprint));
  m.rough=.88f*(1-wet)+.12f*wet;
 }else if(material==1||material==2){
  // Eliminate metre-wide pale/dark camouflage. Granite varies mostly at grain
  // and fracture scale; large colour modulation is restrained.
  V granite=material==1?V(.34f,.329f,.297f):V(.255f,.254f,.240f);
  m.color=granite*(1+.075f*macro+.16f*fbm(p*24));
  float mica=smooth(-.07f,.48f,noise(p*321+V(7,4,1)))/(1+sqr(footprint*260));
  float quartz=smooth(.12f,.61f,noise(p*173+V(12,3,8)))/(1+sqr(footprint*130));
  m.color=mixc(m.color,V(.055f,.053f,.049f),mica*.65f);
  m.color=mixc(m.color,V(.63f,.606f,.545f),quartz*.48f);
  float rind=smooth(.05f,.54f,fbm(p*3.8f))*.20f;
  m.color=mixc(m.color,V(.204f,.147f,.085f),rind);
  float dust=smooth(.5f,.94f,n.z)*smooth(-.1f,.32f,fbm(p*6.3f))*.22f;
  m.color=mixc(m.color,V(.30f,.237f,.166f),dust);
  float mineral=std::exp(-sqr((p.z-level-.036f)/.059f))*(1-smooth(1.08f,1.38f,q));
  m.color=mixc(m.color,V(.63f,.615f,.555f),mineral*.57f);
  m.rough=.84f*(1-wet)+.20f*wet;
  n=unit(n-filteredNoiseSlope(p,n,18.3f,.24f,footprint)-filteredNoiseSlope(p,n,75.f,.31f,footprint)-filteredNoiseSlope(p,n,279.f,.19f,footprint));
 }else if(material==5){
  float slope=smooth(.035f,.29f,1-n.z);
  float layer=smooth(-.55f,.73f,std::sin(p.z*.017f+p.x*.006f-p.y*.0015f+.6f*fbm(p*.011f)));
  float litho=smooth(-.27f,.44f,fbm(V(p.x*.0037f,p.y*.0049f,p.z*.0069f)));
  V talus(.241f,.195f,.152f),rock(.127f,.127f,.129f),granite(.250f,.226f,.194f);
  V face=mixc(rock,granite,.35f+.51f*layer);
  face=mixc(face,V(.248f,.164f,.098f),litho*.23f);
  m.color=mixc(talus,face,slope);
  m.color*=1+.21f*fbm(p*.034f)+.14f*fbm(p*.19f);
  float ramp=smooth(280,1150,p.y);m.color=m.color*ramp+V(.25f,.201f,.144f)*(1-ramp);
  n=unit(n-filteredNoiseSlope(p,n,.54f,.31f,footprint));m.rough=.94f;
 }else if(material==3){
  m.color=V(.45f,.315f,.134f)*(1+.25f*macro+.14f*noise(p*47));m.rough=.88f;
 }else if(material==8){
  m.color=V(.165f,.118f,.071f)*(1+.31f*fbm(p*19));m.rough=.94f;
 }else if(material==9){
  float dry=smooth(-.19f,.30f,noise(p*3.7f));
  m.color=mixc(V(.185f,.222f,.131f),V(.31f,.283f,.171f),dry*.52f);
  m.color*=1+.29f*noise(p*173);m.rough=.83f;
 }else m.color=V(.3f);
 // R2: new stochastic photographed microstructure on actual geometry.
 if(material==1||material==2)cybr_detail::apply(p,originalNormal,n,m.color,m.rough,footprint,.86f,.58f,.85f);
 if(material==0||material==4){
  cybr_detail::apply(p,originalNormal,n,m.color,m.rough,footprint,2.7f,.16f,.30f);
  float lamination=std::exp(-sqr((d-.10f)/.28f))*(.45f+.55f*patch);
  float pore=smooth(.10f,.57f,noise(p*53.f))/(1+sqr(footprint*53.f));
  m.color=mixc(m.color,V(.48f,.424f,.283f),lamination*pore*.20f);
 }
 if(dot(n,originalNormal)<.55f)n=unit(n+originalNormal);
 m.color*=1-.29f*wet;
 m.ior=(p.z<level&&q<1.1f)?1.48f/WATER_IOR:(wet>.2f?1.334f:1.48f);
 m.color=vmin(vmax(m.color,V(.003f)),V(.91f));
 return m;
}
