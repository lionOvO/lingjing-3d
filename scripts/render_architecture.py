"""Render the README architecture as a self-contained PNG (requires Pillow).

Usage: python scripts/render_architecture.py [--font /path/to/cjk-font]
No network service or Mermaid browser renderer is needed.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/images/system-architecture.png"
SCALE = 2
INK, MUTED, LINE = "#18344e", "#50667a", "#4f7394"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--font", type=Path, help="CJK TrueType/OpenType font")
    args = parser.parse_args()
    candidates = [args.font] if args.font else [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    ]
    font_path = next((p for p in candidates if p and p.is_file()), None)
    if font_path is None:
        parser.error("Provide a CJK font with --font.")
    image = Image.new("RGB", (1800 * SCALE, 1200 * SCALE), "#ffffff")
    draw = ImageDraw.Draw(image)
    fonts = {}

    def font(size):
        if size not in fonts:
            fonts[size] = ImageFont.truetype(str(font_path), size * SCALE)
        return fonts[size]

    def text(x, y, value, size=23, color=INK, center=False):
        selected = font(size)
        width = draw.textlength(value, font=selected)
        if center:
            x -= width / (2 * SCALE)
        draw.text((round(x * SCALE), round(y * SCALE)), value, fill=color, font=selected)

    def box(rect, fill, outline="#d7e2ec", radius=18):
        draw.rounded_rectangle(tuple(round(v * SCALE) for v in rect),
                               radius=radius * SCALE, fill=fill, outline=outline, width=2 * SCALE)

    def arrow(points, dashed=False):
        for start, end in zip(points, points[1:]):
            x1, y1 = start
            x2, y2 = end
            distance = math.hypot(x2 - x1, y2 - y1)
            if dashed:
                for offset in range(0, int(distance), 17):
                    a, b = offset / distance, min(offset + 9, distance) / distance
                    draw.line([(round((x1 + (x2-x1)*a)*SCALE), round((y1 + (y2-y1)*a)*SCALE)),
                               (round((x1 + (x2-x1)*b)*SCALE), round((y1 + (y2-y1)*b)*SCALE))],
                              fill=LINE, width=3*SCALE)
            else:
                draw.line([(round(x1*SCALE), round(y1*SCALE)), (round(x2*SCALE), round(y2*SCALE))],
                          fill=LINE, width=3*SCALE)
        a, b = points[-2:]
        angle = math.atan2(b[1]-a[1], b[0]-a[0])
        corners = [b, (b[0]-13*math.cos(angle-.45), b[1]-13*math.sin(angle-.45)),
                   (b[0]-13*math.cos(angle+.45), b[1]-13*math.sin(angle+.45))]
        draw.polygon([(round(x*SCALE), round(y*SCALE)) for x,y in corners], fill=LINE)

    def node(x, y, w, title, lines, fill="#ffffff", h=118):
        box((x, y, x+w, y+h), fill)
        text(x+w/2, y+19, title, 27, center=True)
        for index, line in enumerate(lines):
            text(x+w/2, y+62+index*28, line, 21, MUTED, center=True)

    text(54, 30, "灵境造物 · 系统架构", 43)
    text(56, 91, "参考图准备 → 异步生成 → 结构质检 → GLB 归档与交付", 24, MUTED)

    box((44, 145, 1756, 380), "#f2f7fc")
    text(67, 160, "01  交互与业务接口", 23, MUTED)
    arrow([(564, 267), (664, 267)])
    arrow([(994, 267), (1094, 267)])
    arrow([(1379, 326), (1379, 354), (324, 354), (324, 326)])
    box((580, 336, 1110, 372), "#f2f7fc", "#f2f7fc", 6)
    text(845, 338, "WebSocket 阶段状态；断线回退 HTTP 查询", 21, LINE, center=True)
    node(84, 208, 480, "Vue 3 / TypeScript / Three.js", ["图片准备、任务页面、模型检视"])
    node(664, 208, 330, "Nginx", ["同源入口与代理"])
    node(1094, 208, 570, "FastAPI", ["认证、资源权限、任务与文件接口"])

    box((44, 411, 1756, 830), "#f5f9f8", "#d9e7e3")
    text(67, 425, "02  后台执行与推理", 23, MUTED)
    arrow([(1664, 267), (1735, 267), (1735, 465), (209, 465), (209, 495)])
    box((1140, 445, 1400, 482), "#f5f9f8", "#f5f9f8", 6)
    text(1270, 447, "创建记录并投递任务", 21, LINE, center=True)
    for x in (334, 680, 1026, 1372):
        arrow([(x, 554), (x+96, 554)])
    arrow([(901, 613), (901, 687)], dashed=True)
    arrow([(1593, 613), (1593, 687)])
    arrow([(1593, 791), (1593, 812), (555, 812), (555, 613)])
    box((880, 793, 1300, 828), "#f5f9f8", "#f5f9f8", 6)
    text(1090, 795, "GLB 经共享目录回传 Worker", 21, LINE, center=True)
    node(84, 495, 250, "Redis / Celery", ["后台生成队列"])
    node(430, 495, 250, "Celery Worker", ["消费任务、持久化"])
    node(776, 495, 250, "LangGraph", ["节点、质检、重试"])
    node(1122, 495, 250, "HTTP 适配服务", ["协议与工作流映射"])
    node(1468, 495, 250, "ComfyUI", ["Pixal3D · 宿主机"])
    node(776, 687, 250, "Milvus（可选）", ["参数与失败项参考"], h=104)
    node(1468, 687, 250, "GLB 工件", ["限定目录读取"], h=104)

    box((44, 865, 1756, 1122), "#f7f8fc", "#dfe2ee")
    text(67, 880, "03  数据与文件存储", 23, MUTED)
    text(1510, 883, "FastAPI / Worker 共用", 22, MUTED, center=True)
    node(220, 938, 580, "MySQL", ["用户、项目、任务、检查报告和版本", "阶段与结果写回业务记录"], h=138)
    node(1000, 938, 580, "MinIO", ["参考图、生成模型及修复版本文件", "Worker 完成工件归档后交付"], h=138)
    text(57, 1143, "虚线为可选知识检索；阶段状态不等于采样步级进度。", 22, MUTED)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image.save(OUTPUT, optimize=True)
    print(f"Rendered {OUTPUT.relative_to(ROOT)}: {image.width} x {image.height}")


if __name__ == "__main__":
    main()
