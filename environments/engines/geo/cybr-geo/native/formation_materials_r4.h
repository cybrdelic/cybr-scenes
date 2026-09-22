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

// R4 materials: formation-specific color/roughness/normal scales. Authored values.
float coverage(V p,float coarse,float fine,float threshold){
 return smooth(threshold-.08f,threshold+.08f,noise(p*coarse)+.38f*noise(p*fine));
}
Surface shade(V p,V &n,int id,float footprint){
 Surface m;m.kind=id;m.ior=1.49f;m.rough=.78f;V geometric=n;
 float wet=0,grainWeight=.18f,reliefWeight=.16f;
 float macro=noise(p*.83f),meso=noise(p*13.1f);
 float tiny=1.f/(1.f+sqr(footprint*190.f));
 if(sceneStyle==0){
  if(id==0||id==4){
   float gravel=coverage(p,4.8f,77.f,.06f);
   m.color=mixc(V(.245f,.170f,.112f),V(.42f,.316f,.215f),.60f+.17f*macro);
   m.color*=1+.10f*meso+.13f*noise(p*173)*tiny;
   m.color=mixc(m.color,V(.18f,.126f,.079f),gravel*.12f);
   m.rough=.94f;grainWeight=.44f;reliefWeight=.52f;
  }else{
   // Irregular lithologic blocks rather than equally spaced decorative stripes.
   float bed=p.z+.035f*p.y+.13f*noise(p.y*.24f+(p.x>0?2.f:-2.f),1.f);
   float lith=noise(V(p.y*.22f,bed*1.7f,p.x*.10f));
   float lamina=.5f+.5f*std::sin(bed*83.f+2.1f*noise(V(p.y*1.7f,bed*3.1f,0)));
   m.color=mixc(V(.21f,.100f,.050f),V(.46f,.282f,.142f),.60f+.50f*lith);
   m.color*=.94f+.055f*lamina+.055f*meso;
   // Desert varnish forms interrupted streaks; lighter scabs interrupt the patina.
   float varnish=coverage(V(p.y*1.15f,p.z*.12f,p.x*.10f),1.8f,11.f,.05f);
   varnish*=smooth(.8f,3.3f,p.z)*(1-smooth(.25f,.75f,n.z));
   float scab=coverage(p,8.5f,64.f,.24f);
   varnish*=1-.70f*scab;
   m.color=mixc(m.color,V(.065f,.046f,.034f),varnish*.78f);
   float pale=coverage(V(p.y,p.z*3,p.x*.3f),.7f,5.f,.30f);
   m.color=mixc(m.color,V(.49f,.370f,.242f),pale*.35f);
   float dust=smooth(.42f,.93f,n.z)*(.55f+.30f*noise(p*3));
   m.color=mixc(m.color,V(.38f,.279f,.180f),dust*.6f);
   if(id==2||id==14){m.color=mixc(m.color,V(.35f,.235f,.145f),.40f);varnish*=.25f;}
   m.rough=.79f-.13f*varnish;grainWeight=.40f;reliefWeight=.27f;
   n=unit(n-noiseSlope(p,n,90,.13f,footprint));
  }
 }else if(sceneStyle==1){
  wet=1-smooth(.04f,.72f+.12f*macro,p.z);
  if(id==0||id==4){
   m.color=mixc(V(.023f,.025f,.028f),V(.065f,.060f,.055f),.52f+.22f*macro);
   m.rough=.88f-.55f*wet;grainWeight=.44f;reliefWeight=.45f;
  }else if(id==14){m.color=V(.48f,.446f,.356f)*(1+.13f*meso);m.rough=.8f;
  }else if(id==15){m.color=V(.041f,.065f,.018f)*(1+.20f*meso);m.rough=.42f;
  }else{
   m.color=mixc(V(.025f,.031f,.037f),V(.064f,.070f,.073f),.58f+.3f*macro);
   m.color*=1+.20f*meso+.09f*noise(p*171)*tiny;
   float lichen=coverage(p,9.4f,91.f,.24f)*smooth(.50f,1.65f,p.z);
   lichen*=.48f+.52f*smooth(-.35f,.65f,n.z);
   float fresh=coverage(p,1.5f,4.9f,.31f);
   lichen*=1-.65f*fresh;
   m.color=mixc(m.color,V(.145f,.154f,.128f)*(1+.16f*noise(p*141)*tiny),lichen*.64f);
   float iron=coverage(V(p.x,p.y,p.z*.26f),2.7f,14.f,.24f);
   m.color=mixc(m.color,V(.134f,.080f,.032f),iron*.26f*(1-wet));
   float algae=coverage(p,5.8f,33.f,.12f)*(1-smooth(.27f,.79f,p.z));
   m.color=mixc(m.color,V(.029f,.049f,.007f),algae*.49f);
   if(id==13)m.color=mixc(m.color,V(.091f,.093f,.088f),.26f);
   m.rough=.79f-.56f*wet;grainWeight=.37f;reliefWeight=.20f;
   n=unit(n-noiseSlope(p,n,58,.115f,footprint));
  }
  m.color*=1-.32f*wet;m.ior=wet>.30f?1.334f:1.52f;
 }else{
  wet=1-smooth(.04f,.49f,p.z);
  if(id==0||id==4){
   float moss=coverage(p,3.8f,35.f,.19f)*smooth(.15f,.38f,p.z);
   m.color=mixc(V(.023f,.012f,.006f),V(.083f,.048f,.024f),.56f+.25f*macro);
   m.color=mixc(m.color,V(.026f,.060f,.009f)*(1+.17f*meso),moss*.83f);
   m.rough=.9f-.43f*wet;grainWeight=.36f;reliefWeight=.37f;
  }else if(id==1||id==2||id==5){
   m.color=mixc(V(.059f,.064f,.059f),V(.18f,.176f,.157f),.47f+.4f*macro);
   m.color*=1+.17f*meso;
   float quartz=coverage(p,43.f,193.f,.23f);m.color=mixc(m.color,V(.27f,.275f,.254f),quartz*.30f*tiny);
   float moss=coverage(p,4.1f,57.f,.0f)*smooth(-.12f,.72f,n.z)*smooth(.08f,.30f,p.z);
   m.color=mixc(m.color,V(.024f,.057f,.006f)*(1+.35f*meso),moss*.97f);
   m.rough=.83f-.45f*wet;grainWeight=.35f;reliefWeight=.19f;
   n=unit(n-noiseSlope(p,n,95,.11f,footprint));
  }else if(id==8||id==14){
   float plate=coverage(V(p.x,p.y,p.z*.18f),18.f,57.f,.05f);
   m.color=mixc(V(.031f,.021f,.014f),V(.125f,.094f,.061f),plate);
   m.color*=1+.14f*meso;
   if(id==14){float peel=coverage(V(p.x,p.y,p.z*.26f),15.f,83.f,.10f);m.color=mixc(V(.29f,.295f,.258f),V(.042f,.038f,.029f),peel*.78f);}
   float moss=coverage(p,3.9f,55.f,.08f)*(1-smooth(.60f,2.5f,p.z));
   m.color=mixc(m.color,V(.022f,.049f,.006f),moss*.86f);
   m.rough=.85f;grainWeight=.31f;reliefWeight=.26f;
   n=unit(n-noiseSlope(V(p.x,p.y,p.z*.25f),n,72,.16f,footprint));
  }else if(id==9||id==3||id==13){
   m.color=mixc(V(.020f,.079f,.006f),V(.098f,.195f,.015f),.53f+.40f*noise(p*8));
   if(id==13)m.color=mixc(m.color,V(.20f,.112f,.022f),.79f);
   m.rough=.42f+.14f*(.5f+.5f*noise(p*9));m.ior=1.46f;grainWeight=.025f;reliefWeight=0;
  }else if(id==10){m.color=V(.026f,.073f,.007f)*(1+.32f*meso);m.rough=.87f;grainWeight=.08f;reliefWeight=.04f;
  }else if(id==11){
   float age=noise(p*18.f);m.color=mixc(V(.029f,.011f,.004f),V(.22f,.098f,.027f),.48f+.52f*age);
   m.color*=1+.20f*noise(p*161)*tiny;m.rough=.76f;grainWeight=.19f;reliefWeight=.03f;
  }else if(id==12){m.color=V(.19f,.098f,.038f)*(1+.24f*meso);m.rough=.81f;grainWeight=.3f;reliefWeight=.09f;
  }else{m.color=V(.15f);grainWeight=.12f;}
  if(id<6)m.color*=1-.23f*wet;
 }
 if(grainWeight>0){float g=projectedGrain(p,n,footprint,.46f);m.color*=1+grainWeight*(g-1);}
 if(reliefWeight>0)n=unit(n-projectedRelief(p,n,footprint,reliefWeight));
 if(dot(n,geometric)<.60f)n=unit(n+geometric);
 m.color=vmin(vmax(m.color,V(.002f)),V(.87f));m.rough=clamp(m.rough,.09f,.98f);return m;
}
