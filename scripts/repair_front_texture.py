"""Restore visible front texture from its reference; preserve the original mesh.

This is reference projection, not another Pixal3D prediction. Hidden surfaces
retain the original UV texture. Run only on an axis-aligned, single-mesh GLB.
"""
import argparse
import copy
import io
import json
import struct
from pathlib import Path

import numpy as np
from numba import njit
from PIL import Image
from scipy.ndimage import distance_transform_edt, maximum_filter


def read_glb(path):
    data = path.read_bytes()
    assert data[:4] == b'glTF'
    size, kind = struct.unpack_from('<II', data, 12)
    assert kind == 0x4E4F534A
    doc = json.loads(data[20:20+size])
    length, kind = struct.unpack_from('<II', data, 20+size)
    assert kind == 0x004E4942
    return doc, bytearray(data[28+size:28+size+length])


def accessor(doc, binary, index):
    a = doc['accessors'][index]
    b = doc['bufferViews'][a['bufferView']]
    dtype = {5126:'<f4', 5125:'<u4', 5123:'<u2'}[a['componentType']]
    width = {'SCALAR':1, 'VEC2':2, 'VEC3':3}[a['type']]
    offset = b.get('byteOffset',0)+a.get('byteOffset',0)
    assert b.get('byteStride',np.dtype(dtype).itemsize*width)==np.dtype(dtype).itemsize*width
    return np.frombuffer(binary,dtype=dtype,count=a['count']*width,offset=offset).reshape(a['count'],width).copy()


@njit(cache=True)
def depth_buffer(points, faces, size):
    depth = np.full((size,size),-1e10,np.float32)
    for ids in faces:
        a,b,c = points[ids[0]],points[ids[1]],points[ids[2]]
        den = (b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den)<1e-10:
            continue
        x0 = max(0,int(np.floor(min(a[0],b[0],c[0]))))
        x1 = min(size-1,int(np.ceil(max(a[0],b[0],c[0]))))
        y0 = max(0,int(np.floor(min(a[1],b[1],c[1]))))
        y1 = min(size-1,int(np.ceil(max(a[1],b[1],c[1]))))
        for y in range(y0,y1+1):
            for x in range(x0,x1+1):
                w0 = ((b[1]-c[1])*(x+.5-c[0])+(c[0]-b[0])*(y+.5-c[1]))/den
                w1 = ((c[1]-a[1])*(x+.5-c[0])+(a[0]-c[0])*(y+.5-c[1]))/den
                w2 = 1-w0-w1
                if min(w0,w1,w2)>=-1e-5:
                    z = w0*a[2]+w1*b[2]+w2*c[2]
                    if z>depth[y,x]:
                        depth[y,x]=z
    return depth


def repair(source, reference, output):
    doc,binary = read_glb(source)
    assert len(doc['meshes'])==1 and len(doc['meshes'][0]['primitives'])==1
    assert all(not any(k in n for k in ['matrix','translation','rotation','scale']) for n in doc['nodes'])
    primitive = doc['meshes'][0]['primitives'][0]
    vertices = accessor(doc,binary,primitive['attributes']['POSITION'])
    faces = accessor(doc,binary,primitive['indices']).reshape(-1,3)
    image = Image.open(reference).convert('RGBA')
    rgba = np.array(image)
    bounds = image.getchannel('A').getbbox()
    if bounds is None:
        raise ValueError('Reference has no foreground')
    left,top,right,bottom = bounds
    xy_min,xy_max = vertices[:,:2].min(0),vertices[:,:2].max(0)
    pixels = np.empty((len(vertices),2),np.float32)
    pixels[:,0] = left+(vertices[:,0]-xy_min[0])/(xy_max[0]-xy_min[0])*(right-left-1)
    pixels[:,1] = top+(xy_max[1]-vertices[:,1])/(xy_max[1]-xy_min[1])*(bottom-top-1)
    uv = pixels / np.array([image.width-1,image.height-1],np.float32)
    # glTF samples UV v=0 from the top row of the image; no trimesh V flip.
    size = 1024
    raster = np.column_stack([pixels[:,0]/image.width*size,pixels[:,1]/image.height*size,vertices[:,2]]).astype(np.float32)
    depth = maximum_filter(depth_buffer(raster,faces,size),size=3)
    centroid = raster[faces].mean(axis=1)
    px = np.clip(centroid[:,0].astype(int),0,size-1)
    py = np.clip(centroid[:,1].astype(int),0,size-1)
    front = centroid[:,2] >= depth[py,px]-0.015
    # Do not paint hidden back surfaces or duplicate the face on the crown.
    image_x = np.clip((centroid[:,0]/size*image.width).astype(int),0,image.width-1)
    image_y = np.clip((centroid[:,1]/size*image.height).astype(int),0,image.height-1)
    front &= rgba[image_y,image_x,3]>128
    # Extend edge color under transparent pixels for filtered texture sampling.
    _,nearest = distance_transform_edt(rgba[:,:,3]<=128,return_indices=True)
    rgb = rgba[nearest[0],nearest[1],:3]
    stream = io.BytesIO()
    Image.fromarray(rgb).save(stream,format='PNG')

    def append_view(payload,target=None):
        binary.extend(b'\0'*((-len(binary))%4))
        view={'buffer':0,'byteOffset':len(binary),'byteLength':len(payload)}
        if target:
            view['target']=target
        binary.extend(payload)
        doc['bufferViews'].append(view)
        return len(doc['bufferViews'])-1

    def append_accessor(array,component,kind,target):
        view=append_view(array.tobytes(),target)
        doc['accessors'].append({'bufferView':view,'componentType':component,'count':len(array),'type':kind})
        return len(doc['accessors'])-1

    uv_accessor = append_accessor(uv.astype('<f4'),5126,'VEC2',34962)
    image_view = append_view(stream.getvalue())
    doc['images'].append({'bufferView':image_view,'mimeType':'image/png','name':'Reference front texture'})
    doc['textures'].append({'source':len(doc['images'])-1})
    doc['materials'].append({'name':'Reference front diffuse','pbrMetallicRoughness':{'baseColorTexture':{'index':len(doc['textures'])-1},'metallicFactor':0,'roughnessFactor':1},'doubleSided':True,'alphaMode':'OPAQUE'})
    front_primitive = copy.deepcopy(primitive)
    front_primitive['indices'] = append_accessor(faces[front].reshape(-1).astype('<u4'),5125,'SCALAR',34963)
    front_primitive['attributes']['TEXCOORD_0'] = uv_accessor
    front_primitive['material'] = len(doc['materials'])-1
    back_primitive = copy.deepcopy(primitive)
    back_primitive['indices'] = append_accessor(faces[~front].reshape(-1).astype('<u4'),5125,'SCALAR',34963)
    doc['meshes'][0]['primitives'] = [back_primitive,front_primitive]
    doc['asset']['extras']={'repair':'Visible front reference projection; hidden surfaces preserve Pixal3D texture','source':source.name,'reference':reference.name}
    doc['buffers'][0]['byteLength']=len(binary)
    metadata = json.dumps(doc,separators=(',',':')).encode()
    metadata += b' '*((-len(metadata))%4)
    binary.extend(b'\0'*((-len(binary))%4))
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('wb') as f:
        f.write(struct.pack('<4sII',b'glTF',2,28+len(metadata)+len(binary)))
        f.write(struct.pack('<II',len(metadata),0x4E4F534A));f.write(metadata)
        f.write(struct.pack('<II',len(binary),0x004E4942));f.write(binary)
    check,check_binary=read_glb(output)
    assert np.array_equal(vertices,accessor(check,check_binary,primitive['attributes']['POSITION']))
    assert sum(check['accessors'][p['indices']]['count'] for p in check['meshes'][0]['primitives'])==faces.size
    assert np.allclose(uv[:,1].min(),top/(image.height-1))
    print(json.dumps({'output':str(output),'faces':len(faces),'front_reference_faces':int(front.sum()),'original_hidden_faces':int((~front).sum()),'positions_unchanged':True,'reference_bounds':bounds,'bytes':output.stat().st_size},indent=2),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('reference',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    repair(args.source,args.reference,args.output)
