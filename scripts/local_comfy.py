"""Launch the registered local Pixal3D service with its verified memory profile."""
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


def validate_output_directory(stats, config):
    """Do not silently reuse an engine writing outside Docker's output mount."""
    expected = config.get('output_directory')
    if not expected:
        return
    argv = (stats.get('system') or {}).get('argv')
    if not isinstance(argv, list):
        raise RuntimeError('无法核验 ComfyUI 输出目录，请检查 /system_stats。')
    actual = str(Path(config['root']) / 'output')
    for index, value in enumerate(argv):
        if value == '--output-directory' and index + 1 < len(argv):
            actual = argv[index + 1]
            break
        if isinstance(value, str) and value.startswith('--output-directory='):
            actual = value.split('=', 1)[1]
            break
    actual_path = Path(actual)
    if not actual_path.is_absolute():
        actual_path = Path(config['root']) / actual_path
    if actual_path.resolve() != Path(expected).resolve():
        raise RuntimeError(f'ComfyUI 输出目录与本项目不一致；请关闭当前 ComfyUI 后重新运行一键启动。需要的输出目录：{expected}；不会移动或删除历史模型。')


def ensure_comfy(config, runtime, timeout=180):
    if not config:
        return
    url = config['url'].rstrip('/')
    http = build_opener(ProxyHandler({}))

    def ready():
        try:
            with http.open(url + '/system_stats', timeout=3) as response:
                stats = json.load(response)
                if response.status != 200 or 'devices' not in stats:
                    return False
                validate_output_directory(stats, config)
                return True
        except (OSError, ValueError, URLError):
            return False

    if ready():
        print('ComfyUI 已就绪。', flush=True)
        return
    root = Path(config['root'])
    python = Path(config['python'])
    compiler = python.parent / 'Lib/site-packages/triton/backends/nvidia/bin/ptxas.exe'
    if not all(path.is_file() for path in (root / 'main.py', python, compiler)):
        raise RuntimeError('本机 ComfyUI/Python/Triton 编译器路径无效，请检查 local-stack.json。')
    from urllib.parse import urlparse
    port = urlparse(url).port or 8188
    import socket
    with socket.socket() as probe:
        probe.settimeout(1)
        if probe.connect_ex(('127.0.0.1', port)) == 0:
            raise RuntimeError(f'{port} 端口已被占用且不是就绪的 ComfyUI，请检查该服务。')
    runtime.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S')
    stdout = runtime / f'comfy-{stamp}.log'
    stderr = runtime / f'comfy-{stamp}.err.log'
    env = os.environ.copy()
    env['TRITON_PTXAS.EXE_PATH'] = str(compiler)
    env['TRITON_PTXAS_PATH'] = str(compiler)
    args = [str(python), '-u', 'main.py', '--listen', '0.0.0.0', '--port', str(port),
            '--lowvram', '--use-pytorch-cross-attention', '--disable-all-custom-nodes',
            '--whitelist-custom-nodes', 'ComfyUI-Trellis2-GGUF']
    if config.get('output_directory'):
        output_directory = Path(config['output_directory'])
        if not output_directory.is_absolute():
            raise RuntimeError('local-stack.json 中的 ComfyUI output_directory 必须是绝对路径。')
        output_directory.mkdir(parents=True, exist_ok=True)
        args += ['--output-directory', str(output_directory)]
    with stdout.open('wb') as out, stderr.open('wb') as err:
        process = subprocess.Popen(args, cwd=root, env=env, stdout=out, stderr=err,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    (runtime / 'comfy-process.json').write_text(json.dumps(
        dict(pid=process.pid, url=url, log=str(stdout), error_log=str(stderr)), indent=2), encoding='utf-8')
    print('正在启动本机 ComfyUI（低显存配置）…', flush=True)
    deadline, last_progress = time.monotonic() + timeout, 0
    while time.monotonic() < deadline:
        if ready():
            print('ComfyUI 已就绪。', flush=True)
            return
        if process.poll() is not None:
            raise RuntimeError(f'ComfyUI 启动失败，日志：{stderr}')
        if time.monotonic() - last_progress >= 20:
            print(f'等待 ComfyUI 加载，日志：{stdout}', flush=True)
            last_progress = time.monotonic()
        time.sleep(2)
    raise RuntimeError(f'ComfyUI 未在限定时间内就绪，日志：{stderr}')
