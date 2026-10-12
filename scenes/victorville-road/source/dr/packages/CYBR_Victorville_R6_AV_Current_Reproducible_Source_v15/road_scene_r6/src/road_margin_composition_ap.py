"""AP shared, authored road-margin chronology, not a validated transport solve.
One metric field drives existing fine/gravel exposure and layered plant placement.
Unequal old runoff reaches join one outward swale; grading erases their inner
ends. No photo input, independent texture noise, terrain displacement, or
change to original asphalt/R5D recipes. Actual surface slope gates receivers.
"""
import numpy as np

def smooth(a,b,v):
 t=np.clip((np.asarray(v)-a)/(b-a),0,1);return t*t*(3-2*t)

# World metres, unequal connected reaches. Width increases toward the outer
# receiver. They describe historical sorting, not this morning's simulated rain.
REACHES=(
 ((-3.39,.30,.075),(-3.77,.62,.13),(-4.25,1.16,.26),(-4.65,2.4,.39),(-5.10,4.1,.53)),
 ((-3.42,3.60,.08),(-3.90,3.9,.19),(-4.40,4.3,.31),(-5.10,4.1,.53)),
 ((-3.40,6.20,.10),(-4.08,6.85,.23),(-4.80,8.2,.40),(-5.65,10.8,.62)),
 ((-3.43,12.0,.10),(-4.20,12.9,.25),(-5.65,10.8,.62)),
 ((-3.42,18.8,.13),(-4.45,19.6,.35),(-6.2,22.1,.74)),
 ((-3.46,27.5,.15),(-4.55,28.2,.37),(-6.5,31.8,.90)),
 ((-3.43,39.,.17),(-4.70,40.3,.43),(-7.1,43.5,1.1)),
 ((-3.44,56.,.20),(-5.1,57.4,.56),(-8.,62.,1.3)),
)

def fields(xy,gradient=None):
 p=np.asarray(xy,float).reshape(-1,2);d=-p[:,0]-3.2;y=p[:,1]
 # Nonperiodic maintenance reach, a historical cut-and-graded surface zone.
 outer=np.interp(y,[-1,0,1.4,3.2,6.0,10,17,28,43,65,85],[.68,.51,.93,.64,.91,1.10,.80,1.37,1.05,1.60,1.2])
 grade=1-smooth(outer-.22,outer+.28,d)
 core=np.zeros(len(p));bank=core.copy();receiving=core.copy()
 grad=np.zeros_like(p) if gradient is None else np.asarray(gradient,float)
 for reach in REACHES:
  r=np.asarray(reach)
  for a,b in zip(r[:-1],r[1:]):
   v=b[:2]-a[:2];length=np.linalg.norm(v);t=np.clip(((p-a[:2])@v)/(length*length),0,1);c=a[:2]+t[:,None]*v
   w=a[2]+t*(b[2]-a[2]);q=np.linalg.norm(p-c,axis=1)/w
   down=-np.sum(grad*v/length,axis=1)
   flow=smooth(-.05,.005,down)
   channel=(1-smooth(.2,1.2,q))*flow
   # Receiving broad lower reaches, upper patches favor coarse winnowed lag.
   settle=smooth(.14,.52,w)*(1-smooth(.02,.12,np.linalg.norm(grad,axis=1)))
   core=np.maximum(core,channel)
   bank=np.maximum(bank,(1-smooth(.65,1.65,q))*(.25+.75*flow)*(1-.65*settle))
   receiving=np.maximum(receiving,channel*settle)
 gate=smooth(-.65,-.1,y)*(1-smooth(65,85,y))*smooth(.09,.23,d)*(1-smooth(6.5,9,d))
 coarse=np.clip((.22+.65*bank+.40*(1-grade))*(1-.83*receiving)*(1-.68*grade),0,1)*gate
 fines=np.clip(.18+.72*grade+.60*receiving-.24*bank,0,1)*gate
 # Low plants sit on sheltered banks/receivers, absent from the worked inner
 # shoulder and scoured channel cores. Same field, no unrelated scatter noise.
 plants=smooth(.52,1.3,d)*(.10+.62*bank+.38*receiving)*(1-.75*core)*gate
 return {'coarse':coarse,'fines':fines,'plants':np.clip(plants,0,1),'gate':gate,'graded':grade,'receiving':receiving,'channel':core}
