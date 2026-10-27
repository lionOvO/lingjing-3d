"""Write the handoff only after integrated generation, rendering and cleanup pass."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP, DOCS = ROOT / 'tmp', ROOT / 'docs'
report = json.loads((TMP / 'pixal-round5-final-validation-20261019.json').read_text(encoding='utf-8'))
assert report['visual_assessment']['integrated_actually_viewed']
assert report['cleanup']['process_stopped'] and report['cleanup']['diagnostic_restored_and_disabled']
metric, geometry, installed = report['metrics'], report['geometry'], report['installed']
detail = DOCS / 'Pixal3D_第五轮NAF条件一致性修复_2026-10-19.md'
handoff = DOCS / 'Pixal3D_上下文交接_2026-10-19.md'
history = DOCS / 'Pixal3D_第五轮过程断点历史_20261019.md'
assert not history.exists(), 'Preserve the already finalized record'
history.write_text('# 第五轮过程断点历史（不代表当前状态）\n\n'
                   '以下原文保留试验、撤回及中间断点；当前状态以同目录最新交接文档为准。历史PID不能用于直接操作进程。\n\n'
                   + detail.read_text(encoding='utf-8') + '\n\n---\n\n' + handoff.read_text(encoding='utf-8'), encoding='utf-8')
rows = []
for trial in report['cleanup_trials']:
    a = trial['geometry']
    case = trial['trial']['case'] if 'case' in trial['trial'] else Path(a['model']).stem.split('-')[-2]
    rows.append(f"| {case} | {a['vertices']} | {a['faces']} | {a['zero_area_faces']} | {a['same_winding_duplicate_faces']} | {a['zero_uv_area_faces']} |")
source_lines = '\n'.join(f"- `{key}`：`{installed[key]['path']}`；SHA256 `{installed[key]['sha256']}`；原文件备份 `{installed[key]['backup']}`。" for key in ('naf', 'factory', 'nodes'))
summary = f'''这轮修复已写入共享 Pixal3D 生成链路，并完成最终组合代码的实际完整人物生成。修改并非只作用于某一个GLB，也没有用新参考图替换神经纹理。

最终任务 `{metric['prompt_id']}` 成功，用时 {metric['execution_seconds']} 秒，导出 {metric['vertices']} 顶点 / {metric['faces']} 面。运行使用 RTX 3060 Laptop 6GB、原图/原种子109020838、Q4_K_M、1024_cascade、16/16/20步、目标500001面、1024 SmartUV；未升级依赖或更换权重。导出几何零面积面 {geometry['zero_area_faces']}、同向重复面 {geometry['same_winding_duplicate_faces']}、UV零面积面 {geometry['zero_uv_area_faces']}。保留薄片可能需要的反向重合面，未盲目删除。

真实多视角PBR及基础颜色渲染已检查：大块头发缺失明显恢复，脸部黄白条纹减轻。肤色和眼睛仍与输入有差异，细小头发/颈部/肩部瑕疵仍在，不能称整体纹理完全修好。只对人物做了新NAF的完整生成；机器人、头盔是既有真实神经输出的后处理复验，不能冒充三类新生成。
'''
changes = '''1. NAF低显存路径原来逐块重新编码，GroupNorm统计和RoPE坐标随裁剪变化。现在先做整图编码和全局坐标RoPE，再复用原生邻域注意力分块计算；整图query仅在单次调用中暂存CPU，保持原精度与默认K4，保留bilinear降级路径。
2. GGUF工厂原来扫描已加载模块，实际取到了另一个插件的旧提取器，绕过修复。现在明确构建本包提取器，不再依赖插件加载顺序。
3. 原始双网格碎片在重建前被删除，头发本可重连的部分也丢失。remesh分支改为重建后按原0.005阈值清理；非remesh分支维持原清理路径。降低阈值到0.0001的试验仍有大洞，已拒绝；没有全局关闭碎片清理。
'''
proof = '''真实512阶段三类DINO特征，相对整图NAF的条件误差从旧K4约5.6%～6.1%降至3～4e-7；这是条件一致性，不是画质改善百分比。真实1024阶段K4与K8差约2.5～2.7e-7，额外保留1536MiB的同驻压力测试通过。bilinear降级、重新加载状态、批次2及出界投影回归通过。

本轮共有三次新人物完整运行：第一次发现工厂旁路，NN与历史逐位一致；第二次证明本地NAF生效，但原清理使头发回退，曾立即撤回；最终第三次使用组合修复。最终神经快照与第二次逐字节一致、与旧对照不同，隔离了清理顺序的作用；最后一次不是复用Comfy生成缓存。

三类保存神经输出的清理重放，实际执行AST与最终生产节点一致。下面均非三类新NAF完整生成。头盔2个UV退化三角与历史数量相同，仍待解决。

| 输入 | 顶点 | 面 | 几何零面积 | 同向重复 | UV零面积 |
|---|---:|---:|---:|---:|---:|
''' + '\n'.join(rows) + '\n'
evidence = f'''- 最终模型：`{metric['model']}`。
- 最终NN：`{TMP / 'pixal-round5-final-chain-person-prediction-20261019.npz'}`。
- 最终证据汇总与SHA：`{TMP / 'pixal-round5-final-validation-20261019.json'}`。
- 最终生成清单/工作流/历史：`{TMP / 'pixal-full-round5-final-chain-person-20261019-manifest.json'}`，相邻API与history文件。
- [最终完整流程实际渲染对照](Pixal3D_第五轮最终完整流程对照_20261019.png)、[正面对照](Pixal3D_第五轮最终正面对照_20261019.png)、[三类后处理检查](Pixal3D_第五轮清理顺序三类验证_20261019.png)。基础颜色检查采用双面显示，PBR采用原材质面设置，不能把两种显示差异当算法改进。
- 本地交互预览：<http://127.0.0.1:18765/tmp/inspect-pixal-round5-20261019.html>。仅在只读预览服务运行时可用。
- 三份生产补丁：`docs/Pixal3D_第五轮NAF条件修复_20261019.patch`、`docs/Pixal3D_第五轮条件工厂修复_20261019.patch`、`docs/Pixal3D_第五轮清理顺序修复_20261019.patch`。
'''
cleanup = '''最终自建ComfyUI推理已在队列为空且核对进程身份后停止，临时快照节点恢复原内容并禁用。没有后台推理任务或自动续跑。下一次正常启动ComfyUI会使用当前三处生产修复。18765只读预览不运行推理；以后操作进程必须重新核对身份，不能使用历史PID。
'''
next_work = '''后续优先定位神经PBR肤色和眼睛偏差，区分输入条件、材质通道及重采样影响；用固定输入、种子和PBR/基础颜色多视角对照判断。需要新增机器人/头盔的新NAF完整生成，才能扩大跨输入结论；还需处理头盔2个UV退化面和细发/颈肩破面。Q8、更多随机种子及任意模型上的普遍画质提升均未验证。

不要重新执行本轮已完成的三次人物全流程，也不要把局部特征精度、保存NN后处理或软件渲染通过，写成模型画质已经全部修复。硬件判断仍是已测关键算子兼容，没有证据把主要偏色归因为3060不支持；不承诺换显卡即可解决。
'''
detail.write_text('# Pixal3D 第五轮：共享链路修复结果（2026-10-19）\n\n' + summary + '\n## 三处实际修改\n\n' + changes + '\n## 验证与适用范围\n\n' + proof + '\n## 当前生产源码及回退备份\n\n' + source_lines + '\n\n若需回退，先停推理并核对当前SHA，再使用这三份对应备份作为整体恢复；不要混搭工厂与NAF版本。SmartUV、CuMesh重建源码保持本轮硬件核对时SHA，完整记录在证据汇总中。\n\n## 证据\n\n' + evidence + '\n## 运行状态与剩余问题\n\n' + cleanup + '\n' + next_work + '\n历史失败、撤回和中间断点已原文保存在[过程历史](Pixal3D_第五轮过程断点历史_20261019.md)，这些状态已被本页最终结果替代。\n', encoding='utf-8')
handoff.write_text('# Pixal3D 上下文交接（2026-10-19，最终断点）\n\n' + summary + '\n## 已完成\n\n' + changes + '\n' + cleanup + '\n## 当前生产源码\n\n' + source_lines + '\n\n不要按历史撤回状态重新覆盖当前文件。三份原始备份仍在。\n\n## 复核入口\n\n' + evidence + '\n## 下一轮处理范围\n\n' + next_work + '\n[本轮详细记录](Pixal3D_第五轮NAF条件一致性修复_2026-10-19.md)；[早前硬件判断](Pixal3D_硬件适配与可修复性判断_2026-10-19.md)。\n', encoding='utf-8')
print(detail)
print(handoff)
