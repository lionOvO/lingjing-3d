"""Publish a local review page for completed fixed-geometry UV experiments."""
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
tmp = root / 'tmp'
trials = json.loads((tmp / 'pixal-fixed-geometry-uv-comparison-20261011.json').read_text())
colors = json.loads((tmp / 'pixal-surface-color-comparison-20261011.json').read_text())
assert len(trials) == len(colors) == 12
names = {'person': '人物', 'robot': '机器人', 'helmet': '带翼头盔'}
variants = {'baseline1024': '原展开 · 1024', 'baseline2048': '原展开 · 2048',
            'orientation1024': '朝向约束实验 · 1024', 'orientation2048': '朝向约束实验 · 2048'}
rows = []
for trial, color in zip(trials, colors):
    assert (trial['case'], trial['variant']) == (color['case'], color['variant'])
    key = f"{trial['case']}-{trial['variant']}-20261011"
    quality = json.loads((tmp / f'pixal-uv-export-quality-{key}.json').read_text())
    overlap = json.loads((tmp / f'pixal-uv-overlap-{key}.json').read_text())
    model = Path(trial['model'])
    assert model.is_file() and trial['ordered_geometry_exact']
    rows.append(dict(trial, display_name=f"{names[trial['case']]} · {variants[trial['variant']]}",
                     file_bytes=model.stat().st_size, texture_sizes=[quality['texture_size']],
                     exported_zero_uv_faces=quality['zero_uv_area_faces'],
                     color_mae=color['mean_absolute_rgb_byte_error'],
                     ambiguous_centroid_fraction=overlap['ambiguous_centroid_fraction']))
(tmp / 'pixal-uv-comparison-viewer-metrics-20261011.json').write_text(
    json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
page = (tmp / 'inspect-pixal-pipeline-20261009.html').read_text(encoding='utf-8')
page = page.replace('Pixal3D 完整生成链路样本', 'Pixal3D 固定网格纹理对照')
page = page.replace('/tmp/pixal-round2-viewer-metrics.json', '/tmp/pixal-uv-comparison-viewer-metrics-20261011.json')
page = page.replace('<option value="base">', '<option value="base" selected>', 1)
start = page.index('  const labels=')
end = page.index('  sample.onchange=', start)
page = page[:start] + '''  rows.forEach((row,i)=>{const option=document.createElement('option');option.value=i;option.textContent=row.display_name;sample.append(option)});
  sample.value=rows.findIndex(row=>row.case==='person'&&row.variant==='baseline2048');
''' + page[end:]
page, count = re.subn(r'info\.textContent=`.*?`;',
    lambda _: 'info.textContent=`${filename} · ${current.faces.toLocaleString()} 面 · ${current.texture_sizes[0][0]} 贴图 · 颜色平均误差 ${current.color_mae.toFixed(2)}/255 · 重叠面心样本 ${(current.ambiguous_centroid_fraction*100).toFixed(2)}% · 零 UV 面 ${current.exported_zero_uv_faces}。相同网格与神经纹理重烘焙；拖动旋转，滚轮缩放。`;',
    page, count=1)
assert count == 1
page = page.replace('正在载入完整生成样本。', '正在载入固定网格纹理对照。')
(tmp / 'inspect-pixal-uv-comparison-20261011.html').write_text(page, encoding='utf-8')
print('12 fixed-geometry review models saved; experiments are not installed defaults')
