// GPL-2.0-only. Authored spatially correlated mineral, sediment and rock layers.
// No measured-spectrum claim; no image replacement or screen-space painting.
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
V mixc(V a,V b,float x){return a*(1-x)+b*x;}
Surface shade(V p,V &n,int material,float footprint){
    Surface m;m.kind=material;
    float q0=poolQ(p,0),q1=poolQ(p,1);int pi=q0<q1?0:1;
    float q=std::min(q0,q1),d=(q-1)*pools[pi].rx,level=pools[pi].level;
    float macro=fbm(p*.59f),medium=fbm(p*11.7f);
    float grainFilter=1/(1+sqr(footprint*220));float grain=noise(p*239)*grainFilter;
    float patch=smooth(-.25f,.35f,fbm(V(p.x*.73f+8,p.y*.69f+4,p.z*1.9f)));
    float wet=(1-smooth(level+.025f,level+.16f+.025f*noise(p*4),p.z))*(1-smooth(1.25f,1.48f,q));
    float runnel=p.x-(3.28f+.27f*std::sin(p.y*.94f)+.13f*noise(p.y*3.7f,0));
    float drain=std::exp(-sqr(runnel/.32f))*std::exp(-std::pow((p.y+1.65f)/2.8f,4));
    wet=clamp(wet+.82f*drain);
    float normalStrength=.15f;
    if(material==0||material==4){
        // Sediment, aged crust and newly wetted sinter are distinct reflectances.
        float fresh=std::exp(-sqr((d-.13f)/(.19f+.29f*patch)))*(.60f+.40f*patch);
        float oldflow=smooth(-.26f,.40f,fbm(V(p.x*.42f-6,p.y*.54f+7,p.z*.5f)));
        float old=std::exp(-sqr((d-.85f)/1.65f))*oldflow*.80f;
        old*=.35f+.65f*(1-smooth(-1.8f,5.0f,p.x));
        float deposit=clamp(fresh+old);
        float fine=smooth(-.23f,.37f,fbm(p*.82f));
        V sand(.235f,.181f,.122f),silt(.126f,.106f,.084f),carbonate(.74f,.713f,.650f);
        m.color=mixc(mixc(sand,silt,fine*.55f),carbonate,deposit);
        // Mineral staining follows wetted margins/runnels, rather than noise
        // painted everywhere. Its variation is a defined source-material field.
        float oxide=std::exp(-sqr((d-.055f)/.28f))*(.24f+.76f*(1-patch));
        oxide=clamp(oxide+drain*.83f);
        m.color=mixc(m.color,V(.245f,.094f,.021f),oxide*.79f);
        float oldmat=smooth(-.10f,.32f,fbm(V(p.x*2.6f,p.y*2.1f,p.z*7.0f)))*wet*.20f;
        m.color=mixc(m.color,V(.045f,.060f,.023f),oldmat);
        m.color*=1+.15f*macro+.14f*medium+.12f*grain;
        if(q<.987f){
            float sediment=smooth(-.12f,.45f,fbm(V(p.x*1.45f,p.y*1.2f,p.z*1.8f)));
            float stain=smooth(-.02f,.40f,fbm(p*4.7f));
            m.color=mixc(V(.355f,.37f,.313f),V(.118f,.13f,.112f),sediment*.65f);
            m.color*=1+.18f*medium+.09f*grain;
            m.color=mixc(m.color,V(.415f,.341f,.187f),smooth(.78f,1.f,q)*.71f);
            m.color=mixc(m.color,V(.067f,.075f,.032f),stain*.24f);
            wet=0; // water does its own spectral attenuation, not double darkening
        }
        if(material==4)m.color=V(.57f,.551f,.488f)*(1+.23f*medium+.11f*macro);
        if(q>1.08f&&q<2.1f){
            float gap=cellGap2(p.x*2.3f+.19f*noise(p.x*1.7f,p.y*1.7f),p.y*2.3f+.19f*noise(p.x*1.7f+8,p.y*1.7f));
            float mask=smooth(1.08f,1.25f,q)*(1-smooth(1.9f,2.1f,q))*smooth(-.2f,.18f,noise(p.x*.53f,p.y*.61f));
            float crack=std::exp(-sqr(gap/std::max(.04f,footprint*8)))*mask;
            m.color*=1-.48f*crack;
        }
        if(!photographicGrain.levels.empty()){
            // Authored 64 cm patch width: the old 13 cm mapping mip-averaged
            // nearly all photographic structure away at the wide camera.
            // Albedo only; not a measured height or normal map.
            float u=p.x*.917f+p.y*.399f,v=p.y*.917f-p.x*.399f;
            float grit=photographicGrain.sample(u,v,footprint,.64f);
            m.color*=.36f+.64f*clamp(grit,.18f,2.15f);
        }
        m.rough=.91f*(1-wet)+.095f*wet;normalStrength=.17f;
    }else if(material==1||material==2){
        float lithology=smooth(-.23f,.34f,fbm(p*.91f));
        V pale(.34f,.323f,.292f),dark(.109f,.080f,.054f);
        m.color=material==1?pale*(.77f+.36f*lithology):dark*(.74f+.55f*lithology);
        float strata=smooth(-.3f,.52f,noise(V(p.x*7.1f,p.y*6.3f,p.z*38.1f)));
        m.color*=.79f+.33f*strata;
        float exposed=smooth(-.08f,.32f,fbm(p*8.5f));
        m.color=mixc(m.color,V(.27f,.250f,.211f),exposed*.36f);
        // Local calcite-rich veins and dark varnish; no continuous equator bands.
        float vein=std::exp(-sqr((p.z*.9f+p.x*.48f-p.y*.22f+.06f*fbm(p*12))/.013f));
        vein*=smooth(-.22f,.29f,fbm(p*5));
        m.color=mixc(m.color,V(.71f,.68f,.60f),vein*.64f);
        m.color*=1+.10f*macro+.29f*medium;
        float grainblack=smooth(-.02f,.39f,noise(p*351+V(4,8,19)))*grainFilter;
        m.color*=1-.39f*grainblack;
        float dust=smooth(.46f,.94f,n.z)*smooth(-.2f,.31f,fbm(p*5.2f))*.29f;
        m.color=mixc(m.color,V(.29f,.23f,.156f),dust);
        float crust=std::exp(-sqr((p.z-level-.05f)/.12f))*(1-smooth(1.0f,1.42f,q))*.7f;
        m.color=mixc(m.color,V(.58f,.554f,.473f),crust);
        m.rough=.83f*(1-wet)+.20f*wet;normalStrength=.20f;
    }else if(material==3){
        m.color=V(.32f,.226f,.106f)*(1+.36f*macro+.20f*noise(p*37));m.rough=.91f;
    }else if(material==5){
        float slope=smooth(.025f,.22f,1-n.z);
        float layers=smooth(-.12f,.44f,std::sin((p.z+.31f*p.x-.085f*p.y)*.041f+fbm(p*.006f)*2.3f));
        float geology=smooth(-.27f,.35f,fbm(V(p.x*.0039f,p.y*.0047f,p.z*.007f)));
        V talus(.235f,.185f,.14f),granite(.19f,.173f,.161f),varnish(.082f,.073f,.067f),iron(.228f,.151f,.101f);
        V rock=mixc(granite,varnish,layers*.72f);
        rock=mixc(rock,iron,geology*.38f);
        m.color=mixc(talus,rock,slope);
        float surface=smooth(-.14f,.37f,fbm(p*.083f));
        m.color*=.80f+.33f*surface+.15f*fbm(p*.021f);
        float ramp=smooth(230,950,p.y);
        m.color=m.color*ramp+V(.214f,.17f,.116f)*(1-ramp)*(1+.17f*macro);
        m.rough=.94f;normalStrength=.15f;
    }else if(material==8){
        m.color=V(.125f,.093f,.060f)*(1+.27f*macro+.23f*noise(p*113));m.rough=.94f;
    }else if(material==9){
        float dry=smooth(-.15f,.38f,noise(p*4.1f));
        m.color=mixc(V(.249f,.267f,.208f),V(.315f,.291f,.203f),dry);
        m.color*=1+.33f*macro+.11f*noise(p*97);m.rough=.88f;
    }else m.color=V(.3f);
    m.color*=1-.36f*wet;
    m.ior=(p.z<level&&q<1.1f)?1.48f/WATER_IOR:(wet>.2f?1.334f:1.48f);
    m.color=vmin(vmax(m.color,V(.002f)),V(.88f));
    if(material==0||material==1||material==2||material==4||material==5){
        Frame frame(n);float freq=material==5?.33f:84.f;
        float filter=1/(1+sqr(footprint*freq));V u=frame.t*.016f,b=frame.b*.016f,pf=p*freq;
        float dt=(noise(pf+u)-noise(pf-u))/.032f,db=(noise(pf+b)-noise(pf-b))/.032f;
        n=unit(n-(frame.t*dt+frame.b*db)*(normalStrength*filter));
        float filter2=1/(1+sqr(footprint*433));
        n=unit(n+(frame.t*noise(p*433)+frame.b*noise(p*433+V(5,8,2)))*(.20f*filter2));
    }
    return m;
}
