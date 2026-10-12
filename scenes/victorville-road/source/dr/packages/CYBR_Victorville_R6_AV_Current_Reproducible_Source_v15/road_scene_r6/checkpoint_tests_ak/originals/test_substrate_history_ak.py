"""Focused source-only tests and geometric projection receipt for AK history."""
import hashlib
import json
from pathlib import Path
import sys
import unittest
import numpy as np
from substrate_history_ak import HistorySpec, UNIT_NAMES, substrate_fields, summary

ROOT=Path(__file__).resolve().parents[1]
CAP=ROOT/'captures/ai_sorted_support_context_preview'


class HistoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.f=dict(np.load(CAP/'AH_FIELDS.npz'))
        x,y=cls.f['x_m'],cls.f['y_m'];xx,yy=np.meshgrid(x,y)
        cls.xy=np.stack((xx,yy),axis=-1)
        cls.v=substrate_fields(cls.xy,cls.f)

    def test_outputs_finite_bounded(self):
        for k,v in self.v.items():
            self.assertTrue(np.isfinite(v).all(),k)
            self.assertGreaterEqual(float(v.min()),0,k)
        self.assertLessEqual(float(self.v['prior_fine_cover_m'].max()),.0025)
        for k in ('armor_exposure','compaction','unit_weights','historical_wash','historical_winnowing','historical_sand_opportunity','grading_strength','domain_strength'):
            self.assertLessEqual(float(self.v[k].max()),1,k)

    def test_unit_partition(self):
        np.testing.assert_allclose(self.v['unit_weights'].sum(-1),self.v['domain_strength'],atol=1e-15)

    def test_recent_storms_not_inputs(self):
        f={k:v for k,v in self.f.items() if k in ('x_m','y_m','foundation_z_m')}
        a=substrate_fields(self.xy,f)
        for k,v in self.v.items(): np.testing.assert_array_equal(a[k],v)
        f.update(sediment_delta_m=np.full_like(f['foundation_z_m'],99),retained_deposit_by_class_m=np.full(f['foundation_z_m'].shape+(3,),88),lag=np.zeros_like(f['foundation_z_m']))
        for k,v in substrate_fields(self.xy,f).items(): np.testing.assert_array_equal(v,self.v[k])

    def test_actual_gradient_changes_exposure(self):
        x,y=self.f['x_m'],self.f['y_m'];xx,yy=np.meshgrid(x,y)
        f=dict(self.f);f['foundation_z_m']=-.03*xx-.02*yy
        a=substrate_fields(self.xy,f)
        self.assertGreater(float(np.max(abs(a['armor_exposure']-self.v['armor_exposure']))),.1)

    def test_outside_and_rim_zero(self):
        x,y=self.f['x_m'],self.f['y_m']
        p=np.array([[x[0]-.01,1],[x[-1]+.01,1],[-4,y[0]-.01],[-4,y[-1]+.01],[x[0],1]])
        for k,v in substrate_fields(p,self.f).items(): np.testing.assert_array_equal(v,0)

    def test_no_inputs_mutated(self):
        before={k:v.tobytes() for k,v in self.f.items()}
        substrate_fields(self.xy,self.f)
        self.assertEqual(before,{k:v.tobytes() for k,v in self.f.items()})

    def test_query_chunk_and_order_invariance(self):
        p=self.xy.reshape(-1,2)[::13];v=substrate_fields(p,self.f)
        parts=[substrate_fields(chunk,self.f) for chunk in np.array_split(p,7)]
        reverse=substrate_fields(p[::-1],self.f)
        for k in v:
            np.testing.assert_array_equal(v[k],np.concatenate([a[k] for a in parts]))
            np.testing.assert_array_equal(v[k],reverse[k][::-1])

    def test_skin_variability_exists_without_recent_storms(self):
        cover=self.v['prior_fine_cover_m'];active=self.v['domain_strength']>.99
        self.assertLess(float(np.quantile(cover[active],.2)),.0001)
        self.assertGreater(float(cover[active].max()),.0015)
        self.assertGreater(float(np.ptp(self.v['armor_exposure'][active])),.5)

    def test_connected_and_downhill_authored_routes(self):
        s=summary(self.f)
        for r in s['drainage_routes']:
            self.assertGreater(r['net_foundation_drop_m'],0)
            self.assertLess(r['maximum_local_uphill_increment_m'],1e-8)

    def test_metric_centimeter_transition_is_continuous(self):
        x=np.linspace(-5.05,-3.55,1501);p=np.c_[x,np.full(x.shape,.5)]
        v=substrate_fields(p,self.f)
        self.assertLess(float(np.max(abs(np.diff(v['prior_fine_cover_m'])))),.0001)
        self.assertLess(float(np.max(abs(np.diff(v['armor_exposure'])))),.08)

    def test_invalid_inputs_and_spec_rejected(self):
        with self.assertRaises(ValueError):substrate_fields(np.array([[np.nan,1.]]),self.f)
        with self.assertRaises(ValueError):substrate_fields(self.xy,self.f,HistorySpec(maximum_prior_cover_m=.005))
        f=dict(self.f);f['foundation_z_m']=np.zeros((2,2))
        with self.assertRaises(ValueError):substrate_fields(self.xy,f)
        with self.assertRaises(ValueError):substrate_fields(self.xy,self.f,HistorySpec(drainage_reaches=()))


def write_receipt():
    """Rasterized projected footprints, no Blender and NO occlusion testing."""
    from PIL import Image, ImageDraw
    out=ROOT/'receipts/ak_substrate_history';out.mkdir(exist_ok=True)
    f=dict(np.load(CAP/'AH_FIELDS.npz'));x,y=f['x_m'],f['y_m']
    # 2.5 cm diagnostic tessellation; actual foundation samples remain 5 cm.
    xx=np.linspace(x[0],x[-1],2*(len(x)-1)+1)
    yy=np.linspace(y[0],y[-1],2*(len(y)-1)+1)
    gx,gy=np.meshgrid(xx,yy);xy=np.stack((gx,gy),axis=-1)
    from substrate_history_ak import _sample
    p=xy.reshape(-1,2)
    z=_sample(f['foundation_z_m']+f['sediment_delta_m'],p,x,y)
    job=json.loads((CAP/'INTERNAL_PANEL.png.json').read_text())
    camera=job['effective_capture']['camera'];w,h=job['resolution']
    world=np.c_[p,z,np.ones(len(p))]
    local=world@np.linalg.inv(np.array(camera['matrix_world'])).T
    depth=-local[:,2]
    uv=np.c_[w*(.5+local[:,0]/depth*camera['lens']/camera['sensor_width']),h/2-local[:,1]/depth*(camera['lens']/camera['sensor_width'])*w].reshape(xy.shape)
    depth=depth.reshape(gx.shape)
    centers=np.stack(np.meshgrid((xx[:-1]+xx[1:])/2,(yy[:-1]+yy[1:])/2),axis=-1)
    v=substrate_fields(centers,f);cover=v['prior_fine_cover_m']
    masks={'domain':v['domain_strength']>0,
           'cover_gt_0p2mm':cover>.0002,'cover_gt_0p6mm':cover>.0006,
           'cover_gt_1p5mm':cover>.0015,'armor_gt_half':v['armor_exposure']>.5}
    for k,name in enumerate(UNIT_NAMES):masks['unit_'+name]=np.argmax(v['unit_weights'],axis=-1)==k
    roi=(centers[...,0]>=-4.8)&(centers[...,0]<=-3.6)&(centers[...,1]>=0)&(centers[...,1]<=4)
    masks['near_world_roi']=roi
    rendered={};projection={}
    for name,m in masks.items():
        im=Image.new('L',(w,h));draw=ImageDraw.Draw(im)
        for iy,ix in zip(*np.where(m)):
            q=((iy,ix),(iy,ix+1),(iy+1,ix+1),(iy+1,ix))
            if min(depth[a] for a in q)>camera['clip_start']:
                draw.polygon([tuple(uv[a]) for a in q],fill=255)
        a=np.array(im)>0;rendered[name]=a;rows,cols=np.where(a)
        im.save(out/(name+'.png'))
        projection[name]=dict(projected_pixels=int(a.sum()),fraction_of_frame=float(a.mean()),
            pixel_bounds_xy=[[int(cols.min()),int(rows.min())],[int(cols.max()),int(rows.max())]] if len(rows) else [],
            mask_file=str((out/(name+'.png')).relative_to(ROOT)))
    base=np.array(Image.open(CAP/'INTERNAL_PANEL.png').convert('RGB'))
    colors={'unit_armor_grit':(230,120,70),'unit_compacted_fines':(95,175,225),'unit_thin_sandy_cover':(250,220,95)}
    for k,c in colors.items():base[rendered[k]]=(base[rendered[k]]*.40+np.array(c)*.60).astype(np.uint8)
    Image.fromarray(base).save(out/'projected_units_overlay_NO_OCCLUSION.png')
    report=summary(f)
    report.update(projection=dict(camera=camera,resolution=[w,h],diagnostic_tessellation_m=.025,
        actual_foundation_sample_spacing_m=.05,occlusion_tested=False,
        caveat='These are projected footprints, not visibility proof. No terrain, rock, grass or road occlusion is tested. Overlay colors are diagnostic categories only; no material color overlay is authored.',
        masks=projection,overlay_file=str((out/'projected_units_overlay_NO_OCCLUSION.png').relative_to(ROOT))),
        validation=dict(focused_test_count=11,
            test_command='OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONPATH=src python -m unittest src/test_substrate_history_ak.py -v',
            scene_or_render_run=False,
            recent_storm_independence_tested=True,
            connected_downhill_centerlines_tested=True),
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (CAP/'AH_FIELDS.npz',CAP/'INTERNAL_PANEL.png.json',ROOT/'src/substrate_history_ak.py')})
    (out/'AK_SUBSTRATE_HISTORY.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'whole_domain':report['whole_domain'],'near_visible_world_roi':report['near_visible_world_roi'],'projection':projection},indent=2))


if __name__=='__main__':
    if '--receipt' in sys.argv:
        write_receipt()
    else:unittest.main()
