// SPDX-License-Identifier: GPL-2.0-only
// The including renderer supplies Vec3, sky(), pi, RNG and power_heuristic.
// Full-sphere, piecewise-constant HDR importance sampling, exact cell solid angle.
#pragma once
constexpr int ENV_W=128,ENV_H=64;
std::array<double,ENV_W*ENV_H> env_mass{},env_cdf{};
void prepare_environment_sampler(){
 double total=0;
 for(int y=0;y<ENV_H;y++){double t0=pi*y/ENV_H,t1=pi*(y+1)/ENV_H,ct=.5*(std::cos(t0)+std::cos(t1)),st=std::sqrt(std::max(0.,1-ct*ct));
  double omega=(2*pi/ENV_W)*(std::cos(t0)-std::cos(t1));
  for(int x=0;x<ENV_W;x++){double ph=2*pi*(x+.5)/ENV_W;Vec3 d(st*std::cos(ph),ct,st*std::sin(ph));int i=y*ENV_W+x;
   env_mass[i]=(std::max(0.,lum(sky(d)))+1e-6)*omega;total+=env_mass[i];env_cdf[i]=total;
  }
 }
 for(int i=0;i<ENV_W*ENV_H;i++){env_mass[i]/=total;env_cdf[i]/=total;}env_cdf.back()=1;
}
double environment_pdf(Vec3 d){
 double phi=std::atan2(d.z,d.x);if(phi<0)phi+=2*pi;
 int x=std::clamp(int(phi/(2*pi)*ENV_W),0,ENV_W-1),y=std::clamp(int(std::acos(std::clamp(d.y,-1.,1.))/pi*ENV_H),0,ENV_H-1);
 double omega=(2*pi/ENV_W)*(std::cos(pi*y/ENV_H)-std::cos(pi*(y+1)/ENV_H));return env_mass[y*ENV_W+x]/omega;
}
Vec3 sample_environment(RNG&r,double&pdf){
 auto it=std::upper_bound(env_cdf.begin(),env_cdf.end(),r.uniform());int i=std::min(int(env_cdf.size())-1,int(it-env_cdf.begin())),y=i/ENV_W,x=i%ENV_W;
 double phi=2*pi*(x+r.uniform())/ENV_W,c0=std::cos(pi*y/ENV_H),c1=std::cos(pi*(y+1)/ENV_H),ct=c0+(c1-c0)*r.uniform(),st=std::sqrt(std::max(0.,1-ct*ct));
 pdf=env_mass[i]/((2*pi/ENV_W)*(c0-c1));return Vec3(st*std::cos(phi),ct,st*std::sin(phi));
}
