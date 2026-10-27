"""Compare original and candidate native remeshing geometry and CUDA peaks."""
import argparse
import ast
import gc
import json
from pathlib import Path
import time
import numpy as np
import torch
import trimesh
import cumesh.remeshing as module

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--real',action='store_true');parser.add_argument('--robot',action='store_true');args=parser.parse_args()
functions={}
for name in ('original','memory-candidate'):
 path=ROOT/f'tmp/pixal-cumesh-remesh-{name}-20261009.py'
 fn=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name=='remesh_narrow_band_dc_quad')
 ns=dict(vars(module));exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
 functions[name]=ns[fn.name]
assert Path(module.__file__).read_text(encoding='utf-8')==(ROOT/'tmp/pixal-cumesh-remesh-memory-candidate-20261009.py').read_text(encoding='utf-8')
functions['memory-candidate']=module.remesh_narrow_band_dc_quad
fixtures=[]
if args.robot:
 import pymeshlab
 mesh=trimesh.load(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\output\PixalRound3_Robot_RawCached_GPUFailure_20261009_00001_.glb',force='mesh',process=False)
 v=np.asarray(mesh.vertices,dtype=np.float32);f=np.asarray(mesh.faces,dtype=np.int32);del mesh
 path=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\nodes.py')
 cls=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.ClassDef) and n.name=='MeshUtils')
 ns=dict(globals());exec(compile(ast.Module(body=[cls],type_ignores=[]),str(path),'exec'),ns)
 v,f=ns['MeshUtils'].remove_floater2(v,f)
 assert len(v)==5472234 and len(f)==11114108,(len(v),len(f))
 fixtures=[('robot_cached',v,f,1024)]
elif args.real:
 folder=ROOT/'tmp/pixal-stages-20261009-round2-remesh'
 v=np.load(folder/'01_floaters-vertices.npy');f=np.load(folder/'01_floaters-faces.npy')
 fixtures=[('person_saved',v,f,1024)]
else:
 plane=trimesh.Trimesh(vertices=[[-.4,-.4,0],[.4,-.4,0],[.4,.4,0],[-.4,.4,0]],faces=[[0,1,2],[0,2,3]],process=False)
 for _ in range(2):plane=plane.subdivide()
 for name,mesh in [('sphere',trimesh.creation.icosphere(subdivisions=2)),('box',trimesh.creation.box()),('open_plane',plane)]:
  fixtures.append((name,np.asarray(mesh.vertices,dtype=np.float32),np.asarray(mesh.faces,dtype=np.int32),128))
rows=[]
with torch.no_grad():
 for label,v,f,resolution in fixtures:
  v=torch.from_numpy(v.astype(np.float32,copy=False)).cuda();f=torch.from_numpy(f.astype(np.int32,copy=False)).cuda()
  center=(v.min(0).values+v.max(0).values)*.5;scale=(v.max(0).values-v.min(0).values).max().item()*1.1
  if args.real or args.robot:center=torch.zeros(3,device='cuda');scale=1.1
  for remove_inner in ([True] if args.real or args.robot else [False,True]):
   outputs={};peaks={};times={}
   for version in ['original','memory-candidate']:
    gc.collect();torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();start=time.monotonic()
    ov,of=functions[version](v,f,center,scale,resolution,band=1,verbose=args.real,remove_inner_faces=remove_inner)
    torch.cuda.synchronize();times[version]=time.monotonic()-start;peaks[version]=torch.cuda.max_memory_allocated()
    outputs[version]=(ov.cpu().numpy(),of.cpu().numpy());del ov,of
   cv,cf=outputs['memory-candidate']
   if args.real:
    folder=ROOT/'tmp/pixal-stages-20261009-round2-remesh'
    ev=np.load(folder/'02a_remesh_raw-vertices.npy',mmap_mode='r');ef=np.load(folder/'02a_remesh_raw-faces.npy',mmap_mode='r')
   else:ev,ef=outputs['original']
   assert np.array_equal(cv,ev),(label,'vertices',cv.shape,ev.shape)
   assert np.array_equal(cf,ef),(label,'faces',cf.shape,ef.shape)
   row=dict(input=label,resolution=resolution,remove_inner=remove_inner,vertices=len(cv),faces=len(cf),
            vertices_and_indices_exact=True,peaks=peaks,seconds=times)
   rows.append(row);print(json.dumps(row),flush=True)
   del outputs,cv,cf,ev,ef
  del v,f
label='robot' if args.robot else 'real' if args.real else 'fixtures'
(ROOT/f'tmp/pixal-remesh-memory-{label}-20261009.json').write_text(json.dumps(rows,indent=2))
print('PASS exact vertices and face indices; native math and topology retained',flush=True)
