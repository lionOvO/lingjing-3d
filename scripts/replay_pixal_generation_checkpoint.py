"""Replay actual installed postprocessing from the benchmark's saved neural output."""
from __future__ import annotations
import argparse
import ast
import copy
import gc
import json
from pathlib import Path
import sys
from types import ModuleType
from typing import Dict

import cv2
import cumesh as CuMesh
from flex_gemm.ops.grid_sample import grid_sample_3d
from meshlib import mrmeshnumpy, mrmeshpy
import numpy as np
import nvdiffrast.torch as dr
from PIL import Image
import pymeshlab
import torch
import trimesh as Trimesh
from tqdm import tqdm

ROOT = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF')
WORKSPACE = Path(r'D:\灵境造物')
parser=argparse.ArgumentParser()
parser.add_argument('--branch',choices=['remesh','no_remesh'],required=True)
parser.add_argument('--label',default='20261009')
args=parser.parse_args()
package=ModuleType('pixal_checkpoint_replay');package.__path__=[str(ROOT)]
sys.modules[package.__name__]=package
class ProgressBar:
    def __init__(self,*_): pass
    def update(self,*_): torch.cuda.synchronize()
ns=dict(globals(),__package__=package.__name__,Mesh=type('Mesh',(),{'device':property(lambda self:self.vertices.device)}),Voxel=type('Voxel',(),{}))
base=ast.parse((ROOT/'trellis2_gguf/representations/mesh/base.py').read_text(encoding='utf-8'))
mesh_class=next(n for n in base.body if isinstance(n,ast.ClassDef) and n.name=='MeshWithVoxel')
exec(compile(ast.fix_missing_locations(ast.Module(body=[mesh_class],type_ignores=[])),str(ROOT/'trellis2_gguf/representations/mesh/base.py'),'exec'),ns)
source=ast.parse((ROOT/'nodes.py').read_text(encoding='utf-8'))
helpers=[next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name==name) for name in ('MeshUtils','ImageUtils')]
cls=next(n for n in source.body if isinstance(n,ast.ClassDef) and n.name=='Trellis2_GGUFPostProcessAndUnWrapAndRasterizer')
method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='process');method.decorator_list=[]
exec(compile(ast.fix_missing_locations(ast.Module(body=helpers+[method],type_ignores=[])),str(ROOT/'nodes.py'),'exec'),ns)
data=np.load(WORKSPACE/'tmp/pixal-final-neural-mesh-20261009.npz',allow_pickle=False)
layout={key:slice(*value) if isinstance(value,list) else value for key,value in json.loads(str(data['layout'].item())).items()}
arrays={key:torch.from_numpy(data[key]).cuda() for key in ('vertices','faces','coords','attrs')}
# Full generation's decoded volume origin is fixed at (-.5,-.5,-.5).
mesh=ns['MeshWithVoxel'](arrays['vertices'],arrays['faces'],[-.5]*3,float(data['voxel_size']),
    arrays['coords'],arrays['attrs'],torch.Size(data['voxel_shape'].tolist()),layout,str(data['coordinate_system'].item()))
bvh=CuMesh.cuBVH(mesh.vertices,mesh.faces)
bvh.vertices,bvh.faces=mesh.vertices,mesh.faces
graph=json.loads((WORKSPACE/'tmp/PixalPipeline_OIP_clean_1024_rgba_20261009-cache-fixed_API.json').read_text(encoding='utf-8'))
kwargs=graph['54' if args.branch=='remesh' else '60']['inputs'].copy()
kwargs.update(mesh=mesh,bvh=bvh)
result=ns['process'](None,**kwargs)[0]
path=ROOT.parents[1]/'output'/f'PixalCheckpoint_Person_{args.branch}_{args.label}.glb'
result.export(path)
assert np.isfinite(result.vertices).all() and result.faces.max()<len(result.vertices)
assert np.isfinite(result.visual.uv).all()
print(json.dumps({'source':'saved neural checkpoint / installed postprocessor','branch':args.branch,'path':str(path),'faces':len(result.faces),'vertices':len(result.vertices),'bytes':path.stat().st_size},ensure_ascii=False),flush=True)
