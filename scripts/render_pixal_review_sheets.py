"""Arrange real rendered controls for visual review; no synthetic textures."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
tmp = root / 'tmp'
trials = json.loads((tmp / 'pixal-fixed-geometry-uv-comparison-20261011.json').read_text())
font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 24)
def sheet(rows, modes_axes, output, columns):
    entries = [(r, m, a) for r in rows for m, a in modes_axes]
    width, height = 600, 640
    canvas = Image.new('RGB', (columns*width, ((len(entries)+columns-1)//columns)*height), '#283044')
    draw = ImageDraw.Draw(canvas)
    for i,(row,mode,axis) in enumerate(entries):
        stem = Path(row['model']).stem
        source = tmp / f'{stem}_{mode}_{axis}.png'
        assert source.is_file(), source
        picture = Image.open(source).convert('RGB').resize((600,600))
        x,y = (i%columns)*width,(i//columns)*height
        canvas.paste(picture,(x,y+40))
        draw.text((x+12,y+8),f"{row['case']} | {row.get('variant','full')} | {mode} {axis}",font=font,fill='white')
    canvas.save(root/'docs'/output)

assert len(trials) == 12
sheet(trials,[('base','plusz')],'Pixal3D_固定几何UV对照_20261012.png',4)
full=[]
for case in ('person','robot','helmet'):
    row = json.loads((tmp/f'pixal-full-round3-sparse-resume-{case}-metrics.json').read_text())[0]
    full.append(dict(row,case=case))
sheet(full,[('original','angle'),('base','angle')],'Pixal3D_第三轮完整生成渲染_20261012.png',2)
print('Two sheets saved from actual rendered models')
