"""AN: new local fixed-boundary film event on the sampled CURRENT surface.

Pure NumPy + standard library. No bpy, scene opens, renders, shaders, texture
changes, particles, blur or new noise. Uses the unchanged Z transport solver and
its fixed 10 mm event at 25, 12.5 and 6.25 mm. The old Z ledger is never loaded,
reassigned or replaced. Each grid gets the same physically bounded initial-stock
law on its CURRENT topmost soil/road owner, with independent class conservation.

These are illustrative resolution diagnostics, not a validated site prediction
or a rerun of the old Z event on an unchanged domain. Source axes are cell
centres with equal dx*dy integration, so whole-domain area and initial inventory
have disclosed grid-dependent rim quadrature. Comparison statistics clip cell
areas to the SAME world ROI, without changing the solver's conservation ledger.

CLI: OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python
     src/refined_film_event_an.py --surface path/AN_FINAL_SURFACE.npz
     --output-dir fresh_directory
Run after the parent releases its heavy-scene lock; no scene is needed here.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import argparse
import hashlib
import json
import math
import time
import numpy as np
from flow_sediment_model_z import FlowConfig, simulate_shoulder, CLASS_NAMES

BOUNDS = (-3.8,-2.7,-.3,2.3)
ROI = (-3.8,-2.7,.3,1.8)
SPACING = .00625


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _axes(x,y):
    out=[]
    for a in (x,y):
        a=np.asarray(a,dtype=float)
        _require(a.ndim==1 and len(a)>=3 and np.isfinite(a).all(), 'Finite axes with at least three centres required')
        d=np.diff(a)
        _require(d.min()>0 and np.allclose(d,d[0],rtol=1e-6,atol=1e-10),'Uniform increasing axes required')
        out.append((a,float(f'{d[0]:.12g}')))
    return out[0][0],out[1][0],out[0][1],out[1][1]


def fixed_event_config():
    """Identical physical event settings to prepare_runoff_film_z.py."""
    return FlowConfig(rainfall_m=(.010,),event_duration_s=1200.,upstream_width_m=1.2,
                      max_erosion_m=.001,max_event_erosion_m=.001,max_deposition_m=.001)


def initial_inventory(x,y,pavement,road_edge_x_m):
    """NEW finite stock on current owners, never imported historical Z stock.

    Soil: 300 um total, class fractions .90/.09/.01. Road: matrix-only
    80 um * clip(1-(x-actual_edge)/.42,0,1). Caps limit transported deposits,
    excluding unentrained initial stock, exactly as the Z solver specifies.
    """
    x,y,_,_=_axes(x,y);p=np.asarray(pavement)
    edge=np.asarray(road_edge_x_m,dtype=float)
    _require(p.shape==(len(y),len(x)) and np.all((p==0)|(p==1)),'Binary current pavement ownership required')
    _require(edge.shape==(len(y),) and np.isfinite(edge).all(),'Actual current road edge must be sampled at each Y')
    p=p.astype(bool);feed=np.clip(1-(x[None,:]-edge[:,None])/.42,0,1)
    initial=np.zeros(p.shape+(3,),float)
    initial[~p]=.00030*np.array((.90,.09,.01))
    initial[:,:,0][p]=(.000080*feed)[p]
    return initial,np.where(p,.00035,.00065),feed


def validate_balances(flow,initial,caps,dx,dy):
    """Check absolute class ledgers, nonnegativity, caps and reported water."""
    initial=np.asarray(initial,float);caps=np.asarray(caps,float)
    _require(np.ndim(dx)==np.ndim(dy)==0 and np.isfinite(dx) and np.isfinite(dy) and dx>0 and dy>0, 'Finite positive scalar cell dimensions required')
    _require(np.isfinite(caps).all() and np.all(caps>=0), 'Finite nonnegative deposit caps required')
    area=dx*dy
    remaining=np.asarray(flow.remaining_initial_mobile_class_thickness_m)
    deposit=np.asarray(flow.retained_deposit_by_class_m)
    _require(remaining.shape==deposit.shape==initial.shape and caps.shape==initial.shape[:2], 'Inventory shapes differ')
    for name,a in (('initial',initial),('remaining',remaining),('retained',deposit)):
        _require(np.isfinite(a).all() and np.all(a>=0),name+' stock must be finite and nonnegative')
    _require(np.all(remaining<=initial+1e-15),'Initial stock replenished itself')
    excess=float(np.max(deposit.sum(-1)-caps))
    _require(excess<=1e-12,'Retained transported deposit cap exceeded')
    r=flow.receipt;export=np.asarray(r['boundary_export_by_class_m3'],float)
    correction=np.asarray(r['roundoff_inventory_added_by_class_m3'],float)
    _require(export.shape==(3,) and correction.shape==(3,) and np.isfinite(export).all() and np.isfinite(correction).all() and np.all(export>=0) and np.all(correction>=0),'Finite nonnegative class exports/corrections required')
    initial_v=initial.sum((0,1))*area;remaining_v=remaining.sum((0,1))*area;deposit_v=deposit.sum((0,1))*area
    balance=initial_v+correction-remaining_v-deposit_v-export
    tol=max(1e-12,float(initial_v.sum())*1e-10)
    _require(float(abs(balance).max())<=tol,'Independent class-volume balance failed')
    _require(float(correction.sum())<=tol*.01,'Roundoff correction exceeded tiny budget')
    for key in ('stock_balance_by_class_m3', 'net_bed_plus_export_error_m3','sediment_balance_error_m3','water_balance_error_m3'):
        v=np.asarray(r[key],float)
        _require(np.isfinite(v).all() and np.max(abs(v))<=1e-9,'Reported balance failed: '+key)
    _require(float(r['suspended_end_m3'])==0.,'Unexpected unaccounted suspended store')
    stock=remaining+deposit
    _require(np.allclose((stock-initial).sum(-1),flow.height_delta_m,atol=1e-12,rtol=0),'Virtual height differs from class ledger')
    return dict(initial_by_class_m3=initial_v.tolist(),remaining_initial_by_class_m3=remaining_v.tolist(),
        retained_deposit_by_class_m3=deposit_v.tolist(),export_by_class_m3=export.tolist(),
        roundoff_added_by_class_m3=correction.tolist(),independent_balance_by_class_m3=balance.tolist(),
        absolute_class_tolerance_m3=tol,minimum_stock_m=float(stock.min()),
        maximum_retained_cap_excess_m=max(0.,excess),water_balance_error_m3=float(r['water_balance_error_m3']),
        passed=True)


def roi_weights(x,y,bounds):
    """Exact area of each axis-aligned cell clipped to a common world rectangle."""
    x,y,dx,dy=_axes(x,y);b=np.asarray(bounds,float)
    _require(b.shape==(4,) and np.isfinite(b).all() and b[0]<b[1] and b[2]<b[3],'Finite ordered ROI required')
    wx=np.maximum(0,np.minimum(x+dx/2,b[1])-np.maximum(x-dx/2,b[0]))
    wy=np.maximum(0,np.minimum(y+dy/2,b[3])-np.maximum(y-dy/2,b[2]))
    return wy[:,None]*wx[None,:]


def connected_patch_metrics(mask,x,y,weights=None):
    """Face-connected cell patches, no diagonal merging or post-hoc smoothing.

    Areas/centroids use clipped area weights. Perimeters are the grid-face
    staircase perimeter of the selected cells, including crop boundaries,
    rather than a claim of continuous grain-scale patch shape.
    """
    x,y,dx,dy=_axes(x,y);mask=np.asarray(mask,bool)
    _require(mask.shape==(len(y),len(x)),'Mask and axes differ')
    weight=np.full(mask.shape,dx*dy) if weights is None else np.asarray(weights,float)
    _require(weight.shape==mask.shape and np.isfinite(weight).all() and np.all(weight>=0),'Finite nonnegative cell areas required')
    mask=mask&(weight>0);seen=np.zeros(mask.shape,bool);components=[];ny,nx=mask.shape
    for flat in np.flatnonzero(mask):
        row,col=divmod(int(flat),nx)
        if seen[row,col]:continue
        stack=[(row,col)];seen[row,col]=True;cells=[];perimeter=0.
        while stack:
            r,c=stack.pop();cells.append((r,c))
            for dr,dc,length in ((-1,0,dx),(1,0,dx),(0,-1,dy),(0,1,dy)):
                rr,cc=r+dr,c+dc
                if not(0<=rr<ny and 0<=cc<nx) or not mask[rr,cc]:
                    perimeter+=length
                elif not seen[rr,cc]:seen[rr,cc]=True;stack.append((rr,cc))
        ij=np.asarray(cells);rr,cc=ij.T;w=weight[rr,cc];area=float(w.sum())
        px,py=x[cc],y[rr];cx=float(np.sum(px*w)/area);cy=float(np.sum(py*w)/area)
        d=np.column_stack((px-cx,py-cy));cov=(d*w[:,None]).T@d/area
        # Include finite cell extent so single cells have finite shape metrics.
        cov+=np.diag((dx*dx/12,dy*dy/12));ev=np.linalg.eigvalsh(cov)
        components.append(dict(cells=len(cells),area_m2=area,grid_perimeter_m=float(perimeter),
            grid_compactness=float(4*math.pi*area/perimeter**2),principal_elongation=float(np.sqrt(ev[-1]/ev[0])),
            centroid_xy_m=[cx,cy],cell_footprint_bounds_m=[float(px.min()-dx/2),float(px.max()+dx/2),float(py.min()-dy/2),float(py.max()+dy/2)]))
    components.sort(key=lambda q:q['area_m2'],reverse=True)
    return dict(component_count=len(components),total_area_m2=float(weight[mask].sum()),
                single_cell_components=sum(q['cells']==1 for q in components),largest_components=components[:5],
                connectivity='Four shared faces; diagonal-only contact is disconnected',
                perimeter='Grid staircase, including crop boundary; not a continuous sediment boundary')


def _weighted_stats(values,weights):
    v=np.asarray(values,float).ravel();w=np.asarray(weights,float).ravel();take=w>0;v=v[take];w=w[take]
    if not len(v):return dict(cells=0,area_m2=0.,mean_m=0.,p50_m=0.,p95_m=0.,p99_m=0.,max_m=0.)
    order=np.argsort(v);cum=np.cumsum(w[order]);q=np.interp(np.array([.5,.95,.99])*cum[-1],cum,v[order])
    return dict(cells=len(v),area_m2=float(w.sum()),mean_m=float(np.sum(v*w)/w.sum()),
                p50_m=float(q[0]),p95_m=float(q[1]),p99_m=float(q[2]),max_m=float(v.max()))


def concentration_metrics(stock,pavement,x,y,roi_bounds=ROI):
    stock=np.asarray(stock,float);p=np.asarray(pavement,bool);w=roi_weights(x,y,roi_bounds)
    _require(stock.shape==p.shape+(3,) and p.shape==w.shape and np.isfinite(stock).all() and np.all(stock>=0),'Finite nonnegative class stock on matching owners required')
    wp=w*p;matrix=stock[:,:,0];total=stock.sum(-1);area=float(wp.sum())
    thresholds={}
    for um in (20,60,100,200,300):
        active=p&(matrix>um*1e-6)&(w>0)
        thresholds[str(um)]=dict(pavement_area_fraction=float(w[active].sum()/area) if area else 0.,
                               **connected_patch_metrics(active,x,y,w))
    jumps=[]
    for axis in (0,1):
        a=[slice(None),slice(None)];b=a.copy();a[axis]=slice(None,-1);b[axis]=slice(1,None);a=tuple(a);b=tuple(b)
        good=p[a]&p[b]&(w[a]>0)&(w[b]>0)
        jumps.append(abs(matrix[a]-matrix[b])[good])
    jumps=np.concatenate(jumps)
    return dict(roi_bounds_m=list(roi_bounds),roi_clipped_area_m2=float(w.sum()),
        pavement_area_m2=area,soil_area_m2=float((w*(~p)).sum()),
        pavement_owned_by_class_m3=(stock*wp[:,:,None]).sum((0,1)).tolist(),
        soil_owned_by_class_m3=(stock*(w*(~p))[:,:,None]).sum((0,1)).tolist(),
        pavement_matrix=_weighted_stats(matrix,wp),pavement_total_stock=_weighted_stats(total,wp),
        matrix_threshold_um=thresholds,
        neighboring_pavement_cell_matrix_jump_m=dict(count=len(jumps),p95=float(np.percentile(jumps,95)) if len(jumps) else 0.,maximum=float(jumps.max()) if len(jumps) else 0.),
        coverage_interpretation='Area fraction of current pavement cells above a thickness threshold. Not optical opacity, subcell pore coverage, or calibrated render visibility.')


@dataclass(frozen=True)
class EventConfig:
    strides: tuple = (4,2,1)
    roi_bounds_m: tuple = ROI
    max_cells: int = 80_000


def _validate_source(source):
    _require(str(source.get('surface_schema',''))=='AN_CURRENT_PHYSICAL_V1','Use AN current physical surface output, never old Z fields')
    x,y,dx,dy=_axes(source['x_m'],source['y_m'])
    _require(len(x)==177 and len(y)==417 and abs(dx-SPACING)<1e-12 and abs(dy-SPACING)<1e-12,'Expected fixed 6.25 mm AN source axes')
    expected_x=BOUNDS[0]+np.arange(177)*SPACING;expected_y=BOUNDS[2]+np.arange(417)*SPACING
    _require(np.array_equal(x,expected_x) and np.array_equal(y,expected_y),'AN source axis origin/phase changed')
    z=np.asarray(source['actual_surface_z_m']);p=np.asarray(source['pavement']);owner=np.asarray(source['owner'])
    _require(z.shape==(417,177) and np.isfinite(z).all() and p.shape==z.shape and owner.shape==z.shape,'Current source shape/finite check failed')
    _require(np.all((p==0)|(p==1)) and np.all(np.isin(owner,(0,1,2,3,4))) and np.array_equal(p.astype(bool),np.isin(owner,(1,2,3))),'Current substrate owners disagree')
    edge=np.asarray(source['road_edge_x_m']);_require(edge.shape==(417,) and np.isfinite(edge).all(),'Current actual road edge missing')
    return x,y


def _compare_coincident(coarse,fine,roi):
    ratio=coarse['stride']//fine['stride']
    _require(ratio>=1 and coarse['stride']%fine['stride']==0,'Non-nested comparison grids')
    a,b=coarse['stock'],fine['stock'][::ratio,::ratio]
    p,q=coarse['pavement'],fine['pavement'][::ratio,::ratio]
    w=roi_weights(coarse['x'],coarse['y'],roi);common=(p&q)&(w>0);delta=abs(a[:,:,0]-b[:,:,0])
    denom=float((w*common).sum())
    return dict(coarse_spacing_m=SPACING*coarse['stride'],fine_spacing_m=SPACING*fine['stride'],
        coincident_height_max_difference_m=float(np.max(abs(coarse['z']-fine['z'][::ratio,::ratio]))),
        coincident_owner_disagreement_cells=int(np.sum((p!=q)&(w>0))),
        common_pavement_matrix_mean_abs_difference_m=float((delta*w*common).sum()/denom) if denom else 0.,
        common_pavement_matrix_max_abs_difference_m=float(delta[common].max()) if common.any() else 0.,
        interpretation='Comparison at identical world sample centres; no interpolated height or inventory, no convergence claim from three resolutions.')


def run(surface_path,output_directory,config=None):
    """Run fixed local event sequentially; save three field files and receipt."""
    cfg=config if isinstance(config,EventConfig) else EventConfig(**(config or {}));started=time.perf_counter()
    _require(tuple(cfg.strides) in ((4,),(2,),(1,),(4,2),(2,1),(4,2,1)),'Use ordered supported nested strides')
    _require(tuple(cfg.roi_bounds_m)==ROI and 0<cfg.max_cells<=80_000,'Fixed world comparison ROI and bounded cell cap required')
    path=Path(surface_path);source_sha=hashlib.sha256(path.read_bytes()).hexdigest()
    with np.load(path,allow_pickle=False) as f:source={k:f[k] for k in f.files}
    x,y=_validate_source(source);out=Path(output_directory);out.mkdir(parents=True,exist_ok=True)
    summary_path=out/'AN_FILM_COMPARISON.json';_require(not summary_path.exists(),'Refusing to overwrite AN event receipt')
    report=dict(task='NEW local AN fixed-boundary illustrative finite-film events on final AH/AC/AL geometry',
        source_fields_path=str(path),source_fields_sha256=source_sha,module_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        model_sha256=hashlib.sha256(Path(__file__).with_name('flow_sediment_model_z.py').read_bytes()).hexdigest(),
        configuration=asdict(cfg),flow_configuration=asdict(fixed_event_config()),class_names=list(CLASS_NAMES),
        historical_Z_stock_loaded=False,scene_or_materials_modified=False,grids=[],comparisons=[],
        limitations=[
            'A new local event, not the unchanged historical Z ledger. Old soil stock is never reinterpreted as road stock.',
            'Outer domain centre coordinates are fixed; all rim cells integrate dx*dy, so effective full cell footprints, rainfall and initial class volumes differ slightly by resolution. The comparison ROI uses clipped equal world bounds.',
            'Open rectangular rim with a fixed 0.10 m mobility band and a water-only 1.2 m x_max contributing strip. No surrounding catchment is simulated and boundary influences can reach the comparison ROI.',
            'Soil/road ownership is sampled at cell centres from the current highest physical surface; actual inclined AC section is included by its asphalt/subgrade FACE layer, but exact subcell coverage and unresolved grain relief are not represented.',
            'Identical existing Z seed and resistance/erodibility law, 10 mm rain, 1200 s, finite exchange/wet-connectivity and relaxation rules. No new noise, blur or painted patch masks.',
            '350/650 um caps apply to retained transported deposits, excluding unentrained initial stock. Stored scene geometry remains fixed; virtual event heights are diagnostic fields only.',
            'Threshold patch shape and cell-to-cell stock jumps are grid diagnostics, not opacity, pore-fill equilibrium or a calibrated visual fix. Three resolutions do not prove convergence.' ])
    results=[]
    for stride in cfg.strides:
        label={4:'25mm',2:'12p5mm',1:'6p25mm'}[stride];dest=out/f'AN_FILM_{label}.npz'
        _require(not dest.exists(),'Refusing to overwrite event fields: '+str(dest))
        xx,yy=x[::stride],y[::stride];z=source['actual_surface_z_m'][::stride,::stride]
        p=source['pavement'][::stride,::stride].astype(bool);owner=source['owner'][::stride,::stride]
        edge=source['road_edge_x_m'][::stride];_require(z.size<=cfg.max_cells,'Bounded event cell cap exceeded')
        initial,caps,feed=initial_inventory(xx,yy,p,edge);spacing=SPACING*stride
        print('AN_EVENT_START',label,{'shape':z.shape,'cells':z.size},flush=True)
        flow=simulate_shoulder(xx,yy,z,fixed_event_config(),initial_mobile_class_thickness_m=initial,maximum_deposited_thickness_m=caps)
        ledger=validate_balances(flow,initial,caps,spacing,spacing)
        stock=flow.remaining_initial_mobile_class_thickness_m+flow.retained_deposit_by_class_m
        road_owned=np.where(p[:,:,None],stock,0);soil_owned=np.where(p[:,:,None],0,stock)
        _require(np.array_equal(road_owned+soil_owned,stock),'Current owner stock split must conserve every class exactly')
        np.savez_compressed(dest,x_m=xx,y_m=yy,actual_surface_z_m=z,pavement=p,owner=owner,road_edge_x_m=edge,
            initial_mobile_class_thickness_m=initial,remaining_initial_mobile_class_thickness_m=flow.remaining_initial_mobile_class_thickness_m,
            retained_deposit_by_class_m=flow.retained_deposit_by_class_m,remaining_mobile_class_thickness_m=stock,
            pavement_owned_class_thickness_m=road_owned,soil_owned_class_thickness_m=soil_owned,
            maximum_retained_deposit_m=caps,feed_fraction=feed,virtual_height_delta_m=flow.height_delta_m,
            cumulative_water_m3=flow.cumulative_water_m3,boundary_mobility=flow.boundary_mobility,
            source_fields_sha256=np.array(source_sha),event_schema=np.array('AN_NEW_LOCAL_EVENT_V1'))
        grid=dict(label=label,stride=stride,spacing_m=spacing,shape_yx=list(z.shape),fields_path=str(dest),fields_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
            effective_full_cell_bounds_m=[float(xx[0]-spacing/2),float(xx[-1]+spacing/2),float(yy[0]-spacing/2),float(yy[-1]+spacing/2)],
            integrated_area_m2=z.size*spacing**2,ledger=ledger,model=flow.receipt,
            current_pavement_owned_by_class_m3=(road_owned.sum((0,1))*spacing**2).tolist(),
            current_soil_owned_by_class_m3=(soil_owned.sum((0,1))*spacing**2).tolist(),
            stock_metrics=concentration_metrics(stock,p,xx,yy,cfg.roi_bounds_m),
            retained_deposit_metrics=concentration_metrics(flow.retained_deposit_by_class_m,p,xx,yy,cfg.roi_bounds_m))
        report['grids'].append(grid);results.append(dict(stride=stride,x=xx,y=yy,z=z,pavement=p,stock=stock))
        del flow,initial,caps,feed,road_owned,soil_owned
        print('AN_EVENT_READY',json.dumps({'label':label,'fields_path':str(dest),'ledger':ledger,'pavement_matrix':grid['stock_metrics']['pavement_matrix']}),flush=True)
        # Checkpoint validated finished work before the next slower fine solve.
        (out/f'AN_FILM_{label}.json').write_text(json.dumps(grid,indent=2)+'\n')
    for coarse,fine in zip(results[:-1],results[1:]):report['comparisons'].append(_compare_coincident(coarse,fine,cfg.roi_bounds_m))
    _require(hashlib.sha256(path.read_bytes()).hexdigest()==source_sha,'Sampled source bytes changed during event')
    report.update(source_file_unchanged=True,elapsed_s=time.perf_counter()-started)
    summary_path.write_text(json.dumps(report,indent=2)+'\n')
    print('AN_FILM_COMPARISON_READY',str(summary_path),flush=True)
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--surface',required=True,type=Path)
    parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--strides',default='4,2,1',help='Ordered supported source strides; default all three')
    args=parser.parse_args(argv)
    run(args.surface,args.output_dir,dict(strides=tuple(map(int,args.strides.split(',')))))


if __name__=='__main__':main()
