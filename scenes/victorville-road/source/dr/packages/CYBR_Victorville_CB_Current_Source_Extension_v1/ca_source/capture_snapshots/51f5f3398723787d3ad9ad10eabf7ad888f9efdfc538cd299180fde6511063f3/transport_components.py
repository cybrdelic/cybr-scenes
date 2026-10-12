"""Linear native Cycles pass accounting. No clipping or filtering is performed here."""
import numpy as np
LIGHT_PASSES={
 'diffuse_direct':'DiffDir','diffuse_indirect':'DiffInd','diffuse_color':'DiffCol',
 'glossy_direct':'GlossDir','glossy_indirect':'GlossInd','glossy_color':'GlossCol',
 'transmission_direct':'TransDir','transmission_indirect':'TransInd','transmission_color':'TransCol',
 'emission':'Emit','environment':'Env','volume_direct':'VolumeDir','volume_indirect':'VolumeInd'}

def split(data):
    required={'beauty',*LIGHT_PASSES};assert required<=set(data),'Incomplete physical pass set'
    shape=data['beauty'].shape;assert len(shape)==3 and shape[2]==3
    assert all(a.shape==shape and np.isfinite(a).all() for a in data.values())
    d={k:np.asarray(data[k],dtype=np.float64) for k in required}
    p={k:(d[k+'_direct']+d[k+'_indirect'])*d[k+'_color'] for k in ['diffuse','glossy','transmission']}
    t=(p['transmission']+d['emission']).astype(np.float32)
    r=(p['diffuse']+p['glossy']+d['environment']+d['volume_direct']+d['volume_indirect']).astype(np.float32)
    assert np.all(r>=0) and np.any(r>0),'OIDN remainder must be nonnegative and nonempty'
    delta=d['beauty']-t.astype(np.float64)-r.astype(np.float64)
    # An identity residual alone could hide an omitted pass. Fail closed unless
    # the actual physical pass sum already agrees to the declared native16
    # relative precision budget. This is an integration guard, not a theorem
    # about every Cycles accumulation order or a material calibration.
    scale=np.maximum(np.maximum(abs(d['beauty']),abs(t.astype(np.float64))+r),np.finfo(np.float32).tiny)
    assert np.all(abs(delta)<=scale*2.**-16),'Physical pass reconstruction exceeds native16 relative residual guard'
    assert np.all(np.maximum(-t.astype(np.float64),0)<=scale*2.**-16),'Negative transmission exceeds signed roundoff guard'
    state={'transmission_emission':t,'physical_remainder':r,'roundoff_residual':delta}
    assert np.array_equal(recombine(state,r),data['beauty'].astype(np.float32)),'Identity recombination must recover original float32 Combined'
    return state

def partition_transmission(state):
    """Positive OIDN input and unchanged tiny signed pass-arithmetic terms."""
    t=state['transmission_emission'];r=state['physical_remainder'];delta=state['roundoff_residual']
    assert t.dtype==r.dtype==np.float32 and delta.dtype==np.float64
    assert t.shape==r.shape==delta.shape and all(np.isfinite(a).all() for a in [t,r,delta])
    assert np.all(r>=0)
    beauty=t.astype(np.float64)+r.astype(np.float64)+delta
    scale=np.maximum(np.maximum(abs(beauty),abs(t.astype(np.float64))+r),np.finfo(np.float32).tiny)
    assert np.all(abs(delta)<=scale*2.**-16),'Original physical reconstruction residual exceeds guard'
    assert np.all(np.maximum(-t.astype(np.float64),0)<=scale*2.**-16),'Negative transmission exceeds signed roundoff guard'
    positive=np.where(t>=0,t,np.float32(0));signed=np.where(t<0,t,np.float32(0))
    assert np.array_equal(positive.astype(np.float64)+signed.astype(np.float64),t.astype(np.float64))
    return positive,signed

def recombine(state,filtered,filtered_transmission=None):
    t=state['transmission_emission'];delta=state['roundoff_residual']
    assert filtered.shape==t.shape==delta.shape and np.isfinite(filtered).all()
    assert np.all(filtered>=0),'No negative OIDN output clipping is allowed'
    if filtered_transmission is None:
        # Keep the established LCD/CRT arithmetic order unchanged.
        result=(t.astype(np.float64)+filtered.astype(np.float64)+delta).astype(np.float32)
    else:
        f=np.asarray(filtered_transmission);assert f.shape==t.shape and np.isfinite(f).all() and np.all(f>=0),'Filtered transmission must be nonnegative; no clipping'
        _,signed=partition_transmission(state)
        result=(f.astype(np.float64)+signed.astype(np.float64)+filtered.astype(np.float64)+delta).astype(np.float32)
    assert np.isfinite(result).all() and np.all(result>=0),'No final pixel clipping is allowed'
    return result
