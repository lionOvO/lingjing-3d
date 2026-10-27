"""Validate installed face cleanup against thin/two-sided fixtures and real assets."""
import ast
import hashlib
import json
from pathlib import Path
import numpy as np
import trimesh

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF')
tree = ast.parse((PLUGIN / 'nodes.py').read_text(encoding='utf-8'))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'MeshUtils')
method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'clean_mesh_faces')
method.decorator_list = []
ns = dict(np=np)
exec(compile(ast.fix_missing_locations(ast.Module(body=[method],type_ignores=[])),str(PLUGIN/'nodes.py'),'exec'),ns)
clean = ns['clean_mesh_faces']

def keys(vertices, faces):
    _, ids = np.unique(vertices, axis=0, return_inverse=True)
    tri = vertices[faces].astype(np.float64)
    valid = np.any(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]) != 0,axis=1)
    k = ids[faces[valid]]
    rotation = k.argmin(axis=1)
    k = np.take_along_axis(k,(rotation[:,None]+np.arange(3))%3,axis=1)
    return np.unique(k,axis=0), int(np.count_nonzero(~valid)), len(k)-len(np.unique(k,axis=0))

v = np.array([[0,0,0],[1,0,0],[0,1,0],[0,0,0],[.5,0,0],[0,1e-9,0]],dtype=np.float32)
f = np.array([[0,1,2],[1,2,0],[3,1,2],[0,2,1],[0,4,1],[0,3,1],[0,1,5]],dtype=np.int32)
assert np.array_equal(clean(v,f),f[[0,3,6]])
assert clean(v,f).flags.c_contiguous and clean(v,f).dtype==f.dtype
assert clean(v,np.empty((0,3),dtype=np.int32)).shape==(0,3)
assert clean(v,f[[4,5]]).shape==(0,3)
# A valid open sheet stays open; cleanup introduces no cap and retains reverse faces.
open_faces=f[[0,3,6]]
assert np.array_equal(clean(v,open_faces),open_faces)

rows=[]
stage=ROOT/'tmp/pixal-stages-20261009-round2-remesh'
inputs=[('03_simplify',stage/'03_simplify-vertices.npy',stage/'03_simplify-faces.npy'),
        ('04_holes',stage/'04_holes-vertices.npy',stage/'04_holes-faces.npy')]
for label, vp, fp in inputs:
    vertices, faces=np.load(vp),np.load(fp)
    before, zero, duplicate=keys(vertices,faces)
    output=clean(vertices,faces)
    after, after_zero, after_duplicate=keys(vertices,output)
    assert after_zero==0 and after_duplicate==0 and np.array_equal(before,after)
    rows.append(dict(label=label,faces_before=len(faces),faces_after=len(output),zero_before=zero,
                     same_winding_duplicates_before=duplicate,zero_after=after_zero,
                     same_winding_duplicates_after=after_duplicate,valid_oriented_surface_preserved=True))

for category in ('person','robot','helmet'):
    record=json.loads((ROOT/f'tmp/pixal-full-round2-core-meta-{category}-metrics.json').read_text(encoding='utf-8'))[0]
    mesh=trimesh.load(record['model'],force='mesh',process=False)
    vertices, faces=mesh.vertices.astype(np.float32),mesh.faces.astype(np.int32)
    vertex_hash=hashlib.sha256(vertices.tobytes()).hexdigest()
    before, zero, duplicate=keys(vertices,faces)
    output=clean(vertices,faces)
    after, after_zero, after_duplicate=keys(vertices,output)
    assert after_zero==0 and after_duplicate==0 and np.array_equal(before,after)
    assert hashlib.sha256(vertices.tobytes()).hexdigest()==vertex_hash
    rows.append(dict(label=category,source=record['model'],faces_before=len(faces),faces_after=len(output),
                     zero_before=zero,same_winding_duplicates_before=duplicate,zero_after=after_zero,
                     same_winding_duplicates_after=after_duplicate,valid_oriented_surface_preserved=True))
(ROOT/'tmp/pixal-mesh-cleanup-regression-20261009.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
for row in rows: print(json.dumps(row,ensure_ascii=False),flush=True)
print('PASS: exact zero-area and same-winding duplicates removed; thin/open/reverse surfaces retained.')
