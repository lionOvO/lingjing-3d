"""Restore the previous defaults after visible hair regression; preserve the candidate."""
import hashlib
import json
from pathlib import Path
import socket

ROOT = Path(__file__).resolve().parents[1]
folder = ROOT / 'tmp/pixal-round5-candidate-sources-20261019'
assert not folder.exists()
with socket.socket() as connection:
    assert connection.connect_ex(('127.0.0.1', 8188)) != 0
records = [json.loads((ROOT / 'tmp' / name).read_text(encoding='utf-8')) for name in
           ('pixal-naf-global-installed-20261019.json', 'pixal-local-condition-factory-installed-20261019.json')]
for record in records:
    assert hashlib.sha256(Path(record['path']).read_bytes()).hexdigest() == record['sha256']
    assert hashlib.sha256(Path(record['backup']).read_bytes()).hexdigest() == record['before_sha256']
folder.mkdir()
for record in records:
    path = Path(record['path'])
    (folder / path.name).write_bytes(path.read_bytes())
    path.write_bytes(Path(record['backup']).read_bytes())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == record['before_sha256']
target = ROOT / 'tmp/pixal-round5-rollback-20261019.json'
assert not target.exists()
target.write_text(json.dumps(dict(candidate_deployed=False, reason='Full person render: facial yellow-white bands reduced, but hair holes substantially worse.',
                                  restored=records, preserved_sources=str(folder)), indent=2), encoding='utf-8')
print(target)
