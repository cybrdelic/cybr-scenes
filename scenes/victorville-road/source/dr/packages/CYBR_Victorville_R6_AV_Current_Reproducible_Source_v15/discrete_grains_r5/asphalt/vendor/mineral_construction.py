"""Explicit packed finite mineral grains and finish-dependent construction, r3.
All dimensions are authored approximations in meters. No photographic inputs.
BaseColor is sRGB reflectance authoring; height is SI until encoded for exchange.
"""
import math
import numpy as np
from scipy.ndimage import gaussian_filter
from surface_math import field, smooth, paths

PALETTE=np.array([[.245,.253,.25],[.37,.36,.325],[.165,.18,.178],[.47,.458,.403],[.285,.30,.29],[.52,.515,.47]],np.float32)

def packed_grains(n,tile,seed,bands,rounded_fraction=.25):
    """Rasterize convex irregular polygons with finite beveled crowns.
    Rejection against a spatial bin packing excludes most overlaps. Crown facets
    have independent slopes; grain identity, albedo and relief remain correlated.
    """
    rng=np.random.default_rng(seed);m=np.zeros((n,n),np.float32);z=m.copy();tone=m.copy();rough=m.copy();ident=np.zeros((n,n),np.int32)
    rgb=np.zeros((n,n,3),np.float32);stones=[];bins={};bin_size=.010;serial=0;stats=[]
    for low,high,target,max_tries in bands:
        start=int(np.count_nonzero(m>.5));accepted=0
        for trial in range(max_tries):
            cx,cy=rng.uniform(0,tile,2);radius=math.exp(rng.uniform(math.log(low/2),math.log(high/2)))
            bx,by=int(cx/bin_size),int(cy/bin_size);overlap=False
            for xx in range(bx-2,bx+3):
                for yy in range(by-2,by+3):
                    for x0,y0,r0 in bins.get((xx,yy),[]):
                        if (cx-x0)**2+(cy-y0)**2<(.77*(r0+radius))**2:overlap=True;break
                    if overlap:break
                if overlap:break
            if overlap:continue
            serial+=1;accepted+=1;bins.setdefault((bx,by),[]).append((cx,cy,radius));stones.append((cx,cy,radius))
            # Radius ratios vary independently; angular grains have 5-8 facets.
            rounded=rng.random()<rounded_fraction;k=int(rng.integers(8,13) if rounded else rng.integers(5,9))
            phase=rng.uniform(0,math.tau);angles=np.arange(k)*math.tau/k+phase+rng.uniform(-.15,.15,k)
            radii=radius*rng.uniform(.74,1.18,k);aspect=rng.uniform(.64,1.0);rotation=rng.uniform(0,math.tau)
            px=np.cos(angles)*radii;py=np.sin(angles)*radii*aspect
            c,s=math.cos(rotation),math.sin(rotation);vx=px*c-py*s;vy=px*s+py*c
            extent=radius*1.3;ix=np.arange(math.floor((cx-extent)/tile*n),math.ceil((cx+extent)/tile*n)+1);iy=np.arange(math.floor((cy-extent)/tile*n),math.ceil((cy+extent)/tile*n)+1)
            dx=(ix[None,:]+.5)/n*tile-cx;dy=(iy[:,None]+.5)/n*tile-cy
            # Signed distance to polygon edge; finite-support polygons never fill cells.
            d=np.full((len(iy),len(ix)),1e3,np.float32)
            for q in range(k):
                ex=vx[(q+1)%k]-vx[q];ey=vy[(q+1)%k]-vy[q]
                dd=(ex*(dy-vy[q])-ey*(dx-vx[q]))/max(1e-8,math.hypot(ex,ey));d=np.minimum(d,dd)
            # Finite micro-fracture edge chips interrupt the clean straight polygon rim.
            phase_chip=rng.uniform(0,math.tau)
            d+=radius*.042*np.sin(dx/(radius*.13)+phase_chip)*np.sin(dy/(radius*.11)-phase_chip)
            coverage=smooth(d,-tile/n*.6,tile/n*.6)
            if rounded:crown=np.sqrt(np.maximum(0,1-(np.maximum(0,1-d/max(radius,.0001)))**2))
            else:crown=np.clip(d/max(radius*.72,.0001),0,1)**.47
            facet=np.minimum.reduce([np.broadcast_to(1+rng.uniform(-.38,.38)*dx/radius+rng.uniform(-.38,.38)*dy/radius,d.shape) for _ in range(3)])
            crown*=np.clip(facet,.42,1.2)
            peak=radius*rng.uniform(.24,.53);zz=crown*peak*coverage
            target_idx=np.ix_(iy%n,ix%n);wins=(coverage>.01)&(zz>z[target_idx])
            mineral=PALETTE[int(rng.choice(len(PALETTE),p=[.28,.18,.23,.10,.16,.05]))]*rng.uniform(.88,1.1)
            # Small crystals within a rock alter pigment, without baking light direction.
            crystal=.008*np.sin(dx/(radius*.24)+rng.uniform(0,7))*np.sin(dy/(radius*.17)+rng.uniform(0,7))
            for ch in range(3):rgb[...,ch][target_idx]=np.where(wins,mineral[ch]+crystal,rgb[...,ch][target_idx])
            z[target_idx]=np.where(wins,zz,z[target_idx]);m[target_idx]=np.maximum(m[target_idx],coverage)
            ident[target_idx]=np.where(wins,serial,ident[target_idx]);rough[target_idx]=np.where(wins,rng.uniform(.64,.89),rough[target_idx])
            if accepted%50==0 and (np.count_nonzero(m>.5)-start)/n**2>=target:break
        stats.append(dict(diameter_m=[low,high],count=accepted,area_fraction=float((np.count_nonzero(m>.5)-start)/n**2)))
    return dict(mask=m,height_m=z,rgb=rgb,roughness=rough,ids=ident,stats=stats)

def construction(s,n):
    seed=s['seed'];tile=s['tile_m'];finish=s.get('finish','');asphalt=s['family']=='Asphalt';terrazzo=s['id']=='26_tile_terrazzo'
    # Physically independent bands, not repeated identical noise at new scales.
    bands=[(.0025,.0075,.40,6500),(.0011,.0035,.16,18000),(.00035,.0011,.13,22000)] if asphalt else [(.004,.014,.45,8500),(.0014,.004,.13,16000),(.00045,.0014,.09,22000)]
    g=packed_grains(n,tile,seed+110,bands,.13 if asphalt else .34 if not terrazzo else .08)
    m=g['mask'];z=g['height_m'];broad=field(n,6,seed+111,2);meso=field(n,80,seed+112,2);fine=field(n,min(n//2,410),seed+113)
    rgb=g['rgb'];r=g['roughness'];fracture=field(n,min(n//2,225),seed+127)
    grain_detail=(.000095*meso+.00011*fracture+.000065*fine)*m
    # Only unresolved sand/paste microrelief remains outside explicit grain crowns.
    if asphalt:
        binder=np.stack([.100+.014*broad+.020*fracture,.103+.014*broad+.019*fracture,.100+.013*broad+.018*fracture],axis=-1)
        # Thin residual bitumen coating narrows mineral albedo range, particularly
        # below the abraded upper crowns. It is not a bright uncoated gravel mosaic.
        wear=smooth(z,.00012,.0010)
        coating=.28+.23*wear
        rgb=.055+rgb*coating[...,None]+(.030*fracture+.013*fine)[...,None]
        rgb=binder*(1-m[...,None])+rgb*m[...,None]
        # Compaction flattens the uppermost crowns; bitumen film remains in hollows.
        h=-.00040+.00165*np.tanh(z/.00165)+grain_detail+(.00013*fracture+.000075*meso)*(1-m)
        rough=(.87+.055*meso)*(1-m)+np.clip(r+.07,.74,.96)*m
        process='Dense graded angular aggregate, compacted crowns, bitumen-filled interstices'
    else:
        paste=np.stack([.47+.025*broad+.011*meso,.463+.024*broad+.01*meso,.434+.022*broad+.009*meso],axis=-1)
        # Diverse mineral species are visible only where the finish exposes them.
        rgb=np.clip(rgb*1.25+.04,.10,.76)
        pores=1-smooth(field(n,145,seed+114),.39,.7)
        pores=1-pores
        h=.000027*meso+.000016*fine-.00007*pores
        rough=.77+.045*meso
        process='Cast cement-rich laitance hides bulk aggregate'
        visible=m*.035
        if finish=='exposed_aggregate':
            visible=m;h=-.0008+z+grain_detail+.000045*meso*(1-m);rough=.88*(1-m)+r*m
            process='Washed paste recession exposes finite angular and rounded mineral crowns'
        elif finish=='polished' or terrazzo:
            visible=m;h=.000006*fine-.000024*pores*(1-m);rough=.27*(1-m)+(.20+.06*meso)*m
            process='Ground flat cross-sections through graded mineral, common honed plane'
            if terrazzo:
                pal=np.array([[.22,.28,.285],[.69,.67,.60],[.48,.35,.27],[.82,.81,.74]],np.float32)
                rgb=pal[g['ids']%4]+.008*meso[...,None];paste=np.stack([.60+.006*broad,.565+.006*broad,.505+.006*broad],axis=-1);rough+=.04
        elif finish=='cast':
            # Form-face bugholes plus submillimetre sand and hydration variation.
            from expansion.grain_model import grains
            pm,ph,_=grains(n,seed+115,320,(.0007,.005),.34)
            h-=.00060*ph;rough+=.055*pm
            paste-=.035*pm[...,None]
            h+=.000055*field(n,(16,10),seed+116,2)
        elif finish=='board_formed':
            x=(np.arange(n)[None,:]+.5)/n*tile;y=(np.arange(n)[:,None]+.5)/n*tile
            board=np.floor(y/.105);v=(y/.105)%1;seam=1-smooth(np.minimum(v,1-v),.004,.015)
            wave=np.sin(x/.0009+.6*field(n,(15,7),seed+117))
            h+=.00019*wave+.00009*field(n,(12,130),seed+118)-.00065*seam+.00012*np.sin(board*5.13)
            paste+=.012*wave[...,None];process='Cement-rich negative wood-form imprint with independent board offsets and recessed seams'
        elif finish=='brushed':
            tracks=paths(n,seed+119,340,width=(.0005,.0018),length=(.25,1.3),angle=0,jitter=.009,bend=.002)
            h-=.00036*tracks;rough+=.05*tracks;paste-=.009*tracks[...,None]
            process='Bristles drag irregular overlapping finite grooves through cement-rich surface'
        elif finish=='weathered':
            er=smooth(field(n,(7,17),seed+120,2),-.1,.34);visible=m*er
            h+=er*(z-.00048)*(1+.2*meso);rough+=.07*er
            paste-=.026*er[...,None];process='Localized runoff recession removes laitance and exposes mineral while adjacent paste survives'
        elif finish=='paste':
            m=np.zeros_like(m);visible=m
            ridges=field(n,(5,10),seed+121,2);h+=.00011*ridges;rough=.69+.05*meso
            process='Neat hydrated paste, trowel flow ridges and shrinkage pores, no mineral aggregate'
        rgb=paste*(1-visible[...,None])+rgb*visible[...,None]
    encoded=.5+h/s['height_scale_m']
    return dict(BaseColor=np.clip(rgb,0,1).astype(np.float32),Height=np.clip(encoded,0,1).astype(np.float32),Roughness=np.clip(rough,.05,.98).astype(np.float32),Metallic=np.zeros_like(m),AO=np.ones_like(m),Opacity=np.ones_like(m),AggregateMask=m),dict(process=process,grading=g['stats'],relief_m=[float(h.min()),float(h.max())],clipped_height_pixels=int(np.count_nonzero((encoded<0)|(encoded>1))),seed=seed,normal_convention='OpenGL +Y; paired macro geometry and residual micro field, see map metadata')
