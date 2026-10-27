"""Audit geometric validity, face orientation duplicates and UV density in real GLBs."""
import argparse
import json
from pathlib import Path
import numpy as np
import trimesh

parser=argparse.ArgumentParser()
parser.add_argument('model',type=Path)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--require-clean',action='store_true')
args=parser.parse_args()
mesh=trimesh.load(args.model,force='mesh',process=False)
vertices=mesh.vertices.astype(np.float32)
faces=mesh.faces.astype(np.int32)
tri=vertices[faces].astype(np.float64)
area=np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)*.5
_, ids=np.unique(vertices,axis=0,return_inverse=True)
keys=ids[faces[area>0]]
rot=keys.argmin(axis=1)
keys=np.take_along_axis(keys,(rot[:,None]+np.arange(3))%3,axis=1)
same_winding=len(keys)-len(np.unique(keys,axis=0))
reverse=len(keys)-len(np.unique(np.sort(keys,axis=1),axis=0))-same_winding
uv=mesh.visual.uv[faces]
delta1,delta2=uv[:,1]-uv[:,0],uv[:,2]-uv[:,0]
texture_size=mesh.visual.material.baseColorTexture.size
uv_area=abs(delta1[:,0]*delta2[:,1]-delta1[:,1]*delta2[:,0])*.5*np.prod(texture_size)
row=dict(model=str(args.model),vertices=len(vertices),faces=len(faces),zero_area_faces=int((area==0).sum()),
         same_winding_duplicate_faces=int(same_winding),reverse_coincident_faces=int(reverse),
         finite_vertices=bool(np.isfinite(vertices).all()),tiny_positive_faces=int(((area>0)&(area<1e-12)).sum()),
         texture_size=list(texture_size),zero_uv_area_faces=int((uv_area==0).sum()),
         uv_triangle_pixel_area_quantiles=np.quantile(uv_area,[0,.1,.5,.9,1]).tolist(),
         triangles_below_one_pixel=int((uv_area<1).sum()),triangles_below_quarter_pixel=int((uv_area<.25).sum()))
if args.require_clean:
    assert row['zero_area_faces']==0 and row['same_winding_duplicate_faces']==0 and row['finite_vertices'],row
args.output.write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(row,ensure_ascii=False),flush=True)
