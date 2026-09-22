// GPL-2.0-only. Scene-specific, world-coordinate material fields.
// All reflectances are authored, not measured. No image textures or backplates.
#pragma once
V mixc(V a,V b,float t){return a*(1-t)+b*t;}
V noiseSlope(V p,V n,float f,float a,float footprint){
 Frame frame(n);float filt=1/(1+sqr(footprint*f)),e=.025f;V at=p*f;
 float dx=(noise(at+frame.t*e)-noise(at-frame.t*e))/(2*e);
 float dy=(noise(at+frame.b*e)-noise(at-frame.b*e))/(2*e);
 return (frame.t*dx+frame.b*dy)*(a*filt);
}
Surface shade(V p,V &n,int id,float footprint){
 Surface m;m.kind=id;m.rough=.75f;m.ior=1.48f;
 float coarse=noise(p*.72f),fine=noise(p*41.f),grain=1/(1+sqr(footprint*200));
 if(sceneStyle==0){
   float warp=p.z+.23f*std::sin(p.y*.54f)+.14f*std::sin(p.x*.9f+p.y*.19f);
   float lam=.5f+.5f*std::sin(warp*34+1.9f*noise(p*.92f));
   float band=smooth(-.45f,.63f,std::sin(warp*2.7f+.65f*noise(p*.6f)));
   if(id==0||id==4){
     m.color=mixc(V(.46f,.305f,.176f),V(.65f,.485f,.300f),.5f+.36f*coarse);
     m.color*=1+.075f*fine+.12f*noise(p*240)*grain;
     n=unit(n-noiseSlope(p,n,220,.10f,footprint));m.rough=.95f;
   }else{
     m.color=mixc(V(.32f,.155f,.078f),V(.55f,.31f,.168f),band*.77f);
     m.color*=.91f+.09f*lam+.06f*fine;
     float dark=smooth(.17f,.56f,noise(V(p.y*.41f,p.x*.77f,p.z*.22f)))*smooth(3.8f,8.4f,p.z);
     m.color=mixc(m.color,V(.105f,.061f,.039f),dark*.46f);
     float bleached=smooth(.23f,.50f,noise(p*.28f+V(3,4,8)))*smooth(.65f,.96f,n.z);
     m.color=mixc(m.color,V(.66f,.455f,.245f),bleached*.6f);
     n=unit(n-noiseSlope(p,n,55,.12f,footprint)-noiseSlope(p,n,310,.075f,footprint));
     m.rough=.87f;
   }
 }else if(sceneStyle==1){
   float wet=1-smooth(.08f,.7f+.16f*coarse,p.z);
   if(id==0||id==4){
     m.color=mixc(V(.025f,.028f,.029f),V(.057f,.061f,.064f),.5f+.4f*coarse);
     m.color*=1+.12f*fine+.14f*noise(p*340)*grain;
     m.rough=.83f-.52f*wet;n=unit(n-noiseSlope(p,n,180,.18f,footprint));
   }else if(id==3||id==9){
     m.color=V(.15f,.19f,.065f)*(1+.3f*fine);m.rough=.77f;
   }else{
     float mineral=smooth(.0f,.6f,noise(p*112))/(1+sqr(footprint*85));
     m.color=mixc(V(.043f,.051f,.061f),V(.080f,.091f,.102f),.44f+.25f*coarse);
     m.color*=1+.20f*fine+.16f*mineral;
     float rust=smooth(.14f,.52f,noise(p*3.8f))*smooth(.1f,.65f,noise(p*.5f));
     m.color=mixc(m.color,V(.233f,.134f,.060f),rust*.55f);
     float lichen=smooth(.10f,.49f,noise(p*5.2f+V(10,2,4)))*smooth(.15f,.53f,noise(p*1.4f))*smooth(.5f,.83f,n.z)*smooth(.9f,2.f,p.z);
     m.color=mixc(m.color,V(.38f,.31f,.105f),lichen*.83f);
     n=unit(n-noiseSlope(p,n,27,.14f,footprint)-noiseSlope(p,n,148,.20f,footprint));
     m.rough=.78f-.57f*wet;
   }
   m.color*=1-.32f*wet;m.ior=wet>.3f?1.334f:1.5f;
 }else{
   float damp=1-smooth(.1f,.8f,p.z);
   if(id==0||id==4){
     m.color=mixc(V(.064f,.039f,.017f),V(.14f,.087f,.036f),.5f+.45f*coarse);
     float green=smooth(-.24f,.39f,noise(p*3.1f)+.20f*noise(p*17))*smooth(.1f,.53f,p.z);
     m.color=mixc(m.color,V(.047f,.099f,.009f),green*.94f);
     m.color*=1+.18f*fine;
     n=unit(n-noiseSlope(p,n,140,.19f,footprint));m.rough=.9f-.48f*damp;
   }else if(id==1||id==2||id==5){
     m.color=mixc(V(.094f,.111f,.105f),V(.170f,.184f,.163f),.55f+.3f*coarse);
     m.color*=1+.15f*fine;
     float moss=smooth(.19f,.74f,n.z)*smooth(.015f,.38f,noise(p*2.9f)+.19f)*smooth(.0f,.23f,p.z);
     m.color=mixc(m.color,V(.042f,.086f,.009f)*(1+.4f*fine),moss*.98f);
     n=unit(n-noiseSlope(p,n,22,.19f,footprint)-noiseSlope(p,n,160,.18f,footprint));m.rough=.8f-.44f*damp;
   }else if(id==8){
     m.color=mixc(V(.051f,.027f,.012f),V(.167f,.111f,.058f),.5f+.3f*noise(p*7));
     m.color*=.8f+.25f*smooth(-.8f,.4f,std::sin(p.x*122+p.y*39+.4f*noise(p*8)));
     n=unit(n-noiseSlope(p,n,79,.21f,footprint));m.rough=.94f;
   }else if(id==9){
     m.color=mixc(V(.035f,.105f,.009f),V(.136f,.232f,.029f),.5f+.38f*noise(p*5));
     m.color*=1+.14f*fine;m.rough=.55f;
   }else if(id==10){
     m.color=mixc(V(.029f,.063f,.007f),V(.122f,.192f,.022f),.5f+.35f*noise(p*18));
     m.color*=1+.19f*noise(p*200)*grain;m.rough=.92f;n=unit(n-noiseSlope(p,n,230,.18f,footprint));
   }else if(id==11){
     m.color=mixc(V(.13f,.051f,.009f),V(.26f,.151f,.036f),.5f+.43f*noise(p*3));m.rough=.86f;
   }else if(id==12){
     float rings=.5f+.5f*std::sin(p.x*65+p.z*85+.5f*noise(p*8));
     m.color=mixc(V(.19f,.094f,.028f),V(.34f,.225f,.105f),rings);m.rough=.85f;
   }else {m.color=V(.2f);}
   if(id<=5)m.color*=1-.18f*damp;
 }
 m.color=vmin(vmax(m.color,V(.002f)),V(.92f));
 return m;
}
