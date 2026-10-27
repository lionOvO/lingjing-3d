"""Release finished DINO weights before NAF's full-guide encoder peak."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import socket

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\pipelines\trellis2_image_to_3d.py')
EXPECTED = '136d5aae6462d78d987367526b4733afeb4ce5b70a25da6c9c289a871b62f359'
MARKER = '                        # DINO features are complete; its weights must not overlap NAF encoding.'


def main():
    source = SOURCE.read_text(encoding='utf-8')
    if MARKER in source:
        print('DINO/NAF offload patch already installed.')
        return
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest() == EXPECTED, 'Source changed; review before applying'
    with socket.socket() as connection:
        assert connection.connect_ex(('127.0.0.1', 8188)) != 0, 'Stop ComfyUI before changing inference source'
    anchor = '                        self_instance._load_naf()\n                        lr_features_bchw'
    replacement = '''                        self_instance._load_naf()
                        # DINO features are complete; its weights must not overlap NAF encoding.
                        # Load NAF first while DINO still identifies the correct CUDA device.
                        if self.low_vram:
                            self_instance.model.cpu()
                            self._cleanup_cuda()
                            print('[Pixal3D] DINO offloaded before NAF encoding', flush=True)
                        lr_features_bchw'''
    assert source.count(anchor) == 1
    changed = source.replace(anchor, replacement, 1)
    ast.parse(changed)
    backup = SOURCE.with_name(SOURCE.name + '.bak-before-naf-encoder-offload-20261021')
    assert not backup.exists(), 'Preserve previous backup'
    backup.write_bytes(SOURCE.read_bytes())
    SOURCE.write_text(changed, encoding='utf-8', newline='\n')
    patch = ''.join(difflib.unified_diff(source.splitlines(True), changed.splitlines(True),
                                       fromfile='before/trellis2_image_to_3d.py', tofile='after/trellis2_image_to_3d.py'))
    (ROOT / 'docs/Pixal3D_NAF编码显存修复_20261021.patch').write_text(patch, encoding='utf-8')
    record = dict(path=str(SOURCE), before_sha256=EXPECTED, sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                  backup=str(backup), state='installed_pending_generation')
    (ROOT / 'tmp/pixal-naf-encoder-offload-installed-20261021.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
