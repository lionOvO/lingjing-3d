"""Close the scoped third-round validation without promoting UV experiments."""
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
tmp = root / 'tmp'
plugin = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF')
def read(path):
    return json.loads(path.read_text(encoding='utf-8'))
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

full = read(tmp/'pixal-round3-final-validation-20261011.json')
sources = {}
for name, expected in full['source_sha256'].items():
    path = Path(name) if Path(name).is_absolute() else plugin/name
    if 'Pixal3DValidationSnapshot' in path.parts:
        path = Path(str(path).replace('Pixal3DValidationSnapshot\\', 'Pixal3DValidationSnapshot.disabled\\'))
    actual = sha(path)
    assert actual == expected, f'Installed source changed: {path}'
    sources[str(path)] = actual
for item in read(tmp/'pixal-round3-source-sha-20261009.json'):
    assert sha(Path(item['path'])) == item['sha256']
    assert sha(Path(item['backup'])) == item['backup_sha256']
assert not (plugin.parent/'Pixal3DValidationSnapshot').exists()
trials = read(tmp/'pixal-fixed-geometry-uv-comparison-20261011.json')
colors = read(tmp/'pixal-surface-color-comparison-20261011.json')
assert len(trials) == len(colors) == 12
assert len({(r['case'],r['variant']) for r in trials}) == 12
rows = []
screens = []
for trial, color in zip(trials, colors):
    assert (trial['case'],trial['variant']) == (color['case'],color['variant'])
    key = f"{trial['case']}-{trial['variant']}-20261011"
    quality = read(tmp/f'pixal-uv-export-quality-{key}.json')
    overlap = read(tmp/f'pixal-uv-overlap-{key}.json')
    model = Path(trial['model'])
    assert trial['ordered_geometry_exact'] and trial['missing_voxel_samples'] == 0
    assert trial['valid_pixels_changed_by_inpaint'] == 0
    assert color['valid_neural_samples'] == 25000 and color['missing_neural_samples'] == 0
    assert quality['zero_area_faces'] == quality['same_winding_duplicate_faces'] == 0
    assert quality['finite_vertices']
    assert sha(Path(trial['uv_source'])) == trial['uv_source_sha256']
    rows.append(dict(trial=trial, exported_quality=quality, color=color, overlap=overlap,
                     model_sha256=sha(model)))
models=[Path(r['model']) for r in trials]
for case in ('person','robot','helmet'):
    models.append(Path(read(tmp/f'pixal-full-round3-sparse-resume-{case}-metrics.json')[0]['model']))
for model in models:
    for mode in ('original','base'):
        for axis in ('plusz','plusy','angle'):
            path=tmp/f'{model.stem}_{mode}_{axis}.png'
            assert path.is_file()
            screens.append(dict(path=str(path),sha256=sha(path)))
assert len(screens)==90
smoke=read(tmp/'pixal-round3-viewer-smoke-20261012.json')
assert [r['reviewed_current_models'] for r in smoke]==[3,12]
assert all(not r['page_errors'] for r in smoke)
out=tmp/'pixal-round3-review-final-20261012.json'
assert not out.exists(), 'Preserve final review evidence'
out.write_text(json.dumps(dict(full_generation_proof='tmp/pixal-round3-final-validation-20261011.json',
    installed_source_sha256=sources, fixed_geometry_controls=rows, renders=screens, viewer_smoke=smoke,
    decision='Retain installed precision/memory/cleanup fixes and NAF K4, 1024 defaults. Orientation prototype and 2048 trials remain uninstalled experiments.',
    scope='Three Q4 seeds, fixed exported geometry including existing UV seams. Uniform face-centroid color/overlap measures; not reference-image quality, mipmaps or all-model guarantee.',
    visual_review='Front/oblique/overhead actual renders inspected. Facial colors are positioned on face; pale skin/eye color and hair/shoulder gaps persist. 2048 provides local detail but does not resolve neural color or geometric gaps.'),
    ensure_ascii=False,indent=2),encoding='utf-8')
print('PASS: same installed sources and backups; 3 full generations; 12 exported controls; 90 renders; 15 viewer samples')
