"""Install only the verified island-hole padding correction."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import socket

root=Path(__file__).resolve().parents[1]
path=Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\python_embeded\Lib\site-packages\smart_uv\smart_uv.py')
old_bytes=path.read_bytes();old_sha=hashlib.sha256(old_bytes).hexdigest()
assert old_sha=='7b3837099faf02bcd12df04a04695702f1d09e59afb7b3b5cbb7ac4e6cf0f207'
with socket.socket() as probe:
    probe.settimeout(1)
    assert probe.connect_ex(('127.0.0.1',8188))!=0,'Do not mutate a running inference service'
assert len(json.loads((root/'tmp/pixal-fixed-geometry-uv-comparison-20261012-padding.json').read_text()))==9
assert len(json.loads((root/'tmp/pixal-round4-surface-colors-20261012.json').read_text()))==21
assert len(json.loads((root/'tmp/pixal-round4-padding-clearance-fixtures-20261012.json').read_text()))==480
source=path.read_text(encoding='utf-8')
candidate=(root/'tmp/pixal-smart-uv-padding-candidate.py').read_text(encoding='utf-8')
expected=source.replace('if min_dim <= hole_dw and max_dim <= hole_dh:',
                       'if min_dim + 2*margin <= hole_dw and max_dim + 2*margin <= hole_dh:',1)
expected=expected.replace('hole_u0 + (max_dim if hole_rotate else min_dim),\n                 hole_v0 + (min_dim if hole_rotate else max_dim),',
                        'hole_u0 + (max_dim if hole_rotate else min_dim) + 2*margin,\n                 hole_v0 + (min_dim if hole_rotate else max_dim) + 2*margin,',1)
assert candidate==expected and candidate!=source
ast.parse(candidate)
backup=path.with_name(path.name+'.bak-before-island-padding-20261012')
assert not backup.exists(),'Preserve prior backup'
backup.write_bytes(old_bytes)
path.write_text(candidate,encoding='utf-8')
patch=''.join(difflib.unified_diff(source.splitlines(True),candidate.splitlines(True),
                                fromfile=str(backup),tofile=str(path)))
(root/'docs/Pixal3D_第四轮UV边距修复_20261012.patch').write_text(patch,encoding='utf-8')
records=[]
for record in json.loads((root/'tmp/pixal-round3-source-sha-20261009.json').read_text()):
    current=Path(record['path'])
    records.append(dict(path=str(current),sha256=hashlib.sha256(current.read_bytes()).hexdigest(),
                        changed_this_round=current==path))
records.append(dict(path=str(backup),sha256=old_sha,rollback=True))
(root/'tmp/pixal-round4-source-sha-20261012.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
print('Installed Smart UV padding correction:',hashlib.sha256(path.read_bytes()).hexdigest())
