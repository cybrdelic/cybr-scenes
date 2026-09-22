// SPDX-License-Identifier: GPL-2.0-only
// Active cross-scene formation materials. Metres, linear RGB reflectance anchors.
// Existing CC0 grayscale input + V11 mip-filtered granular relief are actually used.
// Spectra and mesorelief are authored, not spectrometer or photogrammetry measurements.
#pragma once
V mixc(V a,V b,float t){return a*(1-t)+b*t;}
V noiseSlope(V p,V n,float f,float a,float footprint){
 Frame frame(n);float e=.023f,filter=1.f/(1.f+sqr(footprint*f));V q=p*f;
 float dx=(noise(q+frame.t*e)-noise(q-frame.t*e))/(2*e),dy=(noise(q+frame.b*e)-noise(q-frame.b*e))/(2*e);
 return (frame.t*dx+frame.b*dy)*(a*filter);
}
float projectedGrain(V p,V n,float footprint,float width){
 if(photographicGrain.levels.empty())return 1;
 V w(sqr(sqr(n.x)),sqr(sqr(n.y)),sqr(sqr(n.z)));w=w/(w.x+w.y+w.z+1e-8f);
 float result=0;
 if(w.x>.005f)result+=w.x*photographicGrain.sample(p.y+.31f,p.z+.17f,footprint,width);
 if(w.y>.005f)result+=w.y*photographicGrain.sample(p.x-.26f,p.z+.77f,footprint,width);
 if(w.z>.005f)result+=w.z*photographicGrain.sample(p.x+.21f,p.y-.15f,footprint,width);
 return clamp(result,.23f,2.2f);
}
V projectedRelief(V p,V n,float footprint,float amplitude){
 if(granularRelief.levels.empty()||footprint>=.016f)return V(0);
 float f=std::max(.0007f,footprint),support=std::max(.016f,f);
 // Subtract the coarse field: unresolved frequencies alone perturb the normal.
 V w((sqr(n.x)*sqr(sqr(n.x))),(sqr(n.y)*sqr(sqr(n.y))),(sqr(n.z)*sqr(sqr(n.z))));w=w/(w.x+w.y+w.z+1e-8f);V g(0);
 if(w.x>.05f){V d=granularRelief.gradient(p.y,p.z,f)-granularRelief.gradient(p.y,p.z,support);g+=V(0,d.x,d.y)*w.x;}
 if(w.y>.05f){V d=granularRelief.gradient(p.x,p.z,f)-granularRelief.gradient(p.x,p.z,support);g+=V(d.x,0,d.y)*w.y;}
 if(w.z>.05f){V d=granularRelief.gradient(p.x,p.y,f)-granularRelief.gradient(p.x,p.y,support);g+=V(d.x,d.y,0)*w.z;}
 g=g-n*dot(g,n);float magnitude=len(g);return g*(amplitude/(1+1.8f*magnitude));
}
float sedimentCracks(float x,float y,float footprint){
 float wx=x*8+.22f*noise(V(x*2,y*2,0)),wy=y*8+.22f*noise(V(x*2+8,y*2,0));
 int ix=int(std::floor(wx)),iy=int(std::floor(wy));float first=INF,second=INF;
 for(int j=-1;j<=1;j++)for(int i=-1;i<=1;i++){
  uint32_t h=hash3(ix+i,iy+j,4);float u=float(h)/4294967295.f,v=float(h*1664525u+1013904223u)/4294967295.f;
  float dx=ix+i+.18f+.64f*u-wx,dy=iy+j+.18f+.64f*v-wy,d=dx*dx+dy*dy;
  if(d<first){second=first;first=d;}else if(d<second)second=d;
 }
 float gap=std::sqrt(second)-std::sqrt(first);return std::exp(-sqr(gap/std::max(.023f,footprint*8)))/(1+sqr(footprint*40));
}
Surface shade(V p,V &n,int id,float footprint){
 Surface m;m.kind=id;m.ior=1.49f;m.rough=.84f;V geometric=n;
 float macro=noise(p*.66f),meso=noise(p*17.4f),tiny=1/(1+sqr(footprint*240));
 float wet=0,grainWeight=.13f,reliefWeight=.42f;bool organic=false;
 if(sceneStyle==0){
  float bed=p.z+.22f*std::sin(p.y*.33f)+.055f*p.y;
  float layers=.5f+.5f*std::sin(bed*3.6f+.7f*noise(V(p.y*.6f,p.z*.4f,0)));
  float lamina=.5f+.5f*std::sin(bed*49.f+.38f*noise(V(p.y*5,p.z*2,0)))/(1+sqr(footprint*49.f));
  float crossbed=.5f+.5f*std::sin((bed+.10f*std::sin(p.y*.71f))*113.f+p.y*1.2f)/(1+sqr(footprint*114.f));
  if(id==0||id==4){
   float wash=std::exp(-sqr((p.x-(.40f*std::sin(p.y*.21f)+1.35f*std::exp(-sqr((p.y-18)/6.8f))-.9f*std::exp(-sqr((p.y-30)/4.8f))))/.9f));
   m.color=mixc(V(.34f,.225f,.125f),V(.50f,.360f,.222f),.45f+.28f*macro);
   m.color=mixc(m.color,V(.29f,.222f,.151f),wash*.20f);m.color*=1+.04f*meso+.065f*noise(p*277)*tiny;
   float compact=smooth(.19f,.48f,noise(p*.92f+V(4,0,0)));
   if(compact>.03f)m.color*=1-.15f*compact*sedimentCracks(p.x,p.y,footprint);
   m.rough=.96f;grainWeight=.25f;reliefWeight=.70f;
  }else{
   m.color=mixc(V(.335f,.145f,.065f),V(.475f,.255f,.134f),.25f+.60f*layers);
   m.color*=.89f+.085f*lamina+.035f*crossbed+.028f*meso;
   float pale=smooth(.22f,.68f,noise(V(p.y*.5f,p.z*1.9f,p.x*.1f)));
   m.color=mixc(m.color,V(.52f,.35f,.21f),pale*.31f);
   float varnish=smooth(.05f,.48f,noise(V(p.y*2.8f,p.z*.15f,p.x*.21f)))*smooth(1.7f,7.2f,p.z);
   m.color=mixc(m.color,V(.105f,.065f,.042f),varnish*.40f);
   float dust=smooth(.22f,.88f,n.z)*(.50f+.5f*noise(p*2.4f));m.color=mixc(m.color,V(.50f,.355f,.225f),dust*.63f);
   if(id==2){m.color=mixc(m.color,V(.39f,.235f,.128f),.38f);reliefWeight=.35f;}
   if(id==14)m.color=mixc(m.color,V(.51f,.355f,.22f),.70f);
   m.rough=.88f-.09f*varnish;n=unit(n-noiseSlope(p,n,67,.13f,footprint));grainWeight=.27f;
  }
 }else if(sceneStyle==1){
  float salt=smooth(.55f,1.45f,p.z)*(1-smooth(2.2f,3.8f,p.z));wet=1-smooth(.03f,.65f+.12f*macro,p.z);
  if(id==0||id==4){
   m.color=mixc(V(.035f,.038f,.040f),V(.070f,.073f,.075f),.44f+.34f*macro);m.color*=1+.10f*meso;
   m.rough=.94f-.64f*wet;grainWeight=.34f;reliefWeight=.85f;
  }else if(id==14){m.color=V(.46f,.447f,.389f)*(1+.15f*meso);m.rough=.91f;grainWeight=.07f;
  }else if(id==15){m.color=mixc(V(.029f,.050f,.006f),V(.091f,.099f,.013f),.5f+.3f*meso);m.rough=.34f;
  }else{
   m.color=mixc(V(.025f,.032f,.040f),V(.057f,.066f,.079f),.37f+.30f*macro);
   float vein=smooth(.15f,.52f,noise(V(p.x*73,p.y*73,p.z*8)))*tiny;m.color*=1+.09f*meso+.13f*vein;
   float oxidation=smooth(.15f,.50f,noise(V(p.x*2.3f,p.y*3.1f,p.z*.42f)+V(3,4,6)));
   m.color=mixc(m.color,V(.145f,.095f,.051f),oxidation*.14f);
   float lichen=smooth(.15f,.51f,noise(p*4.6f))*smooth(.26f,.68f,n.z)*smooth(.7f,2.5f,p.z);
   m.color=mixc(m.color,V(.31f,.28f,.13f),lichen*.18f);m.color=mixc(m.color,V(.155f,.164f,.151f),salt*.10f);
   if(id==13)m.color=mixc(m.color,V(.074f,.081f,.085f),.26f);
   if(id==2){m.color*=1.04f;reliefWeight=.14f;}
   m.rough=.83f-.51f*wet;reliefWeight=.18f;n=unit(n-noiseSlope(p,n,96,.065f,footprint));grainWeight=.29f;
  }
  m.color*=1-.36f*wet;m.ior=wet>.25f?1.334f:1.52f;
 }else{
  wet=1-smooth(.02f,.54f,p.z);
  if(id==0||id==4){
   float duff=smooth(-.15f,.35f,noise(p*1.7f));m.color=mixc(V(.061f,.032f,.013f),V(.12f,.070f,.026f),duff);
   float moss=smooth(.12f,.45f,noise(p*2.6f)+.22f*noise(p*19))*smooth(.14f,.44f,p.z);
   m.color=mixc(m.color,V(.029f,.068f,.008f),moss*.85f);m.color*=1+.13f*meso;
   m.rough=.94f-.54f*wet;grainWeight=.35f;reliefWeight=.72f;
  }else if(id==1||id==2||id==5){
   m.color=mixc(V(.10f,.107f,.092f),V(.20f,.205f,.171f),.48f+.25f*macro);
   float quartz=smooth(.28f,.59f,noise(p*190))*tiny;m.color*=1+.12f*meso+.14f*quartz;
   float moss=smooth(.05f,.64f,n.z)*smooth(-.11f,.23f,noise(p*2.7f))*smooth(.03f,.3f,p.z);
   m.color=mixc(m.color,V(.027f,.068f,.007f)*(1+.36f*noise(p*58)),moss*.97f);
   m.rough=.84f-.5f*wet;n=unit(n-noiseSlope(p,n,69,.14f,footprint));grainWeight=.19f;reliefWeight=.36f;
  }else if(id==8||id==14){
   organic=true;
   float groove=.5f+.5f*std::sin(p.x*174+p.y*109+1.1f*noise(V(p.x*11,p.y*11,p.z*1.8f)));
   float plates=smooth(-.2f,.45f,noise(V(p.x*22,p.y*22,p.z*5.6f)));
   m.color=mixc(V(.059f,.029f,.012f),V(.19f,.125f,.067f),plates);m.color*=.73f+.31f*groove;
   if(id==14){float scar=smooth(.22f,.53f,noise(V(p.x*39,p.y*39,p.z*7)));m.color=mixc(V(.44f,.43f,.355f),V(.070f,.060f,.044f),scar*.85f);}
   float bryo=smooth(.03f,.43f,noise(p*3.1f))*(1-smooth(.5f,1.5f,p.z));m.color=mixc(m.color,V(.030f,.064f,.008f),bryo*.78f);
   m.rough=.94f;n=unit(n-noiseSlope(V(p.x,p.y,p.z*.22f),n,83,.22f,footprint));grainWeight=.12f;reliefWeight=.22f;
  }else if(id==9||id==13){
   organic=true;float variation=noise(p*11.2f);
   m.color=mixc(V(.032f,.095f,.009f),V(.115f,.215f,.027f),.50f+.34f*variation);m.color*=1+.055f*noise(p*140)*tiny;
   if(id==13)m.color=mixc(m.color,V(.29f,.18f,.039f),.77f);
   m.rough=.66f;grainWeight=0;reliefWeight=0;
  }else if(id==10){organic=true;m.color=V(.037f,.090f,.008f)*(1+.32f*meso);m.rough=.96f;grainWeight=.08f;reliefWeight=.06f;
  }else if(id==11){
   organic=true;m.color=mixc(V(.073f,.026f,.005f),V(.245f,.129f,.026f),.5f+.43f*noise(p*8));
   m.color*=1+.11f*noise(p*149)*tiny;m.rough=.88f;grainWeight=.09f;reliefWeight=.03f;
  }else if(id==12){
   organic=true;float rings=.5f+.5f*std::sin(p.x*150+p.z*205+.5f*noise(p*12));
   m.color=mixc(V(.18f,.079f,.019f),V(.37f,.221f,.091f),rings);m.rough=.9f;grainWeight=.15f;reliefWeight=.05f;
  }else{m.color=V(.2f);grainWeight=.12f;}
  if(!organic)m.color*=1-.23f*wet;
 }
 if(grainWeight>0){float g=projectedGrain(p,n,footprint,.68f);m.color*=1+grainWeight*(g-1);}
 if(reliefWeight>0)n=unit(n-projectedRelief(p,n,footprint,reliefWeight));
 if(dot(n,geometric)<.48f)n=unit(n+geometric);
 m.color=vmin(vmax(m.color,V(.003f)),V(.92f));m.rough=clamp(m.rough,.08f,.98f);return m;
}
