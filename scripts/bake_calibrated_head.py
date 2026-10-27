"""Visible-camera color bake for a separately reconstructed head.

Camera parameters MUST come from the corresponding geometry run. No bounding
box camera fitting or identity generation. Leaves unseen texture unchanged.
"""
import sys,io,json,struct
from pathlib import Path
import numpy as np
from PIL import Image
from scipy.ndimage import maximum_filter,distance_transform_edt
from numba import njit
sys.path.insert(0,str(Path(__file__).parent))
from repair_front_texture import read_glb,accessor,depth_buffer

@njit(cache=True)
def bake(v,f,uv,old,ref,depth,focal,distance):
    out=old.copy();touched=np.zeros(old.shape[:2],np.bool_);size=len(old)
    for ids in f:
        a,b,c=uv[ids[0]]*(size-1),uv[ids[1]]*(size-1),uv[ids[2]]*(size-1)
        den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den)<1e-9:continue
        for y in range(max(0,int(min(a[1],b[1],c[1]))),min(size-1,int(max(a[1],b[1],c[1]))+1)+1):
            for x in range(max(0,int(min(a[0],b[0],c[0]))),min(size-1,int(max(a[0],b[0],c[0]))+1)+1):
                w0=((b[1]-c[1])*(x+.5-c[0])+(c[0]-b[0])*(y+.5-c[1]))/den;w1=((c[1]-a[1])*(x+.5-c[0])+(a[0]-c[0])*(y+.5-c[1]))/den;w2=1-w0-w1
                if min(w0,w1,w2)<-1e-5:continue
                p=w0*v[ids[0]]+w1*v[ids[1]]+w2*v[ids[2]]
                px=(.5+focal*p[0]/(distance-p[2]))*(ref.shape[1]-1);py=(.5-focal*p[1]/(distance-p[2]))*(ref.shape[0]-1)
                ix=int(px);iy=int(py)
                if ix<0 or iy<0 or ix>=ref.shape[1]-1 or iy>=ref.shape[0]-1:continue
                if p[2]<depth[iy,ix]-.006 or ref[iy,ix,3]<240:continue
                fx=px-ix;fy=py-iy
                for k in range(3):out[y,x,k]=(1-fy)*((1-fx)*ref[iy,ix,k]+fx*ref[iy,ix+1,k])+fy*((1-fx)*ref[iy+1,ix,k]+fx*ref[iy+1,ix+1,k])
                touched[y,x]=True
    return out,touched

def main(source,reference,output):
    d,b=read_glb(source);p=d['meshes'][0]['primitives'][0];v=accessor(d,b,p['attributes']['POSITION']);f=accessor(d,b,p['indices']).reshape(-1,3);uv=accessor(d,b,p['attributes']['TEXCOORD_0'])
    fov=.5266384510676052;distance=1.8547451496124268;focal=.5/np.tan(fov/2)
    ref=np.array(Image.open(reference).convert('RGBA'),dtype=np.float32);side=ref.shape[0];assert ref.shape[1]==side
    points=np.stack([(.5+focal*v[:,0]/(distance-v[:,2]))*(side-1),(.5-focal*v[:,1]/(distance-v[:,2]))*(side-1),v[:,2]],1).astype(np.float32)
    depth=maximum_filter(depth_buffer(points,f,side),size=3)
    material=d['materials'][p['material']]['pbrMetallicRoughness'];ti=material['baseColorTexture']['index'];ii=d['textures'][ti]['source'];view=d['bufferViews'][d['images'][ii]['bufferView']];off=view.get('byteOffset',0)
    old=np.array(Image.open(io.BytesIO(bytes(b[off:off+view['byteLength']]))).convert('RGB').resize((4096,4096),Image.Resampling.LANCZOS))
    out,touched=bake(v,f,uv,old,ref,depth,focal,distance)
    occ=depth_buffer(np.column_stack([uv*4095,np.zeros(len(uv))]).astype(np.float32),f,4096)>-1e9
    dist,near=distance_transform_edt(~touched,return_indices=True);gutter=(dist<=4)&(~occ);out[gutter]=out[near[0][gutter],near[1][gutter]]
    st=io.BytesIO();Image.fromarray(out).save(st,format='PNG');payload=st.getvalue();b.extend(b'\0'*((-len(b))%4));d['bufferViews'].append({'buffer':0,'byteOffset':len(b),'byteLength':len(payload)});b.extend(payload);d['images'].append({'bufferView':len(d['bufferViews'])-1,'mimeType':'image/png'});d['textures'][ti]['source']=len(d['images'])-1
    material['metallicFactor']=0;material['roughnessFactor']=1;material.pop('metallicRoughnessTexture',None)
    report={'method':'geometry-run calibrated perspective source color bake','fov':fov,'distance':distance,'painted_texels':int(touched.sum()),'geometry_changed':False,'unseen_surfaces':'generated texture retained; unverified'}
    d['asset'].setdefault('extras',{})['camera_bake']=report;d['buffers'][0]['byteLength']=len(b);meta=json.dumps(d,separators=(',',':')).encode();meta+=b' '*((-len(meta))%4);b.extend(b'\0'*((-len(b))%4));output.write_bytes(struct.pack('<4sII',b'glTF',2,28+len(meta)+len(b))+struct.pack('<II',len(meta),0x4e4f534a)+meta+struct.pack('<II',len(b),0x004e4942)+b)
    dd,bb=read_glb(output)
    for key,index in p['attributes'].items():assert np.array_equal(accessor(d,b,index),accessor(dd,bb,index)),key
    output.with_suffix('.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
if __name__=='__main__':main(*map(Path,sys.argv[1:]))
