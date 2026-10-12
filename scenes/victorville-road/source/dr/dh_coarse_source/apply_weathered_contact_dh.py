"""Full-source late morphology/contact gate, with the DG source already applied."""
def apply(scene,cfg,out):
 assert cfg['revision']==1
 from apply_weathered_fields import apply as replace
 from check_terrain_contact import apply as contact
 r=replace(scene,cfg['coarse'],out)
 cc=dict(cfg['contact']);cc['CG_prototypes']=[e['prototype_index']for e in r['entries']if e['source_kind']=='CG'];cc['AS_mesh_names']=[e['new_mesh']for e in r['entries']if e['source_kind']=='AS']
 c=contact(scene,cc,out)
 assert c['unsupported_bodies']==0,'Changed clast has no exact soil contact witness'
 return {'coarse_geometry':r,'coarse_contact':c}
