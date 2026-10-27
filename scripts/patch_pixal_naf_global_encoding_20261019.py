"""Install the verified NAF global-encoding change with a local rollback copy."""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import socket

ROOT = Path(__file__).resolve().parents[1]
PATH = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\trainers\flow_matching\mixins\image_conditioned_proj.py')
EXPECTED = 'e20dc31cf0fe6e0f9cc7f2ab15d2954ef6147092ae638185477ccc672e3820c4'
INITIAL_INSTALL = '0e9f9669c1327467cb3aec8c235fc677d2d6fd0c2201791cba5f02b1a76ec434'
current_sha = hashlib.sha256(PATH.read_bytes()).hexdigest()
assert current_sha in (EXPECTED, INITIAL_INSTALL)
backup = PATH.with_name(PATH.name + '.bak-before-global-naf-20261019')
with socket.socket() as connection:
    assert connection.connect_ex(('127.0.0.1', 8188)) != 0, 'Stop inference before changing source'
for name in ('pixal-naf-global-encoding-512-chunkrope-offload-20261019.json', 'pixal-naf-global-encoding-1024-chunkrope-offload-20261019.json', 'pixal-naf-global-encoding-1024-reserve1536-chunkrope-offload-20261019.json'):
    report = json.loads((ROOT / 'tmp' / name).read_text(encoding='utf-8'))
    assert report['completed']
    assert len(report['rows']) == (1 if 'reserve1536' in name else 9)
    for row in report['rows']:
        assert row['finite']
        if row['variant'].startswith('global'):
            assert row.get('relative_rmse', 0) < 1e-5
            assert row.get('alternate_vs_k4_relative_rmse', 0) < 1e-5
source = (backup if current_sha == INITIAL_INSTALL else PATH).read_text(encoding='utf-8')
assert hashlib.sha256(source.encode()).hexdigest() == EXPECTED
changed = source.replace('        self.naf_model = None  # Lazy-loaded on first use to avoid import if not needed',
                         '        self.naf_model = None  # Lazy-loaded on first use to avoid import if not needed\n        self._naf_is_bilinear = False', 1)
changed = changed.replace('                self.naf_model = _BilinearNAFFallback().to(device)',
                          '                self.naf_model = _BilinearNAFFallback().to(device)\n                self._naf_is_bilinear = True', 1)
changed = changed.replace('            # NAF is an optional quality enhancement.',
                          '            self._naf_is_bilinear = False\n\n            # NAF is an optional quality enhancement.', 1)
tree = ast.parse(changed)
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'DinoV3ProjFeatureExtractor')
fn = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_proj_naf_tiled')
old_method = ast.get_source_segment(changed, fn)
new_method = (ROOT / 'tmp/pixal-naf-global-encoding-candidate-chunkrope-offload-20261019.py').read_text(encoding='utf-8')
new_method = new_method.replace('''        Tiles include the matching DINO feature crop. Supplying the full feature map
        for every image tile changes NAF attention dilation and mixes unrelated regions.
        This remains an approximation of full-image NAF because RoPE is tile-local.''', '''        Encode the whole guide once so GroupNorm statistics and RoPE coordinates
        match full-image NAF. Only the existing neighborhood attention is tiled,
        with DINO values and globally pooled keys cropped to the same patch cells.''')
new_method = new_method.replace('        for start in range(0, naf_h * naf_w, 16384):',
                               '        # Reuse native RoPE with global coordinates; bound only its temporary tensors.\n        for start in range(0, naf_h * naf_w, 16384):', 1)
begin = new_method.index('        guide = image_for_naf')
end = new_method.index('        for ti in range(K):', begin)
block = new_method[begin:end].rstrip() + '\n'
new_method = new_method[:begin] + '        if not self._naf_is_bilinear:\n' + ''.join('    ' + line if line.strip() else line for line in block.splitlines(True)) + '\n' + new_method[end:]
new_method = new_method.replace('''                tile_hr = self.naf_model.upsampler(
                    global_queries[:, :, out_lo_y:out_hi_y, out_lo_x:out_hi_x].to(device).contiguous(),
                    global_keys[:, :, cell_lo_y:cell_hi_y, cell_lo_x:cell_hi_x].contiguous(),
                    feature_tile,
                )''', '''                if self._naf_is_bilinear:
                    tile_hr = self.naf_model(image_tile, feature_tile, (tile_out_h, tile_out_w))
                else:
                    tile_hr = self.naf_model.upsampler(
                        global_queries[:, :, out_lo_y:out_hi_y, out_lo_x:out_hi_x].to(device).contiguous(),
                        global_keys[:, :, cell_lo_y:cell_hi_y, cell_lo_x:cell_hi_x].contiguous(),
                        feature_tile,
                    )''', 1)
assert 'global_queries[:, :' in new_method and new_method != old_method
assert 'if self._naf_is_bilinear:' in new_method
changed = changed.replace(old_method, new_method, 1)
ast.parse(changed)
if current_sha == EXPECTED:
    assert not backup.exists(), backup
    backup.write_bytes(PATH.read_bytes())
else:
    initial_patch = ROOT / 'tmp/pixal-naf-initial-install-before-fallback-20261019.patch'
    assert not initial_patch.exists()
    initial_patch.write_bytes((ROOT / 'docs/Pixal3D_第五轮NAF条件修复_20261019.patch').read_bytes())
PATH.write_text(changed, encoding='utf-8', newline='\n')
patch = ''.join(difflib.unified_diff(source.splitlines(True), changed.splitlines(True), fromfile='before/image_conditioned_proj.py', tofile='after/image_conditioned_proj.py'))
(ROOT / 'docs/Pixal3D_第五轮NAF条件修复_20261019.patch').write_text(patch, encoding='utf-8')
record = dict(path=str(PATH), before_sha256=EXPECTED, sha256=hashlib.sha256(PATH.read_bytes()).hexdigest(), backup=str(backup), state='installed_pending_full_generation')
if current_sha == INITIAL_INSTALL:
    record['initial_install_sha256'] = INITIAL_INSTALL
    record['initial_install_regression'] = 'Optional bilinear path failed; corrected before any full generation.'
(ROOT / 'tmp/pixal-naf-global-installed-20261019.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps(record, indent=2))
