"""Compare fixed UV trials against their saved neural surface colors."""
import argparse
import gc
import json
from pathlib import Path
import cumesh
from flex_gemm.ops.grid_sample import grid_sample_3d
import numpy as np
import torch
import trimesh

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--cases',nargs='+',choices=['person','robot','helmet'],default=['person','robot','helmet'])
parser.add_argument('--date',default='20261011')
parser.add_argument('--samples',type=int,default=25000)
parser.add_argument('--trials',type=Path)
parser.add_argument('--output',type=Path)
args=parser.parse_args()
trials=json.loads((args.trials or ROOT/f'tmp/pixal-fixed-geometry-uv-comparison-{args.date}.json').read_text())

def sample_texture(image,uv,mip_level=0):
    rgb=np.asarray(image.convert('RGB'),dtype=np.float64)/255
    linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
    for _ in range(mip_level):
        h,w=linear.shape[:2]
        linear=linear.reshape(h//2,2,w//2,2,3).mean(axis=(1,3))
    height,width=linear.shape[:2]
    x=uv[:,0]*width-.5;y=(1-uv[:,1])*height-.5
    ix=np.floor(x).astype(np.int64);iy=np.floor(y).astype(np.int64)
    dx=(x-ix)[:,None];dy=(y-iy)[:,None]
    value=(linear[iy%height,ix%width]*(1-dx)*(1-dy)+
           linear[iy%height,(ix+1)%width]*dx*(1-dy)+
           linear[(iy+1)%height,ix%width]*(1-dx)*dy+
           linear[(iy+1)%height,(ix+1)%width]*dx*dy)
    return np.where(value<=.0031308,value*12.92,1.055*value**(1/2.4)-.055)*255

def compare(case):
    rows=[row for row in trials if row['case']==case]
    assert rows
    geometry=trimesh.load(rows[0]['geometry'],force='mesh',process=False)
    triangles=np.asarray(geometry.vertices,dtype=np.float32)[geometry.faces]
    rng=np.random.default_rng(17)
    ids=rng.choice(len(triangles),min(args.samples,len(triangles)),replace=False)
    positions=torch.from_numpy(triangles[ids].mean(axis=1)).cuda()
    data=np.load(ROOT/f'tmp/pixal-round3-sparse-resume-{case}-prediction-{args.date}.npz',allow_pickle=False)
    assert str(data['coordinate_system'].item())=='y_up'
    vertices=torch.from_numpy(data['vertices']).cuda()
    faces=torch.from_numpy(data['faces']).cuda()
    bvh=cumesh.cuBVH(vertices,faces)
    _,face_id,uvw=bvh.unsigned_distance(positions,return_uvw=True)
    mapped=(vertices[faces[face_id.long()]]*uvw.unsqueeze(-1)).sum(dim=1)
    attrs=torch.from_numpy(data['attrs']).cuda()
    coords=torch.from_numpy(data['coords']).cuda()
    volume=torch.cat([attrs,torch.ones_like(attrs[:,:1])],dim=-1)
    coordinates=torch.cat([torch.zeros_like(coords[:,:1]),coords],dim=-1)
    size=torch.as_tensor(data['voxel_size'],dtype=torch.float32,device='cuda').reshape(-1)
    if size.numel()==1:size=size.repeat(3)
    grid_size=(1/size).round().int()
    sampled=grid_sample_3d(volume,coordinates,shape=torch.Size([1,volume.shape[1],*grid_size.tolist()]),
                          grid=((mapped+.5)/size).reshape(1,-1,3),mode='trilinear').reshape(-1,volume.shape[1])
    layout=json.loads(str(data['layout'].item()))
    color_slice=slice(*layout['base_color'])
    expected=np.clip(sampled[:,color_slice].cpu().numpy(),0,1)*255
    valid=sampled[:,-1].cpu().numpy()>0
    assert valid.any()
    centroid_y=triangles[ids].mean(axis=1)[:,1]
    min_y,max_y=float(geometry.bounds[0,1]),float(geometry.bounds[1,1])
    upper=centroid_y[valid]>=min_y+(max_y-min_y)*2/3
    results=[]
    for row in rows:
        mesh=trimesh.load(row['model'],force='mesh',process=False)
        assert np.array_equal(np.asarray(mesh.vertices,dtype=np.float32)[mesh.faces],triangles)
        uv=np.asarray(mesh.visual.uv)[mesh.faces[ids]].mean(axis=1)
        actual=sample_texture(mesh.visual.material.baseColorTexture,uv)
        error=np.abs(actual[valid]-expected[valid])
        maximum=error.max(axis=1)
        result=dict(case=case,variant=row['variant'],model=row['model'],sampled_face_centroids=len(ids),
                    valid_neural_samples=int(valid.sum()),missing_neural_samples=int((~valid).sum()),
                    mean_absolute_rgb_byte_error=float(error.mean()),rgb_byte_rmse=float(np.sqrt((error**2).mean())),
                    p95_max_channel_byte_error=float(np.quantile(maximum,.95)),
                    max_channel_error_above_32_fraction=float((maximum>32).mean()),
                    upper_third_mean_rgb_byte_error=float(error[upper].mean()) if upper.any() else None,
                    white_neural_samples=int((expected[valid]>=230).all(axis=1).sum()),
                    white_texture_samples=int((actual[valid]>=230).all(axis=1).sum()),
                    white_on_dark_neural_samples=int(((actual[valid]>=230).all(axis=1)&(expected[valid]<80).all(axis=1)).sum()),
                    measure='Uniform face centroid samples; neural BVH/voxel reference vs base-level bilinear sRGB texture. No mipmap, lighting or reference-image quality score.')
        result['controlled_mip_rgb_byte_mae']={str(level):float(np.abs(sample_texture(mesh.visual.material.baseColorTexture,uv,level)[valid]-expected[valid]).mean()) for level in (0,1,2)}
        result['controlled_mip_scope']='Linear box downsampling at fixed levels, no screen-space GPU derivatives; not a real-camera quality score.'
        results.append(result);print(json.dumps(result),flush=True)
    return results

out=args.output or ROOT/f'tmp/pixal-surface-color-comparison-{args.date}.json'
assert not out.exists(),'Preserve previous color comparison'
results=[]
with torch.no_grad():
    for case in args.cases:
        results.extend(compare(case));gc.collect();torch.cuda.empty_cache()
        out.write_text(json.dumps(results,indent=2),encoding='utf-8')
