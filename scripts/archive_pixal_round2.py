"""Archive the exact narrow runtime edits and their backups for context handoff."""
import difflib
import hashlib
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PLUGIN = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF')
runtime = PLUGIN.parents[2] / 'python_embeded/Lib/site-packages/o_voxel/convert/flexible_dual_grid.py'
files = [(runtime, '.bak-before-tile-core-20261009'),
         (PLUGIN / 'patch/flexible_dual_grid.py', '.bak-before-tile-core-20261009'),
         (PLUGIN / 'trellis2_gguf/models/__init__.py', '.bak-before-gguf-meta-20261009'),
         (PLUGIN / 'trellis2_gguf/pipelines/trellis2_image_to_3d.py', '.bak-before-stage-owners-20261009')]
patch = []
records = []
for path, suffix in files:
    backup = path.with_name(path.name + suffix)
    before, after = backup.read_text(encoding='utf-8'), path.read_text(encoding='utf-8')
    patch.extend(difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                    fromfile=str(backup), tofile=str(path)))
    records.append(dict(path=str(path), backup=str(backup),
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                        backup_sha256=hashlib.sha256(backup.read_bytes()).hexdigest()))
(ROOT / 'docs/Pixal3D_第二轮链路优化_20261009.patch').write_text(''.join(patch), encoding='utf-8')
(ROOT / 'tmp/pixal-round2-source-sha-20261009.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(records, ensure_ascii=False, indent=2))
