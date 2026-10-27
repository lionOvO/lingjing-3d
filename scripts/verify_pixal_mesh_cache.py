"""Real CUDA regression for replacing topology after hole filling."""
import ast
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
import trimesh
import cumesh

source=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\nodes.py')
tree=ast.parse(source.read_text(encoding='utf-8'))
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Trellis2_GGUFPostProcessAndUnWrapAndRasterizer')
method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='process')
fill=next(n for n in method.body if isinstance(n,ast.If) and ast.unparse(n.test)=='fill_holes')
assert ast.unparse(fill.body[-2])=='cumesh.clear_cache()'
block=compile(ast.fix_missing_locations(ast.Module(body=fill.body[-2:],type_ignores=[])),str(source),'exec')
box=trimesh.creation.box()
verts=torch.tensor(box.vertices,dtype=torch.float32,device='cuda')
faces=torch.tensor(box.faces,dtype=torch.int32,device='cuda')
mesh=cumesh.CuMesh();mesh.init(verts,faces);mesh.compute_vertex_normals()
original=mesh.read_vertex_normals().clone()
v=torch.cat([verts,verts+2]);f=torch.cat([faces,faces+len(verts)])
mesh.init(v,f)
assert mesh.read_all_cache()['vertex_normals'].shape[0]==8 # real old cache survived init
ns=dict(cumesh=mesh,torch=torch,coords=SimpleNamespace(device='cuda'),new_vertices=v.cpu().numpy(),new_faces=f.cpu().numpy())
exec(block,ns)
mesh.compute_vertex_normals();actual=mesh.read_vertex_normals()
torch.cuda.synchronize()
torch.testing.assert_close(actual,torch.cat([original,original]))
print('PASS: real stale 8-vertex cache replaced by correct 16-vertex normals.',flush=True)
path=Path(r'D:\灵境造物\tmp\pixal-cleaned-geometry-20261009.npz')
if path.is_file():
    data=np.load(path)
    ns.update(new_vertices=data['vertices'],new_faces=data['faces'])
    exec(block,ns)
    mesh.compute_vertex_normals();normals=mesh.read_vertex_normals()
    torch.cuda.synchronize()
    assert normals.shape==ns['new_vertices'].shape
    assert torch.isfinite(normals[torch.tensor(np.unique(ns['new_faces']),device='cuda')]).all()
    print('PASS: actual failed-person filled topology recomputes finite normals.',tuple(normals.shape),flush=True)
