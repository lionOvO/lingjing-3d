"""Archive measured NAF repair and the completed person generation/review."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / 'tmp'
TARGET = TMP / 'pixal-round5-final-validation-20261019.json'
assert not TARGET.exists()
def read(name):
    return json.loads((TMP / name).read_text(encoding='utf-8-sig'))
def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

local_reports = ['pixal-naf-global-encoding-512-chunkrope-offload-20261019.json',
                 'pixal-naf-global-encoding-1024-chunkrope-offload-20261019.json',
                 'pixal-naf-global-encoding-1024-reserve1536-chunkrope-offload-20261019.json',
                 'pixal-naf-installed-regression-20261019.json']
for name in local_reports:
    assert read(name)['completed']
installed = read('pixal-naf-global-installed-20261019.json')
factory = read('pixal-local-condition-factory-installed-20261019.json')
final_install = read('pixal-round5-final-installed-20261019.json')
nodes_install = final_install['nodes']
assert digest(nodes_install['path']) == nodes_install['sha256']
assert digest(nodes_install['backup']) == nodes_install['before_sha256']
assert read('pixal-local-condition-factory-regression-20261019.json')['completed']
assert digest(factory['path']) == factory['sha256']
assert digest(factory['backup']) == factory['before_sha256']
assert digest(installed['path']) == installed['sha256']
assert digest(installed['backup']) == installed['before_sha256']
for row in read('pixal-hardware-source-check-20261019.json'):
    expected = {factory['path']: factory['sha256'], nodes_install['path']: nodes_install['sha256']}.get(row['path'], row['sha256'])
    assert digest(row['path']) == expected
job = read('pixal-full-round5-final-chain-person-20261019-manifest.json')[0]
history = json.loads(Path(job['history_path']).read_text(encoding='utf-8'))
assert history['status']['completed'] and history['status']['status_str'] == 'success'
cached = set()
for kind, payload in history['status']['messages']:
    if kind == 'execution_cached':
        cached.update(payload['nodes'])
assert not cached.intersection(('45', '77', '54', '19'))
naf_key = 'trellis2_gguf/trainers/flow_matching/mixins/image_conditioned_proj.py'
assert job['source_sha256'][naf_key] == installed['sha256']
before_graph = read('pixal-full-20261011-round3-sparse-resume-person-API.json')
after_graph = json.loads(Path(job['workflow']).read_text(encoding='utf-8'))
for key in ('6', '39', '55', '45', '54'):
    assert before_graph[key] == after_graph[key], key
metric = read('pixal-full-round5-final-chain-person-20261019-metrics.json')[0]
geometry = read('pixal-round5-integrated-person-geometry-20261019.json')
assert geometry['finite_vertices'] and geometry['zero_area_faces'] == 0 and geometry['same_winding_duplicate_faces'] == 0
baseline = read('pixal-full-round5-naf-global-person-20261019-metrics.json')[0]
baseline_job = read('pixal-full-round5-naf-global-person-20261019-manifest.json')[0]
assert baseline_job['source_sha256']['nodes.py'] == nodes_install['before_sha256']
assert job['source_sha256']['nodes.py'] == nodes_install['sha256']
assert job['source_sha256']['trellis2_gguf/pipelines/trellis2_image_to_3d.py'] == factory['sha256']
uv_key = next(k for k in job['source_sha256'] if k.endswith('smart_uv.py'))
assert baseline_job['source_sha256'][uv_key] == job['source_sha256'][uv_key]
old_meta = read('pixal-round3-sparse-resume-person-prediction-20261011.json')
baseline_meta = read('pixal-round5-naf-global-person-prediction-20261019.json')
new_meta = read('pixal-round5-final-chain-person-prediction-20261019.json')
assert old_meta == baseline_meta
assert new_meta != baseline_meta, 'Check active routing before claiming the repaired NAF was used'
assert new_meta == read('pixal-round5-local-naf-person-prediction-20261019.json'), 'Final NN changed despite unchanged generation code; inspect'
renders = read('pixal-round5-integrated-renders-20261019.json')
assert len(renders) == 12 and len({r['model'] for r in renders}) == 2
stopped = read('pixal-round5-final-chain-service-stopped-20261019.json')
assert stopped['process_stopped'] and stopped['diagnostic_restored_and_disabled']
review = read('pixal-round5-visual-assessment-20261019.json')
assert review['actually_viewed']
assert review['combined_candidate_accepted'] and review['integrated_actually_viewed']
log = (TMP / 'comfy-general-round5-final-chain-20261019.log').read_text(encoding='utf-8', errors='replace')
err = (TMP / 'comfy-general-round5-final-chain-20261019.err.log').read_text(encoding='utf-8', errors='replace')
assert 'using bilinear feature upsampling fallback' not in (log + err)
evidence = [TMP / name for name in local_reports] + [Path(r['path']) for r in renders]
evidence += [Path(metric['model']), Path(baseline['model']), ROOT / 'docs/Pixal3D_第五轮最终完整流程对照_20261019.png',
             TMP / 'pixal-round5-final-chain-person-prediction-20261019.npz', Path(job['history_path']), Path(job['workflow'])]
cleanup_trials = []
for case in ('person', 'robot', 'helmet'):
    trial = read(f'pixal-postprocess-round5-clean-after-remesh-{case}-20261019.json')
    audit = read(f'pixal-round5-final-{case}-geometry-20261019.json')
    assert trial['executed_ast_sha256'] == final_install['executed_postprocess_ast_sha256']
    assert audit['finite_vertices'] and audit['zero_area_faces'] == audit['same_winding_duplicate_faces'] == 0
    cleanup_trials.append(dict(trial=trial, geometry=audit))
    evidence += [Path(trial['model']), TMP / f'pixal-postprocess-round5-clean-after-remesh-{case}-20261019.json']
report = dict(date='2026-10-19', scope='Shared NAF, explicit local factory and deferred component cleanup. Three real feature inputs, three fresh full person runs (control, intermediate, final), and three saved-neural cleanup replays.',
              installed=final_install, generation=job, metrics=metric, geometry=geometry, comparison=baseline,
              cleanup_trials=cleanup_trials,
              baseline_neural_matches_historical=True, repaired_neural_differs_from_baseline=True,
              final_neural_matches_intermediate=True, cached_nodes=sorted(cached), visual_assessment=review, cleanup=stopped,
              evidence_sha256={str(p): digest(p) for p in evidence})
TARGET.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(TARGET)
