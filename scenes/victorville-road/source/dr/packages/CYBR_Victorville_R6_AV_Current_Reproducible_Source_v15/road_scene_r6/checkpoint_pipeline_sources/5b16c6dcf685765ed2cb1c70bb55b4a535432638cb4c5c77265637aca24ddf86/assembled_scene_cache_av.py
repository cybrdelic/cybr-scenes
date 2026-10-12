"""Optional one-time assembled-scene acceleration, before preview reductions.
The pinned inputs and builder remain the reproducible source path. This cache
never replaces them and is not required by source regeneration instructions.
"""
from pathlib import Path
import hashlib,json,shutil,time
import bpy

def hash_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):h.update(block)
    return h.hexdigest()

def inventory(scene):
    return {'objects':{o.name:{'type':o.type,'data':o.data.name if o.data else None,'matrix':[list(v) for v in o.matrix_world],'hide_render':o.hide_render} for o in scene.objects},
            'meshes':{m.name:{'vertices':len(m.vertices),'edges':len(m.edges),'polygons':len(m.polygons),'loops':len(m.loops),'materials':[x.name if x else None for x in m.materials]} for m in bpy.data.meshes},
            'images':{i.name:{'size':list(i.size),'packed':bool(i.packed_file),'colorspace':i.colorspace_settings.name} for i in bpy.data.images}}

def save(scene,config,source,source_sha256,pipeline,job,adaptations,image_dependencies):
    """Distinct compressed copy only; rejects overwrite and insufficient headroom."""
    start=time.monotonic();dest=Path(config['path']).resolve();source=Path(source).resolve()
    root=Path(__file__).resolve().parents[1]
    # Source snapshots live in pipeline/pipeline_snapshots/<hash>, so the caller
    # supplies and pins the canonical allowed directory instead of inferring it.
    allowed=Path(config['allowed_directory']).resolve()
    if dest.parent!=allowed or dest==source or dest.suffix!='.blend':raise ValueError('Cache target must be a distinct explicit .blend in the allowed directory')
    receipt=dest.with_suffix('.blend.json')
    if dest.exists() or receipt.exists():raise FileExistsError('Refusing to replace an assembled scene cache')
    if not dest.parent.is_dir():raise ValueError('Existing cache directory required')
    reserve=int(config.get('reserve_bytes',120*1024**2));estimate=int(config.get('estimated_max_bytes',800*1024**2))
    if reserve<120*1024**2 or not 0<estimate<=1024**3:raise ValueError('Invalid bounded cache space contract')
    free=shutil.disk_usage(dest.parent).free
    if free<reserve+estimate:raise OSError('Insufficient headroom for one assembled cache plus shared reserve')
    for layer in scene.view_layers:layer.update()
    oldpath=bpy.data.filepath;before=inventory(scene)
    if hash_file(source)!=source_sha256:raise ValueError('Immutable source changed before cache save')
    result=bpy.ops.wm.save_as_mainfile(filepath=str(dest),check_existing=True,compress=True,relative_remap=True,copy=True)
    if 'FINISHED' not in result:raise RuntimeError('Blender cache save did not finish')
    if bpy.data.filepath!=oldpath or inventory(scene)!=before:raise RuntimeError('Copy-save unexpectedly changed in-memory source bindings or inventory')
    if hash_file(source)!=source_sha256:raise RuntimeError('Source bytes changed during cache save')
    report={'path':str(dest),'sha256':hash_file(dest),'bytes':dest.stat().st_size,'source':str(source),'source_sha256':source_sha256,
            'pipeline':pipeline,'assembly_job':job,'completed_adaptations':adaptations,'image_dependencies':image_dependencies,
            'inventory':before,'blender_version':bpy.app.version_string,'elapsed_seconds':time.monotonic()-start,
            'free_before_bytes':free,'free_after_bytes':shutil.disk_usage(dest.parent).free,'estimated_max_bytes':estimate,
            'scope':'Optional assembled cache before camera cull, asphalt geometry stride, image mips, or compositor guide creation. Full intrinsic source data retained; particle allocation is limited to the recorded views and pixel resolutions.',
            'fresh_full_regeneration_verified':False,'saved_before_preview_reductions':True,'immutable_source_verified':True}
    with receipt.open('x') as stream:json.dump(report,stream,indent=2)
    print('ASSEMBLED_CACHE_SAVED',str(dest),report['bytes'],report['sha256'],flush=True)
    return {k:report[k] for k in ('path','sha256','bytes','scope','elapsed_seconds','free_after_bytes')}
