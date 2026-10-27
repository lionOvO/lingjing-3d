"""Show saved neural colors on fixed geometry without a UV texture atlas."""
import gc
import json
from pathlib import Path
import sys
import cumesh
from flex_gemm.ops.grid_sample import grid_sample_3d
import numpy as np
import torch
import trimesh
sys.path.insert(0,str(Path(__file__).resolve().parent))
from pixal_neural_color_glb import write_reference

root=Path(__file__).resolve().parents[1]
output=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\output')
report=root/'tmp/pixal-round4-neural-color-reference-linear-20261012.json'
assert not report.exists(), 'Preserve previous reference export'
rows=[]
def export(case):
    geometry=json.loads((root/f'tmp/pixal-full-round3-sparse-resume-{case}-metrics.json').read_text())[0]['model']
    mesh=trimesh.load(geometry,force='mesh',process=False)
    gv=np.asarray(mesh.vertices,dtype=np.float32);gf=np.asarray(mesh.faces,dtype=np.int32)
    snapshot=root/f'tmp/pixal-round3-sparse-resume-{case}-prediction-20261011.npz'
    data=np.load(snapshot,allow_pickle=False)
    assert str(data['coordinate_system'].item())=='y_up'
    vertices=torch.from_numpy(data['vertices']).cuda();faces=torch.from_numpy(data['faces']).cuda()
    bvh=cumesh.cuBVH(vertices,faces)
    attrs=torch.from_numpy(data['attrs']).cuda();coords=torch.from_numpy(data['coords']).cuda()
    volume=torch.cat([attrs,torch.ones_like(attrs[:,:1])],dim=-1)
    coordinates=torch.cat([torch.zeros_like(coords[:,:1]),coords],dim=-1)
    size=torch.as_tensor(data['voxel_size'],dtype=torch.float32,device='cuda').reshape(-1)
    if size.numel()==1:size=size.repeat(3)
    grid_size=(1/size).round().int()
    layout=json.loads(str(data['layout'].item()));color_slice=slice(*layout['base_color'])
    colors=[];occupancy=[]
    for start in range(0,len(gv),262144):
        positions=torch.from_numpy(gv[start:start+262144]).cuda()
        _,face_id,uvw=bvh.unsigned_distance(positions,return_uvw=True)
        mapped=(vertices[faces[face_id.long()]]*uvw.unsqueeze(-1)).sum(dim=1)
        sampled=grid_sample_3d(volume,coordinates,shape=torch.Size([1,volume.shape[1],*grid_size.tolist()]),
                              grid=((mapped+.5)/size).reshape(1,-1,3),mode='trilinear').reshape(-1,volume.shape[1])
        colors.append(sampled[:,color_slice].cpu().numpy());occupancy.append(sampled[:,-1].cpu().numpy())
    rgb=np.clip(np.concatenate(colors),0,1);valid=np.concatenate(occupancy)>0
    assert valid.all(), 'Do not fill missing colors in a neural reference'
    path=output/f'PixalNeuralColorReference_{case}_linear_fixedgeometry_20261012.glb'
    assert not path.exists()
    write_reference(path,gv,gf,rgb)
    saved=trimesh.load(path,force='mesh',process=False)
    assert np.array_equal(saved.vertices.astype(np.float32)[saved.faces],gv[gf])
    color_path=root/f'tmp/pixal-neural-vertex-colors-{case}-20261012.npz'
    assert not color_path.exists()
    np.savez(color_path,vertices=gv,faces=gf,neural_rgb=rgb)
    row=dict(case=case,model=str(path),geometry=geometry,snapshot=str(snapshot),
             vertices=len(gv),faces=len(gf),valid_samples=int(valid.sum()),missing_samples=0,
             ordered_geometry_exact=True,white_neural_vertices=int((rgb>=230/255).all(axis=1).sum()),
             color_encoding='Float32 linear COLOR_0, converted from native baked sRGB interpretation',
             rgb_quantiles=np.quantile(rgb,[0,.1,.5,.9,1],axis=0).tolist(),
             measure='Neural BVH/voxel RGB sampled at fixed mesh vertices. GPU sampler unchanged; no UV atlas, image projection or inpainting. Vertex interpolation is an approximation of the continuous neural color field.')
    print(json.dumps(row),flush=True)
    return row
with torch.no_grad():
    for case in ('person','robot','helmet'):
        rows.append(export(case));gc.collect();torch.cuda.empty_cache()
        report.write_text(json.dumps(rows,indent=2),encoding='utf-8')
