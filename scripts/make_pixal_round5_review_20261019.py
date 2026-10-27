"""Create a contact sheet from actual model renders without altering their colors."""
import json
import argparse
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--final', action='store_true')
parser.add_argument('--integrated', action='store_true')
args = parser.parse_args()
rows = json.loads((ROOT / 'tmp/pixal-round5-renders-20261019.json').read_text(encoding='utf-8'))
if args.integrated:
    rows = json.loads((ROOT / 'tmp/pixal-round5-integrated-renders-20261019.json').read_text(encoding='utf-8'))
elif args.final:
    rows = rows[:6] + json.loads((ROOT / 'tmp/pixal-round5-after-remesh-renders-20261019.json').read_text(encoding='utf-8'))
models = list(dict.fromkeys(row['model'] for row in rows))
assert len(models) == 2 and len(rows) == 12
target = ROOT / ('docs/Pixal3D_第五轮最终完整流程对照_20261019.png' if args.integrated else ('docs/Pixal3D_第五轮链路修复实际对照_20261019.png' if args.final else 'docs/Pixal3D_第五轮实际模型对照_20261019.png'))
assert not target.exists()
canvas = Image.new('RGB', (1800, 2560), '#283044')
draw = ImageDraw.Draw(canvas)
font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 24)
for model_index, model in enumerate(models):
    for mode_index, mode in enumerate(('original', 'base')):
        y = (model_index * 2 + mode_index) * 640
        for col, axis in enumerate(('+z', 'angle', '+y')):
            row = next(r for r in rows if r['model'] == model and r['mode'] == mode and r['axis'] == axis)
            source = Image.open(row['path']).convert('RGB').resize((600, 600), Image.Resampling.LANCZOS)
            canvas.paste(source, (col * 600, y + 40))
            label = ('Before fix' if model_index == 0 else ('NAF + deferred cleanup' if args.final or args.integrated else 'After NAF fix')) + f' | {mode} | {axis}'
            draw.text((col * 600 + 12, y + 8), label, font=font, fill='white')
canvas.save(target)
if args.final or args.integrated:
    compact = Image.new('RGB', (1200, 640), '#283044')
    labels = ImageDraw.Draw(compact)
    for col, model in enumerate(models):
        row = next(r for r in rows if r['model'] == model and r['mode'] == 'base' and r['axis'] == '+z')
        compact.paste(Image.open(row['path']).convert('RGB').resize((600, 600), Image.Resampling.LANCZOS), (col*600, 40))
        labels.text((col*600+12, 8), 'Before' if col == 0 else 'After (actual model render)', font=font, fill='white')
    compact.save(ROOT / ('docs/Pixal3D_第五轮最终正面对照_20261019.png' if args.integrated else 'docs/Pixal3D_第五轮正面对照_20261019.png'))
print(target)
