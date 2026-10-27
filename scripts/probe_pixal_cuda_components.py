"""Compare native CUDA component connectivity with the current MeshLab selection."""
import json
from pathlib import Path
import numpy as np
import torch
import pymeshlab
import cumesh

rows=[]
fixtures={
 'edge': [[0,1,2],[1,0,3]],
 'vertex_only': [[0,1,2],[0,3,4]],
 'nonmanifold_edge': [[0,1,2],[1,0,3],[0,1,4]],
 'reverse': [[0,1,2],[2,1,0]],
 'degenerate': [[0,1,2],[0,0,3]],
}
vertices=np.array([[0,0,0],[1,0,0],[0,1,0],[0,-1,0],[0,0,1]],dtype=np.float32)
for label,values in fixtures.items():
 dummy=[[5,6+i,7+i] for i in range(100)]
 faces=np.array(values+dummy,dtype=np.int32)
 padded_vertices=np.concatenate([vertices,[[5,0,0]],[[6,i+1,0] for i in range(101)]]).astype(np.float32)
 cm=cumesh.CuMesh();cm.init(torch.from_numpy(padded_vertices).cuda(),torch.from_numpy(faces).cuda())
 cm.get_connected_components();count,ids=cm.read_connected_components()
 ms=pymeshlab.MeshSet();ms.add_mesh(pymeshlab.Mesh(vertex_matrix=padded_vertices,face_matrix=faces))
 # Ratios greater than one half reveal whether faces belong to one component.
 ms.apply_filter('compute_selection_by_small_disconnected_components_per_face',nbfaceratio=.025)
 rows.append(dict(label=label,cuda_count=count,cuda_ids=ids[:len(values)].cpu().tolist(),meshlab_selection=ms.current_mesh().face_selection_array()[:len(values)].tolist()))
 print(rows[-1],flush=True)
 cm.clear_cache();del cm,ms

# Equal size components distinguish the ratio of total faces from largest component.
v=[];f=[]
for component,n in enumerate([200,200,1,2]):
 # A triangle fan joined by edges; component vertices are index-disjoint.
 start=len(v);v.append([component*5,0,0])
 for i in range(n+1):v.append([component*5+1,i+1,0])
 for i in range(n):f.append([start,start+i+1,start+i+2])
v=np.array(v,dtype=np.float32);f=np.array(f,dtype=np.int32)
cm=cumesh.CuMesh();cm.init(torch.from_numpy(v).cuda(),torch.from_numpy(f).cuda());cm.get_connected_components()
count,ids=cm.read_connected_components();sizes=torch.bincount(ids.long()).cpu().tolist()
for ratio in [.005,.01,.5]:
 ms=pymeshlab.MeshSet();ms.add_mesh(pymeshlab.Mesh(vertex_matrix=v,face_matrix=f))
 ms.apply_filter('compute_selection_by_small_disconnected_components_per_face',nbfaceratio=ratio)
 selected=ms.current_mesh().face_selection_array()
 row=dict(label='threshold',ratio=ratio,cuda_sizes=sizes,selected_by_component=[int(selected[a:b].sum()) for a,b in [(0,200),(200,400),(400,401),(401,403)]])
 rows.append(row);print(row,flush=True)
Path('tmp/pixal-cuda-components-probe-20261009.json').write_text(json.dumps(rows,indent=2))
