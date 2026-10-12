// Original CYBR compiled-material adapter. See iv_coastal_return.py and receipt.
#include <algorithm>
#include <cmath>

extern "C" void cybr_shader(double nm,double depth_u,double,const double*,double* value,double* gradient){
 constexpr double wavelength[]={360,400,440,490,520,550,580,620,660,700,750,800,830};
 constexpr double absorption[]={.30,.22,.15,.085,.074,.085,.15,.27,.46,.70,1.5,2.,2.3};
 constexpr double ior=1.333,solar_cos=.7762033919365223;
 double a=absorption[0];
 if(nm>=wavelength[12])a=absorption[12];
 else if(nm>wavelength[0]){int k=1;while(wavelength[k]<nm)++k;double t=(nm-wavelength[k-1])/(wavelength[k]-wavelength[k-1]);a=absorption[k-1]*(1-t)+absorption[k]*t;}
 double bb=.015*550/nm,alpha=a+bb,u=bb/alpha;
 double red=std::exp(-.5*std::pow((nm-610)/43.,2));
 double green=std::exp(-.5*std::pow((nm-545)/34.,2));
 double blue=std::exp(-.5*std::pow((nm-450)/27.,2));
 double bottom=(.1994211328*red+.1798690517*green+.1469720863*blue)/(red+green+blue+1e-30);
 double dd=1/std::sqrt(1-(1-solar_cos*solar_cos)/(ior*ior));
 double dc=1.2*std::sqrt(1+2*u),db=1.1*std::sqrt(1+4.9*u);
 double deep=(.070+.155*std::pow(u,.752))*u;
 double h=std::max(0.,depth_u),H=std::max(.5,h);
 double column=deep*(1-1.03*std::exp(-(dd+dc)*alpha*H));
 double bed=.31*bottom*std::exp(-(dd+db)*alpha*H);
 double f=std::clamp(h/.5,0.,1.);f=f*f*(3-2*f);
 double rrs=f*(column+bed)+(1-f)*bottom/3.14159265358979323846;
 *value=3.14159265358979323846*rrs/(ior*ior*(1-1.562*rrs));
 // There are no exposed differentiable parameters; this shader depends on
 // wavelength and interpolated measured depth only. No AD optics claim.
 for(int i=0;i<3;i++)gradient[i]=0.;
}
