"""Continuous-wavelength optics for Mitsuba 3's CPU spectral backend.

Each camera path carries one wavelength repeated in Mitsuba's four slots.
Repeating both wavelength and its reciprocal-PDF weight preserves the film's
four-slot average. Unlike treating four dispersing wavelengths as a single ray,
this permits a different, physically consistent refracted path at every lambda.
"""
import numpy as np
import drjit as dr
import mitsuba as mi

mi.set_variant('llvm_ad_spectral')
dr.set_thread_count(8)


def quartz_index(wavelength_nm):
    """Ghosh (1999) ordinary-ray alpha quartz, wavelength in nm.

    n^2 - 1 = A + B*l^2/(l^2-C) + D*l^2/(l^2-E), l in micrometers.
    Scalar ordinary-ray approximation: birefringence is not modeled.
    https://doi.org/10.1016/S0030-4018(99)00091-7
    https://refractiveindex.info/?shelf=main&book=SiO2&page=Ghosh-o
    """
    l2 = (wavelength_nm * .001) ** 2
    return dr.sqrt(1.28604141 + 1.07044083*l2/(l2-.0100585997)
                   + 1.10202242*l2/(l2-100.0))


class HeroWavelengthCamera(mi.Sensor):
    def __init__(self, props):
        super().__init__(props)
        self.quadrature = props.has_property('wavelength')
        self.wavelength = dr.opaque(mi.Float,props.get('wavelength',550.0))
        self.inner = mi.load_dict({
            'type': 'thinlens',
            'to_world': props['to_world'],
            'fov': props.get('fov', 35.0),
            'focus_distance': props.get('focus_distance', 12.0),
            'aperture_radius': props.get('aperture_radius', .015),
            'film': self.film(),
            'sampler': self.sampler(),
        })

    def sample_ray(self, time, sample1, sample2, sample3, active=True):
        ray, weight = self.inner.sample_ray(time, sample1, sample2, sample3, active)
        if self.quadrature:
            ray.wavelengths=mi.Spectrum(self.wavelength)
            return ray,mi.Spectrum(470.0)
        ray.wavelengths = mi.Spectrum(ray.wavelengths[0])
        return ray, mi.Spectrum(weight[0])

    def sample_ray_differential(self, time, sample1, sample2, sample3, active=True):
        ray, weight = self.inner.sample_ray_differential(time, sample1, sample2, sample3, active)
        if self.quadrature:
            ray.wavelengths=mi.Spectrum(self.wavelength)
            return ray,mi.Spectrum(470.0)
        ray.wavelengths = mi.Spectrum(ray.wavelengths[0])
        return ray, mi.Spectrum(weight[0])

    def bbox(self):
        return self.inner.bbox()

    def traverse(self,cb):
        super().traverse(cb)
        cb.put('wavelength',self.wavelength,mi.ParamFlags.NonDifferentiable)

    def to_string(self):
        return 'HeroWavelengthCamera[continuous spectral paths, duplicated slots]'


class QuartzDielectric(mi.BSDF):
    def __init__(self, props):
        super().__init__(props)
        r = mi.BSDFFlags.DeltaReflection | mi.BSDFFlags.FrontSide | mi.BSDFFlags.BackSide
        t = mi.BSDFFlags.DeltaTransmission | mi.BSDFFlags.FrontSide | mi.BSDFFlags.BackSide
        self.m_components = [r, t]
        self.m_flags = r | t
        self.absorption = props.get('absorption', .0)
        self.amethyst = props.get('amethyst', .0)
        self.external_ior = props.get('external_ior', 1.000277)
        self.fixed_index = props.get('fixed_index', 0.0)
        self.cavity_ior = props.get('cavity_ior', 0.0)
        self.dispersion_strength = dr.opaque(mi.Float,props.get('dispersion_strength',1.0))

    def sample(self, ctx, si, sample1, sample2, active=True):
        wavelength = si.wavelengths[0]
        index = quartz_index(550.0) + self.dispersion_strength * (quartz_index(wavelength)-quartz_index(550.0))
        eta = (self.fixed_index if self.fixed_index > 0 else index) / self.external_ior
        if self.cavity_ior > 0:
            eta = self.cavity_ior / (self.fixed_index if self.fixed_index > 0 else index)
        F, ct, eta_it, eta_ti = mi.fresnel(si.wi.z, eta)
        allow_r = ctx.is_enabled(mi.BSDFFlags.DeltaReflection, 0)
        allow_t = ctx.is_enabled(mi.BSDFFlags.DeltaTransmission, 1)
        pr = dr.select(allow_t, dr.select(allow_r, F, 0.0), 1.0)
        reflected = (sample1 < pr) & active
        bs = mi.BSDFSample3f()
        bs.wo = dr.select(reflected, mi.reflect(si.wi), mi.refract(si.wi, ct, eta_ti))
        bs.pdf = dr.select(reflected, pr, 1.0-pr)
        bs.eta = dr.select(reflected, 1.0, eta_it)
        bs.sampled_component = dr.select(reflected, mi.UInt32(0), mi.UInt32(1))
        bs.sampled_type = dr.select(reflected, mi.UInt32(+mi.BSDFFlags.DeltaReflection), mi.UInt32(+mi.BSDFFlags.DeltaTransmission))
        correction = dr.square(eta_ti) if ctx.mode == mi.TransportMode.Radiance else 1.0
        weight = dr.select(reflected, F, (1.0-F)*correction) / dr.maximum(bs.pdf, 1e-12)
        # Segment absorption in a closed, nonintersecting crystal. The camera
        # arrives at an internal interface from the back side of its surface.
        # The violet absorption profile is artistic, not measured amethyst data.
        sigma = self.absorption * (.55 + .65*dr.exp(-.5*((si.wavelengths-440)/105)**2))
        sigma += self.amethyst * dr.exp(-.5*((si.wavelengths-545.0)/52.0)**2)
        distance = dr.select(si.wi.z < 0.0, dr.maximum(si.t, 0.0), 0.0)
        weight *= dr.exp(-sigma*distance)
        return bs, mi.Spectrum(dr.select(active, weight, 0.0))

    def traverse(self,cb):
        cb.put('dispersion_strength',self.dispersion_strength,mi.ParamFlags.NonDifferentiable)

    def eval(self, ctx, si, wo, active=True):
        return mi.Spectrum(0.0)

    def pdf(self, ctx, si, wo, active=True):
        return mi.Float(0.0)

    def eval_pdf(self, ctx, si, wo, active=True):
        return mi.Spectrum(0.0), mi.Float(0.0)

    def to_string(self):
        return 'QuartzDielectric[Ghosh ordinary-ray dispersion, Fresnel, Beer attenuation]'


mi.register_sensor('hero_wavelength', lambda p: HeroWavelengthCamera(p))
mi.register_bsdf('spectral_quartz', lambda p: QuartzDielectric(p))


def smoke_test():
    camera = mi.load_dict({'type':'hero_wavelength',
        'to_world':mi.ScalarTransform4f().look_at(origin=[0,-6,3],target=[0,0,.4],up=[0,0,1]),
        'focus_distance':6.4, 'aperture_radius':0.0,
        'film':{'type':'hdrfilm','width':160,'height':120},
        'sampler':{'type':'independent','sample_count':16}})
    scene = mi.load_dict({'type':'scene','integrator':{'type':'path','max_depth':16},
        'sensor':camera,'environment':{'type':'constant','radiance':1.0},
        'sphere':{'type':'sphere','bsdf':{'type':'spectral_quartz'}}})
    a=np.asarray(mi.render(scene,spp=16))
    print('render',a.shape,'finite',np.isfinite(a).all(),'mean',a.mean(axis=(0,1)),flush=True)
    print('ior',[(l,float(quartz_index(l))) for l in [400,550,700]],flush=True)
    mi.util.write_bitmap('smoke_test.png',a)


if __name__=='__main__':
    smoke_test()
