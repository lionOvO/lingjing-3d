"""Compare a Smart UV precision candidate in memory; do not mutate installed files."""
import importlib
import json
from pathlib import Path
import time
import numpy as np
import trimesh

ROOT=Path(__file__).resolve().parents[1]
module=importlib.import_module('smart_uv.smart_uv')
installed=Path(module.__file__)
backup=installed.with_name(installed.name+'.bak-before-uv-precision-20261009')
source=(backup if backup.exists() else installed).read_text(encoding='utf-8')
original_ns=dict(vars(module))
exec(compile(source,'<smart-uv-original-backup>','exec'),original_ns)
candidate=source
for name in ('v0','v1','v2'):
    before=f'{name} = vertices[faces[:, {int(name[1])}]]'
    assert candidate.count(before)==1
    candidate=candidate.replace(before,before+'.astype(np.float64)',1)
for before in ('magnitudes > 1e-8','areas[idx] > 1e-8','areas > 1e-8'):
    candidate=candidate.replace(before,before.replace('1e-8','0'))
before='quantized_uvs = (flat_uvs * 1e5).astype(np.int32)'
assert candidate.count(before)==1
candidate=candidate.replace(before,'quantized_uvs = flat_uvs.view(np.uint32)',1)
ns=dict(vars(module))
exec(compile(candidate,'<smart-uv-precision-candidate>','exec'),ns)
if backup.exists(): assert installed.read_text(encoding='utf-8')==candidate
(ROOT/'tmp/pixal-smart-uv-precision-candidate.py').write_text(candidate,encoding='utf-8')

def metrics(vertices,faces,uv):
    t=vertices[faces].astype(np.float64)
    geometric_area=np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)*.5
    u=uv[faces].astype(np.float64)
    a,b=u[:,1]-u[:,0],u[:,2]-u[:,0]
    area=abs(a[:,0]*b[:,1]-a[:,1]*b[:,0])*.5*1024**2
    return dict(faces=len(faces),positive_geometry_zero_uv=int(((geometric_area>0)&(area==0)).sum()),
                triangles_below_one_pixel=int((area<1).sum()),median_pixel_area=float(np.median(area)),
                finite_uv=bool(np.isfinite(uv).all()),uv_min=float(uv.min()),uv_max=float(uv.max()))

rows=[]
for category in ('tiny_fixture','person','robot','helmet'):
    if category=='tiny_fixture':
        vertices=np.array([[0,0,0],[1e-6,0,0],[0,1e-6,0]],dtype=np.float32)
        faces=np.array([[0,1,2]],dtype=np.int32)
    else:
        record=json.loads((ROOT/f'tmp/pixal-full-round2-core-meta-{category}-metrics.json').read_text(encoding='utf-8'))[0]
        mesh=trimesh.load(record['model'],force='mesh',process=False)
        vertices,faces=mesh.vertices.astype(np.float32),mesh.faces.astype(np.int32)
        tri=vertices[faces].astype(np.float64)
        faces=faces[np.any(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])!=0,axis=1)]
    candidate_function=module.smart_uv_unwrap if backup.exists() else ns['smart_uv_unwrap']
    for label,function in (('original',original_ns['smart_uv_unwrap']),('precision_candidate',candidate_function)):
        start=time.monotonic()
        v,f,uv,vmap=function(vertices,faces,margin=.01,angle_limit=np.pi/3,area_weight=0)
        assert np.array_equal(v[f],vertices[faces])
        row=dict(category=category,variant=label,seconds=time.monotonic()-start,**metrics(v,f,uv))
        rows.append(row)
        print(json.dumps(row),flush=True)
        (ROOT/'tmp/pixal-smart-uv-precision-comparison-20261009.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
        np.savez(ROOT/f'tmp/pixal-smart-uv-{category}-{label}-20261009.npz',vertices=v,faces=f,uv=uv,vmap=vmap)
