"""Export an importable GUI graph matching the measured full-generation parameters."""
import copy
import hashlib
import json
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMFY = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI')
folder = COMFY / 'user/default/workflows'
source = ROOT / 'tmp/pixal-full-round5-final-chain-person-20261019-API.json'
measured = json.loads(source.read_text(encoding='utf-8'))
installed = json.loads((ROOT / 'tmp/pixal-round5-final-installed-20261019.json').read_text(encoding='utf-8'))
for kind in ('naf', 'factory', 'nodes'):
    item = installed[kind]
    assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() == item['sha256']
api = copy.deepcopy(measured)
del api['77']
api['54']['inputs']['mesh'] = ['45', 0]
api['19']['inputs']['filename_prefix'] = 'Pixal3D_Round5_Native_1024'
workflow = json.loads((folder / 'Pixal3D_GGUF_REPAIRED_NATIVE_1024.json').read_text(encoding='utf-8'))
workflow['id'] = str(uuid.uuid4())
workflow['revision'] = 0
workflow['last_node_id'] = 55
workflow['last_link_id'] = max(link[0] for link in workflow['links'])
layout = {6: ([30, 350], [330, 360]), 39: ([30, 30], [330, 260]),
          55: ([400, 350], [300, 140]), 45: ([750, 30], [480, 900]),
          54: ([1300, 30], [450, 750]), 19: ([1810, 30], [300, 135]),
          10: ([1810, 230], [700, 650])}
for node in workflow['nodes']:
    node['pos'], node['size'] = layout[node['id']]
    if str(node['id']) not in api:
        assert node['type'] == 'Preview3D'
        filename = 'PixalFullPipeline_Person_round5-final-chain-person-20261019_00001_.glb'
        node['widgets_values'] = [filename, '']
        node['widgets_values_named'] = dict(model_file=filename, image='')
        props = node['properties']
        props['Last Time Model File'] = filename
        props['Scene Config']['showGrid'] = False
        props['Camera Config']['state'].update(position=dict(x=0, y=0, z=2.2), target=dict(x=0, y=0, z=0), zoom=1)
        continue
    expected = api[str(node['id'])]
    assert node['type'] == expected['class_type']
    named = node['widgets_values_named']
    assert list(named.values()) == node['widgets_values'], 'Template widget order drift'
    for key, value in expected['inputs'].items():
        if not isinstance(value, list):
            assert key in named, key
            named[key] = value
    node['widgets_values'] = list(named.values())
    node['mode'] = 0

# Reconstruct the business graph from actual GUI input links and ordered widgets.
links = {link[0]: link for link in workflow['links']}
reconstructed = {}
for node in workflow['nodes']:
    key = str(node['id'])
    if key not in api:
        continue
    inputs = {}
    for name in api[key]['inputs']:
        slot = next((slot for slot in node['inputs'] if slot['name'] == name), None)
        if slot and slot.get('link') is not None:
            link = links[slot['link']]
            assert link[3] == node['id'] and node['inputs'][link[4]]['name'] == name
            inputs[name] = [str(link[1]), link[2]]
        else:
            inputs[name] = node['widgets_values_named'][name]
    reconstructed[key] = dict(class_type=node['type'], inputs=inputs)
assert reconstructed == api
assert all(n['type'] != 'PixalValidationSnapshot' for n in workflow['nodes'])
workflow['extra']['ds'] = dict(scale=0.55, offset=[20, 40])
workflow['extra']['pixal_round5'] = dict(measured_prompt_id='52a03eef-c8d6-455a-94f1-a764ebe86c9d',
    diagnostic_node_removed=True, scope='Full neural image-to-new-mesh/PBR generation with installed local chain fixes.')
targets = [ROOT / 'docs/Pixal3D_第五轮_完整生成_1024_工作流.json', folder / 'Pixal3D_ROUND5_FULL_1024.json']
api_target = ROOT / 'docs/Pixal3D_第五轮_完整生成_1024_API.json'
for target in targets + [api_target]:
    assert not target.exists(), 'Preserve existing workflow files'
text = json.dumps(workflow, ensure_ascii=False, indent=2)
for target in targets:
    target.write_text(text, encoding='utf-8')
api_target.write_text(json.dumps(api, ensure_ascii=False, indent=2), encoding='utf-8')
report = dict(gui_paths=[str(path) for path in targets], api_path=str(api_target),
    checked_gui_to_api_matches_measured_parameters=True, removed_snapshot_node=True,
    differences_from_measured=['Remove pass-through diagnostic snapshot node; connect mesh directly.', 'Use a new export filename prefix.'],
    default_seed=api['45']['inputs']['seed'], files={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in targets + [api_target]})
record = ROOT / 'tmp/pixal-round5-workflow-delivery-20261019.json'
assert not record.exists()
record.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
