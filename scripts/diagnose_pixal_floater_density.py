"""Check whether existing floater selection changes with main-surface tessellation."""
import json
from pathlib import Path
import numpy as np
import pymeshlab
import trimesh

ROOT=Path(__file__).resolve().parents[1]
rows=[]
for resolution in (16,64):
    xy=np.stack(np.meshgrid(np.linspace(-.4,.4,resolution+1),np.linspace(-.4,.4,resolution+1)),axis=-1).reshape(-1,2)
    vertices=np.column_stack((xy,np.zeros(len(xy))))
    index=np.arange((resolution+1)**2).reshape(resolution+1,resolution+1)
    a=index[:-1,:-1].reshape(-1);b=index[:-1,1:].reshape(-1)
    c=index[1:,1:].reshape(-1);d=index[1:,:-1].reshape(-1)
    faces=np.concatenate((np.stack((a,b,c),axis=1),np.stack((a,c,d),axis=1)))
    detail=trimesh.creation.box(extents=(.02,.02,.02))
    detail.apply_translation((.1,.1,.03))
    vertices=np.concatenate((vertices,detail.vertices))
    detail_start=len(faces)
    faces=np.concatenate((faces,detail.faces+len(xy)))
    meshset=pymeshlab.MeshSet()
    meshset.add_mesh(pymeshlab.Mesh(vertex_matrix=vertices,face_matrix=faces))
    meshset.apply_filter('compute_selection_by_small_disconnected_components_per_face',nbfaceratio=.005)
    mask=meshset.current_mesh().face_selection_array()
    row=dict(main_grid=resolution,main_faces=detail_start,detail_faces=12,selected_detail_faces=int(mask[detail_start:].sum()),
             main_surface_area=.64,detail_surface_area=.0024)
    rows.append(row)
    print(json.dumps(row),flush=True)
(ROOT/'tmp/pixal-floater-density-probe-20261009.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
