"""Stop the owned, idle validation service and restore its temporary output node."""
import hashlib
import json
import argparse
from pathlib import Path
from urllib.request import build_opener, ProxyHandler

import psutil

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--local-factory', action='store_true')
parser.add_argument('--final-cleanup', action='store_true')
args = parser.parse_args()
assert not (args.local_factory and args.final_cleanup)
variant = 'final-chain' if args.final_cleanup else ('local-naf' if args.local_factory else 'naf-global')
tag = '-final-chain' if args.final_cleanup else ('-local-naf' if args.local_factory else '')
SERVICE = ROOT / f'tmp/comfy-general-round5-{variant}-20261019.pid'
manifest = json.loads((ROOT / f'tmp/pixal-full-round5-{variant}-person-20261019-manifest.json').read_text(encoding='utf-8'))[0]
history = json.loads(Path(manifest['history_path']).read_text(encoding='utf-8'))
assert history['status']['completed'] and history['status']['status_str'] == 'success'
with build_opener(ProxyHandler({})).open('http://127.0.0.1:8188/queue', timeout=10) as response:
    queue = json.load(response)
assert not queue['queue_running'] and not queue['queue_pending']
pid = int(SERVICE.read_text(encoding='utf-8-sig').strip())
assert pid == manifest['pid']
process = psutil.Process(pid)
assert Path(process.exe()).resolve() == Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\python_embeded\python.exe').resolve()
command = process.cmdline()
assert 'main.py' in command and '--port' in command and command[command.index('--port')+1] == '8188'
assert (ROOT / f'tmp/pixal-round5-{variant}-person-prediction-20261019.npz').is_file()
process.terminate()
process.wait(timeout=20)
custom = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes')
enabled, disabled = custom / 'Pixal3DValidationSnapshot', custom / 'Pixal3DValidationSnapshot.disabled'
assert enabled.resolve().parent == disabled.resolve().parent == custom.resolve()
assert not disabled.exists()
assert hashlib.sha256((enabled / '__init__.py').read_bytes()).hexdigest() == manifest['source_sha256'][str(enabled / '__init__.py')]
(enabled / '__init__.py').write_bytes((ROOT / f'tmp/pixal-round5{tag}-snapshot-node-before-20261019.py').read_bytes())
enabled.rename(disabled)
record = dict(pid=pid, process_stopped=True, queue_was_empty=True, diagnostic_restored_and_disabled=True)
target = ROOT / f'tmp/pixal-round5{tag}-service-stopped-20261019.json'
assert not target.exists()
target.write_text(json.dumps(record, indent=2), encoding='utf-8')
print(json.dumps(record))
