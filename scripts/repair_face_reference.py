"""Bake a visible face reference into existing UVs. Geometry stays byte-identical.

Requires reviewed upright frontal alignment and preprocessing bounds. This is
not identity reconstruction and is deliberately not enabled automatically.
"""
import argparse, io, json, struct, sys
from pathlib import Path
import numpy as np
from PIL import Image
from numba import njit
from scipy.ndimage import maximum_filter
sys.path.insert(0,str(Path(__file__).parent))
from repair_front_texture import read_glb,accessor,depth_buffer

@njit(cache=True)
def bake(v,f,uv,normals,old,ref,projection,zbuffer):
    size=old.shape[0]; out=old.copy(); weights=np.zeros((size,size),np.float32)
    for ids in f:
        # Only head; body and clothing are preserved.
        if v[ids,1].max()<.285: continue
        a,b,c=uv[ids[0]]*(size-1),uv[ids[1]]*(size-1),uv[ids[2]]*(size-1)
        den=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1])
        if abs(den)<1e-9: continue
        for y in range(max(0,int(min(a[1],b[1],c[1]))),min(size-1,int(max(a[1],b[1],c[1]))+1)+1):
            for x in range(max(0,int(min(a[0],b[0],c[0]))),min(size-1,int(max(a[0],b[0],c[0]))+1)+1):
                w0=((b[1]-c[1])*(x+.5-c[0])+(c[0]-b[0])*(y+.5-c[1]))/den
                w1=((c[1]-a[1])*(x+.5-c[0])+(a[0]-c[0])*(y+.5-c[1]))/den;w2=1-w0-w1
                if min(w0,w1,w2)<-1e-5:continue
                pos=w0*v[ids[0]]+w1*v[ids[1]]+w2*v[ids[2]]
                p=w0*projection[ids[0]]+w1*projection[ids[1]]+w2*projection[ids[2]]
                nx=w0*normals[ids[0],2]+w1*normals[ids[1],2]+w2*normals[ids[2],2]
                # Soft boundary on the head/neck and grazing sides. No back painting.
                weight=min(1.,max(0.,(pos[1]-.295)/.018))*min(1.,max(0.,(.435-pos[1])/.015))*min(1.,max(0.,(.084-abs(pos[0]))/.018))
                ix=int(p[0]);iy=int(p[1])
                if weight<=0 or ix<0 or iy<0 or ix>=ref.shape[1]-1 or iy>=ref.shape[0]-1:continue
                if pos[2]<zbuffer[iy,ix]-.025:continue
                fx=p[0]-ix;fy=p[1]-iy
                rgb=(1-fy)*((1-fx)*ref[iy,ix]+fx*ref[iy,ix+1])+fy*((1-fx)*ref[iy+1,ix]+fx*ref[iy+1,ix+1])
                for k in range(3):out[y,x,k]=min(255,max(0,old[y,x,k]*(1-weight)+rgb[k]*weight))
                weights[y,x]=weight
    return out,weights

def repair(source,reference,output,source_bounds,size=4096):
    d,b=read_glb(source);p=d['meshes'][0]['primitives'][0]
    assert len(d['meshes'])==1 and len(d['meshes'][0]['primitives'])==1
    assert all(not any(k in n for k in ['matrix','translation','rotation','scale']) for n in d['nodes'])
    v=accessor(d,b,p['attributes']['POSITION']);f=accessor(d,b,p['indices']).reshape(-1,3);uv=accessor(d,b,p['attributes']['TEXCOORD_0'])
    import trimesh
    normals=np.asarray(trimesh.Trimesh(v,f,process=False).vertex_normals).copy().astype(np.float32)
    ref=np.array(Image.open(reference).convert('RGB'),dtype=np.float32)
    l,t,r,bot=source_bounds; proj=np.empty_like(v)
    proj[:,0]=l+(v[:,0]-v[:,0].min())/np.ptp(v[:,0])*(r-l-1)
    proj[:,1]=t+(v[:,1].max()-v[:,1])/np.ptp(v[:,1])*(bot-t-1);proj[:,2]=v[:,2]
    # Raster in square coordinates without changing image framing.
    side=max(ref.shape[:2]);z=maximum_filter(depth_buffer(proj,f,side),size=3)
    mi=p['material'];ti=d['materials'][mi]['pbrMetallicRoughness']['baseColorTexture']['index'];ii=d['textures'][ti]['source'];view=d['bufferViews'][d['images'][ii]['bufferView']];off=view.get('byteOffset',0)
    old=Image.open(io.BytesIO(bytes(b[off:off+view['byteLength']]))).convert('RGB').resize((size,size),Image.Resampling.LANCZOS)
    out,weights=bake(v.astype(np.float32),f,uv.astype(np.float32),normals,np.array(old),ref,proj,z)
    # UV island gutters must follow restored colors to avoid old-texture outlines.
    from scipy.ndimage import distance_transform_edt
    touched=weights>0
    uvpoints=np.column_stack([uv*(size-1),np.zeros(len(uv))]).astype(np.float32)
    occupied=depth_buffer(uvpoints,f,size)>-1e9
    dist,near=distance_transform_edt(~touched,return_indices=True)
    gutter=(dist<=4)&(~occupied)
    out[gutter]=out[near[0][gutter],near[1][gutter]]
    stream=io.BytesIO();Image.fromarray(out).save(stream,format='PNG');payload=stream.getvalue()
    b.extend(b'\0'*((-len(b))%4));d['bufferViews'].append({'buffer':0,'byteOffset':len(b),'byteLength':len(payload)});b.extend(payload)
    d['images'].append({'bufferView':len(d['bufferViews'])-1,'mimeType':'image/png','name':'Reviewed face reference restoration'})
    d['textures'][ti]['source']=len(d['images'])-1
    # Skin/head now uses diffuse color; retain roughness and metalness maps.
    d['asset'].setdefault('extras',{})['face_repair']={'method':'visible face reference UV bake','geometry_changed':False,'source_bounds':source_bounds,'reference':reference.name}
    d['buffers'][0]['byteLength']=len(b);meta=json.dumps(d,separators=(',',':')).encode();meta+=b' '*((-len(meta))%4);b.extend(b'\0'*((-len(b))%4))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(struct.pack('<4sII',b'glTF',2,28+len(meta)+len(b))+struct.pack('<II',len(meta),0x4e4f534a)+meta+struct.pack('<II',len(b),0x004e4942)+b)
    dd,bb=read_glb(output)
    for key,index in p['attributes'].items(): assert np.array_equal(accessor(d,b,index),accessor(dd,bb,index)),key
    assert np.array_equal(accessor(d,b,p['indices']),accessor(dd,bb,p['indices']))
    report={'output':str(output),'positions_indices_uv_normals_unchanged':True,'painted_texels':int(touched.sum()),'texture_size':size,'source_bounds':source_bounds,'geometry_limit':'Existing glasses and mouth geometry unchanged'}
    output.with_suffix('.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('source',type=Path);a.add_argument('reference',type=Path);a.add_argument('output',type=Path);a.add_argument('--bounds',type=int,nargs=4,required=True);p=a.parse_args();repair(p.source,p.reference,p.output,p.bounds)
