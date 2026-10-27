"""Compare edge component selection with actual MeshLab on adversarial fixtures."""
import json
import ast
from pathlib import Path
import numpy as np
import pymeshlab
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

ROOT=Path(__file__).resolve().parents[1]
path=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\nodes.py')
cls=next(n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.ClassDef) and n.name=='MeshUtils')
fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='remove_floater_by_edges')
fn.decorator_list=[]
ns={'np':np,'coo_matrix':coo_matrix,'connected_components':connected_components};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(path),'exec'),ns)
candidate=ns['remove_floater_by_edges']

def original(v,f,ratio):
 ms=pymeshlab.MeshSet();ms.add_mesh(pymeshlab.Mesh(vertex_matrix=v,face_matrix=f))
 ms.apply_filter('compute_selection_by_small_disconnected_components_per_face',nbfaceratio=ratio)
 selected=ms.current_mesh().face_selection_array().copy()
 ms.apply_filter('compute_selection_transfer_face_to_vertex',inclusive=False)
 ms.apply_filter('meshing_remove_selected_vertices_and_faces')
 return ms.current_mesh().vertex_matrix(),ms.current_mesh().face_matrix(),selected

def surfaces(v,f):
 # Original winding / face order must stay identical, irrespective of compaction.
 return v[f].astype(np.float32)

rows=[]
rng=np.random.default_rng(17)
for test in range(102):
 v=rng.normal(size=(35,3)).astype(np.float32)
 f=rng.integers(0,25,(100,3),dtype=np.int32)
 # Explicit nonmanifold edge and vertex-only connections among disconnected fans.
 if test==0:f=np.array([[0,1,2],[1,0,3],[0,1,4],[0,5,6],[7,8,9],[8,7,10],[8,10,11]],dtype=np.int32)
 if test==1:f=np.array([[0,1,2],[0,1,1],[0,0,0],[7,8,9],[8,7,10]],dtype=np.int32)
 for ratio in [0,.005,.025,.1,.5,1.0]:
  ov,of,selected=original(v,f,ratio);cv,cf=candidate(v,f,ratio)
  assert np.array_equal(surfaces(ov,of),surfaces(cv,cf)),(test,ratio,selected.tolist(),len(of),len(cf))
  assert np.isfinite(cv).all()
 rows.append(dict(fixture=test,faces=len(f),ratios=6))
for largest in [199,200,201,399,400,401,599,600,601]:
 v=[];f=[]
 for part,size in enumerate([largest,1,2,3]):
  start=len(v);v.append([part*5,0,0])
  for i in range(size+1):v.append([part*5+1,i+1,0])
  for i in range(size):f.append([start,start+i+1,start+i+2])
 v=np.array(v,dtype=np.float32);f=np.array(f,dtype=np.int32)
 ov,of,_=original(v,f,.005);cv,cf=candidate(v,f,.005)
 assert np.array_equal(surfaces(ov,of),surfaces(cv,cf)),largest
 rows.append(dict(largest_component=largest,ratio=.005,input_faces=len(f),output_faces=len(cf)))
# Coincident positions with distinct indices remain topologically disconnected.
v=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,0],[1,0,0],[0,1,0]],dtype=np.float32)
f=np.array([[0,1,2],[3,4,5]],dtype=np.int32)
ov,of,_=original(v,f,1);cv,cf=candidate(v,f,1)
assert np.array_equal(surfaces(ov,of),surfaces(cv,cf))
print('PASS 622 comparisons including default integer-threshold boundaries and unwelded coincident positions',flush=True)
(ROOT/'tmp/pixal-edge-floater-fixtures-20261009.json').write_text(json.dumps(rows,indent=2))
