"""CYBR ELEMENTS lava optics, ported to NumPy + CYBR LIGHT observer.
Original modules: lava_radiation.py and lava_material_texture.py.
The Mitsuba observer dependency is replaced by CYBR LIGHT's analytic fallback.
No claim of a thermomechanical lava simulation is made by this scene.
"""
import numpy as np

def observer(w):
    def g(m,a,b):
        t=(w-m)*np.where(w<m,a,b);return np.exp(-.5*t*t)
    return np.stack((1.056*g(599.8,.0264,.0323)+.362*g(442,.0624,.0374)-.065*g(501.1,.049,.0382),.821*g(568.8,.0213,.0247)+.286*g(530.9,.0613,.0322),1.217*g(437,.0845,.0278)+.681*g(459,.0385,.0725)),axis=-1)

def radiance(temperature):
    wavelength=np.arange(360.,831.);wave=wavelength*1e-9
    power=2*6.62607015e-34*299792458.**2/(wave**5*np.expm1(6.62607015e-34*299792458./(wave*1.380649e-23*temperature)))*1e-9
    xyz=np.trapezoid(power[:,None]*observer(wavelength),wavelength,axis=0)/106.856895
    transform=np.array([[3.240479,-1.537150,-.498535],[-.969256,1.875991,.041556],[.055648,-.204043,1.057311]])
    return np.maximum(0,transform@xyz)

def material_attributes(v,rest,f):
    world=np.stack([v[f[:,1]]-v[f[:,0]],v[f[:,2]]-v[f[:,0]]],axis=2)
    reference=np.stack([rest[f[:,1]]-rest[f[:,0]],rest[f[:,2]]-rest[f[:,0]]],axis=2)
    jacobian=reference@np.linalg.pinv(world,rcond=1e-10)
    weight=np.linalg.norm(np.cross(world[:,:,0],world[:,:,1]),axis=1)
    average=np.zeros((len(v),3,3));total=np.zeros(len(v))
    for corner in range(3):
        np.add.at(average,f[:,corner],jacobian*weight[:,None,None]);np.add.at(total,f[:,corner],weight)
    average/=np.maximum(total,1e-30)[:,None,None]
    return dict(reference=rest,reference_dx=average[:,:,0],reference_dy=average[:,:,1],reference_dz=average[:,:,2])
