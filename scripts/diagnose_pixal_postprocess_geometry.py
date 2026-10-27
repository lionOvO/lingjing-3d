"""Run the installed geometry stages on a saved raw prediction, without rerunning AI."""
from __future__ import annotations
import argparse
import ast
import copy
import gc
import os
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import torch
import trimesh as Trimesh
import cumesh as CuMesh
import pymeshlab
from meshlib import mrmeshnumpy, mrmeshpy
from tqdm import tqdm

ROOT = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF')
parser = argparse.ArgumentParser()
parser.add_argument('--fill-holes', action='store_true')
args = parser.parse_args()
package = ModuleType('pixal_geometry_probe')
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
tree = ast.parse((ROOT / 'nodes.py').read_text(encoding='utf-8'))
mesh_utils = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MeshUtils')
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Trellis2_GGUFPostProcessAndUnWrapAndRasterizer')
method = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'process'))
method.decorator_list = []
stop = next(i for i, n in enumerate(method.body) if ast.unparse(n) == 'print("Sampling attributes...")' or ast.unparse(n) == "print('Sampling attributes...')")
method.body = method.body[:stop]
# Save the cleaned arrays before UV/normals, and synchronize every top-level stage.
instrumented = []
for statement in method.body:
    if isinstance(statement, ast.If) and ast.unparse(statement.test) == "uv_unwrap_method == 'Blender'":
        pass
    if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call) and ast.unparse(statement.value.func) == 'cumesh.compute_vertex_normals':
        instrumented.append(ast.parse("torch.cuda.synchronize(); print('UV complete, computing normals', flush=True)").body[0])
    instrumented.append(statement)
    if isinstance(statement, ast.If) and ast.unparse(statement.test) == 'fill_holes':
        instrumented.extend(ast.parse("v, f = cumesh.read(); torch.cuda.synchronize(); vnp=v.cpu().numpy(); fnp=f.cpu().numpy(); print('cleaned',vnp.shape,fnp.shape,'finite',np.isfinite(vnp).all(),'indices',fnp.min(),fnp.max(),'degenerate',np.count_nonzero((fnp[:,0]==fnp[:,1])|(fnp[:,1]==fnp[:,2])|(fnp[:,0]==fnp[:,2])),flush=True); np.savez('D:/灵境造物/tmp/pixal-cleaned-geometry-20261009.npz',vertices=vnp,faces=fnp)").body)
method.body = instrumented + ast.parse("torch.cuda.synchronize(); print('PASS normals and UV',flush=True); return out_vertices, out_faces, out_uvs").body
class ProgressBar:
    def __init__(self, *_): pass
    def update(self, *_): torch.cuda.synchronize()
ns = dict(__package__=package.__name__, torch=torch, np=np, CuMesh=CuMesh, Trimesh=Trimesh,
          pymeshlab=pymeshlab,
          mrmeshnumpy=mrmeshnumpy, mrmeshpy=mrmeshpy, tqdm=tqdm, gc=gc, copy=copy,
          ProgressBar=ProgressBar)
exec(compile(ast.fix_missing_locations(ast.Module(body=[mesh_utils, method], type_ignores=[])), str(ROOT / 'nodes.py'), 'exec'), ns)
raw = Trimesh.load(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\output\PixalPipeline_OIP_clean_1024_rgba_Raw_20261009-physical-grid_00001_.glb', process=False, force='mesh')
mesh = SimpleNamespace(vertices=torch.tensor(raw.vertices,dtype=torch.float32,device='cuda'),
    faces=torch.tensor(raw.faces,dtype=torch.int32,device='cuda'), attrs=torch.zeros(1,6,device='cuda'),
    coords=torch.zeros(1,3,dtype=torch.int32,device='cuda'), layout={},voxel_size=1/1024,coordinate_system='y_up')
del raw
ns['process'](None,mesh=mesh,mesh_cluster_threshold_cone_half_angle_rad=60,
    mesh_cluster_refine_iterations=0,mesh_cluster_global_iterations=1,mesh_cluster_smooth_strength=1,
    texture_size=1024,remesh=False,remesh_band=1,remesh_project=0,target_face_num=500001,
    simplify_method='Cumesh',fill_holes=args.fill_holes,texture_alpha_mode='OPAQUE',
    dual_contouring_resolution='1024',double_side_material=False,remove_floaters=True,
    bake_on_vertices=False,use_custom_normals=False,uv_unwrap_method='Smart',bvh=None,remove_inner_faces=True)
