"""Compare real pre-postprocess predictions using saved per-array byte hashes."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
before=json.loads((ROOT/'tmp/pixal-round3-memory-final-person-prediction-20261009.json').read_text())
after=json.loads((ROOT/'tmp/pixal-round3-sparse-final-person-prediction-20261010.json').read_text())
result={name:dict(before=before[name],after=after[name],exact=before[name]==after[name]) for name in before}
out=ROOT/'tmp/pixal-real-neural-sparse-projection-comparison-20261010.json'
out.write_text(json.dumps(result,indent=2))
print(json.dumps({name:row['exact'] for name,row in result.items()}))
assert all(row['exact'] for row in result.values()),'Real neural predictions differ; inspect before claiming exactness'
