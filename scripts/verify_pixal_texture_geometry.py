"""Verify automatic texturing kept the supplied geometry and exported PBR UVs."""
from pathlib import Path
import argparse
import json
import struct
import numpy as np
from scipy.spatial import cKDTree
parser=argparse.ArgumentParser()
parser.add_argument('result')
parser.add_argument('--original', type=Path)
args=parser.parse_args()
folder=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\output')

def read(path):
    data=path.read_bytes()
    assert data[:4]==b'glTF'
    size,kind=struct.unpack_from('<II',data,12)
    doc=json.loads(data[20:20+size])
    start=20+size
    bsize,bkind=struct.unpack_from('<II',data,start)
    binary=memoryview(data)[start+8:start+8+bsize]
    primitive=doc['meshes'][0]['primitives'][0]
    def accessor(index):
        item=doc['accessors'][index]
        view=doc['bufferViews'][item['bufferView']]
        dtype={5126:'<f4',5125:'<u4',5123:'<u2'}[item['componentType']]
        width={'VEC3':3,'VEC2':2,'SCALAR':1}[item['type']]
        assert 'byteStride' not in view
        offset=view.get('byteOffset',0)+item.get('byteOffset',0)
        return np.frombuffer(binary,dtype=dtype,count=item['count']*width,offset=offset).reshape(item['count'],width)
    return doc,primitive,accessor
original,op,oa=read(args.original or folder/'Pixal3D_Geometry_512_00001_.glb')
result,rp,ra=read(Path(args.result))
old_vertices=oa(op['attributes']['POSITION'])
new_vertices=ra(rp['attributes']['POSITION'])
old_faces=oa(op['indices']).reshape(-1,3)
new_faces=ra(rp['indices']).reshape(-1,3)
assert len(old_faces)==len(new_faces)
center=(old_vertices.max(0)+old_vertices.min(0))/2
scale=.99999/(old_vertices.max(0)-old_vertices.min(0)).max()
normalized=(old_vertices-center)*scale
# Hash each triangle's unordered coordinates. UV unwrapping may reorder and duplicate vertices.
def triangle_keys(vertices,faces):
    points=np.rint((vertices+.5)*1_000_000).astype(np.uint64)
    keys=points[:,0]*np.uint64(73856093)^points[:,1]*np.uint64(19349663)^points[:,2]*np.uint64(83492791)
    face_keys=np.sort(keys[faces],axis=1)
    digest=face_keys[:,0]*np.uint64(0x9e3779b185ebca87)^face_keys[:,1]*np.uint64(0xc2b2ae3d27d4eb4f)^face_keys[:,2]
    return np.sort(digest)
# Resolve tiny GLB float round trips before matching complete triangle sets.
distance,vertex_ids=cKDTree(normalized).query(new_vertices,workers=4)
assert distance.max()<2e-7, float(distance.max())
np.testing.assert_array_equal(triangle_keys(normalized,old_faces),triangle_keys(normalized[vertex_ids],new_faces))
uv=ra(rp['attributes']['TEXCOORD_0'])
assert np.isfinite(uv).all() and uv.min()>=0 and uv.max()<=1
material=result['materials'][rp['material']]['pbrMetallicRoughness']
assert 'baseColorTexture' in material and 'metallicRoughnessTexture' in material
print(json.dumps({'faces_preserved':len(old_faces),'vertices_with_uv':len(new_vertices),'all_triangle_positions_preserved':True,'max_position_error':float(distance.max()),'finite_uv':True,'base_color_and_metallic_roughness':True}),flush=True)
