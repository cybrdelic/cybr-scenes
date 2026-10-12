"""Original metre-scale multistem crown reconstruction, retaining leaf budgets.

Shared crooked root crowns feed unequal low forks and attached continuation axes.
This is authored regional-inspired morphology, not a validated botanical model.
CJ materials, physical leaf construction, budgets and low-pale prototype retained.
"""
import math,random
from dataclasses import dataclass
import bpy
from mathutils import Vector
import architectural_scrub_cj_v2 as old
base=old.base; UP=Vector((0,0,1)); SPECS=old.SPECS
LEAF_BUDGET=(9875,7775,4804,1481)
@dataclass
class Axis:
 points:list
 radii:list
 order:int
 parent:int
 attachment:float
 live:bool
 group:int

def path(a,d,e,rng,amount=.02):
 q=base._curve(a,a+d.normalized()*(e-a).length*.32,e,6)
 # One persistent lateral bend, not alternating zig-zag tubes.
 side=Vector((d.y,-d.x,.15)).normalized(); bend=rng.uniform(-1,1)*amount
 for i in range(1,5):q[i]+=side*(math.sin(math.pi*i/5)*bend)
 return q

def skeleton(kind,seed):
 spec=SPECS[kind];rng=random.Random(seed+9407);axes=[]
 # Three unequal old basal origins occupy a compact crown. Every above-ground
 # branch begins on a real parent axis, rather than growing from independent poles.
 major=[]; phase=rng.uniform(-.4,.4)
 root_params=[((-.022,-.011,-.004),(.008,.006,.135),.017,3),((.021,.012,-.006),(-.017,.010,.09),.0135,2),((-.006,.032,-.005),(.012,-.012,.065),.0085,2)]
 for g,(loc,delta,radius,count) in enumerate(root_params):
  a=Vector(loc);e=a+Vector(delta);p=path(a,UP,e,rng,.009)
  rid=len(axes);axes.append(Axis(p,[radius*(1-.48*i/5)for i in range(6)],0,-1,0,True,g))
  for k in range(count):
   t=[.47,.73,.98][k] if count==3 else [.62,.99][k]
   start,d=base._sample(p,t)
   # Unequal azimuths surround the crown through depth; no opposing wing motif.
   heading=phase+[.20,2.2,4.4,1.05,3.5,5.3,2.75][len(major)]+rng.uniform(-.2,.2)
   reach=spec.span*rng.uniform(.17,.30); rise=spec.height*rng.uniform(.43,.72)
   if g==2:rise*=.68
   end=start+old.polar(heading,reach,rise)
   r0=radius*(1-.48*t)*rng.uniform(.49,.68)
   axid=len(axes); axes.append(Axis(path(start,d+UP*.25,end,rng,.055),[r0*(1-.79*i/5)for i in range(6)],1,rid,t,True,g));major.append(axid)
 # Recursive laterals and terminal branches follow the parent tangent at their
 # union and diverge progressively; all attachments are recorded and verifiable.
 for j,mid in enumerate(major):
  parent=axes[mid];az0=math.atan2(parent.points[-1].y-parent.points[0].y,parent.points[-1].x-parent.points[0].x)
  for k in range(5):
   t=.10+.86*(k+rng.uniform(.18,.80))/5; a,d=base._sample(parent.points,t)
   az=az0+(1 if k%2 else -1)*rng.uniform(.65,1.45)
   if k==1:az+=1.05 # occasional inward continuation crosses the apparent cleft
   e=a+old.polar(az,spec.span*rng.uniform(.10,.20)*(1-.3*t),spec.height*rng.uniform(.06,.20))
   r0=(parent.radii[0]*(1-.79*t))*rng.uniform(.30,.49);sid=len(axes)
   axes.append(Axis(path(a,d,e,rng,.019),[r0*(1-.84*i/5)for i in range(6)],2,mid,t,True,j))
   for q in range(rng.randint(3,5)):
    t2=.08+.86*(q+rng.uniform(.1,.9))/4.9;t2=min(t2,.97);a2,d2=base._sample(axes[sid].points,t2)
    az2=az+rng.uniform(-1.55,1.55);e2=a2+old.polar(az2,rng.uniform(.055,.135),rng.uniform(-.02,.105))
    tr=r0*(1-.84*t2)*rng.uniform(.23,.42);tid=len(axes)
    axes.append(Axis(path(a2,d2,e2,rng,.007),[max(.00010,tr*(1-.88*i/5))for i in range(6)],3,sid,t2,True,j))
    for h in range(rng.randint(2,4)):
     t3=.11+.83*(h+rng.uniform(.15,.8))/3.8;a3,d3=base._sample(axes[tid].points,t3)
     az3=az2+rng.uniform(-1.6,1.6);e3=a3+old.polar(az3,rng.uniform(.025,.065),rng.uniform(-.025,.057))
     rr=rng.uniform(.00025,.0005);axes.append(Axis(path(a3,d3,e3,rng,.0025),[max(.000065,rr*(1-.83*i/5))for i in range(6)],4,tid,t3,True,j))
 # Fit crown axes before adding original centimetre leaves. Basal geometry is
 # identical between the three woody variants only at its compact root origins.
 allp=[p for ax in axes for p in ax.points];lo=[min(p[k]for p in allp)for k in range(3)];hi=[max(p[k]for p in allp)for k in range(3)]
 factors=((spec.span-.04)/(hi[0]-lo[0]),(spec.span*spec.aspect-.04)/(hi[1]-lo[1]),(spec.height-.025)/(hi[2]-lo[2]))
 for ax in axes:
  ax.points=[Vector((p.x*factors[0],p.y*factors[1],p.z*factors[2]))for p in ax.points]
  ax.radii=[r*min(factors)for r in ax.radii]
 # Local dying sectors are inherited by twigs. The structure remains connected;
 # leaf budget is redistributed over live branches, never increased to hide shape.
 for ax in axes:
  if ax.order>=2:
   turn=math.atan2(ax.points[-1].y,ax.points[-1].x)
   deadchance=.17 if kind!=3 else (.74 if -.1<turn<1.5 else .40)
   ax.live=axes[ax.parent].live and rng.random()>deadchance*(.45 if ax.order==2 else .35)
 return axes

def geometry(kind,seed):
 axes=skeleton(kind,seed);spec=SPECS[kind];rng=random.Random(seed+700001);m=base._Mesh()
 for ax in axes:m.tube(ax.points,ax.radii,0 if ax.order<2 and ax.live else (1 if ax.live else 2),7 if ax.order==0 else (6 if ax.order==1 else 4))
 candidates=[a for a in axes if a.order>=3 and a.live]
 # Fixed original count. Allocate leaf pairs on fine twigs proportional to their
 # physical axis length, using a deterministic stratified cumulative measure.
 lengths=[sum((b-a).length for a,b in zip(x.points,x.points[1:]))for x in candidates];total=sum(lengths);cum=[];s=0
 for l in lengths:s+=l;cum.append(s)
 import bisect
 budget=LEAF_BUDGET[kind];counts=[0]*len(candidates)
 for i in range((budget+1)//2):counts[bisect.bisect_left(cum,(i+.5)*total/((budget+1)//2))]+=1
 for ax,count in zip(candidates,counts):
  phase=rng.uniform(0,math.tau)
  for n in range(count):
   t=.06+.91*(n+rng.uniform(.1,.9))/count;a,tangent=base._sample(ax.points,t);ref=old.polar(phase+n*2.399,1.,rng.uniform(-.1,.2));side=tangent.cross(ref).normalized()
   for sign in (-1,1):
    if m.leaf_count>=budget:break
    direction=(side*sign+tangent*rng.uniform(.22,.75)+UP*rng.uniform(-.2,.45)).normalized();length=rng.uniform(.011,.019);width=length*rng.uniform(.35,.51);normal=(UP+ref*rng.uniform(-.55,.55)).normalized();mat=rng.choice((3,4,4,5))
    if rng.random()<.055+spec.thinning*.09:mat=9
    m.leaf(a,direction,normal,length,width,rng.uniform(-.22,.20),mat)
 # Original sparse disconnected litter, kept separate from rooted wood.
 for k in range(9 if kind==3 else 4):
  a=old.polar(rng.uniform(0,math.tau),spec.span*rng.uniform(.18,.39),.003);e=a+old.polar(rng.uniform(0,math.tau),rng.uniform(.055,.10),.003);m.tube([a,a.lerp(e,.47)+UP*.005,e],[.001,.0005,.00012],2,4)
 assert m.leaf_count==budget
 def residual(ax):
  p=ax.points[0];best=1e9
  for a,b in zip(axes[ax.parent].points,axes[ax.parent].points[1:]):
   d=b-a;t=max(0.,min(1.,(p-a).dot(d)/max(d.length_squared,1e-18)));best=min(best,(p-(a+t*d)).length)
  return best
 m.cm_stats={'leaf_budget':budget,'root_crowns':3,'major_axes':7,'attached_axes':len(axes),'maximum_order':4,'branch_attachment_max_error_m':max(residual(a)for a in axes if a.parent>=0)}
 assert m.cm_stats['branch_attachment_max_error_m']<2e-6
 return m

def create_variants(collection,seed=26101020,materials=None):
 palette=list(materials)if materials is not None else base._palette();result={'all':[],'shrubs':[]}
 for kind,spec in enumerate(SPECS):
  local_seed=seed+104729*kind
  if kind==0:mesh=old.geometry(spec,local_seed);extra={'unchanged_CJ_low_mesh':True}
  else:mesh=geometry(kind,local_seed);extra=mesh.cm_stats
  ob=mesh.object('CM / '+spec.name,collection,palette,{'family':'coherent_shrub_cm','nominal_height_m':spec.height,'nominal_spread_m':spec.span,**extra});result['all'].append(ob);result['shrubs'].append(ob)
 return result
