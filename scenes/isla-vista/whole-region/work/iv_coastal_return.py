"""Qualified depth-dependent water return, separate from volume transport.

Lee et al.1998, DOI10.1364/AO.37.006329, equations16/21 supply a
nadir homogeneous-water return approximation. This original adapter maps it
to a bounded diffuse return beneath the existing native Fresnel surface.
It is not a calibrated Isla Vista water-quality model or an angular water BSDF.
"""
import numpy as np

ABSORPTION=np.array([[360,.30],[400,.22],[440,.15],[490,.085],[520,.074],[550,.085],[580,.15],[620,.27],[660,.46],[700,.70],[750,1.5],[800,2.0],[830,2.3]])
IOR=1.333
BACKSCATTER_550=.015 # m^-1, authored coastal scenario, not a measured local value
BACKSCATTER_EXPONENT=1.0
BOTTOM_CONTROLS=np.array([.1994211328,.1798690517,.1469720863])

def native_basis(wavelength_nm):
 w=np.asarray(wavelength_nm);b=np.exp(-.5*((w[:,None]-np.array([610,545,450]))/np.array([43,34,27]))**2);return b/(b.sum(1,keepdims=True)+1e-30)

def water_return(depth_m,wavelength_nm,solar_cosine=.7762033919365223):
 """Return effective native substrate albedo, plus separate audit terms.

The model's calibrated depth range starts at0.5m. At shallower depth this
adapter explicitly blends to the zero-depth Lambertian bottom limit; it does
not extrapolate the fitted negative column term to a black zero-depth bottom.
 """
 h=np.asarray(depth_m,float).reshape(-1,1);w=np.asarray(wavelength_nm,float).reshape(-1);assert np.all(h>=0) and 0<solar_cosine<=1
 a=np.interp(w,ABSORPTION[:,0],ABSORPTION[:,1]);bb=BACKSCATTER_550*(550/w)**BACKSCATTER_EXPONENT;alpha=a+bb;u=bb/alpha
 bottom=native_basis(w)@BOTTOM_CONTROLS;cos_underwater=np.sqrt(1-(1-solar_cosine**2)/IOR**2);dd=1/cos_underwater;dc=1.2*np.sqrt(1+2*u);db=1.1*np.sqrt(1+4.9*u);deep=(.070+.155*u**.752)*u
 def modeled(H):
  column=deep*(1-1.03*np.exp(-(dd+dc)*alpha*H));bed=.31*bottom*np.exp(-(dd+db)*alpha*H);return column,bed
 column,bed=modeled(np.maximum(h,.5));f=np.clip(h/.5,0,1);f=f*f*(3-2*f);rrs=f*(column+bed)+(1-f)*bottom/np.pi
 # Nadir internal-return parameter from the paper, with the native surface's
 # two Fresnel transmission factors left for the actual shader, not baked twice.
 effective=np.pi*rrs/(IOR**2*(1-1.562*rrs))
 assert np.isfinite(effective).all() and effective.min()>=0 and effective.max()<=1
 return effective,{'subsurface_rrs_sr-1':rrs,'column_rrs_sr-1':column,'bottom_rrs_sr-1':bed,'deep_rrs_sr-1':deep,'absorption_m-1':a,'backscatter_m-1':bb,'substrate_spectrum':bottom,'subsurface_solar_cosine':cos_underwater}
