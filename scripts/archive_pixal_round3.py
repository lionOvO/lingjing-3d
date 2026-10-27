"""Archive the installed third-round mesh cleanup, preserving prior runtime patches."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
files=[(Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\nodes.py'),'.bak-before-mesh-cleanup-20261009'),
       (Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\python_embeded\Lib\site-packages\smart_uv\smart_uv.py'),'.bak-before-uv-precision-20261009'),
       (Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\python_embeded\Lib\site-packages\cumesh\remeshing.py'),'.bak-before-memory-lifetime-20261009'),
       (Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\pipelines\trellis2_image_to_3d.py'),'.bak-before-sparse-projection-20261010')]
patch=[]
records=[]
for path,suffix in files:
    backup=path.with_name(path.name+suffix)
    before,after=backup.read_text(encoding='utf-8'),path.read_text(encoding='utf-8')
    ast.parse(after)
    patch.extend(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),fromfile=str(backup),tofile=str(path)))
    records.append(dict(path=str(path),backup=str(backup),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        backup_sha256=hashlib.sha256(backup.read_bytes()).hexdigest()))
(ROOT/'docs/Pixal3D_第三轮网格与UV修复_20261009.patch').write_text(''.join(patch),encoding='utf-8')
(ROOT/'tmp/pixal-round3-source-sha-20261009.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(records,ensure_ascii=False))
