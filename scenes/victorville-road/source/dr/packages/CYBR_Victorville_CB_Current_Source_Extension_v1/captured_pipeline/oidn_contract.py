"""OIDN 2.5 RT guide contract. No clipping, normalization or optical changes."""
DOC='https://www.openimagedenoise.org/documentation.html'
def validate_stats(stats,require_nonzero_features=False):
    violations=[]
    for name in ('beauty','albedo','normal'):
        s=stats[name]
        if not s.get('finite',True):violations.append(name+': nonfinite values')
        lo,hi=s['min'],s['max']
        if name=='beauty' and lo<0:violations.append('HDR beauty: expected nonnegative linear values')
        if name=='albedo' and (lo<0 or hi>1):violations.append('Albedo: expected [0,1], got '+str((lo,hi)))
        if name=='normal' and (lo< -1 or hi>1):violations.append('Normal: expected signed [-1,1], got '+str((lo,hi)))
        if require_nonzero_features and name in ('albedo','normal') and s.get('nonzero_pixel_fraction',0)<=0:
            violations.append(name+': declared opaque surface feature has zero coverage')
    return {'valid':not violations,'violations':violations,'policy':'Fail closed; retain untouched linear beauty and raw guides. No silent clipping or color-only fallback.','documentation':DOC,'ranges':{n:{k:stats[n][k] for k in ('min','max')} for n in stats}}
