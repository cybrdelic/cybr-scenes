"""Extract granular support masks from the already supplied CC0 photograph.
This is authored microgeometry, not measured height or photogrammetry.
"""
from pathlib import Path
import json
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, distance_transform_edt
from skimage.segmentation import watershed, find_boundaries
from skimage.feature import peak_local_max
p=Path(__file__).parent/'assets'
g=np.asarray(Image.open(p/'gravel_cc0_original.png').convert('L'),dtype=float)/255
# Pad with wrapping for a seamless support field.
g=np.pad(g,32,mode='wrap');s=gaussian_filter(g,1)
coords=peak_local_max(s,min_distance=5,threshold_abs=.45)
markers=np.zeros(g.shape,dtype=np.int32);markers[tuple(coords.T)]=np.arange(len(coords))+1
labels=watershed(-s,markers)
bound=find_boundaries(labels,mode='thick')
mask=(~bound)&(s>.26)
d=distance_transform_edt(mask)
height=.0052*(1-np.exp(-d/2.5))+.00030*(g-gaussian_filter(g,3))
height=gaussian_filter(height,.45)[32:-32,32:-32].astype('<f4')
np.save(p/'granular_relief.npy',height)
# Native mipmap payload, raw metre elevations; no sRGB transfer on height.
with (p/'granular_relief.bin').open('wb') as f:
 np.array([0x31465247,height.shape[1],height.shape[0]],dtype='<u4').tofile(f);height.tofile(f)
(p/'granular_relief_provenance.json').write_text(json.dumps({'source':'Existing supplied gravel_cc0_original.png','method':'Watershed support masks and authored 5.2 mm rounded granular caps','measured_height':False,'image_generation':False,'height_min_m':float(height.min()),'height_max_m':float(height.max())},indent=2))
print(height.shape,height.min(),height.max())
