"""Enable only the existing temporary output snapshot node with a fresh prefix."""
from pathlib import Path
import socket
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--local-factory', action='store_true')
parser.add_argument('--final-cleanup', action='store_true')
args = parser.parse_args()
assert not (args.local_factory and args.final_cleanup)
variant = 'final-chain' if args.final_cleanup else ('local-naf' if args.local_factory else 'naf-global')
tag = '-final-chain' if args.final_cleanup else ('-local-naf' if args.local_factory else '')

ROOT = Path(__file__).resolve().parents[1]
CUSTOM = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes')
disabled = CUSTOM / 'Pixal3DValidationSnapshot.disabled'
enabled = CUSTOM / 'Pixal3DValidationSnapshot'
assert disabled.resolve().parent == CUSTOM.resolve() == enabled.resolve().parent
assert disabled.is_dir() and not enabled.exists()
with socket.socket() as connection:
    assert connection.connect_ex(('127.0.0.1', 8188)) != 0
original = (disabled / '__init__.py').read_bytes()
backup = ROOT / f'tmp/pixal-round5{tag}-snapshot-node-before-20261019.py'
assert not backup.exists()
backup.write_bytes(original)
changed = original.decode('utf-8').replace('pixal-round3-sparse-resume-{case}-prediction-20261011.npz', f'pixal-round5-{variant}-{{case}}-prediction-20261019.npz')
assert changed != original.decode('utf-8')
for case in ('person', 'robot', 'helmet'):
    assert not (ROOT / f'tmp/pixal-round5-{variant}-{case}-prediction-20261019.npz').exists()
(ROOT / f'scripts/comfy_pixal_validation_snapshot_round5{tag}.py').write_text(changed, encoding='utf-8')
(disabled / '__init__.py').write_text(changed, encoding='utf-8')
disabled.rename(enabled)
print(f'Enabled diagnostic output node: {enabled}')
