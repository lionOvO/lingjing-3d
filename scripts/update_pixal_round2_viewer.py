"""Collect audited results and label them by actual validation provenance."""
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
paths = [ROOT / 'tmp/pixal-generation-cascade-metrics-20261009.json',
         ROOT / 'tmp/pixal-full-round2-release-metrics.json']
paths += sorted((ROOT / 'tmp').glob('pixal-full-round2-core-meta-*-metrics.json'))
paths += sorted((ROOT / 'tmp').glob('pixal-full-round3-memory-final-*-metrics.json'))
paths += sorted((ROOT / 'tmp').glob('pixal-full-round3-sparse-final-*-metrics.json'))
rows = []
for path in paths:
    for row in json.loads(path.read_text(encoding='utf-8')):
        if not any(existing['model'] == row['model'] for existing in rows):
            rows.append(row)
(ROOT / 'tmp/pixal-round2-viewer-metrics.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
path = ROOT / 'tmp/inspect-pixal-pipeline-20261009.html'
source = path.read_text(encoding='utf-8')
source = source.replace("'/tmp/pixal-generation-cascade-metrics-20261009.json'", "'/tmp/pixal-round2-viewer-metrics.json'")
old = "const variant=row.label==='20261009-cascade'?'（投影网格修正前）':row.export_node==='20'?'（保留预测网格）':'（重建网格）';"
previous = "const variant=row.label.includes('round2-core-meta')?'（第二轮完整生成）':row.label==='20261009-round2-release'?'（第一轮最终版完整生成）':row.label==='20261009-cascade'?'（投影网格修正前）':row.export_node==='20'?'（保留预测网格）':'（重建网格）';"
new = "const variant=row.label.includes('round3-sparse-final')?'（第三轮稀疏投影版完整生成）':row.label.includes('round3-memory-final')?'（第三轮完整生成）':row.label.includes('round2-core-meta')?'（第二轮完整生成）':row.label==='20261009-round2-release'?'（第一轮最终版完整生成）':row.label==='20261009-cascade'?'（投影网格修正前）':row.export_node==='20'?'（保留预测网格）':'（重建网格）';"
source = source.replace(old, new).replace(previous, new)
source = source.replace("const latest=rows.findIndex(row=>row.image==='OIP_clean_1024_rgba.png'&&row.export_node==='19');", "const latest=rows.findLastIndex(row=>row.image==='OIP_clean_1024_rgba.png'&&row.export_node==='19');")
path.write_text(source, encoding='utf-8')
print(f'{len(rows)} audited models')
