"""Exercise actual masked/chunked baking against a known linear PBR field."""
import ast
from pathlib import Path
from types import SimpleNamespace
import torch
import flex_gemm
source=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\pipelines\trellis2_image_to_3d.py')
tree=ast.parse(source.read_text(encoding='utf-8'))
klass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Trellis2ImageTo3DPipeline')
method=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name=='postprocess_mesh')
start=next(i for i,n in enumerate(method.body) if isinstance(n,ast.Assign) and isinstance(n.targets[0],ast.Name) and n.targets[0].id=='attrs')
end=next(i for i,n in enumerate(method.body[start:],start) if isinstance(n,ast.Expr) and ast.unparse(n.value)=='torch.cuda.synchronize()')
block=ast.fix_missing_locations(ast.Module(body=method.body[start:end],type_ignores=[]))
points=torch.stack(torch.meshgrid(*[torch.arange(4,device='cuda')]*3,indexing='ij'),-1).reshape(-1,3)
coords=torch.cat([torch.zeros((64,1),device='cuda',dtype=torch.int),points.int()],1)
feats=torch.cat([points.float()/3,torch.full((64,3),.4,device='cuda')],1)
voxel=SimpleNamespace(feats=feats,coords=coords,shape=torch.Size([1,6]),spatial_shape=torch.Size([4,4,4]))
torch.manual_seed(112)
pos=torch.rand((513,513,3),device='cuda')*.75-.375
mask=torch.ones((513,513),dtype=torch.bool,device='cuda')
mask[0,0]=False
mask[2,3]=False
ns={'torch':torch,'flex_gemm':flex_gemm,'pbr_voxel':voxel,'pos':pos,'mask':mask,'resolution':4,'texture_size':513,'self':SimpleNamespace(device='cuda')}
exec(compile(block,str(source),'exec'),ns)
attrs=ns['attrs']
sampled=attrs[mask]
torch.testing.assert_close(sampled[:,:3],((pos[mask]+.5)*4-.5)/3,rtol=1e-5,atol=1e-6)
torch.testing.assert_close(sampled[:,3:],torch.full_like(sampled[:,3:],.4),rtol=1e-5,atol=1e-6)
assert not attrs[~mask].any()
assert int(mask.sum())>262144
print('PASS: real CUDA PBR interpolation, chunk boundary, and masked texels match the known linear field.')
