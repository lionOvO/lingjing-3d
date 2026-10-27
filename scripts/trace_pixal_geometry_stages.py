"""Capture the installed geometry stages from one saved neural prediction."""
from __future__ import annotations
import argparse
import ast
import copy
import gc
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import cumesh as CuMesh
from meshlib import mrmeshnumpy, mrmeshpy
import numpy as np
import pymeshlab
import torch
import trimesh as Trimesh
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF')
parser = argparse.ArgumentParser()
parser.add_argument('--branch', choices=['remesh', 'no_remesh'], required=True)
parser.add_argument('--label', required=True)
args = parser.parse_args()
folder = ROOT / 'tmp' / f'pixal-stages-{args.label}-{args.branch}'
folder.mkdir(parents=True, exist_ok=True)
records = []


def capture(stage, vertices, faces):
    torch.cuda.synchronize()
    v = vertices.detach().cpu().numpy() if torch.is_tensor(vertices) else np.asarray(vertices)
    f = faces.detach().cpu().numpy() if torch.is_tensor(faces) else np.asarray(faces)
    np.save(folder / f'{stage}-vertices.npy', v.astype(np.float32, copy=False))
    np.save(folder / f'{stage}-faces.npy', f.astype(np.int32, copy=False))
    row = {'stage': stage, 'vertices': len(v), 'faces': len(f)}
    records.append(row)
    (folder / 'manifest.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    print(json.dumps(row), flush=True)


package = ModuleType('pixal_geometry_trace')
package.__path__ = [str(PLUGIN)]
sys.modules[package.__name__] = package
source = ast.parse((PLUGIN / 'nodes.py').read_text(encoding='utf-8'))
helpers = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'MeshUtils')
cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == 'Trellis2_GGUFPostProcessAndUnWrapAndRasterizer')
method = copy.deepcopy(next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'process'))
method.decorator_list = []


def instrument(statements):
    result = []
    for statement in statements:
        if isinstance(statement, ast.If):
            statement.body = instrument(statement.body)
            statement.orelse = instrument(statement.orelse)
        result.append(statement)
        text = ast.unparse(statement)
        stage = None
        if isinstance(statement, ast.Assign) and text == 'mesh_copy = MeshUtils.remove_floater(mesh_copy)':
            result.extend(ast.parse("capture('01_floaters', mesh_copy.vertices, mesh_copy.faces)").body)
        if isinstance(statement, ast.Expr) and text.startswith('print('):
            if 'After remeshing:' in text:
                stage = '02b_remesh_floaters'
            elif 'After simplifying:' in text:
                stage = '03_simplify'
            elif 'After initial cleanup:' in text:
                stage = '03_cleanup'
        if isinstance(statement, ast.Expr) and any(isinstance(call, ast.Call) and
                ast.unparse(call.func) == 'CuMesh.remeshing.remesh_narrow_band_dc_quad' for call in ast.walk(statement)):
            stage = '02a_remesh_raw'
        if stage:
            result.extend(ast.parse(f"capture('{stage}', *cumesh.read())").body)
        if isinstance(statement, ast.If) and ast.unparse(statement.test) == 'fill_holes':
            result.extend(ast.parse("capture('04_holes', *cumesh.read())").body)
    return result


# Geometry ends before the vertex-color or UV/texture branch.
stop = next(i for i, n in enumerate(method.body) if isinstance(n, ast.If) and ast.unparse(n.test) == 'bake_on_vertices')
method.body = instrument(method.body[:stop]) + ast.parse('return ()').body
class ProgressBar:
    def __init__(self, *_): pass
    def update(self, *_): torch.cuda.synchronize()

ns = dict(globals(), __package__=package.__name__)
exec(compile(ast.fix_missing_locations(ast.Module(body=[helpers, method], type_ignores=[])), str(PLUGIN / 'nodes.py'), 'exec'), ns)
data = np.load(ROOT / 'tmp/pixal-final-neural-mesh-20261009.npz', allow_pickle=False)
capture('00_prediction', data['vertices'], data['faces'])
mesh = SimpleNamespace(vertices=torch.from_numpy(data['vertices']).cuda(), faces=torch.from_numpy(data['faces']).cuda(),
                       coords=torch.from_numpy(data['coords']).cuda(), attrs=torch.from_numpy(data['attrs']).cuda(),
                       layout={}, voxel_size=float(data['voxel_size']), coordinate_system=str(data['coordinate_system'].item()))
graph = json.loads((ROOT / 'tmp/PixalPipeline_OIP_clean_1024_rgba_20261009-cache-fixed_API.json').read_text(encoding='utf-8'))
kwargs = graph['54' if args.branch == 'remesh' else '60']['inputs'].copy()
kwargs.update(mesh=mesh, bvh=None)
ns['process'](None, **kwargs)
