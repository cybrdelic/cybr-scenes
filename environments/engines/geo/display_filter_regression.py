#!/usr/bin/env python3
"""Regression cases for the explicitly biased, non-neural sky display filter."""
from pathlib import Path
import json,sys
import numpy as np
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'cybr-geo/examples/three_scenes'))
from finish import robust_sky_outliers

def run():
    rgb=np.full((17,17,3),.4,np.float32);g=np.zeros((17,17,9),np.float32)
    g[:,:,8]=-1;counts=np.full((17,17),128,np.uint16)
    metadata={'spp':128,'camera_origin_m':[0,0,0],'camera_target_m':[0,1,0],
              'sun_direction':[0,-1,1],'horizontal_fov_degrees':65}
    rgb[8,8]=[-2,4,67];g[8,8,7]=50
    fixed,mask=robust_sky_outliers(rgb,g,metadata,counts)
    assert mask.sum()==1 and np.allclose(fixed[8,8],.4)
    g[8,8,8]=1;other,mask=robust_sky_outliers(rgb,g,metadata,counts)
    assert not mask.any() and np.array_equal(rgb,other)
    g[8,8,8]=-1;counts[8,8]=320
    other,mask=robust_sky_outliers(rgb,g,metadata,counts)
    assert not mask.any() and np.array_equal(rgb,other)
    counts[:]=128;metadata['sun_direction']=[0,1,0]
    other,mask=robust_sky_outliers(rgb,g,metadata,counts)
    assert not mask.any() and np.array_equal(rgb,other)
    metadata['sun_direction']=[0,-1,1];rgb[7:10,7:10]=50;g[7:10,7:10,7]=50
    other,mask=robust_sky_outliers(rgb,g,metadata,counts)
    assert not mask.any() and np.array_equal(rgb,other)
    return {'scope':'Display-filter regression, not a transport correction',
            'isolated_spike_rejected':True,'geometry_untouched':True,
            'water_pixels_untouched':True,'sun_neighbourhood_untouched':True,
            'extended_highlights_untouched':True,'passed':True}
if __name__=='__main__':
    value=run();(ROOT/'verification/display_filter_test.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(value,indent=2))
