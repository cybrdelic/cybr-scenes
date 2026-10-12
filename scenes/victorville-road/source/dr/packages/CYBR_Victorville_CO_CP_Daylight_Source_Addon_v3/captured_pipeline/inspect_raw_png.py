"""Validate native opaque RGB PNG structure/CRC/sample storage without editing it.
No color transform, Blender scene loading, image encode, HDR or guide qualification.
"""
from pathlib import Path
import hashlib,json,sys,struct,zlib
from capture_modes import is_png_only_raw
p=Path(sys.argv[1]);r=json.loads(p.read_text());j=r['job'];assert is_png_only_raw(j) and r['engine']=='CYCLES' and not r['guide_paths']
raw=Path(j['output']);data=raw.read_bytes();before=hashlib.sha256(data).hexdigest();assert data[:8]==b'\x89PNG\r\n\x1a\n';pos=8;idat=[];ihdr=None;end=False
while pos<len(data):
 n=struct.unpack('>I',data[pos:pos+4])[0];kind=data[pos+4:pos+8];body=data[pos+8:pos+8+n];crc=struct.unpack('>I',data[pos+8+n:pos+12+n])[0];assert zlib.crc32(kind+body)&0xffffffff==crc;pos+=12+n
 if kind==b'IHDR':assert ihdr is None;ihdr=struct.unpack('>IIBBBBB',body)
 if kind==b'IDAT':idat.append(body)
 assert kind!=b'tRNS','Transparency unsupported'
 if kind==b'IEND':assert n==0;end=True;break
assert end and pos==len(data) and ihdr is not None
w,h,depth,color,compression,filtermethod,interlace=ihdr
assert depth==int(j.get('color_depth',16)) and depth in(8,16);assert color==2,'Only intrinsically opaque truecolor RGB PNG supported';assert (compression,filtermethod,interlace)==(0,0,0);assert [w,h]==r['resolution']
scan=zlib.decompress(b''.join(idat));stride=w*3*(depth//8)+1;assert len(scan)==stride*h and all(scan[y*stride] in range(5)for y in range(h))
native=dict(bit_depth=depth,opaque=True,width=w,height=h,raw_sha256=before,validation='Native RGB PNG IHDR, complete CRCs, zlib stream, scanline sizes and filter codes checked without re-encoding. Integer RGB is intrinsically opaque. No HDR retention, linear roundtrip or denoising qualification.',validator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
assert hashlib.sha256(raw.read_bytes()).hexdigest()==before
raw.with_suffix('.png.native.json').write_text(json.dumps(native,indent=2)+'\n');print('VALIDATED_NATIVE_RAW_PNG',json.dumps(native),flush=True)
