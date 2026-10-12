"""Original woody shrub architecture workshop CJ, in real metres.

Four unequal stem-group architectures, three orders of attached side branching,
small folded physical leaves on live sectors, and disconnected dead litter.
No radial ray layout, cards, spheres, scanned/generated images, modifiers, or
road scatter. This is Mojave-inspired scene dressing, not a species reconstruction.

Only the existing original tube/leaf construction and material palette are reused.
All crown architecture below is new. Existing bank/materials are never changed.
Use create_variants(collection), then link visible instances to prototype.data.
The optional palette argument follows desert_scrub's original 14-slot order.
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass
from typing import Any
import bpy
from mathutils import Vector
import desert_scrub as base

UP = Vector((0., 0., 1.))

@dataclass(frozen=True)
class Spec:
    name: str
    height: float
    span: float
    aspect: float
    silver: bool
    thinning: float
    # Each tuple is an unequal basal group: x, y, heading, count, vigor, height.
    groups: tuple
    note: str

SPECS = (
    Spec('Pale low broken crown', .34, .69, .72, True, .10,
         ((-.055, -.025, 3.45, 4, .97, .65), (.05, .03, .38, 3, .97, .84),
          (.015, .07, 1.60, 1, .18, 1.0)),
         'Low broad wings separated by an open cleft; one weathered high remnant'),
    Spec('Open woody creosote-inspired', .77, 1.13, .79, False, .13,
         ((-.045, -.055, 3.75, 4, .97, .88), (.07, .025, .42, 3, .95, 1.0),
          (-.01, .075, 1.45, 1, .32, .72)),
         'Unequal old basal groups; open lower framework and locally full live tips'),
    Spec('Narrow leaning live crown', .88, .78, .65, False, .19,
         ((-.04, -.02, 1.2, 3, .97, 1.0), (.055, .025, -.30, 4, .92, .68),
          (-.03, .065, 2.70, 1, .22, .53)),
         'Tall offset leader plus a lower side crown; strongly unequal crown aspect'),
    Spec('Drought-thinned divided crown', .63, 1.03, .78, False, .57,
         ((-.045, -.055, 3.75, 3, .18, .88), (.07, .025, .42, 2, .96, 1.0),
          (-.01, .075, 1.45, 1, .24, .72)),
         'Mixed living terminal islands, bare old forks, and separate fallen twigs'),
)

@dataclass
class Branch:
    points: list
    radius: float
    order: int
    live: bool
    vigor: float
    group: int
    parent: int


def polar(angle, length, z=0.):
    return Vector((math.cos(angle)*length, math.sin(angle)*length, z))


def crooked(a, tangent, end, rng, amount=.06):
    """Five-segment axis with persistent direction and unequal local kinks."""
    length = (end-a).length
    shoulder = a + tangent.normalized()*length*.30
    points = base._curve(a, shoulder, end, 6)
    for i in (2, 3, 4):
        points[i] += polar(rng.uniform(0, math.tau), length*amount,
                           length*rng.uniform(-.02, .025))
    return points


def architecture(spec, seed):
    """Decurrent shrub axes branch from low nodes; terminal sprays are secondary.

    Architectural correction after the first actual shape proof: lower/middle
    second-order branch structure starts close to the basal junction and overlaps
    into an irregular permeable crown. It is not a collection of leaf bouquets at
    the ends of long poles. Each axis remains attached to its recorded parent.
    """
    rng = random.Random(seed)
    branches = []
    for gi, (gx, gy, heading, count, vigor, elevation) in enumerate(spec.groups):
        for stem in range(count):
            root = Vector((gx+rng.uniform(-.018,.018), gy+rng.uniform(-.018,.018), 0.))
            az = heading + rng.gauss(0,.40 if spec.silver else .28)
            reach = rng.uniform(.23,.43)*(1 if spec.height < .8 else .72)
            rise = elevation*rng.uniform(.24,.40) if spec.silver else elevation*rng.uniform(.38,.56)
            target = root+polar(az,reach,rise)
            tangent = (UP*rng.uniform(.5,.9)+polar(az-.45,.45)).normalized()
            live = vigor > .4 and not (stem == count-1 and rng.random() < .12)
            radius = rng.uniform(.006,.010) if spec.silver else rng.uniform(.008,.012)
            path = crooked(root,tangent,target,rng,.075)
            main_id = len(branches)
            branches.append(Branch(path,radius,0,live,vigor,gi,-1))
            # Deliberately low branching origins are the substantive change.
            # The lower axes are long enough to carry real attached leaf-bearing
            # structure, while higher forks form shorter irregular shoulders.
            fork_count = 6 if spec.silver else 5
            phase = rng.uniform(0,math.tau)
            for fork in range(fork_count):
                attachment = .055+.87*(fork+rng.uniform(.05,.85))/fork_count
                start,direction = base._sample(path,attachment)
                side = math.sin(phase+fork*2.399)
                az2 = az+side*rng.uniform(.55,1.7)
                # Occasional inward, cross-crown fork links the apparent mass
                # across basal groups instead of creating isolated endpoint tufts.
                if fork in (1,3) and stem%2 == 0:
                    az2 += rng.uniform(.65,1.15)
                reach2 = rng.uniform(.16,.29)*(1-.27*attachment)
                rise2 = rng.uniform(.035,.11) if spec.silver else elevation*rng.uniform(.055,.18)
                tip = start+polar(az2,reach2,rise2)
                fork_path = crooked(start,direction,tip,rng,.12)
                fork_live = live and rng.random() > spec.thinning*.38
                fork_id=len(branches)
                branches.append(Branch(fork_path,radius*rng.uniform(.27,.43),1,
                                       fork_live,vigor,gi,main_id))
                # Branchlet origins span each lateral, including its proximal
                # half. Leaf-bearing structure is distributed through depth.
                sub_count=rng.randint(3,4) if spec.silver else rng.randint(2,4)
                for sub in range(sub_count):
                    t=.10+.86*(sub+rng.uniform(.1,.85))/sub_count
                    start2,tangent2=base._sample(fork_path,t)
                    az3=az2+rng.uniform(-1.6,1.6)
                    end2=start2+polar(az3,rng.uniform(.055,.13),
                                      rng.uniform(-.02,.075 if spec.silver else .105))
                    sub_path=crooked(start2,tangent2,end2,rng,.11)
                    sub_live=fork_live and rng.random()>spec.thinning*.22
                    sub_id=len(branches)
                    branches.append(Branch(sub_path,radius*rng.uniform(.10,.17),2,
                                           sub_live,vigor,gi,fork_id))
                    twig_phase=rng.uniform(0,math.tau)
                    twig_count=rng.randint(3,5)
                    for twig in range(twig_count):
                        t=.08+.85*(twig+rng.uniform(.1,.8))/twig_count
                        a,tangent3=base._sample(sub_path,t)
                        az4=az3+math.sin(twig_phase+twig*2.399)*rng.uniform(.6,1.55)
                        v=polar(az4,rng.uniform(.027,.071),rng.uniform(-.025,.055))
                        twig_path=crooked(a,tangent3,a+v,rng,.08)
                        twig_live=sub_live and rng.random()>spec.thinning*.26
                        branches.append(Branch(twig_path,rng.uniform(.00045,.0008),3,
                                               twig_live,vigor,gi,sub_id))
    # Fit only woody axes. Leaves are subsequently added in real centimetres.
    all_points=[p for b in branches for p in b.points]
    lo=[min(p[k] for p in all_points) for k in range(3)]
    hi=[max(p[k] for p in all_points) for k in range(3)]
    sx=(spec.span-.035)/(hi[0]-lo[0])
    sy=(spec.span*spec.aspect-.035)/(hi[1]-lo[1])
    sz=(spec.height-.025)/(hi[2]-lo[2])
    for b in branches:
        b.points=[Vector((p[0]*sx,p[1]*sy,max(.002,p[2]*sz))) for p in b.points]
        b.radius*=min(sx,sy,sz)
    return branches


def foliage(mesh, branch, spec, rng):
    path = branch.points
    # Terminal live regions bear leaf mass; bottom half of old wood remains open.
    nodes = rng.randint(7,10) if spec.silver else rng.randint(7,11)
    phase = rng.uniform(0,math.tau)
    for node in range(nodes):
        if rng.random() < .07 + spec.thinning*.20:
            continue
        t = .08+.90*(node+rng.uniform(.05,.90))/nodes
        a, tangent = base._sample(path,t)
        ref = polar(phase+node*2.399,1.,rng.uniform(-.1,.2))
        side = tangent.cross(ref).normalized()
        if side.length_squared < 1e-9:
            side = Vector((1.,0.,0.))
        # Silver individual blades; paired short olive leaflets. Both are small,
        # cupped, irregular and physically connected at a twig node.
        for sign in (-1.,1.):
            direction = (side*sign+tangent*rng.uniform(.22,.75)+UP*rng.uniform(-.2,.45)).normalized()
            length = rng.uniform(.014,.024) if spec.silver else rng.uniform(.011,.019)
            width = length*(rng.uniform(.43,.62) if spec.silver else rng.uniform(.35,.51))
            normal = (UP+ref*rng.uniform(-.55,.55)).normalized()
            mat = rng.choice((6,7,7,8)) if spec.silver else rng.choice((3,4,4,5))
            if rng.random() < .055+spec.thinning*.09:
                mat = 9
            mesh.leaf(a,direction,normal,length,width,rng.uniform(-.22,.20),mat)


def geometry(spec, seed):
    rng = random.Random(seed+700001)
    mesh = base._Mesh()
    branches = architecture(spec,seed)
    live_twigs = dead_twigs = 0
    for b in branches:
        mat = 0 if b.order == 0 and b.live else (1 if b.live else 2)
        radii = [max(.00007,b.radius*(1-.90*i/5)) for i in range(6)]
        mesh.tube(b.points,radii,mat,6 if b.order==0 else (5 if b.order==1 else 4))
        if b.order == 3:
            if b.live:
                foliage(mesh,b,spec,rng)
                live_twigs += 1
            else:
                dead_twigs += 1
                if rng.random()<.16:
                    a,tangent=base._sample(b.points,rng.uniform(.6,.9))
                    mesh.leaf(a,tangent+UP*.3,UP,.013,.006,-.23,9)
        elif b.order == 2 and b.live and rng.random() < .90:
            foliage(mesh,b,spec,rng)
    # Detached dead wood belongs to its own geometry component, not a continuous
    # circular skirt. Every piece sits above z=0 and outside the root cluster.
    litter_count = 9 if spec.thinning>.4 else 4
    for i in range(litter_count):
        az = rng.uniform(0,math.tau)
        start = polar(az,spec.span*rng.uniform(.17,.43),.006)
        direction = polar(az+rng.uniform(-1.5,1.5),rng.uniform(.055,.13),.004)
        end = start+direction
        path = [start,start.lerp(end,.42)+UP*rng.uniform(.003,.013),end]
        mesh.tube(path,[.0015,.0008,.00016],2,4)
        if rng.random()<.6:
            a=path[1]
            tip=a+polar(az+1.2,rng.uniform(.022,.051),-.002)
            mesh.tube([a,tip],[.00065,.00012],2,3)
    mesh.cj_stats = {'live_terminal_twigs':live_twigs,'dead_terminal_twigs':dead_twigs,
                     'detached_litter_pieces':litter_count,'attached_branch_orders':4,
                     'basal_groups':len(spec.groups),'basal_stem_counts':[g[3] for g in spec.groups]}
    return mesh


def create_variants(collection:Any,seed:int=26101020,materials=None):
    """Return four hidden prototypes, without altering any old bank or scene."""
    palette = list(materials) if materials is not None else base._palette()
    if len(palette)<14:
        raise ValueError('Expected the original 14-slot material palette')
    result={'all':[],'shrubs':[]}
    for i,spec in enumerate(SPECS):
        local_seed=int(seed)+104729*i
        mesh=geometry(spec,local_seed)
        attributes={'family':'architectural_scrub_cj','nominal_height_m':spec.height,
                    'nominal_spread_m':spec.span,'generation_seed':local_seed,
                    'description':spec.note,**mesh.cj_stats}
        obj=mesh.object('CJ / '+spec.name,collection,palette,attributes)
        result['all'].append(obj)
        result['shrubs'].append(obj)
    return result


def variant_summary(variants):
    return base.variant_summary(variants)
