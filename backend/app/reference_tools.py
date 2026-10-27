"""Conservative pixel diagnostics for image-conditioned 3D input.

No pose/person identification or generative restoration is performed here.
An estimated mask guides framing only; it never erases source pixels.
"""
from collections import deque
import hashlib
import io

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError


def validate_generation_reference(data: bytes, original_data: bytes | None = None, background_risk_accepted: bool = False) -> dict:
    """Framing is not foreground extraction. Inspect bytes, never client flags."""
    actual = analyze_reference(data)
    original = analyze_reference(original_data) if original_data is not None else actual
    complex_background = actual['background_kind'] != 'alpha' and (
        actual['background_kind'] == 'complex' or original['background_kind'] == 'complex'
    )
    if complex_background and background_risk_accepted is not True:
        raise ValueError('参考图仍含复杂背景，直接生成可能得到背景板。请先抠图，或明确确认保留背景直接生成。')
    return {'version': 2, 'sha256': hashlib.sha256(data).hexdigest(),
            'background_risk_accepted': complex_background and background_risk_accepted is True,
            'background_kind': actual['background_kind'], 'original_background_kind': original['background_kind']}


def analyze_reference(data: bytes) -> dict:
    try:
        with Image.open(io.BytesIO(data)) as source:
            if source.format not in {'PNG', 'JPEG', 'WEBP'} or source.width*source.height > 20_000_000:
                raise ValueError('图片无效或超过 2000 万像素')
            image = ImageOps.exif_transpose(source).convert('RGBA')
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('图片无法读取，请更换 PNG、JPG 或 WEBP 图片') from exc
    original_size = image.size
    image.thumbnail((512, 512), Image.Resampling.LANCZOS)
    pixels = np.asarray(image)
    rgb, alpha = pixels[:, :, :3].astype(np.float32), pixels[:, :, 3]
    visible = alpha > 12
    if not visible.any():
        raise ValueError('图片没有可见主体，请重新选择图片')
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    color = np.median(border, axis=0)
    border_distance = np.max(np.abs(border-color), axis=1)
    uniform = float(np.mean(border_distance < 24)) >= .88
    meaningful_alpha = float(np.mean(alpha < 250)) > .005
    mask, method = None, 'uncertain'
    if meaningful_alpha:
        mask, method = visible, 'alpha'
    elif uniform:
        # Only border-connected pixels similar to the border colour count as
        # background. A similarly coloured shirt inside a silhouette survives.
        eligible = np.max(np.abs(rgb-color), axis=2) < 26
        height, width = eligible.shape
        background = np.zeros_like(eligible)
        pending = deque()
        for row, col in [(0,c) for c in range(width)]+[(height-1,c) for c in range(width)]+[(r,0) for r in range(height)]+[(r,width-1) for r in range(height)]:
            if eligible[row,col] and not background[row,col]:
                background[row,col] = True
                pending.append((row,col))
        while pending:
            row,col=pending.popleft()
            for nr,nc in ((row-1,col),(row+1,col),(row,col-1),(row,col+1)):
                if 0<=nr<height and 0<=nc<width and eligible[nr,nc] and not background[nr,nc]:
                    background[nr,nc]=True
                    pending.append((nr,nc))
        candidate = ~background
        if .005 < float(candidate.mean()) < .94:
            mask,method=candidate,'border-connected'
    warnings=[]
    if method=='border-connected':
        warnings.append({'code':'estimated-outline','message':'构图使用像素轮廓估计，浅色衣物或细配饰可能与背景接近；若范围不准，请关闭按轮廓整理并手动框选。'})
    bbox=None
    occupancy=None
    touching=[]
    if mask is not None:
        rows,cols=np.where(mask)
        left,top,right,bottom=int(cols.min()),int(rows.min()),int(cols.max()+1),int(rows.max()+1)
        # Percentages refer to the EXIF-corrected source, with one analysis
        # pixel of safety against downsampled fine hairs or detached jewellery.
        bbox={'x':max(0,left-1)/image.width*100,'y':max(0,top-1)/image.height*100,
              'right':min(image.width,right+1)/image.width*100,'bottom':min(image.height,bottom+1)/image.height*100}
        occupancy=round(float(mask.mean()),3)
        touching=[name for name,hit in [('左侧',left<=1),('上方',top<=1),('右侧',right>=image.width-1),('下方',bottom>=image.height-1)] if hit]
        if touching:
            warnings.append({'code':'edge-contact','message':f'轮廓靠近{"、".join(touching)}边缘，请核对头发、手脚和配饰是否截断；整理图片不能补回缺失部位。'})
        if occupancy < .18:
            warnings.append({'code':'small-subject','message':'有效轮廓占比较小，将按轮廓整理构图；放大不能恢复原图缺失的细节。'})
    else:
        warnings.append({'code':'uncertain-background','message':'背景或轮廓不够明确，默认保留整图。可手动框选人物，或单独预览去背景效果。'})
    gray=rgb.mean(axis=2)
    laplace=4*gray[1:-1,1:-1]-gray[:-2,1:-1]-gray[2:,1:-1]-gray[1:-1,:-2]-gray[1:-1,2:]
    active=(mask if mask is not None else visible)[1:-1,1:-1]
    sharpness=float(np.var(laplace[active])) if active.any() else 0
    if min(original_size)<512:
        warnings.append({'code':'low-resolution','message':'原图短边不足 512 像素，人物细节可能不足；优先换用清晰原图，避免反复放大。'})
    if sharpness<25:
        warnings.append({'code':'soft-detail','message':'局部边缘对比偏低，请放大检查五官和发丝。轻度锐化只增强已有边缘，不会补出细节。'})
    return {'version':2,'width':original_size[0],'height':original_size[1],
            'background_kind':'alpha' if meaningful_alpha else 'simple' if method=='border-connected' else 'complex',
            'background_color':'#'+''.join(f'{int(v):02x}' for v in color),
            'framing_method':method,'subject_bounds':bbox,'foreground_fraction':occupancy,
            'edge_contact':touching,'sharpness':round(sharpness,1),'warnings':warnings,
            'recommendation':'保留原图像素，按已有透明轮廓整理构图' if method=='alpha' else '保留简单背景，按估计轮廓整理构图' if method=='border-connected' else '保留整图，先检查人物范围与背景干扰'}
