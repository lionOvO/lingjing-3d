"""Install the fixed-grid-tested Smart UV precision candidate with exact backup."""
import ast
import hashlib
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
path=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\python_embeded\Lib\site-packages\smart_uv\smart_uv.py')
backup=path.with_name(path.name+'.bak-before-uv-precision-20261009')
if backup.exists(): raise RuntimeError('Backup exists; inspect installed source rather than reapplying')
source=path.read_text(encoding='utf-8')
for name in ('v0','v1','v2'):
    before=f'{name} = vertices[faces[:, {int(name[1])}]]'
    assert source.count(before)==1
    source=source.replace(before,before+'.astype(np.float64)',1)
for before in ('magnitudes > 1e-8','areas[idx] > 1e-8','areas > 1e-8'):
    source=source.replace(before,before.replace('1e-8','0'))
before='quantized_uvs = (flat_uvs * 1e5).astype(np.int32)'
assert source.count(before)==1
source=source.replace(before,'quantized_uvs = flat_uvs.view(np.uint32)',1)
assert source==(ROOT/'tmp/pixal-smart-uv-precision-candidate.py').read_text(encoding='utf-8')
ast.parse(source)
backup.write_bytes(path.read_bytes())
path.write_text(source,encoding='utf-8',newline='\n')
print('Installed Smart UV precision:',hashlib.sha256(path.read_bytes()).hexdigest())
