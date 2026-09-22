// Heterogeneous 3-D cloud extinction field. All lighting and camera visibility
// are transported in trace(); no sky image or 2-D cloud composite is used.
#pragma once
constexpr int CLOUD_NX=640,CLOUD_NY=512,CLOUD_NZ=48;
const V CLOUD_LO(-24000.f,-18000.f,2900.f),CLOUD_HI(24000.f,28000.f,3280.f);
constexpr float CLOUD_MAJORANT=.024f,CLOUD_G=.76f;
std::vector<float> cloudGrid,cloudMajorants;
constexpr int CLOUD_TILE=8, CLOUD_MX=(CLOUD_NX-2)/CLOUD_TILE+1, CLOUD_MY=(CLOUD_NY-2)/CLOUD_TILE+1;
bool useClouds=true;
inline float saturateCloud(float x){x=clamp(x);return x*x*(3-2*x);}
float cloudAnalytic(V p){
    float h=(p.z-CLOUD_LO.z)/(CLOUD_HI.z-CLOUD_LO.z);
    float warp=fbm(V(p.x*.00009f,p.y*.00009f,3.4f));
    float macro=fbm(V(p.x*.00029f+warp*.72f,p.y*.00057f-warp*.46f,4.1f));
    float coverage=saturateCloud((macro-.27f)*3.1f);
    float field=std::exp(-std::pow((p.x-6200.f)/8600.f,4.f)-std::pow((p.y-8300.f)/10200.f,4.f));
    coverage*=field;
    float bottom=.12f+.14f*noise(V(p.x*.0006f,p.y*.0006f,4));
    float shape=saturateCloud((h-bottom)*6)*(1-saturateCloud((h-.51f)/.45f));
    float detail=clamp(.61f+.35f*fbm(V(p.x*.004f,p.y*.0044f,p.z*.008f)));
    return .009f*coverage*shape*detail;
}
void initClouds(){
    if(!useClouds)return;
    cloudGrid.resize(size_t(CLOUD_NX)*CLOUD_NY*CLOUD_NZ);
    #pragma omp parallel for schedule(static)
    for(int k=0;k<CLOUD_NZ;k++)for(int j=0;j<CLOUD_NY;j++)for(int i=0;i<CLOUD_NX;i++){
        V p(CLOUD_LO.x+(CLOUD_HI.x-CLOUD_LO.x)*i/(CLOUD_NX-1),CLOUD_LO.y+(CLOUD_HI.y-CLOUD_LO.y)*j/(CLOUD_NY-1),CLOUD_LO.z+(CLOUD_HI.z-CLOUD_LO.z)*k/(CLOUD_NZ-1));
        float rho=cloudAnalytic(p);
        cloudGrid[(size_t(k)*CLOUD_NY+j)*CLOUD_NX+i]=rho<1e-8f?0.f:rho;
    }
    // Conservative XY column majorants include every Z sample and both sides
    // of each trilinear cell. Empty columns can be traversed without null events.
    cloudMajorants.assign(CLOUD_MX*CLOUD_MY,0.f);
    #pragma omp parallel for schedule(static)
    for(int ty=0;ty<CLOUD_MY;ty++)for(int tx=0;tx<CLOUD_MX;tx++){
        float maximum=0;
        for(int z=0;z<CLOUD_NZ;z++)
          for(int y=ty*CLOUD_TILE;y<=std::min((ty+1)*CLOUD_TILE,CLOUD_NY-1);y++)
            for(int x=tx*CLOUD_TILE;x<=std::min((tx+1)*CLOUD_TILE,CLOUD_NX-1);x++)
              maximum=std::max(maximum,cloudGrid[(size_t(z)*CLOUD_NY+y)*CLOUD_NX+x]);
        cloudMajorants[ty*CLOUD_MX+tx]=maximum>0?std::nextafter(maximum,INF):0;
    }
}
float cloudDensity(V p){
    if(!useClouds||cloudGrid.empty())return 0;
    if(p.x<CLOUD_LO.x||p.y<CLOUD_LO.y||p.z<CLOUD_LO.z||p.x>CLOUD_HI.x||p.y>CLOUD_HI.y||p.z>CLOUD_HI.z)return 0;
    float x=(p.x-CLOUD_LO.x)/(CLOUD_HI.x-CLOUD_LO.x)*(CLOUD_NX-1),y=(p.y-CLOUD_LO.y)/(CLOUD_HI.y-CLOUD_LO.y)*(CLOUD_NY-1),z=(p.z-CLOUD_LO.z)/(CLOUD_HI.z-CLOUD_LO.z)*(CLOUD_NZ-1);
    int ix=std::min(int(x),CLOUD_NX-2),iy=std::min(int(y),CLOUD_NY-2),iz=std::min(int(z),CLOUD_NZ-2);
    float fx=x-ix,fy=y-iy,fz=z-iz,out=0;
    for(int k=0;k<2;k++)for(int j=0;j<2;j++)for(int i=0;i<2;i++)out+=cloudGrid[(size_t(iz+k)*CLOUD_NY+iy+j)*CLOUD_NX+ix+i]*(i?fx:1-fx)*(j?fy:1-fy)*(k?fz:1-fz);
    return out;
}
bool cloudInterval(const Ray&r,float maximum,float&a,float&b){
    a=0;b=maximum;
    for(int k=0;k<3;k++){
        if(std::fabs(r.d[k])<1e-10f){if(r.o[k]<CLOUD_LO[k]||r.o[k]>CLOUD_HI[k])return false;continue;}
        float x=(CLOUD_LO[k]-r.o[k])/r.d[k],y=(CLOUD_HI[k]-r.o[k])/r.d[k];if(x>y)std::swap(x,y);
        a=std::max(a,x);b=std::min(b,y);if(a>=b)return false;
    }return true;
}

// Piecewise-constant-majorant null-collision tracking. The DDA visits columns
// exactly at their ray intersections; no geometric region is skipped because
// it merely has low extinction. A fresh exponential in each interval is valid
// by the memoryless property of the inhomogeneous Poisson process.
float trackCloud(const Ray&r,float maximum,RNG&rng,bool collision,float&transmittance){
    transmittance=1.f;
    if(!useClouds||cloudMajorants.empty())return INF;
    float aa,bb;if(!cloudInterval(r,maximum,aa,bb))return INF;
    const double dx=(double(CLOUD_HI.x)-CLOUD_LO.x)*CLOUD_TILE/(CLOUD_NX-1);
    const double dy=(double(CLOUD_HI.y)-CLOUD_LO.y)*CLOUD_TILE/(CLOUD_NY-1);
    double t=aa,end=bb;
    int ix=std::max(0,std::min(CLOUD_MX-1,int(std::floor((r.o.x+double(r.d.x)*t-CLOUD_LO.x)/dx))));
    int iy=std::max(0,std::min(CLOUD_MY-1,int(std::floor((r.o.y+double(r.d.y)*t-CLOUD_LO.y)/dy))));
    int sx=r.d.x>=0?1:-1,sy=r.d.y>=0?1:-1;
    double stepx=std::fabs(r.d.x)>1e-12f?dx/std::fabs(r.d.x):1e100;
    double stepy=std::fabs(r.d.y)>1e-12f?dy/std::fabs(r.d.y):1e100;
    double nextx=std::fabs(r.d.x)>1e-12f?(CLOUD_LO.x+(ix+(sx>0?1:0))*dx-r.o.x)/r.d.x:1e100;
    double nexty=std::fabs(r.d.y)>1e-12f?(CLOUD_LO.y+(iy+(sy>0?1:0))*dy-r.o.y)/r.d.y:1e100;
    while(t<end&&ix>=0&&ix<CLOUD_MX&&iy>=0&&iy<CLOUD_MY){
        double stop=std::min(end,std::min(nextx,nexty));
        float majorant=cloudMajorants[iy*CLOUD_MX+ix];
        if(majorant>0&&stop>t){
            double event=t;
            for(;;){
                event+=-std::log(std::max(1e-8f,1-rng.uniform()))/majorant;
                if(event>=stop)break;
                float fraction=clamp(cloudDensity(r.o+r.d*float(event))/majorant);
                if(collision){if(rng.uniform()<fraction)return float(event);}
                else{
                    transmittance*=1-fraction;
                    if(transmittance<1e-6f){transmittance=0;return INF;}
                }
            }
        }
        t=stop;
        bool crossx=nextx<=stop+1e-8,crossy=nexty<=stop+1e-8;
        if(crossx){ix+=sx;nextx+=stepx;}
        if(crossy){iy+=sy;nexty+=stepy;}
        if(!crossx&&!crossy)break;
    }
    return INF;
}
float sampleCloud(const Ray&r,float maximum,RNG&rng){float ignored;return trackCloud(r,maximum,rng,true,ignored);}
float cloudTransmittance(const Ray&r,float maximum,RNG&rng){float tr;trackCloud(r,maximum,rng,false,tr);return tr;}
