"""Reference-visible timber fence frame and static hanging deck cords.
All dimensions are manually estimated; these are authored meshes, not a survey.
"""
import math
import numpy as np

def add(b,m):
 y=b.cfg.bluff_edge_y+920;start,end=-6500.,10200.
 # Brown timber framing is a conspicuous ocean-photo feature around the mesh.
 for i,x in enumerate(np.linspace(start,end,10)):
  b.box(f'photo_fence_timber_post_{i}',(95,100,1330),(x,y,620),m.WOOD,'fence','Photo-visible brown timber fence post; dimensions estimated')
  for j,z in enumerate([260,1165]):
   b.cylinder(f'photo_fence_bolt_{i}_{j}',(x,y-52,z),(x,y-60,z),9,m.METAL,'fasteners','Actual bolt end in timber rail joint',sides=10)
 for name,z,h in [('top',1160,85),('lower',240,65)]:
  for i,(a,c) in enumerate(zip(np.linspace(start,end,10)[:-1],np.linspace(start,end,10)[1:])):
   b.box(f'photo_fence_{name}_rail_{i}',(c-a-3,70,h),((a+c)/2,y+8,z),m.WOOD_LIGHT if i%4==1 else m.WOOD,'fence','Photo-visible timber rail supporting original chain-link mesh')
 b.cylinder('retained_left_metal_fence_top',(-15200,y,1160),(start,y,1160),15,m.METAL,'fence','Original left boundary metal rail retained',sides=12)
 # Several hanging deck cords are visible in the reference. Their suspended
 # shapes are authored static curves; no cloth/rope solver is asserted.
 for i,(x,width,sag) in enumerate([(4720,160,1420),(5080,250,1740),(5280,115,1160)]):
  points=[]
  for j in range(41):
   t=j/40;points.append((x+width*t+24*math.sin(math.pi*t*2),-2015-35*math.sin(math.pi*t),3600-sag*math.sin(math.pi*t)))
  for j,(a,c) in enumerate(zip(points,points[1:])):
   b.cylinder(f'photo_deck_cord_{i}_{j}',a,c,4.2,m.WHITE,'patio_objects','Reference-visible pale hanging cord, authored static curve',sides=6)
 return {'timber_fence_posts':10,'timber_fence_rails':18,'hanging_cord_loops':3,'reference_basis':'Original ocean photograph shows brown timber posts and two timber rail bands framing chain-link, and pale cords hanging over the ocean-side deck rail. Dimensions and curve positions are manual estimates.'}

def excludes_base(name):
 if name=='bluff_fence_top':return True
 if name.startswith('bluff_fence_post_'):
  i=int(name.rsplit('_',1)[1]);return -15200+i*1830>=-6500
 return False
