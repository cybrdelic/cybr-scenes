// V9 correlated substrate, evaporite, wetting, mineral grain and fractured rock.
// Authored material controls. These are not measured mineral reflectance spectra.
#pragma once
float cellGap2(float x,float y){
    int ix=int(std::floor(x)),iy=int(std::floor(y));float a=INF,b=INF;
    for(int j=-1;j<=1;j++)for(int i=-1;i<=1;i++){
        uint32_t h=hash3(ix+i,iy+j,0),q=h*1664525u+1013904223u;
        float dx=ix+i+.18f+.64f*(float(h)/4294967295.f)-x;
        float dy=iy+j+.18f+.64f*(float(q)/4294967295.f)-y;
        float r=dx*dx+dy*dy;
        if(r<a){b=a;a=r;}else if(r<b)b=r;
    }return std::sqrt(b)-std::sqrt(a);
}
Surface shade(V p,V &n,int material,float footprint){
    Surface m;m.kind=material;
    float q0=poolQ(p,0),q1=poolQ(p,1);int pi=q0<q1?0:1;
    float q=std::min(q0,q1),d=(q-1)*pools[pi].rx,level=pools[pi].level;
    float macro=fbm(p*.73f),medium=fbm(p*13.7f);
    float grainFilter=1/(1+sqr(footprint*260));float grain=noise(p*263)*grainFilter;
    float patch=fbm(V(p.x*.92f+4,p.y*.86f-2,p.z*2.7f));
    float wet= (1-smooth(level+.008f,level+.10f+.02f*noise(p*3.4f),p.z))*(1-smooth(1.19f,1.45f,q));
    float normalStrength=.09f;
    if(material==0||material==4){
        // Ground is a mixture, not one tan material scaled by scalar noise.
        float deposit=std::exp(-sqr((d-.13f)/(.36f+.25f*smooth(-.3f,.3f,patch))));
        deposit*=.40f+.60f*smooth(-.26f,.32f,patch);
        float oldcrust=smooth(-.08f,.36f,fbm(V(p.x*.71f-4,p.y*1.1f+5,p.z*3)));
        oldcrust*=std::exp(-sqr((d-.69f)/.64f))*.68f;
        deposit=clamp(deposit+oldcrust);
        V sand(.32f,.258f,.184f),silt(.215f,.173f,.127f),carbonate(.82f,.785f,.69f);
        float fine=smooth(-.23f,.40f,fbm(p*.48f));
        m.color=(sand*(1-fine)+silt*fine)*(1-deposit)+carbonate*deposit;
        m.color*=1+.08f*macro+.11f*medium+.14f*grain;
        float iron=std::exp(-sqr((q-1.027f)/.072f))*(.18f+.82f*smooth(-.26f,.37f,fbm(V(p.x*1.17f,p.y*.93f,p.z*3))));
        float runnel=p.x-(3.28f+.27f*std::sin(p.y*.94f)+.13f*noise(p.y*3.7f,0));
        float drain=std::exp(-sqr(runnel/.37f))*std::exp(-std::pow((p.y+1.65f)/2.8f,4));
        iron=clamp(iron+drain*.40f);
        m.color=m.color*(1-iron*.68f)+V(.29f,.132f,.043f)*(iron*.68f);
        if(q<.986f){
            float plume=smooth(-.2f,.37f,fbm(V(p.x*1.01f,p.y*1.43f,p.z*1.3f)));
            m.color=V(.43f,.45f,.39f)*(.88f+.18f*plume)*(1+.14f*medium+.08f*grain);
            float edge=smooth(.82f,1.f,q);
            m.color=m.color*(1-edge*.68f)+V(.71f,.655f,.48f)*(edge*.68f);
            float stains=smooth(-.01f,.46f,fbm(p*3.3f))*smooth(.72f,.94f,q)*.25f;
            m.color=m.color*(1-stains)+V(.21f,.14f,.059f)*stains;
        }
        if(material==4)m.color=V(.67f,.628f,.518f)*(1+.22f*medium+.10f*macro);
        if(q>1.08f&&q<2.1f){
            float gap=cellGap2(p.x*6.3f+.25f*noise(p.x*3,p.y*3),p.y*6.3f+.25f*noise(p.x*3+8,p.y*3));
            float mask=smooth(1.07f,1.25f,q)*(1-smooth(1.8f,2.1f,q))*smooth(-.15f,.22f,noise(p.x*.72f,p.y*.72f));
            float crack=std::exp(-sqr(gap/std::max(.025f,footprint*9)))*mask;
            m.color*=1-.42f*crack;
        }
        m.rough=.90f*(1-wet)+.22f*wet;
        if(!photographicGrain.levels.empty()){
            float u=p.x*.917f+p.y*.399f,v=p.y*.917f-p.x*.399f;
            float grit=photographicGrain.sample(u,v,footprint,.25f);
            m.color*=.63f+.37f*clamp(grit,.15f,2.0f);
        }
        normalStrength=.16f;
    }else if(material==1||material==2){
        // Chalky gray fractured carbonate and iron-coated darker clasts.
        float lithology=smooth(-.28f,.34f,fbm(p*1.12f));
        V pale(.54f,.497f,.418f),dark(.216f,.170f,.116f);
        m.color=material==1?pale*(.78f+.27f*lithology):dark*(.73f+.48f*lithology);
        float stains=smooth(.04f,.44f,fbm(V(p.x*2.7f,p.y*2.2f,p.z*8.2f)))*.47f;
        m.color=m.color*(1-stains)+V(.225f,.163f,.095f)*stains;
        m.color*=1+.10f*macro+.23f*medium;
        float grainblack=smooth(.05f,.43f,noise(p*315+V(4,8,19)))*grainFilter;
        float calcite=smooth(.20f,.59f,noise(p*189))*grainFilter;
        m.color*=1-.47f*grainblack;
        m.color=m.color*(1-calcite*.28f)+V(.79f,.77f,.70f)*(calcite*.28f);
        // Dust coats upward-facing recesses; broken vertical faces retain gray.
        float dust=smooth(.25f,.83f,n.z)*smooth(-.2f,.30f,fbm(p*5.2f))*.26f;
        m.color=m.color*(1-dust)+V(.35f,.267f,.173f)*dust;
        float crust=std::exp(-sqr(d/.39f))*smooth(-.06f,.43f,patch)*.46f;
        m.color=m.color*(1-crust)+V(.67f,.645f,.564f)*crust;
        if(!photographicGrain.levels.empty()){
            V w(n.x*n.x,n.y*n.y,n.z*n.z);
            float grit=w.x*photographicGrain.sample(p.y,p.z,footprint,.17f)+w.y*photographicGrain.sample(p.x,p.z,footprint,.17f)+w.z*photographicGrain.sample(p.x,p.y,footprint,.17f);
            m.color*=.69f+.31f*clamp(grit,.12f,2.2f);
        }
        m.rough=.79f*(1-wet)+.24f*wet;normalStrength=.15f;
    }else if(material==3){
        m.color=V(.37f,.274f,.139f)*(1+.40f*macro+.13f*noise(p*53));m.rough=.94f;
    }else if(material==5){
        float slope=smooth(.009f,.13f,1-n.z);
        float strata=smooth(-.05f,.44f,std::sin((p.z+.22f*p.x-.06f*p.y)*.028f+fbm(p*.0023f)*1.6f));
        float old=smooth(-.26f,.36f,fbm(V(p.x*.0063f,p.y*.0067f,p.z*.007f)));
        V talus(.34f,.262f,.191f),limestone(.385f,.347f,.302f),varnish(.179f,.172f,.163f);
        V bedrock=limestone*(1-strata*.53f)+varnish*(strata*.53f);
        bedrock=bedrock*(1-old*.16f)+V(.31f,.216f,.153f)*(old*.16f);
        m.color=talus*(1-slope)+bedrock*slope;
        m.color*=1+.14f*fbm(p*.039f)+.08f*noise(p*.47f);
        float ramp=smooth(260,850,p.y);
        m.color=m.color*ramp+V(.215f,.171f,.126f)*(1-ramp)*(1+.15f*macro);
        m.rough=.94f;normalStrength=.09f;
    }else if(material==8){
        m.color=V(.17f,.148f,.117f)*(1+.28f*macro+.15f*noise(p*97));m.rough=.92f;
    }else if(material==9){
        float dry=smooth(-.15f,.40f,noise(p*3.1f));
        m.color=V(.23f,.267f,.171f)*(1-dry)+V(.348f,.329f,.263f)*dry;
        m.color*=1+.25f*macro+.10f*noise(p*89);m.rough=.89f;
    }else m.color=V(.3f);
    m.color*=1-.32f*wet;
    m.ior=(p.z<level&&q<1.1f)?1.48f/WATER_IOR:(wet>.2f?1.334f:1.48f);
    m.color=vmin(vmax(m.color,V(.002f)),V(.88f));
    if(material==0||material==1||material==2||material==4||material==5){
        Frame frame(n);float freq=material==5?.68f:112.f;
        float filter=1/(1+sqr(footprint*freq));V u=frame.t*.016f,b=frame.b*.016f,pf=p*freq;
        float dt=(noise(pf+u)-noise(pf-u))/.032f,db=(noise(pf+b)-noise(pf-b))/.032f;
        n=unit(n-(frame.t*dt+frame.b*db)*(normalStrength*filter));
        float filter2=1/(1+sqr(footprint*387));
        n=unit(n+(frame.t*noise(p*387)+frame.b*noise(p*387+V(5,8,2)))*(.17f*filter2));
    }
    return m;
}
