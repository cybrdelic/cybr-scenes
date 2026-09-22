// SPDX-License-Identifier: GPL-2.0-only
// Per-component coordinates for genuine triangle surfaces. Authored, not scanned.
#pragma once
struct SurfaceFrame6 {V origin,d,side,normal;float length,width,kind,seed;};
static_assert(sizeof(SurfaceFrame6)==64,"Unexpected frame packing");
std::vector<SurfaceFrame6> surfaceFrames6;
void loadSurfaceFrames6(const std::string &mesh){
    const auto pos=mesh.find_last_of("/\\");
    std::string path=(pos==std::string::npos?std::string():mesh.substr(0,pos+1))+"surface_frames.bin";
    std::ifstream f(path,std::ios::binary);surfaceFrames6.clear();if(!f)return;
    char tag[4];uint32_t n=0;f.read(tag,4);f.read(reinterpret_cast<char*>(&n),4);
    if(!f||std::memcmp(tag,"FRM6",4)||n>2000000)throw std::runtime_error("Invalid surface-frame sidecar");
    surfaceFrames6.resize(n);f.read(reinterpret_cast<char*>(surfaceFrames6.data()),n*sizeof(SurfaceFrame6));
    if(!f||f.peek()!=std::char_traits<char>::eof())throw std::runtime_error("Truncated/overlong frame table");
    for(uint32_t i=1;i<n;++i){const auto &a=surfaceFrames6[i];
        const float *p=reinterpret_cast<const float*>(&a);for(int k=0;k<16;++k)if(!std::isfinite(p[k]))throw std::runtime_error("Nonfinite local frame");
        if(a.length<=0||a.width<=0||std::fabs(len(a.d)-1)>.001||std::fabs(len(a.side)-1)>.001||std::fabs(dot(a.d,a.side))>.001)throw std::runtime_error("Invalid local frame axes");
    }
    std::cerr<<"R6 local surface coordinate frames: "<<n<<"\n";
}
Surface shadeAt6(V p,V &n,int id,float footprint,int group){
    if(sceneStyle!=2){
        V gn=n;Surface material=shadeLegacyR5(p,n,id,footprint);
        bool rock=id==1||id==2||id==13;
        if(rock){
            cybr_detail::apply(p,gn,n,material.color,material.rough,footprint,
                sceneStyle==0?.67f:.93f,sceneStyle==0?.56f:.46f,.72f);
            // Salt/rust deposition is spatial, not a repeated bright texture.
            if(sceneStyle==1){float edge=std::exp(-sqr((p.z-.43f)/.19f));
                float algae=edge*smooth(-.12f,.37f,noise(p*9.2f));
                material.color=mixc(material.color,V(.030f,.045f,.020f),algae*.34f);
            }
        }else if(id==0||id==4){cybr_detail::apply(p,gn,n,material.color,material.rough,footprint,1.85f,.15f,.28f);}
        material.color=vmin(vmax(material.color,V(.003f)),V(.88f));
        if(dot(n,gn)<.60f)n=unit(n+gn);
        return material;
    }
    Surface m;m.kind=id;m.rough=.80f;m.ior=1.49f;V gn=n;
    float grain=.12f,relief=.09f;
    float wet=1-smooth(.00f,.19f,p.z),macro=noise(p*.94f),fine=1/(1+sqr(footprint*140));
    const SurfaceFrame6 *f=(group>0&&size_t(group)<surfaceFrames6.size())?&surfaceFrames6[group]:nullptr;
    if(id==0||id==4){
        float mineral=smooth(.03f,.39f,noise(p*5.8f));
        m.color=mixc(V(.024f,.014f,.007f),V(.078f,.048f,.021f),.55f+.30f*macro);
        m.color=mixc(m.color,V(.115f,.098f,.066f),mineral*.35f*(1-smooth(.01f,.22f,p.z)));
        m.color*=1+.08f*noise(p*171)*fine;
        m.rough=.92f-.48f*wet;grain=.37f;relief=.36f;
    }else if(id==1||id==2||id==5){
        // Coarser independent mineral domains with a much finer grain, not large pits.
        m.color=mixc(V(.067f,.072f,.068f),V(.173f,.165f,.135f),.40f+.28f*macro);
        float grainy=smooth(.03f,.62f,noise(p*150));
        m.color*=1+.12f*noise(p*19)+.13f*grainy*fine;
        float fleck=smooth(.30f,.64f,noise(p*290));
        m.color=mixc(m.color,V(.30f,.31f,.28f),fleck*.17f*fine);
        float stain=smooth(.22f,.48f,noise(p*4.4f));m.color=mixc(m.color,V(.043f,.071f,.020f),stain*.30f*smooth(.015f,.16f,p.z));
        m.color*=1-.32f*wet;m.rough=.77f-.52f*wet;grain=.26f;relief=.15f;
        n=unit(n-noiseSlope(p,n,119,.06f,footprint));
    }else if(id==8||id==14){
        float plate;
        if(f){
            V q=p-f->origin;float height=dot(q,f->d),arc=std::atan2(dot(q,f->normal),dot(q,f->side))*f->width;
            V local(arc,height,f->seed);float drift=.36f*noise(V(arc*11,height*1.3f,f->seed));
            float groove=std::pow(std::max(0.f,std::cos(arc*94.f+drift)),8.f);
            plate=.5f+.5f*noise(V(arc*23,height*4.5f,f->seed));
            m.color=mixc(V(.034f,.024f,.017f),V(.146f,.112f,.072f),plate);
            m.color*=1-.39f*groove/(1+sqr(footprint*90));
            if(id==14){
                float mark=smooth(.25f,.57f,noise(V(arc*13,height*27.f,f->seed)));
                m.color=mixc(V(.31f,.303f,.253f),V(.044f,.035f,.025f),mark*.82f);
                m.color*=.88f+.18f*plate;
            }
            // Small normal perturbation follows the tree axis, never diagonal world stripes.
            V tangent=unit(cross(f->d,n));
            n=unit(n+tangent*(.045f*std::sin(arc*94+drift)/(1+sqr(footprint*94))));
        }else{
            plate=.5f+.5f*noise(V(p.x*24,p.y*24,p.z*3));m.color=mixc(V(.032f,.022f,.014f),V(.12f,.091f,.050f),plate);
        }
        float bryo=smooth(.10f,.43f,noise(p*4.5f))*(1-smooth(.12f,1.2f,p.z));
        m.color=mixc(m.color,V(.026f,.064f,.011f),bryo*.71f);
        m.rough=.85f;grain=.23f;relief=.18f;
    }else if(id==3||id==9||id==13||id==11){
        float component=f?(.5f+.5f*std::sin(f->seed*2.71f)):(.5f+.5f*noise(p*12));
        bool dead=id==11||id==13;
        m.color=dead?mixc(V(.031f,.022f,.013f),V(.185f,.126f,.069f),component):mixc(V(.028f,.105f,.009f),V(.110f,.235f,.034f),component*.78f);
        m.rough=dead?(.78f-.27f*wet):(.34f+.23f*component);m.ior=1.45f;grain=dead?.035f:0;relief=0;
        if(id==3){m.color=mixc(V(.018f,.048f,.012f),V(.052f,.108f,.024f),component);m.rough=.56f;}
        if(f){
            V q=p-f->origin;float u=dot(q,f->d)/f->length,v=dot(q,f->side)*2/f->width;
            float filtered=1/(1+sqr(footprint/std::max(.001f,f->length*.022f)));
            float mid=std::exp(-sqr(v/.031f))*filtered;
            float sequence=u*8.5f-std::fabs(v)*1.0f;
            float d=std::fabs(sequence-std::round(sequence));
            float vein=std::exp(-sqr(d/.030f))*filtered*(1-mid);
            float mottling=noise(V(u*10,v*5,f->seed));
            m.color*=1+.060f*mottling;
            m.color=mixc(m.color,dead?V(.26f,.164f,.058f):V(.13f,.218f,.032f),.34f*mid+.17f*vein);
            if(dead){float decay=smooth(.06f,.48f,noise(V(u*9,v*6,f->seed)));
                m.color=mixc(m.color,V(.020f,.015f,.008f),decay*(.30f+.30f*wet));
            }else{
                // Chlorophyll variation follows each leaf, not world-space tiles.
                float chlorosis=smooth(.26f,.61f,noise(V(u*4.7f,v*3.2f,f->seed)));
                m.color=mixc(m.color,V(.135f,.181f,.036f),chlorosis*.22f);
            }
            // Sparse gloss modulation and a vein ridge normal in the leaf's own frame.
            float delta=.016f*std::sin(sequence*2*PI)*filtered;
            V tangent=f->side-n*dot(f->side,n);n=unit(n+tangent*delta);
        }
    }else if(id==10){
        float local=.5f+.5f*noise(p*47);
        m.color=mixc(V(.016f,.045f,.005f),V(.056f,.112f,.012f),local);
        m.rough=.96f;grain=.05f;relief=.055f;
    }else if(id==12){
        float lines=noise(V(p.x*37,p.y*37,p.z*7));
        m.color=mixc(V(.047f,.023f,.010f),V(.18f,.10f,.042f),.48f+.38f*lines);m.rough=.94f;grain=.24f;relief=.15f;
    }else{m.color=V(.10f);grain=.1f;}
    if(id==1||id==2||id==5)cybr_detail::apply(p,gn,n,m.color,m.rough,footprint,1.2f,.42f,.60f);
    if(grain>0)m.color*=1+grain*(projectedGrain(p,n,footprint,.39f)-1);
    if(relief>0)n=unit(n-projectedRelief(p,n,footprint,relief));
    if(dot(n,gn)<.70f)n=unit(n+gn);
    m.color=vmin(vmax(m.color,V(.002f)),V(.88f));m.rough=clamp(m.rough,.11f,.98f);return m;
}
// Preserve the original public material-test interface for unframed samples.
Surface shade(V p,V &n,int id,float footprint){return shadeAt6(p,n,id,footprint,0);}
