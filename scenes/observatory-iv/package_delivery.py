"""Package the executed scene without caches, font files, or old previews."""
from __future__ import annotations
import hashlib,json,shutil,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OUT=ROOT.parent
TOP='CYBR_Observatory_IV'

def digest(path:Path)->str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for data in iter(lambda:f.read(1<<20),b''):h.update(data)
    return h.hexdigest()

def main():
    source=[]
    for n in ['CMakeLists.txt','LICENSE','README.md','RAW_FORMATS.md','THIRD_PARTY_NOTICES.md','requirements.txt','requirements-tested.txt','build_scene.py','finish.py','verify.py','render.sh','package_delivery.py','make_gallery.py']:
        source.append(ROOT/n)
    source+=sorted((ROOT/'src').glob('*'))
    source+=sorted((ROOT/'assets').glob('*'))
    common=source+[ROOT/'scene/manifest.json',ROOT/'scene/texture_manifest.json']
    common+=sorted(p for p in (ROOT/'verification').glob('*.json') if 'preview' not in p.name)
    common+=sorted(p for p in (ROOT/'verification').glob('*.log') if p.name in ['final_render.log','archive_smoke.log','delivery_verify.log'])
    common+=sorted(p for p in (ROOT/'renders').glob('Observatory_IV*') if p.suffix in ['.png','.json'] and '_quick' not in p.stem)
    ready=common+sorted(p for p in (ROOT/'scene').rglob('*') if p.is_file() and p not in common)
    ready+=[ROOT/'renders/Observatory_IV_raw.exr']
    raw=sorted(p for p in (ROOT/'renders').glob('Observatory_IV*') if p.suffix in ['.pfm','.guides','.samples','.spectral','.npz','.exr','.json'])
    raw+=[ROOT/'RAW_FORMATS.md',ROOT/'finish.py',ROOT/'requirements.txt']
    sets={'CYBR_Observatory_IV_Source.zip':common,'CYBR_Observatory_IV_Ready_to_Render.zip':ready,'CYBR_Observatory_IV_Raw_Data.zip':raw}
    results=[]
    for name,paths in sets.items():
        dest=OUT/name
        unique=sorted(set(paths))
        for p in unique:
            if not p.is_file():raise FileNotFoundError(p)
            if p.suffix.lower() in ('.ttf','.otf','.woff','.woff2'):raise RuntimeError('Font file must not be distributed')
        hashes={str(p.relative_to(ROOT)):digest(p) for p in unique}
        with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=4,allowZip64=True) as z:
            for p in unique:z.write(p,f'{TOP}/{p.relative_to(ROOT)}')
            z.writestr(f'{TOP}/FILE_HASHES.json',json.dumps(hashes,indent=2))
            if 'Source.zip' in name:
                z.writestr(f'{TOP}/BUILD_FIRST.txt','This compact archive contains the full renderer source, authoring recipe, retained source geometry, material previews, and finished image. Run python build_scene.py first to generate the large ready-to-render mesh and float material maps. The larger Ready_to_Render archive already includes those assets.\n')
        with zipfile.ZipFile(dest) as z:
            actual_file_count=len(z.infolist());bad=z.testzip()
            if bad:raise RuntimeError(f'Archive CRC failure: {bad}')
        result={'name':name,'path':str(dest),'bytes':dest.stat().st_size,'sha256':digest(dest),'files':actual_file_count,'crc_verified':True}
        results.append(result);print(json.dumps(result),flush=True)
    receipt={'archives':results,'render_metadata':json.loads((ROOT/'renders/Observatory_IV.json').read_text()),'scope':'Actual rendered images and native scene; no generative processing; native/raw file hashes included'}
    (OUT/'CYBR_Observatory_IV_Delivery.json').write_text(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
