"""Fetch checked public inputs; never replace a changed geographic snapshot."""
from pathlib import Path
import argparse,hashlib,json,os,tempfile,time,urllib.request
ROOT=Path(__file__).resolve().parent

def normalized(value):
    if isinstance(value,float) and value.is_integer():return int(value)
    if isinstance(value,list):return [normalized(x) for x in value]
    if isinstance(value,dict):return {k:normalized(v) for k,v in value.items()}
    return value

def canonical(document):
    # All ordered features and all their attributes/geometry are preserved.
    # ArcGIS fields/type schema is not read anywhere by the source adapter.
    payload={'features':document['features'],'wkid':document.get('spatialReference',{}).get('wkid',4326)}
    return hashlib.sha256(json.dumps(normalized(payload),sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()

def validate(data,row):
    raw=hashlib.sha256(data).hexdigest()
    if raw==row['sha256']:return {'match':'raw_sha256','raw_sha256':raw}
    expected=row.get('consumed_features_sha256')
    if expected:
        actual=canonical(json.loads(data))
        if actual==expected:return {'match':'ordered_features_and_crs','raw_sha256':raw,'consumed_features_sha256':actual,'metadata_limit':'Only unconsumed service schema or JSON formatting differs.'}
    raise ValueError('Source changed: '+row['path']+'; historical sha256='+row['sha256']+' actual='+raw+'. A compatible dated public snapshot is required. Changed data was not installed.')

def resolve(root=ROOT,download=False,kind=None):
    manifest=json.loads((ROOT/'INPUTS.json').read_text());report=[]
    for row in manifest['files']:
        if kind and row['kind']!=kind:continue
        destination=(root/row['path']).resolve()
        if not destination.is_relative_to(root.resolve()):raise ValueError('Unsafe input path')
        if destination.is_file():status=validate(destination.read_bytes(),row);status['source']='local'
        elif download:
            request=urllib.request.Request(row['url'],headers={'User-Agent':'CYBR-Isla-Vista-source-replay/1','Accept-Encoding':'identity'})
            with urllib.request.urlopen(request,timeout=60) as response:
                data=response.read(20*1024*1024+1)
            if len(data)>20*1024*1024:raise ValueError('Input exceeds bounded download size')
            status=validate(data,row);destination.parent.mkdir(parents=True,exist_ok=True)
            fd,name=tempfile.mkstemp(prefix=destination.name+'.',suffix='.partial',dir=destination.parent)
            try:
                with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
                os.replace(name,destination)
            finally:
                if os.path.exists(name):os.unlink(name)
            status['source']='public_download'
        else:raise FileNotFoundError('Missing '+row['path']+'; run python public_inputs.py fetch first.')
        status['path']=row['path'];report.append(status);print(json.dumps(status),flush=True)
    receipt={'checked_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'files':report,'passed':True,'warning':'Public live GIS URLs are mutable. Any feature/attribute/coordinate drift fails; no durable provider archive is claimed.'}
    (root/'PUBLIC_INPUT_VALIDATION.json').write_text(json.dumps(receipt,indent=2)+'\n');return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['fetch','verify']);p.add_argument('--kind',choices=['geographic','material']);p.add_argument('--destination',type=Path,default=ROOT);a=p.parse_args();a.destination.mkdir(parents=True,exist_ok=True);resolve(a.destination,a.action=='fetch',a.kind)
