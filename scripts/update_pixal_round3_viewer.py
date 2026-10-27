"""Create a third-round viewer from completed audited exports."""
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
paths=[ROOT/'tmp/pixal-generation-cascade-metrics-20261009.json',ROOT/'tmp/pixal-full-round2-release-metrics.json']
for pattern in ('pixal-full-round2-core-meta-*-metrics.json','pixal-full-round3-memory-final-*-metrics.json','pixal-full-round3-sparse-final-*-metrics.json','pixal-full-round3-sparse-resume-*-metrics.json'):
    paths.extend(sorted((ROOT/'tmp').glob(pattern)))
rows=[]
for path in paths:
    for row in json.loads(path.read_text(encoding='utf-8')):
        assert Path(row['model']).is_file()
        if not any(saved['model']==row['model'] for saved in rows):rows.append(row)
metrics=ROOT/'tmp/pixal-round3-viewer-metrics-20261011.json'
metrics.write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
source=(ROOT/'tmp/inspect-pixal-pipeline-20261009.html').read_text(encoding='utf-8')
source=source.replace('/tmp/pixal-round2-viewer-metrics.json','/tmp/pixal-round3-viewer-metrics-20261011.json')
variant="const variant=row.label.includes('round3-sparse-resume')?'（第三轮稀疏投影版完整生成）':row.label.includes('round3')?'（第三轮早期完整生成）':row.label.includes('round2-core-meta')?'（第二轮完整生成）':row.label==='20261009-round2-release'?'（第一轮最终版完整生成）':row.label==='20261009-cascade'?'（投影网格修正前）':row.export_node==='20'?'（保留预测网格）':'（重建网格）';"
source,count=re.subn(r'const variant=.*?;',lambda _:variant,source,count=1)
assert count==1
source=source.replace('const latest=rows.findIndex(', 'const latest=rows.findLastIndex(')
(ROOT/'tmp/inspect-pixal-pipeline-20261011.html').write_text(source,encoding='utf-8')
print(f'{len(rows)} audited models; third-round viewer saved')
