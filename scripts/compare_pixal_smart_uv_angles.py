"""Test projection-angle constraints without changing the active runtime dependency."""
import importlib
import argparse
import json
from pathlib import Path
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--minimum-dot',type=float,default=None)
args=parser.parse_args()
label='angle' if args.minimum_dot is None else 'orientation'
module=importlib.import_module('smart_uv.smart_uv')
source=Path(module.__file__).read_text(encoding='utf-8')
before='best_proj_idx = np.argmax(smoothed_dots, axis=1)'
after='''best_proj_idx = np.argmax(np.where(dot_matrix_full >= angle_limit_cos, smoothed_dots, -np.inf), axis=1)
    uncovered = valid_face_mask & (dot_matrix_full.max(axis=1) < angle_limit_cos)
    best_proj_idx[uncovered] = np.argmax(dot_matrix_full[uncovered], axis=1)'''
assert source.count(before)==1
source=source.replace(before,after,1)
before='''        can_update = face_is_tiny & (best_axis_map[labels_curr] != -1)
        proj_idx_per_face[can_update] = best_axis_map[labels_curr[can_update]]'''
after='''        proposed = best_axis_map[labels_curr]
        proposed_dot = dot_matrix_full[np.arange(num_faces), np.maximum(proposed, 0)]
        can_update = face_is_tiny & (proposed != -1) & (proposed_dot >= angle_limit_cos)
        proj_idx_per_face[can_update] = proposed[can_update]'''
assert source.count(before)==1
source=source.replace(before,after,1)
if args.minimum_dot is not None:
    source=source.replace('dot_matrix_full >= angle_limit_cos','dot_matrix_full >= '+str(args.minimum_dot))
    source=source.replace('dot_matrix_full.max(axis=1) < angle_limit_cos','dot_matrix_full.max(axis=1) < '+str(args.minimum_dot))
    source=source.replace('proposed_dot >= angle_limit_cos','proposed_dot >= '+str(args.minimum_dot))
(ROOT/f'tmp/pixal-smart-uv-{label}-candidate.py').write_text(source,encoding='utf-8')
ns=dict(vars(module))
exec(compile(source,'<angle-constrained-smart-uv-candidate>','exec'),ns)
rows=[]
for category in ('person','robot','helmet'):
    # The previous precision run preserves each triangle's 3D positions exactly.
    data=np.load(ROOT/f'tmp/pixal-smart-uv-{category}-precision_candidate-20261009.npz')
    vertices,faces=data['vertices'],data['faces']
    start=time.monotonic()
    v,f,uv,vmap=ns['smart_uv_unwrap'](vertices,faces,margin=.01,angle_limit=np.pi/3,area_weight=0)
    assert np.array_equal(v[f],vertices[faces])
    t=uv[f].astype(np.float64)
    a,b=t[:,1]-t[:,0],t[:,2]-t[:,0]
    area=abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])*.5*1024**2
    row=dict(category=category,faces=len(f),vertices=len(v),seconds=time.monotonic()-start,
             zero_uv_faces=int((area==0).sum()),triangles_below_one_pixel=int((area<1).sum()),
             median_pixel_area=float(np.median(area)),finite_uv=bool(np.isfinite(uv).all()),
             uv_min=float(uv.min()),uv_max=float(uv.max()),summed_pixel_area=float(area.sum()))
    rows.append(row)
    print(json.dumps(row),flush=True)
    np.savez(ROOT/f'tmp/pixal-smart-uv-{category}-{label}-candidate-20261009.npz',vertices=v,faces=f,uv=uv,vmap=vmap)
    (ROOT/f'tmp/pixal-smart-uv-{label}-comparison-20261009.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
