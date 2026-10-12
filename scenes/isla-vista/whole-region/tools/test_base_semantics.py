#!/usr/bin/env python3
"""Small positive and negative controls for strict decoded scene checks."""
import io
import json
from pathlib import Path
import struct
import tempfile

import numpy as np
from PIL import Image
from inspect_base_semantics import inspect_glb, inspect_npz, differences


def glb(path, *, compression=6, delta=0., translation=0., generator='fixture'):
    positions = np.array([[0,0,0],[1,0,0],[0,1,0]],dtype='<f4')
    positions[1,0] += delta
    image = Image.fromarray(np.arange(48,dtype='uint8').reshape(4,4,3))
    output = io.BytesIO(); image.save(output,format='PNG',compress_level=compression)
    png = output.getvalue(); binary = positions.tobytes() + png
    doc = {'asset':{'version':'2.0','generator':generator},
           'buffers':[{'byteLength':len(binary)}],
           'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':positions.nbytes},
                          {'buffer':0,'byteOffset':positions.nbytes,'byteLength':len(png)}],
           'accessors':[{'componentType':5126,'type':'VEC3','bufferView':0,'count':3}],
           'images':[{'bufferView':1,'mimeType':'image/png'}],
           'nodes':[{'mesh':0,'translation':[translation,0,0]}],
           'meshes':[{'primitives':[{'attributes':{'POSITION':0},'material':0}]}],
           'materials':[{'pbrMetallicRoughness':{'baseColorTexture':{'index':0}}}],
           'textures':[{'source':0}], 'scene':0,'scenes':[{'nodes':[0]}]}
    encoded = json.dumps(doc).encode(); encoded += b' '*(-len(encoded)%4)
    binary += b'\0'*(-len(binary)%4)
    total = 12+8+len(encoded)+8+len(binary)
    path.write_bytes(struct.pack('<4sII',b'glTF',2,total)+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(binary),0x004e4942)+binary)


def main():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); base = root/'base.glb'; other = root/'other.glb'
        glb(base); expected = inspect_glb(base)
        glb(other,compression=0,generator='alternate-container')
        actual = inspect_glb(other)
        assert actual['raw_sha256'] != expected['raw_sha256']
        assert actual['encoded_image_sha256'] != expected['encoded_image_sha256']
        assert not differences(actual['semantic'],expected['semantic'])
        glb(other,delta=1e-6)
        assert differences(inspect_glb(other)['semantic'],expected['semantic']), 'Must reject a numerical geometry change'
        glb(other,translation=.001)
        assert differences(inspect_glb(other)['semantic'],expected['semantic']), 'Must reject a node transform change'
        a=root/'a.npz';b=root/'b.npz'
        np.savez(a,metadata=np.array('{"a":1,"b":2}'),height=np.array([1.,2.]))
        np.savez_compressed(b,height=np.array([1.,2.]),metadata=np.array('{ "b": 2, "a": 1 }'))
        assert inspect_npz(a)['raw_sha256'] != inspect_npz(b)['raw_sha256']
        assert not differences(inspect_npz(a)['semantic'],inspect_npz(b)['semantic'])
        np.savez(b,metadata=np.array('{"a":1,"b":2}'),height=np.array([1.,2.+1e-12]))
        assert differences(inspect_npz(a)['semantic'],inspect_npz(b)['semantic']), 'Must reject tiny terrain changes'
    print('PASS: PNG/container-only change accepted; geometry, transform and terrain changes rejected.')

if __name__ == '__main__': main()
