"""Start the existing local Compose application with available host ports."""
import argparse
import hashlib
from contextlib import contextmanager
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser
from local_comfy import ensure_comfy

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / 'tmp/local-launcher'
STATE = RUNTIME / 'state.json'
CONFIG_FILE = ROOT / 'local-stack.json'
CONFIG = json.loads(CONFIG_FILE.read_text(encoding='utf-8')) if CONFIG_FILE.is_file() else {}
if CONFIG and Path(CONFIG.get('root', '')).resolve() != ROOT.resolve():
    raise RuntimeError('local-stack.json 与当前项目目录不匹配。')
PROJECT = CONFIG.get('project') or 'lingjing-' + hashlib.sha256(str(ROOT.resolve()).casefold().encode('utf-8')).hexdigest()[:10]
HTTP = build_opener(ProxyHandler({}))
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def available(port, host):
    # Docker Desktop can forward a listening port without reserving a normal
    # Windows bind socket. Test connectivity as well as exclusive binding.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.15)
        if probe.connect_ex(('127.0.0.1' if host == '0.0.0.0' else host, port)) == 0:
            return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        if os.name == 'nt':
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind((host, port))
            return True
        except OSError:
            return False


def choose_port(preferred, host, excluded=()):
    for port in range(preferred, min(preferred + 1000, 65536)):
        if port not in excluded and available(port, host):
            return port
    raise RuntimeError(f'{preferred} 起的1000个端口均不可用，请换一个起始端口。')


def request(url):
    try:
        with HTTP.open(url, timeout=4) as response:
            return response.status, response.read()
    except HTTPError as error:
        return error.code, error.read()


@contextmanager
def startup_lock():
    import msvcrt
    RUNTIME.mkdir(parents=True, exist_ok=True)
    with (RUNTIME / 'startup.lock').open('a+b') as lock:
        lock.write(b'0')
        lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise RuntimeError('另一个启动脚本正在运行，请等待它完成。') from error
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def docker_paths():
    candidates = [Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/DockerDesktop',
                  Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'Docker/Docker']
    for folder in candidates:
        cli = folder / 'resources/bin/docker.exe'
        if cli.is_file():
            return str(cli), folder / 'Docker Desktop.exe'
    cli = shutil.which('docker.exe')
    if cli:
        return cli, None
    raise RuntimeError('没有找到 Docker Desktop，请安装后重试。')


class Docker:
    def __init__(self, cli):
        # Select the local Linux engine without changing the user's global context.
        self.command = [cli, '--context', 'desktop-linux']
        self.compose = self.command + ['compose', '--project-name', PROJECT, '--project-directory', str(ROOT), '-f', str(ROOT / 'docker-compose.yml')]
        if CONFIG.get('compose_override'):
            override = ROOT / CONFIG['compose_override']
            if override.resolve().parent != ROOT.resolve() or not override.is_file():
                raise RuntimeError('本地 Compose 覆盖文件无效。')
            self.compose += ['-f', str(override)]

    def capture(self, args, env=None, timeout=20, check=True):
        result = subprocess.run(args, cwd=ROOT, env=env, capture_output=True,
                                text=True, encoding='utf-8', errors='replace',
                                timeout=timeout, creationflags=NO_WINDOW)
        if check and result.returncode:
            raise RuntimeError(result.stderr.strip() or 'Docker 命令执行失败。')
        return result

    def ready(self):
        try:
            return self.capture(self.command + ['info', '--format', '{{.ServerVersion}}'], timeout=5, check=False).returncode == 0
        except subprocess.TimeoutExpired:
            return False

    def containers(self):
        ids = self.capture(self.compose + ['ps', '--all', '--quiet']).stdout.split()
        if not ids:
            return []
        rows = json.loads(self.capture(self.command + ['inspect'] + ids).stdout)
        # Only selected metadata is retained; inspect output/environment is never logged.
        for row in rows:
            labels = row['Config'].get('Labels') or {}
            owner = labels.get('com.docker.compose.project.working_dir', '')
            approved = CONFIG.get('preserved_data_containers', {}).get(row.get('Id', ''))
            if approved and owner == approved.get('owner') and labels.get('com.docker.compose.service') == approved.get('service'):
                continue
            if not owner or Path(owner).resolve() != ROOT.resolve():
                raise RuntimeError('同名 Compose 项目属于另一个目录，已停止操作，避免影响它的服务。')
        return rows


def running_port(containers, service, container_port):
    for row in containers:
        if row['Config']['Labels'].get('com.docker.compose.service') != service or not row['State']['Running']:
            continue
        bindings = (row['NetworkSettings'].get('Ports') or {}).get(f'{container_port}/tcp') or []
        for binding in bindings:
            if binding['HostIp'] in ('0.0.0.0', '127.0.0.1', ''):
                return int(binding['HostPort'])
    return None


def ensure_engine(docker, desktop, timeout):
    if docker.ready():
        return
    if not desktop or not desktop.is_file():
        raise RuntimeError('Docker 引擎未运行，请先启动 Docker Desktop。')
    print('正在启动 Docker Desktop…', flush=True)
    # Explorer launches outside the caller's packaged-app AppData context.
    subprocess.Popen([str(Path(os.environ['WINDIR']) / 'explorer.exe'), str(desktop)], creationflags=NO_WINDOW)
    deadline, last_progress = time.monotonic() + timeout, 0
    while time.monotonic() < deadline:
        if docker.ready():
            return
        if time.monotonic() - last_progress >= 20:
            print('等待 Docker Linux 引擎就绪…', flush=True)
            last_progress = time.monotonic()
        time.sleep(2)
    raise RuntimeError('Docker Desktop 未在限定时间内启动。如出现 sailor-ingest.sock 报错，请退出报错窗口后从 Windows 开始菜单启动 Docker；不要恢复出厂设置。')


def compose_up(docker, env, build, wait_timeout, logfile):
    command = docker.compose + ['up', '-d', '--wait', '--wait-timeout', str(wait_timeout)]
    if CONFIG.get('application_services'):
        command.append('--no-deps')
    if build:
        command.append('--build')
    command += CONFIG.get('application_services', [])
    with logfile.open('a', encoding='utf-8') as log:
        process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
        started, last_progress = time.monotonic(), 0
        try:
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if elapsed > 1800:
                    process.terminate()
                    process.wait(timeout=10)
                    raise RuntimeError(f'构建/启动超过30分钟，详见 {logfile}')
                if elapsed - last_progress >= 20:
                    print(f'正在构建/启动项目并等待健康检查（{int(elapsed)}秒），日志：{logfile}', flush=True)
                    last_progress = elapsed
                time.sleep(1)
        except KeyboardInterrupt:
            process.terminate()
            process.wait(timeout=10)
            raise
    return process.returncode


def verify_services(frontend_url, api_url):
    status, body = request(api_url + '/healthz')
    if status != 200 or json.loads(body).get('status') != 'ok':
        raise RuntimeError('后端健康检查未通过。')
    status, body = request(api_url + '/openapi.json')
    if status != 200 or json.loads(body)['info']['title'] != 'AI 3D Digital Human API':
        raise RuntimeError('选中的后端不是灵境造物 API。')
    status, body = request(frontend_url + '/')
    if status != 200 or '灵境造物' not in body.decode('utf-8', errors='replace'):
        raise RuntimeError('前端页面检查未通过。')
    direct = request(api_url + '/api/v1/auth/me')
    proxied = request(frontend_url + '/api/v1/auth/me')
    if direct[0] != 401 or proxied[0] != 401 or json.loads(direct[1]) != json.loads(proxied[1]):
        raise RuntimeError('前端到后端的 API 代理检查未通过。')


def main():
    parser = argparse.ArgumentParser(description='灵境造物：一键启动现有前后端及依赖，自动避开占用端口。')
    parser.add_argument('--frontend-port', type=int, default=8080)
    parser.add_argument('--api-port', type=int, default=8000)
    parser.add_argument('--build', action='store_true', help='重建应用镜像以包含最新源代码')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--stop', action='store_true', help='停止本目录 Compose 项目，保留容器和数据卷')
    parser.add_argument('--docker-timeout', type=int, default=120)
    parser.add_argument('--wait-timeout', type=int, default=300)
    args = parser.parse_args()
    if any(not 1 <= p <= 65535 for p in (args.frontend_port, args.api_port)):
        parser.error('端口必须在1～65535之间')
    if args.docker_timeout < 1 or args.wait_timeout < 1:
        parser.error('等待时间必须为正数')
    if not (ROOT / '.env').is_file():
        raise RuntimeError('项目 .env 不存在，请先根据 .env.example 配置。')
    cli, desktop = docker_paths()
    docker = Docker(cli)
    with startup_lock():
        if args.stop and not docker.ready():
            print('Docker 引擎未运行，无需停止服务。')
            return
        ensure_engine(docker, desktop, args.docker_timeout)
        containers = docker.containers()
        if args.stop:
            docker.capture(docker.compose + ['stop'], timeout=120)
            if STATE.is_file():
                state = json.loads(STATE.read_text(encoding='utf-8'))
                state['status'] = 'stopped'
                STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
            print('灵境造物项目已停止，数据卷已保留。')
            return
        if CONFIG.get('preserved_data_containers'):
            missing = set(CONFIG['preserved_data_containers']) - {row['Id'] for row in containers}
            if missing:
                raise RuntimeError('已登记的历史数据容器缺失，已停止启动以避免连接空数据库。请检查 Docker 中的原数据容器。')
            stopped = [row['Id'] for row in containers if row['Id'] in CONFIG['preserved_data_containers'] and not row['State']['Running']]
            if stopped:
                docker.capture(docker.command + ['start'] + stopped, timeout=90)
        ensure_comfy(CONFIG.get('comfyui'), RUNTIME)
        frontend_port = running_port(containers, 'frontend', 8080) or choose_port(args.frontend_port, '0.0.0.0')
        api_port = running_port(containers, 'api', 8000) or choose_port(args.api_port, '127.0.0.1', {frontend_port})
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
        logfile = RUNTIME / f'start-{stamp}-{os.getpid()}.log'
        for attempt in range(3):
            env = os.environ.copy()
            frontend_url, api_url = f'http://127.0.0.1:{frontend_port}', f'http://127.0.0.1:{api_port}'
            env.update(FRONTEND_PORT=str(frontend_port), API_PORT=str(api_port),
                       CORS_ORIGINS=','.join((frontend_url, f'http://localhost:{frontend_port}', api_url)))
            print(f'前端端口：{frontend_port}；后端端口：{api_port}', flush=True)
            log_offset = logfile.stat().st_size if logfile.exists() else 0
            if compose_up(docker, env, args.build, args.wait_timeout, logfile) == 0:
                break
            with logfile.open('rb') as log:
                log.seek(log_offset)
                output = log.read().decode('utf-8', errors='replace').lower()
            if not any(marker in output for marker in ('port is already allocated', 'address already in use', 'ports are not available', 'bind: an attempt was made')):
                if 'error while creating mount source path' in output:
                    raise RuntimeError(f'Docker 无法挂载宿主机目录，请核对 .env 中的目录以及 Docker Desktop 的磁盘共享；这不是端口冲突。详见 {logfile}')
                if any(marker in output for marker in ('failed to resolve source metadata', 'proxyconnect', 'connecting via app settings https proxy')):
                    raise RuntimeError(f'镜像下载失败，请检查 Docker Desktop 的代理/网络设置。已有镜像不必重建；详见 {logfile}')
                raise RuntimeError(f'Docker Compose 启动失败，详见 {logfile}')
            if attempt == 2:
                raise RuntimeError(f'端口被其他程序抢占，三次重试仍失败，详见 {logfile}')
            containers = docker.containers()
            frontend_port = running_port(containers, 'frontend', 8080) or choose_port(frontend_port + 1, '0.0.0.0')
            api_port = running_port(containers, 'api', 8000) or choose_port(api_port + 1, '127.0.0.1', {frontend_port})
            print('检测到端口竞争，重新选择端口…', flush=True)
        verify_services(frontend_url, api_url)
        if CONFIG.get('comfyui'):
            status, body = request(frontend_url + '/api/v1/generation/capabilities')
            if status != 200 or 'high_quality' not in json.loads(body).get('available_modes', []):
                raise RuntimeError('网页/API 已启动，但本机高质量生成服务未就绪，请检查 Trellis/ComfyUI 日志。')
        state = dict(status='running', root=str(ROOT), project=PROJECT, frontend_url=frontend_url, api_url=api_url,
                     api_docs_url=api_url + '/docs', log=str(logfile), checked_at=datetime.now().isoformat())
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'\n启动成功\n前端：{frontend_url}\n后端文档：{api_url}/docs\n启动记录：{STATE}', flush=True)
        if not args.no_browser:
            webbrowser.open(frontend_url)


if __name__ == '__main__':
    try:
        main()
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.SubprocessError, URLError) as error:
        print(f'\n启动失败：{error}', file=sys.stderr, flush=True)
        sys.exit(1)
    except KeyboardInterrupt:
        print('\n启动已取消；已创建的容器保留，可重新运行脚本。', file=sys.stderr)
        sys.exit(130)
