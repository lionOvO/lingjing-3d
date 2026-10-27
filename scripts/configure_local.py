"""Create ignored machine-local settings; never print generated credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--comfy-root', type=Path, required=True)
    parser.add_argument('--comfy-python', type=Path)
    args = parser.parse_args()
    engine = args.comfy_root.resolve()
    python = (args.comfy_python or engine.parent / 'python_embeded/python.exe').resolve()
    if not (engine / 'main.py').is_file() or not python.is_file():
        parser.error('ComfyUI main.py or its Python executable does not exist.')
    config = ROOT / 'local-stack.json'
    if config.exists():
        parser.error('local-stack.json already exists; edit it deliberately instead of overwriting.')
    env_file = ROOT / '.env'
    if not env_file.exists():
        values = {
            'MYSQL_PASSWORD': secrets.token_urlsafe(24),
            'MYSQL_ROOT_PASSWORD': secrets.token_urlsafe(24),
            'MINIO_ROOT_PASSWORD': secrets.token_urlsafe(24),
            'JWT_SECRET': secrets.token_urlsafe(48),
            'TRELLIS_PROVIDER': 'local_comfyui',
            'TRELLIS_COMFY_ENABLED': 'true',
            'TRELLIS_COMFY_OUTPUT_DIR': '/comfy-output',
            'TRELLIS_COMFY_HOST_OUTPUT_DIR': './tmp/comfy-output',
            'GENERATION_HTTP_TIMEOUT': '3600',
        }
        values['MINIO_SECRET_KEY'] = values['MINIO_ROOT_PASSWORD']
        lines = []
        for line in (ROOT / '.env.example').read_text(encoding='utf-8').splitlines():
            key = line.split('=', 1)[0]
            lines.append(key + '=' + values[key] if key in values else line)
        env_file.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    config.write_text(json.dumps({
        'root': str(ROOT),
        'project': 'lingjing-' + hashlib.sha256(str(ROOT).encode()).hexdigest()[:10],
        'compose_override': 'docker-compose.local.yml',
        'comfyui': {'url': 'http://127.0.0.1:8188', 'root': str(engine),
                    'python': str(python), 'output_directory': str(ROOT / 'tmp/comfy-output')},
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Created local-stack.json; .env created if absent. Credentials were not printed.')

if __name__ == '__main__':
    main()
