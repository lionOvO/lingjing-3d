"""Build the review page and sheets from the actual completed controls."""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root=Path(__file__).resolve().parents[1];tmp=root/'tmp'
trials=json.loads((tmp/'pixal-round4-color-trials-20261012.json').read_text())
colors=json.loads((tmp/'pixal-round4-surface-colors-20261012.json').read_text())
refs=json.loads((tmp/'pixal-round4-neural-color-reference-linear-20261012.json').read_text())
labels={'baseline1024':'原版 1024','padding1024':'修复边距 1024','paddinghalf1024':'半边距实验 1024',
        'orientationhalf1024':'朝向+半边距实验','neural':'神经顶点色参考（无图集）'}
names={'person':'人物','robot':'机器人','helmet':'带翼头盔'}
rows=[]
for case in names:
    for variant in labels:
        if variant=='neural':
            row=dict(next(r for r in refs if r['case']==case),variant=variant,texture_sizes=[[0,0]],color_mae=None)
        else:
            row=dict(next(r for r in trials if r['case']==case and r['variant']==variant))
            row['texture_sizes']=[[1024,1024]]
            row['color_mae']=next(r for r in colors if r['case']==case and r['variant']==variant)['mean_absolute_rgb_byte_error']
        row.update(display_name=f"{names[case]} · {labels[variant]}",file_bytes=Path(row['model']).stat().st_size)
        rows.append(row)
(tmp/'pixal-round4-viewer-metrics-20261012.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
page=(tmp/'inspect-pixal-uv-comparison-20261011.html').read_text(encoding='utf-8')
page=page.replace('/tmp/pixal-uv-comparison-viewer-metrics-20261011.json','/tmp/pixal-round4-viewer-metrics-20261012.json')
page=page.replace("row.variant==='baseline2048'","row.variant==='padding1024'")
page=page.replace('new THREE.MeshBasicMaterial({map:o.material.map,color:o.material.color,side:THREE.DoubleSide})',
                  'new THREE.MeshBasicMaterial({map:o.material.map,color:o.material.color,vertexColors:!!o.geometry.attributes.color,side:THREE.DoubleSide})')
old='${current.texture_sizes[0][0]} 贴图 · 颜色平均误差 ${current.color_mae.toFixed(2)}/255 · 重叠面心样本 ${(current.ambiguous_centroid_fraction*100).toFixed(2)}% · 零 UV 面 ${current.exported_zero_uv_faces}'
new='${current.variant===\'neural\'?\'神经RGB顶点插值参考，无图集\':\'1024贴图 · 颜色平均误差 \'+current.color_mae.toFixed(2)+\'/255\'}'
assert old in page
page=page.replace(old,new)
page=page.replace('相同网格与神经纹理重烘焙；','相同网格与神经纹理对照；神经顶点色采用线性编码，半边距及朝向均为实验；')
page=page.replace('Pixal3D 固定网格纹理对照','Pixal3D 第四轮纹理诊断')
(tmp/'inspect-pixal-round4-20261012.html').write_text(page,encoding='utf-8')
font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',23)
canvas=Image.new('RGB',(3000,1920),'#283044');draw=ImageDraw.Draw(canvas)
for i,row in enumerate(rows):
    x,y=(i%5)*600,(i//5)*640
    picture=tmp/f"{Path(row['model']).stem}_base_plusz.png"
    assert picture.exists()
    canvas.paste(Image.open(picture).convert('RGB').resize((600,600)),(x,y+40))
    draw.text((x+10,y+8),f"{row['case']} | {row['variant']}",font=font,fill='white')
canvas.save(root/'docs/Pixal3D_第四轮UV与神经颜色对照_20261012.png')
print('15 actual controls in fourth-round viewer and sheet')
