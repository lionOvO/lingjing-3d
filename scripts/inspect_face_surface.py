"""CPU raster diagnostics: identical camera for texture and clay, no mesh edits."""
import argparse
import io
import sys
from pathlib import Path
import numpy as np
from PIL import Image
from numba import njit
sys.path.insert(0, str(Path(__file__).parent))
from repair_front_texture import read_glb, accessor

@njit(cache=True)
def raster(v, f, uv, tex, size, mode):
    zbuf=np.full((size,size),-1e10,np.float32)
    out=np.full((size,size,3),44,np.uint8)
    for ids in f:
        a,b,c=v[ids[0]],v[ids[1]],v[ids[2]]
        den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den)<1e-10: continue
        n=np.cross(b-a,c-a); n=n/(np.sqrt((n*n).sum())+1e-10)
        shade=.35+.65*abs(n[2]*.85-n[0]*.3-n[1]*.4)
        for y in range(max(0,int(min(a[1],b[1],c[1]))),min(size-1,int(max(a[1],b[1],c[1]))+1)+1):
            for x in range(max(0,int(min(a[0],b[0],c[0]))),min(size-1,int(max(a[0],b[0],c[0]))+1)+1):
                w0=((b[1]-c[1])*(x+.5-c[0])+(c[0]-b[0])*(y+.5-c[1]))/den
                w1=((c[1]-a[1])*(x+.5-c[0])+(a[0]-c[0])*(y+.5-c[1]))/den
                w2=1-w0-w1
                z=w0*a[2]+w1*b[2]+w2*c[2]
                if min(w0,w1,w2)<-1e-5 or z<=zbuf[y,x]: continue
                zbuf[y,x]=z
                t=w0*uv[ids[0]]+w1*uv[ids[1]]+w2*uv[ids[2]]
                tx=min(tex.shape[1]-1,max(0,int(t[0]*(tex.shape[1]-1))))
                ty=min(tex.shape[0]-1,max(0,int(t[1]*(tex.shape[0]-1))))
                for k in range(3): out[y,x,k]=min(255,(tex[ty,tx,k] if mode==0 else 205)* (1 if mode==0 else shade))
    return out,zbuf

def render(source, output, angle=0):
    d,b=read_glb(source); size=800
    result=np.full((size,size,3),44,np.uint8); depth=np.full((size,size),-1e10,np.float32)
    for p in d['meshes'][0]['primitives']:
        v=accessor(d,b,p['attributes']['POSITION']); f=accessor(d,b,p['indices']).reshape(-1,3); uv=accessor(d,b,p['attributes']['TEXCOORD_0'])
        # Full body Y-up, face occupies the upper fifth. Fixed physical crop.
        rad=np.radians(angle); x=v[:,0]*np.cos(rad)+v[:,2]*np.sin(rad); z=-v[:,0]*np.sin(rad)+v[:,2]*np.cos(rad)
        points=np.stack([(x+.105)/.21*size,(.49-v[:,1])/.21*size,z/.21*size],axis=1).astype(np.float32)
        image_id=d['textures'][d['materials'][p['material']]['pbrMetallicRoughness']['baseColorTexture']['index']]['source']
        view=d['bufferViews'][d['images'][image_id]['bufferView']]; off=view.get('byteOffset',0)
        tex=np.array(Image.open(io.BytesIO(bytes(b[off:off+view['byteLength']]))).convert('RGB'))
        for mode in [0,1]:
            frame,dep=raster(points,f,uv,tex,size,mode)
            if mode==0:
                take=dep>depth;result[take]=frame[take];depth[take]=dep[take]
            else:
                if 'clay' not in locals(): clay=np.full_like(result,44);cd=np.full_like(depth,-1e10)
                take=dep>cd;clay[take]=frame[take];cd[take]=dep[take]
    Image.fromarray(result).save(output)
    Image.fromarray(clay).save(output.with_stem(output.stem+'-clay'))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('source',type=Path);a.add_argument('output',type=Path);a.add_argument('--angle',type=float,default=0);p=a.parse_args();render(p.source,p.output,p.angle)

