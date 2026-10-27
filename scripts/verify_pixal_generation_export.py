"""Run installed export code on analytical PBR fields, without loading weights."""
import ast
import copy
import gc
from pathlib import Path
from types import SimpleNamespace
from typing import Dict

import cv2
import cumesh as CuMesh
import numpy as np
import nvdiffrast.torch as dr
from PIL import Image
import torch
import trimesh as Trimesh
from flex_gemm.ops.grid_sample import grid_sample_3d

ROOT = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF')


def installed_method(path, class_name, method_name, namespace):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == class_name)
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == method_name)
    method.decorator_list = []
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(path), 'exec'), namespace)
    return namespace[method_name]


class ProgressBar:
    def __init__(self, *_): pass
    def update(self, *_): pass


class ImageUtils:
    @staticmethod
    def pil_to_tensor(image):
        return torch.from_numpy(np.asarray(image).copy()).float()[None] / 255


base_path = ROOT / 'trellis2_gguf/representations/mesh/base.py'
tree = ast.parse(base_path.read_text(encoding='utf-8'))
mesh_cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MeshWithVoxel')
namespace = {'torch': torch, 'Dict': Dict, 'Mesh': type('Mesh', (), {'device': property(lambda self: self.vertices.device)}), 'Voxel': type('Voxel', (), {})}
exec(compile(ast.fix_missing_locations(ast.Module(body=[mesh_cls], type_ignores=[])), str(base_path), 'exec'), namespace)
MeshWithVoxel = namespace['MeshWithVoxel']

box = Trimesh.creation.box(extents=[.6, .4, .2])
vertices = torch.tensor(box.vertices, dtype=torch.float32, device='cuda')
faces = torch.tensor(box.faces, dtype=torch.int32, device='cuda')
coords = torch.stack(torch.meshgrid(*[torch.arange(8, device='cuda', dtype=torch.int32)] * 3, indexing='ij'), -1).reshape(-1, 3)
attrs = torch.zeros(len(coords), 6, device='cuda')
attrs[coords[:, 0] >= 4, 0] = 1
attrs[:, 3] = .3  # metallic
attrs[:, 4] = .7  # roughness
attrs[:, 5] = 1   # alpha
layout = {'base_color': slice(0, 3), 'metallic': 3, 'roughness': 4, 'alpha': 5}
mesh = MeshWithVoxel(vertices, faces, [-.5] * 3, 1 / 8, coords, attrs, torch.Size([1, 6, 8, 8, 8]), layout, 'y_up')
assert mesh.to('cpu').to('cuda').coordinate_system == 'y_up'
assert MeshWithVoxel(vertices, faces, [-.5] * 3, 1 / 8, coords, attrs, torch.Size([1, 6, 8, 8, 8]), layout).coordinate_system == 'z_up'

bvh = CuMesh.cuBVH(vertices, faces)
bvh.vertices, bvh.faces = vertices, faces
sample_batches = []
inpaint_calls = []


def sample(*args, **kwargs):
    sample_batches.append(kwargs['grid'].shape[1])
    return grid_sample_3d(*args, **kwargs)


def inpaint(image, mask, *args):
    inpaint_calls.append((image.copy(), mask.copy()))
    return cv2.inpaint(image, mask, *args)


ns = dict(torch=torch, np=np, Trimesh=Trimesh, Image=Image, ImageUtils=ImageUtils, ProgressBar=ProgressBar,
          copy=copy, gc=gc, CuMesh=CuMesh, dr=dr, grid_sample_3d=sample,
          cv2=SimpleNamespace(inpaint=inpaint, INPAINT_TELEA=cv2.INPAINT_TELEA))
node_path = ROOT / 'nodes.py'
method = installed_method(node_path, 'Trellis2_GGUFPostProcessAndUnWrapAndRasterizer', 'process', ns)
kwargs = dict(mesh_cluster_threshold_cone_half_angle_rad=60, mesh_cluster_refine_iterations=0,
              mesh_cluster_global_iterations=1, mesh_cluster_smooth_strength=1, texture_size=1024,
              remesh=False, remesh_band=1, remesh_project=0, target_face_num=100,
              simplify_method='Cumesh', fill_holes=False, texture_alpha_mode='OPAQUE',
              dual_contouring_resolution='1024', double_side_material=False, remove_floaters=False,
              bake_on_vertices=False, use_custom_normals=True, uv_unwrap_method='Xatlas',
              bvh=bvh, remove_inner_faces=False)
new_mesh = method(None, mesh=mesh, **kwargs)[0]
assert np.allclose(new_mesh.bounds, box.bounds)
assert max(sample_batches) <= 262144
assert len(sample_batches) >= 2
rgb, new_mask = inpaint_calls[0]
valid_black = (rgb.max(-1) == 0) & (new_mask == 0)
assert valid_black.sum() > 10000
new_texture = np.asarray(new_mesh.visual.material.baseColorTexture)
assert (new_texture[..., :3][valid_black] == 0).all()

old_calls = []
old_ns = dict(ns)
old_ns['cv2'] = SimpleNamespace(INPAINT_TELEA=cv2.INPAINT_TELEA,
    inpaint=lambda image, mask, *args: (old_calls.append((image.copy(), mask.copy())) or cv2.inpaint(image, mask, *args)))
old = installed_method(Path(str(node_path) + '.bak-before-general-pipeline-20261009'),
                       'Trellis2_GGUFPostProcessAndUnWrapAndRasterizer', 'process', old_ns)
old_mesh = old(None, mesh=mesh, **kwargs)[0]
old_rgb, old_mask = old_calls[0]
assert np.array_equal(old_rgb, rgb)
assert (old_mask[valid_black] != 0).all()
old_texture = np.asarray(old_mesh.visual.material.baseColorTexture)
changed_black = int((old_texture[..., :3][valid_black].max(-1) != 0).sum())
assert changed_black > 0
print(f'PASS: {valid_black.sum()} valid black texels preserved; old code altered {changed_black}.')

mesh.coordinate_system = 'z_up'
vertex_mesh = method(None, mesh=mesh, **{**kwargs, 'bake_on_vertices': True})[0]
expected = box.vertices[:, [0, 2, 1]] * [1, 1, -1]
assert np.allclose(vertex_mesh.bounds, np.array([expected.min(0), expected.max(0)]))
mesh.coordinate_system = 'y_up'
vertex_mesh = method(None, mesh=mesh, **{**kwargs, 'bake_on_vertices': True})[0]
assert np.allclose(vertex_mesh.bounds, box.bounds)

for system in ('y_up', 'z_up'):
    bare = MeshWithVoxel(vertices.cpu(), faces.cpu(), [-.5] * 3, 1 / 8, None, None, None, layout, system)
    result = method(None, mesh=bare, **kwargs)[0]
    bounds = box.bounds if system == 'y_up' else np.array([expected.min(0), expected.max(0)])
    assert np.allclose(result.bounds, bounds)
    torch.testing.assert_close(bare.vertices, vertices.cpu())
legacy = SimpleNamespace(vertices=vertices.cpu(), faces=faces.cpu(), attrs=None, coords=None)
result = method(None, mesh=legacy, **kwargs)[0]
assert np.allclose(result.bounds, np.array([expected.min(0), expected.max(0)]))
torch.testing.assert_close(legacy.vertices, vertices.cpu())
print('PASS: PBR, vertex-color and geometry-only export axes; device transfer; chunked CUDA/BVH sampling.')
print('PASS: legacy mesh objects without coordinate metadata retain the Z-up export convention.')

# Sparse interpolation must distinguish absent voxels from valid zero RGB.
one_coords = torch.tensor([[0, 2, 2, 2]], dtype=torch.int32, device='cuda')
one_feat = torch.tensor([[0, 0, 0, .3, .7, 1, 1]], dtype=torch.float32, device='cuda')
queries = torch.tensor([[[2.5, 2.5, 2.5], [3., 2.5, 2.5], [6.5, 6.5, 6.5]]], device='cuda')
values = grid_sample_3d(one_feat, one_coords, torch.Size([1, 7, 8, 8, 8]), queries)
torch.testing.assert_close(values[0, :2, -1], torch.ones(2, device='cuda'))
assert values[0, 2, -1] == 0
assert not values[0, :2, :3].any()
print('PASS: sparse occupied black and partially supported samples remain valid; empty samples are missing.')

class Latent:
    def __init__(self, feats, coords):
        self.feats, self.coords = feats, coords

    def replace(self, feats, coords):
        return Latent(feats, coords)


decode = installed_method(ROOT / 'trellis2_gguf/pipelines/trellis2_image_to_3d.py',
    'Trellis2ImageTo3DPipeline', 'decode_latent',
    {'torch': torch, 'SparseTensor': Latent, 'List': list, 'MeshWithVoxel': MeshWithVoxel})
voxel = SimpleNamespace(coords=torch.cat([torch.zeros_like(coords[:, :1]), coords], -1),
                        feats=attrs, shape=torch.Size([1, 6]), spatial_shape=torch.Size([8, 8, 8]))
latent = Latent(attrs, voxel.coords)
for is_pixal in (True, False):
    pipeline = SimpleNamespace(isPixal3D=is_pixal, low_vram=False, pbr_attr_layout=layout,
        decode_shape_slat=lambda *_args, **_kwargs: ([SimpleNamespace(vertices=vertices, faces=faces)], None),
        decode_tex_slat=lambda *_args: [voxel])
    for texture in (None, latent):
        decoded = decode(pipeline, latent, texture, 8)[0]
        assert decoded.coordinate_system == ('y_up' if is_pixal else 'z_up')
print('PASS: actual latent decoder labels textured and geometry-only Pixal3D/TRELLIS outputs.')
