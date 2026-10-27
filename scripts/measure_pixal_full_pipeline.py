"""Run the saved business graph and record local process memory through completion."""
import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.error import URLError
from urllib.request import build_opener, ProxyHandler, Request

import psutil

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF')
opener = build_opener(ProxyHandler({}))


def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    with opener.open(Request('http://127.0.0.1:8188' + path, data,
                            {'Content-Type': 'application/json'}), timeout=30) as response:
        return json.load(response)


parser = argparse.ArgumentParser()
parser.add_argument('--pid', type=int, required=True)
parser.add_argument('--label', required=True)
parser.add_argument('--log', type=Path, required=True)
parser.add_argument('--image', default='OIP_clean_1024_rgba.png')
parser.add_argument('--workflow', type=Path, default=ROOT / 'tmp/PixalPipeline_OIP_clean_1024_rgba_20261009-cache-fixed_API.json')
parser.add_argument('--save-prediction',action='store_true')
args = parser.parse_args()
graph = json.loads(args.workflow.read_text(encoding='utf-8'))
# Exactly one business export branch, with the original deterministic neural inputs.
graph = {key: graph[key] for key in ('6', '39', '55', '45', '54', '19')}
graph['54']['inputs']['mesh'] = ['45', 0]
graph['6']['inputs']['image'] = args.image
if args.save_prediction:
    category={'OIP_clean_1024_rgba.png':'person','robot.png':'robot','Helmet.png':'helmet'}[args.image]
    graph['77']={'class_type':'PixalValidationSnapshot','inputs':{'mesh':['45',0],'case':category}}
    graph['54']['inputs']['mesh']=['77',0]
model_name = 'Person' if args.image == 'OIP_clean_1024_rgba.png' else Path(args.image).stem
graph['19']['inputs']['filename_prefix'] = f'PixalFullPipeline_{model_name}_{args.label}'
schema = request('/object_info')
for node in graph.values():
    missing = set(schema[node['class_type']]['input'].get('required', {})) - set(node['inputs'])
    if missing:
        raise RuntimeError(f"Missing required inputs for {node['class_type']}: {sorted(missing)}")
workflow = ROOT / f'tmp/pixal-full-{args.label}-API.json'
workflow.write_text(json.dumps(graph, ensure_ascii=False, indent=2), encoding='utf-8')
source_hashes = {name: hashlib.sha256((PLUGIN / name).read_bytes()).hexdigest() for name in (
    'nodes.py', 'trellis2_gguf/pipelines/trellis2_image_to_3d.py', 'trellis2_gguf/representations/mesh/base.py',
    'trellis2_gguf/models/__init__.py', '__init__.py',
    'trellis2_gguf/trainers/flow_matching/mixins/image_conditioned_proj.py')}
tile_source = PLUGIN.parents[2] / 'python_embeded/Lib/site-packages/o_voxel/convert/flexible_dual_grid.py'
source_hashes[str(tile_source)] = hashlib.sha256(tile_source.read_bytes()).hexdigest()
source_hashes['patch/flexible_dual_grid.py'] = hashlib.sha256((PLUGIN / 'patch/flexible_dual_grid.py').read_bytes()).hexdigest()
uv_source = PLUGIN.parents[2] / 'python_embeded/Lib/site-packages/smart_uv/smart_uv.py'
source_hashes[str(uv_source)] = hashlib.sha256(uv_source.read_bytes()).hexdigest()
remesh_source=PLUGIN.parents[2]/'python_embeded/Lib/site-packages/cumesh/remeshing.py'
source_hashes[str(remesh_source)] = hashlib.sha256(remesh_source.read_bytes()).hexdigest()
if args.save_prediction:
    snapshot_source=PLUGIN.parent/'Pixal3DValidationSnapshot/__init__.py'
    source_hashes[str(snapshot_source)]=hashlib.sha256(snapshot_source.read_bytes()).hexdigest()
error_log = args.log.with_name(args.log.stem + '.err.log')
position = args.log.stat().st_size
error_position = error_log.stat().st_size if error_log.is_file() else 0
result = request('/prompt', {'prompt': graph, 'client_id': 'pixal-full-memory-validation'})
job = {'image': args.image, 'prompt_id': result['prompt_id'], 'workflow': str(workflow),
       'label': args.label, 'submitted': time.time(), 'pid': args.pid, 'source_sha256': source_hashes}
job['history_path'] = str(ROOT / f'tmp/pixal-full-{args.label}-history.json')
manifest = ROOT / f'tmp/pixal-full-{args.label}-manifest.json'
manifest.write_text(json.dumps([job], ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(job, ensure_ascii=False), flush=True)
process = psutil.Process(args.pid)
markers = ('Loading ', 'Getting ', 'Sampling ', 'Decoding ', 'Performing ', 'Current vertices:',
           'After ', 'Removing ', 'Cleaning mesh', 'holes found', 'Unifying ', 'Baking ', 'Finalizing ', 'Saved ')
stage = 'submitted'
last_history_check = 0
peak = {'private': 0, 'rss': 0}
samples_path = ROOT / f'tmp/pixal-full-{args.label}-memory.jsonl'
with samples_path.open('w', encoding='utf-8') as samples:
    while process.is_running():
        with args.log.open('r', encoding='utf-8', errors='replace') as log:
            log.seek(position)
            lines = log.read().splitlines()
            position = log.tell()
        for line in lines:
            if any(marker in line for marker in markers):
                stage = line.strip()
        if error_log.is_file():
            with error_log.open('r', encoding='utf-8', errors='replace') as log:
                log.seek(error_position)
                lines = log.read().splitlines()
                error_position = log.tell()
            for line in lines:
                if 'Sampling ' in line or 'Fast Tiled Decoding' in line or 'Filling holes' in line:
                    stage = line.strip().split(':', 1)[0]
        try:
            memory = process.memory_info()
        except psutil.NoSuchProcess:
            break
        private = memory.private
        rss = memory.rss
        peak = {key: max(peak[key], value) for key, value in (('private', private), ('rss', rss))}
        samples.write(json.dumps({'time': time.time(), 'stage': stage, 'private': private, 'rss': rss,
                                  'system_available': psutil.virtual_memory().available}) + '\n')
        samples.flush()
        if time.monotonic() - last_history_check >= 10:
            last_history_check = time.monotonic()
            try:
                history = request('/history/' + job['prompt_id']).get(job['prompt_id'])
            except (URLError, TimeoutError, ConnectionError) as error:
                job['last_monitor_error'] = str(error)
                if not process.is_running():
                    break
                time.sleep(3)
                continue
            if history:
                Path(job['history_path']).write_text(
                    json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')
                job.update(peak_bytes=peak, status=history.get('status'), finished=time.time())
                manifest.write_text(json.dumps([job], ensure_ascii=False, indent=2), encoding='utf-8')
                print(json.dumps({'status': job['status'], 'peak_bytes': peak, 'outputs': history.get('outputs')},
                                 ensure_ascii=False), flush=True)
                break
        time.sleep(3)
if not job.get('finished'):
    job.update(peak_bytes=peak, status={'completed': False, 'status_str': 'process_exited'}, finished=time.time())
    manifest.write_text(json.dumps([job], ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'status': job['status'], 'peak_bytes': peak}, ensure_ascii=False), flush=True)
    raise SystemExit(1)
