"""Validate compact edge filtering against the saved 12-million-face MeshLab output."""
import json
import ast
from pathlib import Path
import threading
import time
import numpy as np
import psutil
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

ROOT=Path(__file__).resolve().parents[1]
folder=ROOT/'tmp/pixal-stages-20261009-round2-remesh'
path=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\nodes.py')
cls=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.ClassDef) and n.name=='MeshUtils')
fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='remove_floater_by_edges')
fn.decorator_list=[]
ns={'np':np,'coo_matrix':coo_matrix,'connected_components':connected_components};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
v=np.load(folder/'02a_remesh_raw-vertices.npy',mmap_mode='r')
f=np.load(folder/'02a_remesh_raw-faces.npy',mmap_mode='r')
ev=np.load(folder/'02b_remesh_floaters-vertices.npy',mmap_mode='r')
ef=np.load(folder/'02b_remesh_floaters-faces.npy',mmap_mode='r')
samples=[];done=threading.Event();process=psutil.Process()
def sample():
 while not done.wait(.2):
  m=process.memory_info();samples.append(dict(private=m.private,rss=m.rss))
thread=threading.Thread(target=sample,daemon=True);thread.start()
start=time.monotonic();cv,cf=ns['remove_floater_by_edges'](v,f)
assert len(cf)==len(ef),(len(cf),len(ef))
for offset in range(0,len(cf),100000):
 assert np.array_equal(cv[cf[offset:offset+100000]],ev[ef[offset:offset+100000]].astype(np.float32)),offset
done.set();thread.join()
row=dict(input_vertices=len(v),input_faces=len(f),output_vertices=len(cv),output_faces=len(cf),
         old_vertices=len(ev),old_faces=len(ef),ordered_surface_exact=True,seconds=time.monotonic()-start,
         peak_private=max(x['private'] for x in samples),peak_rss=max(x['rss'] for x in samples))
(ROOT/'tmp/pixal-edge-floater-real-20261009.json').write_text(json.dumps(row,indent=2))
print(json.dumps(row),flush=True)
print('PASS full saved remesh: exact ordered oriented surfaces match MeshLab output',flush=True)
