"""Submit reproducible image-to-new-mesh jobs using the application's workflow."""
import argparse
import importlib.util
import json
from pathlib import Path
import time
from typing import Any
from urllib.request import build_opener, ProxyHandler, Request

ROOT = Path(__file__).resolve().parents[1]
URL = 'http://127.0.0.1:8188'
opener = build_opener(ProxyHandler({}))


def request(path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    with opener.open(Request(URL + path, data, {'Content-Type': 'application/json'}), timeout=30) as response:
        return json.load(response)


parser = argparse.ArgumentParser()
parser.add_argument('action', choices=['submit', 'status'])
parser.add_argument('--images', nargs='+', default=['robot.png', 'Helmet.png'])
parser.add_argument('--manifest', type=Path, default=ROOT / 'tmp/pixal-generation-benchmark-20261009.json')
parser.add_argument('--label', default='20261009')
args = parser.parse_args()
if args.action == 'submit':
    adapter_path = ROOT / 'services/trellis/app.py'
    spec = importlib.util.spec_from_file_location('pixal_benchmark_adapter', adapter_path)
    adapter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(adapter)
    adapter.GenerateRequest.model_rebuild(_types_namespace={'Any': Any})
    schema = request('/object_info')
    jobs = []
    for name in args.images:
        payload = adapter.GenerateRequest(input_image='local-benchmark', texture_resolution='1024', mesh_density='medium')
        prompt = adapter._build_comfy_prompt(name, f'benchmark-{args.label}-{Path(name).stem}', payload)
        for node in prompt.values():
            definition = schema[node['class_type']]
            inputs = node['inputs']
            missing = set(definition['input'].get('required', {})) - set(inputs)
            if missing:
                raise RuntimeError(f"{node['class_type']} missing required inputs: {sorted(missing)}")
        prompt_file = ROOT / f'tmp/PixalPipeline_{Path(name).stem}_{args.label}_API.json'
        prompt_file.write_text(json.dumps(prompt, ensure_ascii=False, indent=2), encoding='utf-8')
        result = request('/prompt', {'prompt': prompt, 'client_id': 'pixal-pipeline-benchmark'})
        jobs.append({'image': name, 'prompt_id': result['prompt_id'], 'workflow': str(prompt_file), 'label': args.label, 'submitted': time.time()})
        # Keep each accepted job recoverable even if a later submission fails.
        args.manifest.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(jobs[-1], ensure_ascii=False))
else:
    for job in json.loads(args.manifest.read_text(encoding='utf-8')):
        history = request('/history/' + job['prompt_id']).get(job['prompt_id'])
        if history:
            history_file = ROOT / f"tmp/PixalPipeline_{Path(job['image']).stem}_{job.get('label', '20261009')}_history.json"
            history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps({'image': job['image'], 'status': history.get('status'), 'outputs': history.get('outputs')}, ensure_ascii=False))
        else:
            print(json.dumps({'image': job['image'], 'status': 'pending'}, ensure_ascii=False))
    print(json.dumps(request('/queue'), ensure_ascii=False))
