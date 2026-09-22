// Wavelength-resolved single-scattering atmosphere LUT. No HDRI or backplate.
// Quadratic near-observer quadrature resolves the shallow aerosol layer.
// Spherical atmosphere; Rayleigh + Henyey-Greenstein aerosol scattering.
// This deliberately does not claim a full multiple-scattering sky solution.
constexpr int SKY_W=384,SKY_H=144;
std::vector<Spec> skyLUT;
Spec upperSun;
double atmosphereExit(double x,double y,double z,V d) {
    constexpr double rt=6460000.;
    double b=x*d.x+y*d.y+z*d.z;
    double c=x*x+y*y+z*z-rt*rt;
    return -b+std::sqrt(std::max(0.,b*b-c));
}
void opticalDepthToSun(double x,double y,double z,double &rr,double &mm){
    double length=atmosphereExit(x,y,z,SUN);
    rr=mm=0;
    for(int i=0;i<32;i++){
        double a=double(i)/32,b=double(i+1)/32;
        double lo=a*a*length,hi=b*b*length,ds=hi-lo,t=(lo+hi)*.5;
        double px=x+SUN.x*t,py=y+SUN.y*t,pz=z+SUN.z*t;
        double h=std::max(0.,std::sqrt(px*px+py*py+pz*pz)-6360000.);
        rr+=std::exp(-h/8000.)*ds;mm+=std::exp(-h/1200.)*ds;
    }
}
void buildPhysicalSky(){
    upperSun=blackbody(5778.f)*9.0f;
    skyLUT.resize(SKY_W*SKY_H);
    double sr,sm;opticalDepthToSun(0,0,6360001.,sr,sm);
    for(int k=0;k<NBANDS;k++){
        double wavelength=WL0+(k+.5)*DL;
        double br=13.5e-6*std::pow(550./wavelength,4.08);
        double bm=2.8e-6*std::pow(550./wavelength,1.3);
        solar.v[k]=upperSun.v[k]*std::exp(-br*sr-bm*sm)/SUN_SOLID;
    }
    #pragma omp parallel for schedule(dynamic,1)
    for(int j=0;j<SKY_H;j++){
        double theta=((j+.5)/SKY_H)*(PI*.5),cz=std::cos(theta),sz=std::sin(theta);
        for(int i=0;i<SKY_W;i++){
            double phi=((i+.5)/SKY_W)*2*PI;
            V d(sz*std::cos(phi),sz*std::sin(phi),cz);
            double maxT=atmosphereExit(0,0,6360001.,d);
            double viewR=0,viewM=0,c=dot(d,SUN);
            double pr=3*(1+c*c)/(16*PI),g=.76;
            double pm=(1-g*g)/(4*PI*std::pow(1+g*g-2*g*c,1.5));
            Spec sum;
            for(int s=0;s<64;s++){
                double a=double(s)/64,b=double(s+1)/64;
                double lo=a*a*maxT,hi=b*b*maxT,ds=hi-lo,t=(lo+hi)*.5;
                double x=t*d.x,y=t*d.y,z=6360001.+t*d.z;
                double h=std::max(0.,std::sqrt(x*x+y*y+z*z)-6360000.);
                double dr=std::exp(-h/8000.),dm=std::exp(-h/1200.);
                viewR+=dr*ds*.5;viewM+=dm*ds*.5;
                double sr,sm;opticalDepthToSun(x,y,z,sr,sm);
                for(int k=0;k<NBANDS;k++){
                    double w=WL0+(k+.5)*DL,br=13.5e-6*std::pow(550./w,4.08),bm=2.8e-6*std::pow(550./w,1.3);
                    double tr=std::exp(-br*(viewR+sr)-bm*(viewM+sm));
                    sum.v[k]+=upperSun.v[k]*tr*(br*dr*pr+.93*bm*dm*pm)*ds;
                }
                viewR+=dr*ds*.5;viewM+=dm*ds*.5;
            }
            skyLUT[j*SKY_W+i]=sum;
        }
    }
}
Spec physicalSky(V d){
    if(d.z<0)return upperSun*.009f;
    float u=std::atan2(d.y,d.x)/(2*PI);if(u<0)u+=1;
    float v=std::acos(clamp(d.z))/(PI*.5f);
    float xx=u*SKY_W-.5f,yy=clamp(v*SKY_H-.5f,0.f,float(SKY_H-1));
    int x=int(std::floor(xx)),y=int(std::floor(yy));float fx=xx-x,fy=yy-y;
    int x0=(x+SKY_W)%SKY_W,x1=(x0+1)%SKY_W,y1=std::min(y+1,SKY_H-1);
    return (skyLUT[y*SKY_W+x0]*(1-fx)+skyLUT[y*SKY_W+x1]*fx)*(1-fy)
         +(skyLUT[y1*SKY_W+x0]*(1-fx)+skyLUT[y1*SKY_W+x1]*fx)*fy;
}
