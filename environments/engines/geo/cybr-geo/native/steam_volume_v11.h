// GPL-2.0-only. Trilinear representation of the authored steam field.
// The tracking majorant is computed from EVERY grid vertex. A trilinear sample
// is a convex combination, hence cannot exceed that bound. No density image,
// billboard, learned volume, or fluid/thermal simulation is used.
#pragma once
constexpr int STEAM_NX=256, STEAM_NY=288, STEAM_NZ=80;
std::vector<float> steamGrid;
float steamGridMajorant=0;
void initSteam(){
    if(!useSteam)return;
    steamGrid.resize(size_t(STEAM_NX)*STEAM_NY*STEAM_NZ);
    float maximum=0;int invalid=0;
    #pragma omp parallel for reduction(max:maximum) reduction(|:invalid) schedule(static)
    for(int k=0;k<STEAM_NZ;k++)for(int j=0;j<STEAM_NY;j++)for(int i=0;i<STEAM_NX;i++){
        V p(FOG_LO.x+(FOG_HI.x-FOG_LO.x)*i/(STEAM_NX-1),
            FOG_LO.y+(FOG_HI.y-FOG_LO.y)*j/(STEAM_NY-1),
            FOG_LO.z+(FOG_HI.z-FOG_LO.z)*k/(STEAM_NZ-1));
        float value=steamAnalytic(p);
        if(!std::isfinite(value)||value<0){invalid=1;value=0;}
        steamGrid[(size_t(k)*STEAM_NY+j)*STEAM_NX+i]=value;
        maximum=std::max(maximum,value);
    }
    if(invalid)throw std::runtime_error("Invalid authored steam density");
    steamGridMajorant=std::nextafter(maximum*1.000005f+1e-8f,INF);
}
float steamDensity(V p){
    if(!useSteam)return 0;
    if(steamGrid.empty())return steamAnalytic(p);
    if(p.x<FOG_LO.x||p.y<FOG_LO.y||p.z<FOG_LO.z||p.x>FOG_HI.x||p.y>FOG_HI.y||p.z>FOG_HI.z)return 0;
    float x=(p.x-FOG_LO.x)/(FOG_HI.x-FOG_LO.x)*(STEAM_NX-1);
    float y=(p.y-FOG_LO.y)/(FOG_HI.y-FOG_LO.y)*(STEAM_NY-1);
    float z=(p.z-FOG_LO.z)/(FOG_HI.z-FOG_LO.z)*(STEAM_NZ-1);
    int ix=std::min(int(x),STEAM_NX-2),iy=std::min(int(y),STEAM_NY-2),iz=std::min(int(z),STEAM_NZ-2);
    float fx=x-ix,fy=y-iy,fz=z-iz,sum=0;
    for(int k=0;k<2;k++)for(int j=0;j<2;j++)for(int i=0;i<2;i++)
        sum+=steamGrid[(size_t(iz+k)*STEAM_NY+iy+j)*STEAM_NX+ix+i]*(i?fx:1-fx)*(j?fy:1-fy)*(k?fz:1-fz);
    return sum;
}
float trackingSteamMajorant(){return steamGrid.empty()?MAJORANT:steamGridMajorant;}
