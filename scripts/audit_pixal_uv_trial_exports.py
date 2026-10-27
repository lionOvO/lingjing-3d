"""Audit the actual exported UV trials, including the float32 V flip."""
import json
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
trials = json.loads((root / 'tmp/pixal-fixed-geometry-uv-comparison-20261011.json').read_text())
assert len(trials) == 12
for row in trials:
    output = root / f"tmp/pixal-uv-export-quality-{row['case']}-{row['variant']}-20261011.json"
    assert not output.exists(), 'Preserve existing export audit'
    subprocess.run([sys.executable, str(root / 'scripts/audit_pixal_mesh_quality.py'),
                    row['model'], '--output', str(output), '--require-clean'], check=True)
