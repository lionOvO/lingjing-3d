"""Check independent real checkpoint loader runs without loading models again."""
import json
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
rows = []
for component in ('ss', 'shape512', 'shape1024', 'texture'):
    bases = [ROOT / f'tmp/pixal-gguf-{component}-{variant}-round2' for variant in ('old', 'new')]
    old, new = [json.loads(base.with_suffix('.json').read_text(encoding='utf-8')) for base in bases]
    assert old['tensors'] == new['tensors'], component + ': tensor bytes/dtype/shape mismatch'
    assert old['ggml_metadata'] == new['ggml_metadata'], component + ': quant metadata mismatch'
    assert old['cpu_rng_sha256'] == new['cpu_rng_sha256'], component + ': CPU RNG state mismatch'
    first, second = [np.load(base.with_suffix('.npz')) for base in bases]
    assert first.files == second.files
    for name in first.files:
        np.testing.assert_array_equal(first[name], second[name], err_msg=component + '/' + name)
    rows.append(dict(component=component, tensors=len(new['tensors']), exact_gpu_linear_outputs=len(first.files),
                     old_seconds=old['seconds'], new_seconds=new['seconds'],
                     old_peak_private_bytes=old['peak_private_bytes'], new_peak_private_bytes=new['peak_private_bytes']))
print(json.dumps(rows, indent=2))
(ROOT / 'tmp/pixal-gguf-loader-comparison-round2-metrics.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')
