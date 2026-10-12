"""Prepare a bounded view from the one verified AV assembled cache.
No scene construction, geometry mutation, render, or overwrite is performed.
Only the two pixel resolutions/poses used by the finite grain allocator qualify.
"""
from pathlib import Path
import argparse,copy,hashlib,json

def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for b in iter(lambda:stream.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def prepare(cache,output,view):
    cache=Path(cache).resolve();meta=json.loads(cache.with_suffix('.blend.json').read_text())
    if digest(cache)!=meta['sha256'] or cache.stat().st_size!=meta['bytes']:raise ValueError('Assembled cache bytes differ')
    if meta.get('saved_before_preview_reductions') is not True:raise ValueError('Cache lacks pre-LOD qualification')
    old=meta['assembly_job'];allocation=old['refresh_view_grains_au']
    views=[{k:allocation[k] for k in ('camera_location','camera_target','lens','width','height')}]+allocation.get('additional_views',[])
    index={'outward':0,'road':1}[view]
    if index>=len(views):raise ValueError('Requested camera not allocated in cache')
    pose=views[index];out=Path(output).resolve()
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True)
    keys=('engine','samples','capture_mode','save_guides','light_tree','color_depth','dither_intensity','use_adaptive_sampling','rss_cap_mib','compact_bvh','camera_cull_prefixes','camera_cull_margin','asphalt_preview_map_size','preview_cull_terrain_faces','terrain_cull_margin','asphalt_preview_grid_stride','release_unused_heap')
    job={k:copy.deepcopy(old[k]) for k in keys if k in old}
    job.update(pose,source=str(cache),source_sha256=meta['sha256'],output=str(out/'INTERNAL_PANEL.png'),time_limit_seconds=360,sync_limit_seconds=300,
               view_scope='Exact verified AV assembled cache; camera and resolution already included in finite-particle allocation. Same documented preview mips/culls; no rebuild or claimed native-detail equivalence.')
    (out/'job.json').write_text(json.dumps(job,indent=2))
    (out/'ASSEMBLED_CACHE_PROVENANCE.json').write_text(json.dumps({'source_cache_sha256':meta['sha256'],'source_receipt_sha256':digest(cache.with_suffix('.blend.json')),'assembly_pipeline':meta['pipeline'],'assembly_job':old,'selected_qualified_view':pose,'source_admission':'Exact assembled cache bytes, derived from pinned source via the recorded complete audited assembly'},indent=2))
    return out/'job.json'

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cache',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--view',choices=['outward','road'],required=True);a=p.parse_args();print(prepare(a.cache,a.output,a.view))
