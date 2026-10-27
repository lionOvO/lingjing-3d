"""Write float linear vertex colors for atlas-free diagnostic rendering."""
import json
import struct
from pathlib import Path
import numpy as np

def write_reference(path, vertices, faces, srgb):
    path=Path(path)
    assert not path.exists(), 'Preserve previous reference'
    linear=np.where(srgb<=.04045,srgb/12.92,((srgb+.055)/1.055)**2.4).astype('<f4')
    arrays=[np.asarray(vertices,dtype='<f4'),np.asarray(faces,dtype='<u4').reshape(-1),linear]
    views=[];offset=0
    for array in arrays:
        views.append(dict(buffer=0,byteOffset=offset,byteLength=array.nbytes))
        offset+=array.nbytes
    document=dict(asset=dict(version='2.0',generator='Pixal neural-color diagnostic'),scene=0,
        scenes=[dict(nodes=[0])],nodes=[dict(mesh=0)],
        meshes=[dict(primitives=[dict(attributes=dict(POSITION=0,COLOR_0=2),indices=1,material=0)])],
        materials=[dict(pbrMetallicRoughness=dict(baseColorFactor=[1,1,1,1],metallicFactor=0,roughnessFactor=1))],
        buffers=[dict(byteLength=offset)],bufferViews=views,
        accessors=[dict(bufferView=0,componentType=5126,count=len(vertices),type='VEC3',
                        min=arrays[0].min(axis=0).tolist(),max=arrays[0].max(axis=0).tolist()),
                   dict(bufferView=1,componentType=5125,count=faces.size,type='SCALAR'),
                   dict(bufferView=2,componentType=5126,count=len(vertices),type='VEC3')])
    encoded=json.dumps(document,separators=(',',':')).encode('utf-8')
    encoded+=b' '*((-len(encoded))%4)
    binary=b''.join(a.tobytes() for a in arrays)
    payload=(struct.pack('<III',0x46546c67,2,12+8+len(encoded)+8+len(binary))+
             struct.pack('<II',len(encoded),0x4e4f534a)+encoded+
             struct.pack('<II',len(binary),0x004e4942)+binary)
    path.write_bytes(payload)
    # Check serialized colors rather than a reader's optional 8-bit conversion.
    json_length=struct.unpack_from('<I',payload,12)[0]
    saved=np.frombuffer(payload,dtype='<f4',offset=28+json_length+views[2]['byteOffset']).reshape(-1,3)
    assert np.array_equal(saved,linear)
    return linear
