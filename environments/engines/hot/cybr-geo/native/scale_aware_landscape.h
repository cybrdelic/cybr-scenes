// CYBR GEO v8: scale-aware authored materials. No photograph used as height.
// Values are authored reflectances, not measured mineral spectra.
#pragma once
Surface shade(V p,V &n,int material,float footprint){
    Surface m;m.kind=material;
    const float q0=poolQ(p,0),q1=poolQ(p,1);const int pool=q0<q1?0:1;
    const float q=std::min(q0,q1),d=(q-1)*pools[pool].rx,level=pools[pool].level;
    float macro=fbm(p*.64f),meso=fbm(p*17.1f);
    float patch=fbm(V(p.x*.94f,p.y*1.15f,p.z*3.4f));
    float wet=(1-smooth(level+.005f,level+.092f+.016f*noise(p*7),p.z))*(1-smooth(1.18f,1.45f,q));
    float fineFilter=1/(1+sqr(footprint*240.f));
    float grain=noise(p*243.7f)*fineFilter;
    float normalStrength=.065f;
    if(material==0||material==4){
        // Fines have modest variation; real visible clasts are separate meshes.
        float mineral=std::exp(-sqr(d/(.20f+.18f*smooth(-.3f,.4f,patch))));
        float deposition=clamp(mineral*(.87f+.63f*patch)*smooth(-.48f,.07f,fbm(p*1.73f)));
        V sand(.275f,.213f,.145f),carbonate(.72f,.657f,.544f);
        m.color=sand*(1-deposition)+carbonate*deposition;
        m.color*=1+.16f*macro+.105f*meso+.10f*grain;
        if(q<.99f){
            float sediment=smooth(-.35f,.43f,fbm(V(p.x*.81f,p.y*.87f,p.z*1.4f)));
            m.color=V(.298f,.286f,.222f)*(.91f+.16f*sediment)*(1+.10f*meso+.04f*grain);
            float rim=smooth(.81f,.99f,q)*.68f;
            m.color=m.color*(1-rim)+V(.61f,.589f,.495f)*rim;
        }
        float iron=std::exp(-sqr((q-1.014f)/.078f))*smooth(-.15f,.42f,fbm(V(p.x*.85f,p.y*1.8f,p.z*4)));
        m.color=m.color*(1-iron*.56f)+V(.235f,.102f,.028f)*(iron*.56f);
        if(material==4)m.color=V(.59f,.529f,.41f)*(1+.10f*meso+.08f*macro)*(1-.18f*iron);
        m.rough=.89f*(1-wet)+.32f*wet;
        if(!photographicGrain.levels.empty()){
            float u=p.x*.917f+p.y*.399f,v=p.y*.917f-p.x*.399f;
            float grit=photographicGrain.sample(u,v,footprint,.22f);
            m.color*=.44f+.56f*clamp(grit,.20f,2.1f);
        }
        normalStrength=.11f;
    }else if(material==1||material==2){
        float litho=smooth(-.3f,.45f,fbm(p*.53f));
        V dark(.178f,.131f,.085f),tan(.337f,.257f,.167f);
        m.color=material==1?V(.42f,.358f,.279f):(dark*(1-litho)+tan*litho);
        m.color*=1+.23f*macro+.48f*meso;
        float quartz=smooth(.22f,.57f,noise(p*231.1f))*fineFilter;
        float darkgrain=smooth(.18f,.52f,noise(p*391.3f+V(8,3,1)))*fineFilter;
        m.color=m.color*(1-quartz*.52f)+V(.56f,.522f,.444f)*(quartz*.52f);
        m.color*=1-darkgrain*.55f;
        // Occasional narrow vein, not repeated dark horizontal stripe bands.
        float plane=p.z+.36f*p.x-.18f*p.y+.05f*noise(p*5.1f);
        float vein=std::exp(-sqr((plane-.23f)/.009f))*smooth(-.05f,.32f,noise(p*1.8f));
        m.color=m.color*(1-vein*.46f)+V(.61f,.573f,.474f)*(vein*.46f);
        float crust=std::exp(-sqr(d/.29f))*smooth(.06f,.55f,patch)*smooth(.13f,.73f,n.z)*.39f;
        m.color=m.color*(1-crust)+V(.54f,.49f,.38f)*crust;
        if(!photographicGrain.levels.empty()){
            V w(n.x*n.x,n.y*n.y,n.z*n.z);
            float grit=w.x*photographicGrain.sample(p.y,p.z,footprint,.28f)+w.y*photographicGrain.sample(p.x,p.z,footprint,.28f)+w.z*photographicGrain.sample(p.x,p.y,footprint,.28f);
            m.color*=.40f+.60f*clamp(grit,.25f,2.2f);
        }
        m.rough=.85f*(1-wet)+.29f*wet;normalStrength=.085f;
    }else if(material==3){
        m.color=V(.43f,.307f,.144f)*(1+.24f*macro+.16f*noise(p*51));m.rough=.92f;
    }else if(material==5){
        float slope=smooth(.07f,.43f,1-n.z);
        float lithology=smooth(-.24f,.35f,fbm(V(p.x*.009f,p.y*.010f,p.z*.022f)));
        V talus(.271f,.219f,.164f),rock(.157f,.126f,.101f);
        float exposed=clamp(slope*.86f+.24f*lithology);
        float strata=std::sin(p.z*.091f+p.x*.019f+fbm(p*.018f)*.70f);
        m.color=(talus*(1-exposed)+rock*exposed)*(1+.17f*fbm(p*.63f)+.08f*noise(p*2.8f)+.09f*strata);
        float ramp=smooth(260,700,p.y);
        m.color=m.color*ramp+V(.275f,.213f,.145f)*(1-ramp)*(1+.16f*fbm(p*.64f));
        m.rough=.94f;normalStrength=.115f;
    }else if(material==8){
        m.color=V(.139f,.111f,.077f)*(1+.19f*macro+.18f*noise(p*79));m.rough=.94f;
    }else if(material==9){
        float dry=smooth(-.26f,.42f,noise(p*4.3f));
        m.color=V(.229f,.270f,.133f)*(1-dry)+V(.39f,.348f,.201f)*dry;
        m.color*=1+.17f*macro+.07f*noise(p*68);m.rough=.92f;
    }else{m.color=V(.3f);}
    m.color*=1-.35f*wet;
    m.ior=(p.z<level&&q<1.1f)?1.48f/WATER_IOR:(wet>.2f?1.334f:1.48f);
    m.color=vmin(vmax(m.color,V(.003f)),V(.88f));
    if(material==0||material==1||material==2||material==4||material==5){
        // Residual subpixel relief is normal mapped. Macro relief stays geometry.
        Frame frame(n);float freq=material==5?.64f:96.f;
        float filter=1/(1+sqr(footprint*freq));
        V u=frame.t*.016f,b=frame.b*.016f,pf=p*freq;
        float dt=(noise(pf+u)-noise(pf-u))/.032f;
        float db=(noise(pf+b)-noise(pf-b))/.032f;
        n=unit(n-(frame.t*dt+frame.b*db)*(normalStrength*filter));
        float filter2=1/(1+sqr(footprint*390));
        n=unit(n+(frame.t*noise(p*390)+frame.b*noise(p*390+V(5,8,2)))*(.12f*filter2));
    }
    return m;
}
