"""Execute installed pre-fill/fill/post-fill code on the saved simplified prediction."""
import argparse
import ast
import gc
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import time
import cumesh as CuMesh
from meshlib import mrmeshnumpy, mrmeshpy
import numpy as np
import pymeshlab
import torch
from tqdm import tqdm

ROOT=Path(__file__).resolve().parents[1]
PLUGIN=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF')
parser=argparse.ArgumentParser()
parser.add_argument('--fill-holes',action='store_true')
args=parser.parse_args()
source=(PLUGIN/'nodes.py').read_text(encoding='utf-8')
tree=ast.parse(source)
mesh_utils=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='MeshUtils')
cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Trellis2_GGUFPostProcessAndUnWrapAndRasterizer')
method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='process')
fill_index=next(i for i,n in enumerate(method.body) if isinstance(n,ast.If) and ast.unparse(n.test)=='fill_holes')
stop=next(i for i,n in enumerate(method.body) if isinstance(n,ast.If) and ast.unparse(n.test)=='bake_on_vertices')
block=method.body[fill_index-3:stop]
assert ast.unparse(block[0])=='new_vertices, new_faces = cumesh.read()'
folder=ROOT/'tmp/pixal-stages-20261009-round2-remesh'
vertices=np.load(folder/'03_simplify-vertices.npy')
faces=np.load(folder/'03_simplify-faces.npy')
cm=CuMesh.CuMesh()
cm.init(torch.from_numpy(vertices).cuda(),torch.from_numpy(faces).cuda())
ns=dict(globals(),cumesh=cm,coords=torch.empty((0,3),device='cuda'),fill_holes=args.fill_holes)
start=time.monotonic()
exec(compile(ast.fix_missing_locations(ast.Module(body=[mesh_utils]+block,type_ignores=[])),str(PLUGIN/'nodes.py'),'exec'),ns)
v,f=cm.read()
v,f=v.cpu().numpy(),f.cpu().numpy()
tri=v[f].astype(np.float64)
assert np.any(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])!=0,axis=1).all()
assert np.isfinite(v).all() and f.min()>=0 and f.max()<len(v)
assert len(np.unique(f))==len(v)
label='filled' if args.fill_holes else 'open'
path=ROOT/f'tmp/pixal-hole-stage-round3-{label}.npz'
np.savez(path,vertices=v,faces=f)
result=dict(label=label,vertices=len(v),faces=len(f),zero_area=0,seconds=time.monotonic()-start,
            source_sha256=hashlib.sha256((PLUGIN/'nodes.py').read_bytes()).hexdigest())
(ROOT/f'tmp/pixal-hole-stage-round3-{label}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result),flush=True)
print('PASS installed hole stage, finite geometry, zero-area removal and compact vertex references')
