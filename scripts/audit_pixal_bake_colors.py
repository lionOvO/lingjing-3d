"""Trace neural samples through the installed bake and inpaint on a known replay GLB."""
import ast
import json
from pathlib import Path

import cv2
import cumesh as CuMesh
from flex_gemm.ops.grid_sample import grid_sample_3d
import numpy as np
import nvdiffrast.torch as dr
from PIL import Image
import torch
import trimesh

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF')
asset = PLUGIN.parents[1] / 'output/PixalCheckpoint_Person_remesh_20261009.glb'
mesh = trimesh.load(asset, force='mesh', process=False)
texture_size = mesh.visual.material.baseColorTexture.width
data = np.load(ROOT / 'tmp/pixal-final-neural-mesh-20261009.npz', allow_pickle=False)
vertices = torch.from_numpy(data['vertices']).cuda()
faces = torch.from_numpy(data['faces']).cuda()
bvh = CuMesh.cuBVH(vertices, faces)
bvh.vertices, bvh.faces = vertices, faces
out_vertices = torch.from_numpy(np.asarray(mesh.vertices, dtype=np.float32)).cuda()
out_faces = torch.from_numpy(np.asarray(mesh.faces, dtype=np.int32)).cuda()
uv = np.asarray(mesh.visual.uv, dtype=np.float32).copy()
uv[:, 1] = 1 - uv[:, 1]
out_uvs = torch.from_numpy(uv).cuda()
attr_volume = torch.from_numpy(data['attrs']).cuda()
coords = torch.from_numpy(data['coords']).cuda()
attr_layout = {key: slice(*value) if isinstance(value, list) else value for key, value in json.loads(str(data['layout'].item())).items()}
voxel_size = torch.full((3,), float(data['voxel_size']), device='cuda')
aabb = torch.tensor([[-.5]*3, [.5]*3], device='cuda')
grid_size = ((aabb[1]-aabb[0])/voxel_size).round().int()
texture_alpha_mode = 'OPAQUE'
class ProgressBar:
    def update(self, *_): pass
pbar = ProgressBar()
source = ast.parse((PLUGIN / 'nodes.py').read_text(encoding='utf-8'))
cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Trellis2_GGUFPostProcessAndUnWrapAndRasterizer')
method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'process')
start = next(i for i, n in enumerate(method.body) if isinstance(n, ast.Expr) and 'Sampling attributes...' in ast.unparse(n))
stop = next(i for i, n in enumerate(method.body) if isinstance(n, ast.Assign) and any(isinstance(target, ast.Name) and target.id == 'material' for target in n.targets))
body = method.body[start:stop]
instrumented = []
for statement in body:
    if isinstance(statement, ast.Assign) and ast.unparse(statement).startswith('base_color = cv2.inpaint'):
        instrumented.extend(ast.parse('before_inpaint = base_color.copy()').body)
    instrumented.append(statement)
ns = dict(globals())
exec(compile(ast.fix_missing_locations(ast.Module(body=instrumented, type_ignores=[])), str(PLUGIN / 'nodes.py'), 'exec'), ns)
mask = ns['mask']
valid = mask & (ns['missing_samples'] == 0)
before, after = ns['before_inpaint'], ns['base_color']
stored = np.asarray(mesh.visual.material.baseColorTexture.convert('RGB'))
changed = np.any(before != after, axis=-1)
error = np.max(np.abs(stored.astype(np.int16)-after.astype(np.int16)), axis=-1)
metrics = dict(asset=str(asset), faces=len(mesh.faces), texture_size=texture_size,
               rasterized_pixels=int(mask.sum()), missing_samples=int(ns['missing_samples'].sum()),
               valid_pixels_changed_by_inpaint=int((changed & valid).sum()),
               white_valid_neural_samples=int(((before >= 230).all(axis=-1) & valid).sum()),
               stored_pixels_equal_rebake=int((error == 0).sum()), stored_pixels_error_at_most_2=int((error <= 2).sum()),
               stored_valid_pixels_error_at_most_2=int(((error <= 2) & valid).sum()),
               max_stored_valid_pixel_error=int(error[valid].max()))
(ROOT / 'tmp/pixal-bake-color-trace-round2-metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
Image.fromarray(before).save(ROOT / 'tmp/pixal-neural-bake-before-inpaint-round2.png')
Image.fromarray(after).save(ROOT / 'tmp/pixal-neural-bake-after-inpaint-round2.png')
Image.fromarray(valid.astype(np.uint8)*255).save(ROOT / 'tmp/pixal-neural-bake-valid-round2.png')
print(json.dumps(metrics), flush=True)
assert metrics['valid_pixels_changed_by_inpaint'] == 0
