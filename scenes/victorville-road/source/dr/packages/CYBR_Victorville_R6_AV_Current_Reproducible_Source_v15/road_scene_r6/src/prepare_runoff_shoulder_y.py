"""Y: stage-limited connected wet-footprint terrain-driven conservative sediment field over immutable S.
No source-material edits. Source-only procedural scene, not validated hydrology.
"""
from pathlib import Path
import sys,os,time,json,hashlib
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='2'
import numpy as np
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
import prepare_physical_lenses as u
from approved_density_lod import restore_approved_density
from flow_sediment_model_y import simulate_shoulder,FlowConfig
from scipy.ndimage import map_coordinates
from transport_surface_scene_y import apply_transported_exposure
import bpy
SOURCE=R/'relief_correction/road_r6_s_coupled.blend';OUTPUT=R/'preview/road_r6_y_wet_connected.blend';RECEIPT=R/'receipts/flow_shoulder_y.json'
BOUNDS=(-5.80,-3.25,-.60,8.20);PATCH=(-6.25,-3.17,-.70,8.32)

def sample_field(field,xy,x,y,outside=0.):
    p=np.asarray(xy);shape=p.shape[:-1];flat=p.reshape(-1,2)
    coords=np.array(((flat[:,1]-y[0])/(y[1]-y[0]),(flat[:,0]-x[0])/(x[1]-x[0])))
    if field.ndim==2:return map_coordinates(field,coords,order=1,mode='constant',cval=outside).reshape(shape)
    return np.stack([map_coordinates(field[:,:,k],coords,order=1,mode='constant',cval=outside) for k in range(field.shape[2])],-1).reshape(shape+(field.shape[2],))

def field_noise(x,y,spacing,seed):
    xx=np.asarray(x)/spacing;yy=np.asarray(y)/spacing;i=np.floor(xx);j=np.floor(yy);fx=xx-i;fy=yy-j;fx=fx*fx*(3-2*fx);fy=fy*fy*(3-2*fy)
    def h(a,b):
        q=np.sin(a*127.1+b*311.7+seed*17.37)*43758.5453123;return(q-np.floor(q))*2-1
    return(h(i,j)*(1-fx)+h(i+1,j)*fx)*(1-fy)+(h(i,j+1)*(1-fx)+h(i+1,j+1)*fx)*fy

def main():
    start=time.monotonic();assert not OUTPUT.exists() and not RECEIPT.exists()
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--source-fingerprint',type=Path)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
    source_sha=u.sha256(SOURCE)
    if source_sha!=u.SOURCE_SHA256 and not args.source_fingerprint:raise ValueError('Rebuilt S requires the locked structural fingerprint')
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE));scene=bpy.context.scene;scene.render.threads_mode='FIXED';scene.render.threads=2;scene.cycles.device='CPU'
    existing=list(bpy.data.objects);required=[u.GROUND,u.ORIGINS,*u.RIGID];mutable={scene.objects[n].data.name for n in required};roots={o.name for o in scene.objects if o.name.startswith(u.PLANT_PREFIXES)}
    protected=u.protected_snapshot(bpy,existing,mutable,roots)
    structure=dict(protected=protected,mutable_coordinates={scene.objects[n].data.name:u.data_digest(scene.objects[n].data.vertices,'co',3,'f4') for n in required},root_matrices={n:np.asarray(scene.objects[n].matrix_world).tolist() for n in sorted(roots)})
    structural_sha=hashlib.sha256(json.dumps(structure,sort_keys=True).encode()).hexdigest()
    if source_sha!=u.SOURCE_SHA256 and structural_sha!=json.loads(args.source_fingerprint.read_text())['source_scene_structural_sha256']:raise ValueError('Rebuilt source structure differs')
    print('Y_SOURCE_VERIFIED',source_sha,structural_sha,flush=True)
    u.EDIT_BOUNDS=BOUNDS;u.PATCH_BOUNDS=PATCH;u.in_bounds.__defaults__=(BOUNDS,0.)
    ground=scene.objects[u.GROUND];before=u.exact_patch(ground,PATCH,220000)
    x=np.linspace(BOUNDS[0],BOUNDS[1],103);y=np.linspace(BOUNDS[2],BOUNDS[3],353);xx,yy=np.meshgrid(x,y);xy=np.stack((xx,yy),-1)
    z=before.height(xy);config=FlowConfig();result=simulate_shoulder(x,y,z,config)
    # Never mutate real geometry with unstable transport, even if a solver
    # reports a misleading relative residual against an exploded gross total.
    dz=result.height_delta_m;mobility=result.boundary_mobility
    if not np.isfinite(dz).all() or np.any(dz < -config.max_erosion_m*mobility-1e-9) or np.any(dz > config.max_deposition_m*mobility+1e-9):
        raise AssertionError('Transport failed finite metric displacement bounds before mesh mutation')
    for key in ('net_bed_plus_export_error_m3','sediment_balance_error_m3','water_balance_error_m3'):
        if not np.isfinite(result.receipt[key]) or abs(result.receipt[key])>1e-9:
            raise AssertionError('Transport failed absolute conservation gate: '+key)
    print('FLOW_SOLVED',json.dumps(result.receipt),flush=True)
    co=u.read_coordinates(ground.data);world=u.world_coordinates(ground,co);delta=sample_field(result.height_delta_m,world[:,:2],x,y);u.write_world_z(ground,co,delta);after=u.exact_patch(ground,PATCH,220000)
    disks=u.DiskIndex();movement,root_movement,_,_=u.move_existing(scene,before,after,disks)
    # Statistical source-scale sorting plus transport-driven class exposure.
    def weights(xy):
        px,py=xy[:,0],xy[:,1];d=np.clip(.46+.32*field_noise(px,py,.031,8)+.16*field_noise(px,py,.008,28),.07,.94)
        lag=sample_field(result.lag_exposure,xy,x,y);flowdep=sample_field(result.final_deposit_m,xy,x,y)
        frac=sample_field(result.surface_fraction,xy,x,y,outside=0.)
        inside=(px>=x[0])&(px<=x[-1])&(py>=y[0])&(py<=y[-1])
        fractions=np.where(inside[:,None],frac,np.array([.68,.24,.08]))
        chips=(.10+.92*(1-d)**1.8)/.38;grit=(.26+.78*(1-d))/.68
        chips*=np.clip(.60+5.*fractions[:,2]+.55*lag,.25,2.2)
        grit*=np.clip(.58+1.9*fractions[:,1],.35,1.6)
        return np.stack((np.clip(chips,.08,2.5),np.clip(grit,.1,2.2)),-1)
    # Bounds fit both actual views, with the transport field extending farther
    # down-road than the original density domain. Existing geometry is not scaled.
    density=restore_approved_density(scene,after,before_surface=before,burial_shift=u.loose_shift,bounds=(-6.2,-3.25,-.60,8.2),max_instances=320000,exclusion=disks,population_weights=weights)
    exposure=apply_transported_exposure(scene,result,x,y)
    verified=u.protected_snapshot(bpy,existing,mutable,roots)
    if verified!=protected:raise AssertionError('Protected source geometry/material/camera/light changed')
    # Measure interpolation to existing triangles separately from model balance.
    projected=after.height(xy)-before.height(xy);area=(x[1]-x[0])*(y[1]-y[0]);projection_error=float(np.sum(projected-result.height_delta_m)*area)
    fields=R/'receipts/flow_shoulder_y_fields.npz';np.savez_compressed(fields,x_m=x,y_m=y,source_z_m=z,delta_m=result.height_delta_m,water_m3=result.cumulative_water_m3,erosion_m=result.cumulative_erosion_m,deposition_m=result.cumulative_deposition_m,surface_fraction=result.surface_fraction,lag=result.lag_exposure,compacted_bare=result.compacted_bare,final_deposit_m=result.final_deposit_m)
    scene['scene_version']='R6 Y stage-limited connected wet deposition with transported-grain exposure';scene['flow_limits']='Nonvalidated art-directed multi-event drainage/capacity model; not a surveyed site or engineering forecast'
    bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT),compress=True)
    report=dict(source_scene_sha256=u.sha256(SOURCE),source_scene_structural_sha256=structural_sha,output_scene_sha256=u.sha256(OUTPUT),generator_sha256=u.sha256(Path(__file__)),flow_model_sha256=u.sha256(R/'src/flow_sediment_model_y.py'),density_helper_sha256=u.sha256(R/'src/approved_density_lod.py'),terrain_bounds_m=BOUNDS,grid_shape=list(z.shape),grid_spacing_m=[float(x[1]-x[0]),float(y[1]-y[0])],model=result.receipt,geometry=dict(changed_existing_vertices=int(np.count_nonzero(delta)),displacement_min_max_m=[float(delta.min()),float(delta.max())],projection_volume_difference_m3=projection_error,projected_delta_RMSE_m=float(np.sqrt(np.mean((projected-result.height_delta_m)**2))),additional_ground_sheets=0),density=density,transported_exposure=exposure,exposure_helper_sha256=u.sha256(R/'src/transport_surface_scene_y.py'),allocation_helper_sha256=u.sha256(R/'src/transported_grain_exposure.py'),moved_grains=movement,moved_roots=root_movement,protected_materials_geometry_cameras_lights_unchanged=True,CPU_threads=2,rendered=False,elapsed_seconds=time.monotonic()-start)
    RECEIPT.write_text(json.dumps(report,indent=2)+'\n');print('Y_READY',json.dumps(report),flush=True)

if __name__=='__main__':main()
