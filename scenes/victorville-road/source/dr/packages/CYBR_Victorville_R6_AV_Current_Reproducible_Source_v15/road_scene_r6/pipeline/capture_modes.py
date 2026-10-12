"""Explicit capture policy. A failed guided capture never chooses another mode."""
from pathlib import Path
def component_filter_policy(job):
    policy=job.get('component_filter_policy','retain_transmission')
    if policy not in ('retain_transmission','filter_both'):raise ValueError('Unsupported component_filter_policy: '+str(policy))
    if 'component_filter_policy' in job and job.get('capture_mode','guided')!='component-recombined':raise ValueError('Component filter policy requires component-recombined capture')
    return policy
def capture_mode(job):
    mode=job.get('capture_mode','guided')
    if mode not in ('guided','unfiltered','component-recombined'):raise ValueError('Unsupported capture_mode: '+str(mode))
    component_filter_policy(job)
    return mode
def final_image(job):
    raw=Path(job['output']);prefix={'guided':'CLEAN_OIDN_','unfiltered':'UNFILTERED_','component-recombined':'COMPONENT_RECOMBINED_'}[capture_mode(job)]
    return raw.parent/(prefix+raw.stem.removeprefix('INTERNAL_')+'.png')
def is_workbench_raw(job):
    return capture_mode(job)=='unfiltered' and job.get('engine')=='BLENDER_WORKBENCH'
if __name__=='__main__':
    import json,sys
    action,path=sys.argv[1:];job=json.load(open(path))
    if action=='mode':print(capture_mode(job))
    elif action=='image':print(final_image(job))
    elif action=='workbench':print('yes' if is_workbench_raw(job) else 'no')
    elif action=='component-policy':print(component_filter_policy(job))
    else:raise ValueError('Unknown action')
