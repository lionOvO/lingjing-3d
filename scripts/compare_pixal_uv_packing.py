"""Test padded island bounds in the existing UV packer, without runtime mutation."""
import importlib
import json
from pathlib import Path
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
module=importlib.import_module('smart_uv.smart_uv')
source=Path(module.__file__).read_text(encoding='utf-8')
before='if min_dim <= hole_dw and max_dim <= hole_dh:'
assert source.count(before)==1
source=source.replace(before,'if min_dim + 2*margin <= hole_dw and max_dim + 2*margin <= hole_dh:',1)
before='''hole_u0 + (max_dim if hole_rotate else min_dim),
                 hole_v0 + (min_dim if hole_rotate else max_dim),'''
assert source.count(before)==1
source=source.replace(before,'''hole_u0 + (max_dim if hole_rotate else min_dim) + 2*margin,
                 hole_v0 + (min_dim if hole_rotate else max_dim) + 2*margin,''',1)
(ROOT/'tmp/pixal-smart-uv-padding-candidate.py').write_text(source,encoding='utf-8')
ns=dict(vars(module));exec(compile(source,'<padded-uv-packer-candidate>','exec'),ns)

def rectangle_overlap(rectangles):
    lower=np.array([r.min(axis=0) for r in rectangles]);upper=np.array([r.max(axis=0) for r in rectangles])
    overlaps=0
    for i in range(len(lower)):
        width=np.minimum(upper[i],upper[i+1:])-np.maximum(lower[i],lower[i+1:])
        overlaps+=int(np.all(width>1e-12,axis=1).sum())
    return overlaps,float(upper.max())

rng=np.random.default_rng(42)
islands=[]
for width,height in rng.uniform(.005,.2,size=(400,2)):
    islands.append(np.array([[0,0],[width,0],[width,height],[0,height]]))
fixture=[]
for label,function in (('original',module.pack_islands),('padding_candidate',ns['pack_islands'])):
    packed=function(islands,margin=.01)
    overlap,maximum=rectangle_overlap(packed)
    fixture.append(dict(label=label,overlapping_rectangle_pairs=overlap,max_uv=maximum))
print(json.dumps(fixture),flush=True)
assert fixture[0]['overlapping_rectangle_pairs']>0
assert fixture[1]['overlapping_rectangle_pairs']==0 and fixture[1]['max_uv']<=1

rows=[]
for category in ('person','robot','helmet'):
    data=np.load(ROOT/f'tmp/pixal-smart-uv-{category}-precision_candidate-20261009.npz')
    vertices,faces=data['vertices'],data['faces']
    started=time.monotonic()
    v,f,uv,vmap=ns['smart_uv_unwrap'](vertices,faces,margin=.01,angle_limit=np.pi/3,area_weight=0)
    assert np.array_equal(v[f],vertices[faces])
    t=uv[f].astype(np.float64);a,b=t[:,1]-t[:,0],t[:,2]-t[:,0]
    area=abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])*.5*1024**2
    row=dict(category=category,faces=len(f),vertices=len(v),seconds=time.monotonic()-started,
             zero_uv_faces=int((area==0).sum()),triangles_below_one_pixel=int((area<1).sum()),
             median_pixel_area=float(np.median(area)),finite_uv=bool(np.isfinite(uv).all()),
             uv_min=float(uv.min()),uv_max=float(uv.max()))
    rows.append(row);print(json.dumps(row),flush=True)
    np.savez(ROOT/f'tmp/pixal-smart-uv-{category}-padding-candidate-20261009.npz',vertices=v,faces=f,uv=uv,vmap=vmap)
    (ROOT/'tmp/pixal-smart-uv-padding-comparison-20261009.json').write_text(json.dumps(dict(fixture=fixture,models=rows),indent=2),encoding='utf-8')
