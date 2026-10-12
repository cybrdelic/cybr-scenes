"""Metric authored maintenance/traffic history for a representative desert road.

No measured age, traffic count or durability prediction. Footprints are world XY
and remain independent of cameras, tiles and raster resolution. The shared field
is evaluated beneath dust and beneath/through original paint on the same road
surface; it does not create an intersecting overlay or enlarge aggregate.
"""
from __future__ import annotations
import numpy as np

# Convex flush repair footprints, metres. The first intersects the old edge
# stripe, so the old paint is absent over that patch; it has not been restriped.
PATCHES = (
    ((-3.047, 3.36), (-2.393, 3.42), (-2.336, 5.23), (-2.966, 5.40)),
    ((-1.274, 12.60), (-.412, 12.47), (-.353, 15.48), (-1.184, 15.69)),
    ((1.514, 27.2), (2.745, 27.32), (2.683, 29.24), (1.552, 29.14)),
)
REPAIR_TRANSITION_M = .006
TRACK_CENTRES_M = (1.00, 2.25)
TRACK_CORE_HALF_WIDTH_M = .115
TRACK_SHOULDER_HALF_WIDTH_M = .255
BINDER_REFERENCE_LINEAR = (.047, .047, .045)
AGE_ROUGHNESS = .86
POLISH_ROUGHNESS_REDUCTION = .115


def smooth(a, b, x):
    t = np.clip((np.asarray(x) - a) / (b - a), 0., 1.)
    return t*t*(3.-2.*t)


def polygon_inset(x, y, polygon):
    """Positive inside convex counter-clockwise polygon; exact edge distance."""
    ds=[]
    for a,b in zip(polygon, polygon[1:]+polygon[:1]):
        dx,dy=b[0]-a[0],b[1]-a[1]
        ds.append((dx*(y-a[1])-dy*(x-a[0]))/np.hypot(dx,dy))
    return np.minimum.reduce(ds)


def fields(x, y, crown=None):
    x,y=np.broadcast_arrays(np.asarray(x,float), np.asarray(y,float))
    # Gentle shared driver-path drift is authored geometry of usage, not a
    # randomized albedo overlay. Centimetric drift over tens of metres.
    drift=.055*np.sin(y*.061+.4)+.019*np.sin(y*.147+1.6)
    ax=np.abs(x)-drift
    d=np.minimum(abs(ax-TRACK_CENTRES_M[0]), abs(ax-TRACK_CENTRES_M[1]))
    traffic=1-smooth(TRACK_CORE_HALF_WIDTH_M,TRACK_SHOULDER_HALF_WIDTH_M,d)
    crown=np.zeros_like(x) if crown is None else np.broadcast_to(crown,x.shape)
    # At most 1.2 mm boundary excursion, coherent with actual source aggregate.
    patches=[smooth(-REPAIR_TRANSITION_M,REPAIR_TRANSITION_M,
                    polygon_inset(x,y,p)+.0012*(crown-.5)) for p in PATCHES]
    repair=np.maximum.reduce(patches)
    # Binder exposure is supplied separately from the native source albedo.
    age=(.60-.30*traffic)*(1-repair)
    return dict(traffic=traffic,repair=repair,age=age,
                paint_retention=1-repair)
