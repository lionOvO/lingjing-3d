"""Check the installed Pixal3D mesh entry/exit against its native projector."""
import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Tuple
import numpy as np
import torch
import trimesh

source=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\pipelines\trellis2_image_to_3d.py')
tree=ast.parse(source.read_text(encoding='utf-8'))
klass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Trellis2ImageTo3DPipeline')
preprocess=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name=='preprocess_mesh')
ns={'trimesh':trimesh,'np':np}
exec(compile(ast.fix_missing_locations(ast.Module(body=[preprocess],type_ignores=[])),str(source),'exec'),ns)
mesh=trimesh.creation.box(extents=(1.,3.,2.))
original=mesh.vertices.copy()
canonical=(original-(original.min(0)+original.max(0))/2)*(.99999/3)
native=ns['preprocess_mesh'](SimpleNamespace(isPixal3D=True),mesh)
np.testing.assert_allclose(native.vertices,canonical)
np.testing.assert_array_equal(mesh.vertices,original)
legacy=ns['preprocess_mesh'](SimpleNamespace(isPixal3D=False),mesh)
np.testing.assert_allclose(legacy.vertices,np.stack((canonical[:,0],-canonical[:,2],canonical[:,1]),-1))
postprocess=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name=='postprocess_mesh')
conversion=next(n for n in postprocess.body if isinstance(n,ast.If) and ast.unparse(n.test)=='not self.isPixal3D')
for pixal,vertices in [(True,native.vertices.copy()),(False,legacy.vertices.copy())]:
    exit_ns={'self':SimpleNamespace(isPixal3D=pixal),'vertices':vertices,'normals':vertices.copy()}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[conversion],type_ignores=[])),str(source),'exec'),exit_ns)
    np.testing.assert_allclose(exit_ns['vertices'],canonical)
vertex_bake=next(n for n in postprocess.body if isinstance(n,ast.If) and ast.unparse(n.test)=='bake_on_vertices')
vertex_conversion=next(n for n in vertex_bake.body if isinstance(n,ast.If) and ast.unparse(n.test)=='not self.isPixal3D')
for pixal,vertices in [(True,native.vertices.copy()),(False,legacy.vertices.copy())]:
    exit_ns={'self':SimpleNamespace(isPixal3D=pixal),'vertices_np':vertices,'normals_np':vertices.copy()}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[vertex_conversion],type_ignores=[])),str(source),'exec'),exit_ns)
    np.testing.assert_allclose(exit_ns['vertices_np'],canonical)
texture=next(n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name=='texture_mesh')
calls=[n for n in ast.walk(texture) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='sample_tex_slat']
assert any(any(k.arg=='fixed_mesh_projection' and isinstance(k.value,ast.Constant) and k.value.value is True for k in call.keywords) for call in calls)
projection_source=source.parents[1]/'trainers/flow_matching/mixins/image_conditioned_proj.py'
projection_tree=ast.parse(projection_source.read_text(encoding='utf-8'))
projection=next(n for n in projection_tree.body if isinstance(n,ast.FunctionDef) and n.name=='project_points_to_image_batch')
projection.decorator_list=[]
projection_ns={'torch':torch,'Tuple':Tuple}
exec(compile(ast.fix_missing_locations(ast.Module(body=[projection],type_ignores=[])),str(projection_source),'exec'),projection_ns)
points=torch.tensor([[0.,-.25,.2],[0.,.25,.2]])
world=torch.stack((points[:,0],-points[:,2],points[:,1]),-1)
camera=torch.tensor([[[1.,0.,0.,0.],[0.,0.,-1.,-2.],[0.,1.,0.,0.],[0.,0.,0.,1.]]])
pixels,depth,valid=projection_ns['project_points_to_image_batch'](world,camera,torch.tensor([.857556]),100)
assert pixels[0,0,1]>pixels[0,1,1] and valid.all() and (depth>0).all()
print('PASS: Pixal3D Y-up geometry, native projection height, PBR and vertex-color export round trips; TRELLIS conversion preserved.')
