"""Bind Pixal3D conditioning to this GGUF package instead of scanning module globals."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import socket

ROOT = Path(__file__).resolve().parents[1]
PATH = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\pipelines\trellis2_image_to_3d.py')
BEFORE = '5b4c6778fad379fa82645ec9d5403ce8ad5f947e5c805a323f0c7c88c48e2cd0'
assert hashlib.sha256(PATH.read_bytes()).hexdigest() == BEFORE
with socket.socket() as connection:
    assert connection.connect_ex(('127.0.0.1', 8188)) != 0
source = PATH.read_text(encoding='utf-8')
cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'Trellis2ImageTo3DPipeline')
method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_get_build_pixal3d_image_cond_model')
old = ast.get_source_segment(source, method)
changed = source.replace(old, '''def _get_build_pixal3d_image_cond_model(self):
        return build_pixal3d_image_cond_model''', 1)
changed = changed.replace('def pil2tensor(image):', '''def build_pixal3d_image_cond_model(config: dict):
    from ..trainers.flow_matching.mixins.image_conditioned_proj import DinoV3ProjFeatureExtractor
    model = DinoV3ProjFeatureExtractor(**config)
    model.eval()
    return model


def pil2tensor(image):''', 1)
ast.parse(changed)
backup = PATH.with_name(PATH.name + '.bak-before-local-condition-factory-20261019')
assert not backup.exists()
backup.write_bytes(PATH.read_bytes())
PATH.write_text(changed, encoding='utf-8', newline='\n')
patch = ''.join(difflib.unified_diff(source.splitlines(True), changed.splitlines(True), fromfile='before/trellis2_image_to_3d.py', tofile='after/trellis2_image_to_3d.py'))
(ROOT / 'docs/Pixal3D_第五轮条件工厂修复_20261019.patch').write_text(patch, encoding='utf-8')
record = dict(path=str(PATH), before_sha256=BEFORE, sha256=hashlib.sha256(PATH.read_bytes()).hexdigest(), backup=str(backup))
(ROOT / 'tmp/pixal-local-condition-factory-installed-20261019.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps(record, indent=2))
