"""Read task/ComfyUI progress without submitting or interrupting inference."""
import asyncio
import json
from pathlib import Path
import time
import sys
from urllib.request import build_opener, ProxyHandler

import websockets

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'tmp/high-quality-integration'
HTTP = build_opener(ProxyHandler({}))
TASK_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 26


def get(url):
    with HTTP.open(url, timeout=6) as response:
        return json.load(response)


async def main():
    queue = get('http://127.0.0.1:8188/queue')
    entry = next(iter(queue['queue_running']), None)
    if entry is None:
        task = get(f'http://127.0.0.1:8080/api/v1/tasks/{TASK_ID}')
        snapshot = dict(task_id=TASK_ID, updated_at=time.time(), task={
            k:task.get(k) for k in ('status','output_model_url','error_message','completed_at')})
        (OUTPUT / 'progress.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
        print('No ComfyUI job is running; current task:', json.dumps(snapshot['task'], ensure_ascii=False), flush=True)
        return
    client_id = entry[3]['client_id']
    snapshot = dict(task_id=TASK_ID, prompt_id=entry[1], monitor_started=time.time())
    (OUTPUT / 'submitted-prompt.json').write_text(json.dumps(entry[2], ensure_ascii=False, indent=2), encoding='utf-8')
    deadline = time.monotonic() + 3600
    last_poll = 0
    async with websockets.connect(f'ws://127.0.0.1:8188/ws?clientId={client_id}', max_size=8*1024*1024, ping_timeout=None) as ws:
        while time.monotonic() < deadline:
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=5)
                if isinstance(message, str):
                    event = json.loads(message)
                    kind, data = event.get('type'), event.get('data') or {}
                    if kind == 'executing':
                        snapshot['node'] = data.get('node')
                        print('Executing node:', data.get('node'), flush=True)
                    elif kind == 'progress':
                        snapshot['progress'] = {k:data.get(k) for k in ('value','max','node')}
                    elif kind == 'execution_error':
                        snapshot['execution_error'] = {k:data.get(k) for k in ('node_id','exception_type','exception_message')}
                        print('Execution error:', json.dumps(snapshot['execution_error']), flush=True)
            except TimeoutError:
                pass
            if time.monotonic() - last_poll > 15:
                task = get(f'http://127.0.0.1:8080/api/v1/tasks/{TASK_ID}')
                snapshot['task'] = {k:task.get(k) for k in ('status','output_model_url','error_message','completed_at')}
                last_poll = time.monotonic()
            snapshot['updated_at'] = time.time()
            (OUTPUT / 'progress.json').write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding='utf-8')
            if snapshot.get('task', {}).get('status') in ('completed', 'failed'):
                print('Task final:', json.dumps(snapshot['task'], ensure_ascii=False), flush=True)
                return
    raise RuntimeError('Monitoring deadline reached; inference was not interrupted')


if __name__ == '__main__':
    asyncio.run(main())
