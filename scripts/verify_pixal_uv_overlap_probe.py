"""Validate the spatially distinct UV overlap measurement on known triangles."""
import numpy as np
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('pixal_uv_overlap',Path(__file__).with_name('audit_pixal_uv_overlap.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
measure_overlap=module.measure_overlap

v=np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,1],[1,0,1],[0,1,1]],dtype=np.float32)
f=np.array([[0,1,2],[3,4,5]])
uv=np.array([[0,0],[1,0],[0,1],[0,0],[1,0],[0,1]],dtype=np.float32)
assert measure_overlap(v,f,uv)['ambiguous_centroid_fraction']==1
v[3:]=v[:3]
assert measure_overlap(v,f,uv)['ambiguous_centroid_fraction']==0
v[3:,2]=1;uv[3:]+=2
assert measure_overlap(v,f,uv)['ambiguous_centroid_fraction']==0
assert measure_overlap(v,f,np.zeros_like(uv))['sampled_face_centroids']==0
print('PASS known distinct, coincident, disjoint and degenerate UV fixtures')
