"""Reapply the installed business postprocessor to a preserved neural snapshot."""
import argparse
import ast
import copy
import gc
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace

compiler = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\python_embeded\Lib\site-packages\triton\backends\nvidia\bin\ptxas.exe')
assert compiler.is_file()
os.environ['TRITON_PTXAS.EXE_PATH'] = str(compiler)
os.environ['TRITON_PTXAS_PATH'] = str(compiler)

import cumesh as CuMesh
import cv2
from flex_gemm.ops.grid_sample import grid_sample_3d
from meshlib import mrmeshnumpy, mrmeshpy
import nvdiffrast.torch as dr
import numpy as np
from PIL import Image, ImageSequence, ImageOps
import pymeshlab
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
import torch
import trimesh as Trimesh
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF')
parser = argparse.ArgumentParser()
parser.add_argument('--snapshot', type=Path, required=True)
parser.add_argument('--label', required=True)
parser.add_argument('--keep-floaters', action='store_true')
parser.add_argument('--case', choices=['person', 'robot', 'helmet'], default='person')
parser.add_argument('--floater-ratio', type=float)
parser.add_argument('--floaters-after-remesh', action='store_true')
args = parser.parse_args()
output = PLUGIN.parents[1] / 'output' / f'PixalPostprocess_{args.label}.glb'
record_path = ROOT / f'tmp/pixal-postprocess-{args.label}.json'
assert not output.exists() and not record_path.exists()
torch.set_num_threads(4)

class ProgressBar:
    def __init__(self, *_): pass
    def update(self, *_): torch.cuda.synchronize()

package = ModuleType('pixal_postprocess_replay')
package.__path__ = [str(PLUGIN)]
sys.modules[package.__name__] = package
source = (PLUGIN / 'nodes.py').read_text(encoding='utf-8')
tree = ast.parse(source)
definitions = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ('MeshUtils', 'ImageUtils')]
if args.floater_ratio is not None:
    assert 0 < args.floater_ratio <= .005 and not args.keep_floaters
    helpers = next(n for n in definitions if n.name == 'MeshUtils')
    edges = next(n for n in helpers.body if isinstance(n, ast.FunctionDef) and n.name == 'remove_floater_by_edges')
    assert edges.args.defaults[-1].value == .005
    edges.args.defaults[-1] = ast.Constant(args.floater_ratio)
    lab = next(n for n in helpers.body if isinstance(n, ast.FunctionDef) and n.name == 'pymeshlab_remove_floater')
    ratios = [kw for n in ast.walk(lab) if isinstance(n, ast.Call) for kw in n.keywords if kw.arg == 'nbfaceratio']
    assert len(ratios) == 1 and ratios[0].value.value == .005
    ratios[0].value = ast.Constant(args.floater_ratio)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Trellis2_GGUFPostProcessAndUnWrapAndRasterizer')
method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'process')
if args.floaters_after_remesh:
    assert not args.keep_floaters and args.floater_ratio is None
    initial = [n for n in method.body if isinstance(n, ast.If) and ast.unparse(n.test) == 'remove_floaters'
               and any(isinstance(x, ast.Call) and ast.unparse(x.func) == 'MeshUtils.remove_floater' for x in ast.walk(n))]
    assert len(initial) == 1
    initial[0].test = ast.parse('remove_floaters and not remesh', mode='eval').body
ns = dict(globals(), __package__=package.__name__)
exec(compile(ast.fix_missing_locations(ast.Module(body=definitions + [method], type_ignores=[])), str(PLUGIN / 'nodes.py'), 'exec'), ns)
workflow = ROOT / f'tmp/pixal-full-20261011-round3-sparse-resume-{args.case}-API.json'
kwargs = json.loads(workflow.read_text(encoding='utf-8'))['54']['inputs'].copy()
if args.keep_floaters:
    kwargs['remove_floaters'] = False
started = time.monotonic()
with torch.inference_mode():
    data = np.load(args.snapshot, allow_pickle=False)
    layout = {key: slice(*value) if isinstance(value, list) else value for key, value in json.loads(str(data['layout'].item())).items()}
    mesh = SimpleNamespace(**{name: torch.from_numpy(data[name]).cuda() for name in ('vertices', 'faces', 'coords', 'attrs')},
                           voxel_size=float(data['voxel_size']), voxel_shape=tuple(data['voxel_shape']), layout=layout,
                           coordinate_system=str(data['coordinate_system'].item()))
    data.close()
    bvh = CuMesh.cuBVH(mesh.vertices.detach().clone(), mesh.faces.detach().clone())
    bvh.vertices = mesh.vertices.detach().clone()
    bvh.faces = mesh.faces.detach().clone()
    kwargs.update(mesh=mesh, bvh=bvh)
    result, _, _ = ns['process'](None, **kwargs)
    result.export(str(output))
record = dict(snapshot=str(args.snapshot), model=str(output), source_sha256=hashlib.sha256((PLUGIN / 'nodes.py').read_bytes()).hexdigest(),
              uv_sha256=hashlib.sha256((PLUGIN.parents[2] / 'python_embeded/Lib/site-packages/smart_uv/smart_uv.py').read_bytes()).hexdigest(),
              workflow=str(workflow), kind='saved_neural_postprocess_replay', seconds=time.monotonic()-started,
              remove_floaters=kwargs['remove_floaters'],
              trial_floater_ratio=args.floater_ratio, case=args.case,
              trial_floaters_after_remesh=args.floaters_after_remesh,
              executed_ast_sha256=hashlib.sha256(ast.dump(ast.Module(body=definitions+[method], type_ignores=[]), include_attributes=False).encode()).hexdigest(),
              vertices=len(result.vertices), faces=len(result.faces))
record_path.write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps(record, indent=2), flush=True)
