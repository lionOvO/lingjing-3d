"""CPU regression for the actual installed fixed-mesh projection method.

Extracting the method avoids initializing ComfyUI, downloading model weights,
or requiring a GPU. It exercises projector restoration and sparse indexing.
"""
import ast
import contextlib
import json
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import torch
from PIL import Image, ImageDraw

SOURCE = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\pipelines\trellis2_image_to_3d.py')
tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Trellis2ImageTo3DPipeline')
method = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == 'get_proj_cond_shape')
method.decorator_list = []
class Sparse:
    def __init__(self, feats, coords): self.feats, self.coords = feats, coords
ns = {'torch': torch, 'nn': torch.nn, 'np': np, 'Image': Image, 'SparseTensor': Sparse, 'hide_src_module': contextlib.nullcontext}
exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(SOURCE), 'exec'), ns)
run = ns['get_proj_cond_shape']
class Grid:
    def __init__(self, grid_resolution, image_resolution):
        self.grid_resolution, self.image_resolution = grid_resolution, image_resolution
        a = torch.linspace(-1, 1, grid_resolution)
        raw = torch.stack(torch.meshgrid(a, a, a, indexing='ij'), -1).reshape(-1, 3)
        self.grid_points = torch.stack((raw[:, 0], -raw[:, 2], raw[:, 1]), -1)
    def to(self, device): return self
class Model:
    def __init__(self):
        self.grid_resolution = 2
        self.proj_grid = Grid(2, 512)
        self.naf_target_size = 1024
        self.fail = False
    def forward(self, image, camera_angle_x=None, distance=None, mesh_scale=None, transform_matrix=None):
        if self.fail: raise RuntimeError('intentional feature extraction failure')
        self.camera_angle_x = camera_angle_x
        self.distance = distance
        self.mesh_scale = mesh_scale
        return torch.zeros(1, 5, 1), self.proj_grid.grid_points.unsqueeze(0).clone()
    def __call__(self, *args, **kwargs): return self.forward(*args, **kwargs)
def no_camera(): raise RuntimeError('camera estimation disabled for CPU regression')
pipeline = SimpleNamespace(device='cpu', low_vram=False, load_moge_model=no_camera)
model = Model()
original = model.proj_grid
original_points = original.grid_points.clone()
coords = torch.tensor([[0,x,y,z] for x in range(3) for y in range(3) for z in range(3)])
a = torch.linspace(-1,1,3)
canonical = torch.stack(torch.meshgrid(a,a,a,indexing='ij'),-1).reshape(-1,3)
rotated=torch.stack((canonical[:,0],-canonical[:,2],canonical[:,1]),-1)
for repeat in range(2):
    result=run(pipeline,model,[],coords,grid_resolution_override=3,fixed_mesh_projection=True)
    torch.testing.assert_close(result['cond']['proj'].feats,rotated)
    assert model.proj_grid is original and model.grid_resolution == 2
    torch.testing.assert_close(original.grid_points, original_points)
result=run(pipeline,model,[],coords,grid_resolution_override=3)
torch.testing.assert_close(result['cond']['proj'].feats,rotated)
model.fail=True
try: run(pipeline,model,[],coords,grid_resolution_override=3,fixed_mesh_projection=True)
except RuntimeError as e: assert 'intentional' in str(e)
else: raise AssertionError('expected exception')
assert model.proj_grid is original and model.grid_resolution==2
# Exercise the real perspective projection, not just the grid's coordinate order.
projection_source = SOURCE.parents[1] / 'trainers/flow_matching/mixins/image_conditioned_proj.py'
projection_tree = ast.parse(projection_source.read_text(encoding='utf-8'))
projection = next(n for n in projection_tree.body if isinstance(n,ast.FunctionDef) and n.name=='project_points_to_image_batch')
projection.decorator_list=[]
projection_ns={'torch':torch,'Tuple':__import__('typing').Tuple}
exec(compile(ast.fix_missing_locations(ast.Module(body=[projection],type_ignores=[])),str(projection_source),'exec'),projection_ns)
pixels_from_world=projection_ns['project_points_to_image_batch']
model.fail=False
run(pipeline,model,[],coords,grid_resolution_override=3,fixed_mesh_projection=True)
assert float(model.distance)==2
world=rotated/2
camera=torch.tensor([[[1.,0.,0.,0.],[0.,0.,-1.,-float(model.distance)],[0.,1.,0.,0.],[0.,0.,0.,1.]]])
pixels,depth,valid=pixels_from_world(world,camera,model.camera_angle_x,resolution=100)
# At fixed X and depth, increasing world height must move upward in the image.
assert pixels[0,10,1] > pixels[0,16,1]
assert valid.all() and (depth>0).all()
assert model.proj_grid is original and model.grid_resolution==2
run(pipeline,model,[],coords,grid_resolution_override=3)
assert float(model.distance)==2 # generated-geometry behavior remains unchanged
image=Image.new('RGBA',(100,100),(0,0,0,0))
ImageDraw.Draw(image).rectangle((10,10,89,89),fill=(255,255,255,255))
run(pipeline,model,[image],coords,grid_resolution_override=3,fixed_mesh_projection=True)
distance80=float(model.distance)
camera[:,1,3]=-distance80
pixels,_,_=pixels_from_world(world,camera,model.camera_angle_x,resolution=100)
torch.testing.assert_close(torch.max(pixels[0],0).values-torch.min(pixels[0],0).values,torch.tensor([80.,80.]),atol=1e-4,rtol=1e-5)
image=Image.new('RGBA',(100,100),(0,0,0,0))
ImageDraw.Draw(image).rectangle((20,20,79,79),fill=(255,255,255,255))
run(pipeline,model,[image],coords,grid_resolution_override=3,fixed_mesh_projection=True)
assert float(model.distance)>distance80
assert model.proj_grid is original and model.grid_resolution==2
print(json.dumps({'passed':['native_grid_retained_for_fixed_and_generated_mesh','repeated_calls_preserve_projector','generated_projection_unchanged','projector_restored_after_exception','native_Y_maps_to_image_height','alpha_framing_matches_real_perspective_projection','more_padding_increases_camera_distance']},indent=2))
