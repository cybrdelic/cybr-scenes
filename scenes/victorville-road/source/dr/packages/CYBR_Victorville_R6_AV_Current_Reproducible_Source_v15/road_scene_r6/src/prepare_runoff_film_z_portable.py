"""Z: one finite loose-film runoff event over immutable Y road/shoulder geometry."""
from pathlib import Path
import os,sys,json,time,hashlib,ast
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS'):os.environ[k]='2'
import numpy as np
import bpy
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'src'))
import prepare_physical_lenses as u
from road_film_surface_z import sample
from road_film_shader_z import apply
from flow_sediment_model_z import FlowConfig,simulate_shoulder
SOURCE=R/'preview/road_r6_y_wet_connected.blend';OUTPUT=R/'preview/road_r6_z_runoff_film.blend';RECEIPT=R/'receipts/runoff_film_z.json'
# Portable admission wrapper. Original rendered builder remains separate and byte-identical.
import argparse
import semantic_scene_guard_z as semantic_guard
SEMANTIC_GUARD_PATH=R/'receipts/y_semantic_source_guard_v3.json'
SEMANTIC_GUARD_FILE_SHA256='ade5e70e390fe6cd0b4bc3a6c5c338178aa6dbd79982cc32a46d6e79c2b86210'

def load_semantic_guard():
    if u.sha256(SEMANTIC_GUARD_PATH)!=SEMANTIC_GUARD_FILE_SHA256:
        raise ValueError('Pinned semantic source manifest differs; never bypass or replace it')
    contract=json.loads(SEMANTIC_GUARD_PATH.read_text())
    if semantic_guard.digest_record(contract['snapshot'])!=contract['semantic_sha256']:
        raise ValueError('Semantic manifest internal digest differs')
    for path,key in ((R/'src/semantic_scene_guard_z.py','helper_sha256'),(R/'src/prepare_physical_lenses.py','base_helper_sha256')):
        if u.sha256(path)!=contract[key]:raise ValueError('Semantic admission helper differs: '+path.name)
    return contract

def validate_loaded_scene():
    """Validate the currently loaded scene without executing model/shader code."""
    contract=load_semantic_guard()
    bpy.context.view_layer.update()
    actual=semantic_guard.verify_scene(bpy,contract)
    return dict(semantic_sha256=actual,semantic_match=True,
        expected_original_Y_sha256=contract['source_sha256'],
        guard_file_sha256=SEMANTIC_GUARD_FILE_SHA256,
        guard_helper_sha256=contract['helper_sha256'])

def admit_source(source):
    """Read real bytes, load Y, and require the complete pinned semantic snapshot."""
    before=u.sha256(source)
    bpy.ops.wm.open_mainfile(filepath=str(source))
    receipt=validate_loaded_scene()
    if u.sha256(source)!=before:raise ValueError('Source bytes changed during semantic admission')
    receipt.update(actual_source_sha256=before,
        source_serialization_matches_original=before==receipt['expected_original_Y_sha256'],
        serialized_byte_equality_required=False)
    return receipt

def source_arguments():
    parser=argparse.ArgumentParser(description='Portable Z entrypoint with strict semantic Y admission')
    parser.add_argument('--source',type=Path,default=SOURCE)
    parser.add_argument('--validate-only','--validation-only',dest='validate_only',action='store_true')
    parser.add_argument('--admission-receipt',type=Path)
    return parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])

def geometry_fingerprint():
    h=hashlib.sha256()
    for mesh in sorted(bpy.data.meshes,key=lambda m:m.name):
        h.update(mesh.name.encode());h.update(u.read_coordinates(mesh).tobytes())
        for prop,width in [('vertex_index',1)]:
            a=np.empty(len(mesh.loops)*width,np.int32);mesh.loops.foreach_get(prop,a);h.update(a.tobytes())
    for ob in sorted(bpy.context.scene.objects,key=lambda o:o.name):h.update(ob.name.encode());h.update(np.asarray(ob.matrix_world,dtype=np.float64).tobytes())
    return h.hexdigest()
def main():
    global SOURCE
    args=source_arguments();SOURCE=args.source
    t=time.monotonic()
    if not args.validate_only:
        if OUTPUT.exists() or RECEIPT.exists():raise FileExistsError('Preserve prior Z output/receipt; use a fresh extraction')
    admission=admit_source(SOURCE)
    if args.validate_only:
        admission.update(validation_only=True,model_executed=False,material_body_executed=False,scene_written=False)
        if args.admission_receipt:
            with args.admission_receipt.open('x') as output:output.write(json.dumps(admission,indent=2)+'\n')
        print('Z_SEMANTIC_ADMISSION_ONLY',json.dumps(admission),flush=True)
        return
    s=bpy.context.scene;s.render.threads_mode='FIXED';s.render.threads=2;s.cycles.device='CPU';bpy.context.view_layer.update()
    before=geometry_fingerprint();x=np.linspace(-5.8,-2.6,129);y=np.linspace(-.6,8.2,353);xx,yy=np.meshgrid(x,y);xy=np.stack((xx,yy),-1)
    z,pavement,sampling=sample(s,xy,(-5.9,-2.5,-.7,8.3));print('Z_ACTUAL_SURFACE',sampling,flush=True)
    tree=ast.parse((R/'src/build_scene.py').read_text());defs=[q for q in tree.body if isinstance(q,ast.FunctionDef) and q.name in {'field','edge_y'}];ns={'np':np};exec(compile(ast.Module(body=defs,type_ignores=[]),'<retained-road-planform>','exec'),ns)
    inset=xx-ns['edge_y'](yy,-1);feed=np.clip(1-inset/.42,0,1)
    initial=np.zeros(z.shape+(3,));initial[~pavement]=.00030*np.array([.90,.09,.01]);initial[:,:,0][pavement]=(.000080*feed)[pavement]
    caps=np.where(pavement,.00035,.00065)
    cfg=FlowConfig(rainfall_m=(.010,),event_duration_s=1200.,upstream_width_m=1.2,max_erosion_m=.001,max_event_erosion_m=.001,max_deposition_m=.001)
    flow=simulate_shoulder(x,y,z,cfg,initial_mobile_class_thickness_m=initial,maximum_deposited_thickness_m=caps)
    stock=flow.remaining_initial_mobile_class_thickness_m+flow.retained_deposit_by_class_m;matrix=stock[:,:,0]
    for key in ('net_bed_plus_export_error_m3','sediment_balance_error_m3','water_balance_error_m3'):assert abs(flow.receipt[key])<1e-9,key
    assert np.min(stock)>=0 and np.max(flow.retained_deposit_by_class_m.sum(axis=-1)-caps)<1e-12
    # Stored heights remain fixed: the event is a submillimetre visual film.
    data=np.ones(z.shape+(4,),np.float32);data[:,:,0]=matrix;data[:,:,1]=initial[:,:,0];data[:,:,2]=pavement.astype(np.float32)
    im=bpy.data.images.new('Z finite surface-film inventory / metres',width=len(x),height=len(y),float_buffer=True,alpha=True);im.colorspace_settings.name='Non-Color';im.alpha_mode='CHANNEL_PACKED';im.pixels.foreach_set(data.ravel());im.update();im.pack()
    materials=apply(s,im,(x,y));assert geometry_fingerprint()==before,'Scene geometry or transforms changed during the film pass'
    fields=R/'receipts/runoff_film_z_fields.npz';np.savez_compressed(fields,x_m=x,y_m=y,actual_surface_z_m=z,pavement=pavement,initial_mobile_class_thickness_m=initial,remaining_mobile_class_thickness_m=stock,retained_deposit_by_class_m=flow.retained_deposit_by_class_m,virtual_height_delta_m=flow.height_delta_m,cumulative_water_m3=flow.cumulative_water_m3)
    area=(x[1]-x[0])*(y[1]-y[0]);road_stats={'area_m2':float(pavement.sum()*area),'initial_matrix_volume_m3':float(initial[:,:,0][pavement].sum()*area),'final_matrix_volume_m3':float(matrix[pavement].sum()*area),'fraction_road_over20um':float(np.mean(matrix[pavement]>.000020)),'fraction_road_over60um':float(np.mean(matrix[pavement]>.000060)),'max_final_road_film_m':float(stock[pavement].sum(axis=-1).max())}
    s['scene_version']='R6 Z finite loose-film runoff over immutable Y geometry';bpy.context.preferences.filepaths.save_version=0;bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT),compress=True)
    report={'source_sha256':u.sha256(SOURCE),'scene_sha256':u.sha256(OUTPUT),'builder_sha256':u.sha256(Path(__file__)),'model_sha256':u.sha256(R/'src/flow_sediment_model_z.py'),'surface_helper_sha256':u.sha256(R/'src/road_film_surface_z.py'),'shader_helper_sha256':u.sha256(R/'src/road_film_shader_z.py'),'geometry_unchanged_sha256':before,'surface_sampling':sampling,'model':flow.receipt,'road_film':road_stats,'materials':materials,'field_sha256':u.sha256(fields),'limits':'One art-directed10mm rain event, finite submillimetre loose reservoir over fixed Y surface. Absolute film opacity and shelter retention are uncalibrated visual approximations. Virtual height feedback is not applied to native scene geometry. No validated site reconstruction or hydrology.','CPU_threads':2,'elapsed_seconds':time.monotonic()-t}
    report['semantic_source_admission']=admission
    RECEIPT.write_text(json.dumps(report,indent=2)+'\n');print('Z_READY',json.dumps(report),flush=True)
if __name__=='__main__':main()
