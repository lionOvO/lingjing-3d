"""Arrange all actual cleanup-order trial renders for inspection."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT = Path(__file__).resolve().parents[1]
rows = []
for name in ('pixal-round5-after-remesh-renders-20261019.json', 'pixal-round5-categories-renders-20261019.json'):
    rows += json.loads((ROOT / 'tmp' / name).read_text(encoding='utf-8'))
assert len(rows) == 18
target = ROOT / 'docs/Pixal3D_第五轮清理顺序三类验证_20261019.png'
assert not target.exists()
canvas = Image.new('RGB', (1800, 3840), '#283044')
draw = ImageDraw.Draw(canvas)
font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 24)
for i, row in enumerate(rows):
    x, y = i % 3 * 600, i // 3 * 640
    case = next(case for case in ('person', 'robot', 'helmet') if case+'-20261019' in row['model'])
    canvas.paste(Image.open(row['path']).convert('RGB').resize((600, 600), Image.Resampling.LANCZOS), (x, y+40))
    draw.text((x+12, y+8), f"{case} | {row['mode']} | {row['axis']}", font=font, fill='white')
canvas.save(target)
print(target)
