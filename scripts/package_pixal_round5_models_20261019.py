"""Deliver existing, verified model files without regenerating or modifying them."""
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\output')
TARGET = ROOT / 'exports/Pixal3D_模型效果_20261019'
assert not TARGET.exists(), 'Preserve any existing delivery'
TARGET.mkdir(parents=True)
items = [
    ('01_人物_本轮最终.glb', 'PixalFullPipeline_Person_round5-final-chain-person-20261019_00001_.glb', '人物：本轮最终', '修复后完整新生成，原图和种子不变。'),
    ('02_人物_修复前对照.glb', 'PixalFullPipeline_Person_round5-naf-global-person-20261019_00001_.glb', '人物：修复前对照', '本轮旧NAF的完整生成，用于与最终模型比较。'),
    ('03_机器人_清理修复验证.glb', 'PixalPostprocess_round5-clean-after-remesh-robot-20261019.glb', '机器人：清理修复验证', '历史神经输出使用新清理顺序导出；不是新NAF完整生成。'),
    ('04_头盔_清理修复验证.glb', 'PixalPostprocess_round5-clean-after-remesh-helmet-20261019.glb', '头盔：清理修复验证', '历史神经输出使用新清理顺序导出；仍有2个UV退化三角。'),
]
def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

manifest = []
for filename, original, title, scope in items:
    source, destination = SOURCE / original, TARGET / filename
    shutil.copy2(source, destination)
    sha = digest(source)
    assert sha == digest(destination)
    manifest.append(dict(file=filename, title=title, scope=scope, source=str(source), bytes=destination.stat().st_size, sha256=sha))
(TARGET / '模型清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
(TARGET / '查看说明.txt').write_text('''这四个文件都是实际生成的GLB，贴图已嵌入模型，可直接导入Blender等支持GLB的软件。
01：人物最终结果；02：人物旧实现对照；03/04：机器人、头盔的新清理顺序验证。
01与02使用同一输入及种子。03/04使用历史神经输出，不代表新NAF完整生成。
尚存问题：人物肤色/眼睛偏差、细发和颈肩瑕疵；头盔仍有2个UV退化三角。
这些文件未手绘补纹理，也没有用新生成参考图替代神经纹理。

本机交互查看：
http://127.0.0.1:18765/tmp/pixal-model-gallery-20261019.html
该页面需要本机预览服务运行；GLB本身不依赖该服务。
截图中的Pixal3D_Repaired_Texture_512_00005_.glb是较早的文件，不是本轮最终结果。
''', encoding='utf-8-sig')
archive = TARGET.with_suffix('.zip')
assert not archive.exists()
with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as z:
    for path in TARGET.iterdir():
        z.write(path, arcname=TARGET.name + '/' + path.name)
print(json.dumps(dict(folder=str(TARGET), archive=str(archive), archive_bytes=archive.stat().st_size, models=manifest), ensure_ascii=False, indent=2))
