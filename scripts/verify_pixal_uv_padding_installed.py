"""Verify the real imported default unwrap matches the baked candidate exactly."""
import importlib
import json
from pathlib import Path
import numpy as np
import trimesh

root=Path(__file__).resolve().parents[1]
module=importlib.import_module('smart_uv.smart_uv')
assert Path(module.__file__)==Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\python_embeded\Lib\site-packages\smart_uv\smart_uv.py')
rows=[]
for case in ('person','robot','helmet'):
    candidate=np.load(root/f'tmp/pixal-round4-density-{case}-padded_m010-20261012.npz')
    model=json.loads((root/f'tmp/pixal-full-round3-sparse-resume-{case}-metrics.json').read_text())[0]['model']
    mesh=trimesh.load(model,force='mesh',process=False)
    vertices=np.asarray(mesh.vertices,dtype=np.float32);faces=np.asarray(mesh.faces,dtype=np.int32)
    # Omit margin to test the unchanged public default (.01).
    result=module.smart_uv_unwrap(vertices,faces,angle_limit=np.pi/3,area_weight=0)
    for key,value in zip(('vertices','faces','uv','vmap'),result):
        assert np.array_equal(value,candidate[key]),(case,key)
    assert np.array_equal(result[0][result[1]],vertices[faces])
    rows.append(dict(case=case,installed_default_exact_to_baked_candidate=True,ordered_geometry_exact=True))
out=root/'tmp/pixal-round4-installed-validation-20261012.json'
assert not out.exists()
out.write_text(json.dumps(rows,indent=2),encoding='utf-8')
print('PASS installed native unwrap default and four arrays exact for all three baked candidates')
