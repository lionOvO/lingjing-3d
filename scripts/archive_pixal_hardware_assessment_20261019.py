"""Archive bounded hardware assessment, preserving earlier experiment records."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TMP = ROOT / 'tmp'

def read(name):
    return json.loads((TMP / name).read_text(encoding='utf-8-sig'))

linear = read('pixal-hardware-linear-20261019.json')
decoder = read('pixal-hardware-decoder-20261019.json')
sources = read('pixal-hardware-source-check-20261019.json')
naf = read('pixal-naf-full-tiled-round2-metrics.json')
assert linear['completed'] and decoder['completed']
assert all(row['matches_archive'] for row in sources)
ops = [row for row in linear['rows'] if 'quant' in row]
comparisons = [row for row in decoder['rows'] if row['kind'] == 'decoder_comparison']
assert len(ops) == 24 and len(comparisons) == 2
naf_source = Path(r'E:\ComfyUI-Easy-Install\ComfyUI-Easy-Install\ComfyUI\custom_nodes\ComfyUI-Trellis2-GGUF\trellis2_gguf\trainers\flow_matching\mixins\image_conditioned_proj.py')
assert all(row['source_sha256'] == hashlib.sha256(naf_source.read_bytes()).hexdigest() for row in naf)
metrics = dict(sampled_layers=len(ops), cpu_gpu_weights_all_exact=all(r['weight']['exact'] for r in ops),
               cpu_gpu_float32_relative_rmse_max=max(r['cpu_gpu_float32']['relative_rmse'] for r in ops),
               offload_roundtrips_all_exact=all(r['offload_roundtrip']['exact'] for r in ops),
               bf16_relative_rmse_range=[min(r['bf16_vs_float32']['relative_rmse'] for r in ops), max(r['bf16_vs_float32']['relative_rmse'] for r in ops)],
               decoder_comparisons=comparisons,
               historical_naf_k4_relative_rmse=[r['relative_rmse'] for r in naf if r['tile_factor'] == 4])
evidence = ['pixal-hardware-linear-20261019.json', 'pixal-hardware-decoder-20261019.json',
            'pixal-hardware-source-check-20261019.json', 'pixal-hardware-linear-20261019.log',
            'pixal-hardware-decoder-20261019.log', 'pixal-hardware-decoder-guided-20261019.log',
            'pixal-naf-full-tiled-round2-metrics.json', 'pixal-round3-final-validation-20261011.json',
            'pixal-round4-final-validation-20261012.json']
record = dict(date='2026-10-19', metrics=metrics, production_changed=False,
              conclusion='No sampled evidence of basic GPU numerical incompatibility; low-memory approximations can change results; root cause of remaining visual defects unresolved.',
              limitations=['No second machine or full precision end-to-end control',
                           'No fresh Q4/Q8 end-to-end quality comparison',
                           'Synthetic decoder latents and all-child subdivision masks are not saved real production latents',
                           'NAF evidence is historical 512-stage features, not a 1024 texture quality score'],
              evidence={name:hashlib.sha256((TMP / name).read_bytes()).hexdigest() for name in evidence})
target = TMP / 'pixal-hardware-assessment-20261019.json'
assert not target.exists(), target
target.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding='utf-8')
table = '\n'.join(f"| {r['extent']} | {r['same_coordinates']} | {r['low_vs_normal']['exact']} | {r['low_vs_normal']['relative_rmse']:.8g} |" for r in comparisons)
document = f'''# Pixal3D 硬件适配与可修复性判断（2026-10-19）

本轮受用户要求完成判断：现有肤色/眼部偏差与头发缺口，是否主要由电脑不适配引起，以及是否值得继续修复。只做有限诊断，没有修改生产源码、模型权重或默认参数，没有重跑三例完整生成。

## 判断

1. 在已测范围内，RTX 3060 Laptop 6GB 能正确执行当前 Pixal3D 的关键运算。没有发现 CPU/GPU 反量化差异、卸载损坏或明显计算异常，不能把残余画质问题判为显卡不适配。
2. 6GB 显存确实限制运行方式。现用 Q4 和 NAF K4 近似；NAF 整图与分块不是严格等价。这是资源约束的间接影响，不等于硬件损坏或不支持模型。
3. 肤色偏差在绕过图集后的神经颜色参考中仍存在，不能继续只修 UV。分块条件、量化、输入条件/采样、解码与模型本身仍未完成因果区分；头发缺口来源也未最终定位。
4. 存在软件层改善的可能，但本轮没有发现足以保证修好主要视觉缺陷的新代码错误。不能给成功百分比，不能保证换显卡或切 Q8 就能解决。

## 本轮真实运行

- 环境：{linear['gpu']}，计算能力 {linear['capability']}，Torch {linear['torch']} / CUDA {linear['cuda']}；本次 nvidia-smi 驱动 616.64。
- SS、shape512、shape1024、texture 四个真实权重组件，Q4_K_M/Q8_0 各取入口、第一层 self-attention QKV、出口三层，共24层。CPU/GPU float32反量化权重全部精确相同；CPU/GPU线性输出最大相对RMSE {metrics['cpu_gpu_float32_relative_rmse_max']:.8g}；24次权重CUDA/CPU往返输出全部精确相同。
- 同样输入的 bfloat16 与 float32 单层相对RMSE范围 {metrics['bf16_relative_rmse_range'][0]:.6g}～{metrics['bf16_relative_rmse_range'][1]:.6g}。这些是局部数值误差，不是皮肤颜色误差，也不能线性外推整段扩散结果。
- 本地 Q4/Q8 文件的相同层、相同输入输出存在差异。不同权重格式的局部差异不能当作Q8画质必然更好或偏色已归因的证明。
- 使用实际948MB纹理解码权重、FP16 torso、FlexGEMM稀疏卷积，分别比较普通/低显存模式。使用固定随机合成潜变量和全部子节点引导，分别输出32768及73728体素；后者跨越默认65536分块边界。比较结果如下。

| 潜变量空间范围 | 输出坐标相同 | 输出值精确相同 | 相对RMSE |
| --- | --- | --- | --- |
{table}

解码器测试只覆盖两种合成输入，不代表484万体素的真实人物全部解码都等价。首版测试漏传必需的guide_subs，触发Cache not found；已按实际接口传入引导，失败日志单独保留，不能将测试输入错误称为生产bug。

## 已有证据复核

- 四个生产文件及回滚备份SHA全部与第四轮归档一致。NAF源码SHA也与旧实测报告一致。
- 10月11～12日三类真实Q4完整生成连续成功，是已有证据，本轮没有重复生成或冒充新的端到端结果。
- 历史512阶段三图真实DINO/NAF对照：K4相对整图投影特征RMSE为 {', '.join(f'{v:.2%}' for v in metrics['historical_naf_k4_relative_rmse'])}。这是特征差异，不是模型画质下降百分比；没有证据证明它就是肤色或头发问题的主因，也没有把512结果当作1024纹理对照。
- 历史正确Q8固定网格纹理生成也有头发杂色、眼周色差和后续白斑记录，但与当前完整Q4链路的几何、种子/步数不同，不能作为严格排除量化影响的A/B。
- 启动时Comfy quant_ops给出cu130优化算子提示。源码实际操作是禁用comfy-kitchen CUDA优化后端；本次原生GGUF与FlexGEMM测试继续运行通过。因此该提示本身不能证明显卡不支持，也不能以此声称升级Torch就能修画质。未升级软件。

## 结论边界与后续止损条件

本轮完成的是适配性评估，尚未完成残余视觉缺陷的最终根因归属。没有第二台机器，也没有原精度、不分块路径的完整同输入/同种子对照。因此不能排除未覆盖算子或低显存近似的影响；也不能宣称模型自身一定有问题。

现阶段不据此建议换电脑。若继续，只值得进行一组预先固定输入、种子、几何/潜变量、相机、采样步数的画质对照，每次只改变量化或NAF分块一项，并在神经RGB与几何阶段检查结果。需要的原精度/整图路径若本机无法容纳，应明确记为资源边界；本轮没有其他机器可用于补齐，不能假装验证过。若未出现可重复改善或可定位缺陷，应停止这一路线，不能继续靠UV、调暗或无边界参数尝试消耗时间。

证据汇总：[pixal-hardware-assessment-20261019.json](/D:/灵境造物/tmp/pixal-hardware-assessment-20261019.json)。脚本scripts/diagnose_pixal_hardware_20261019.py；原始运算、解码、源码校验及失败日志均保留于tmp，历史第三/四轮归档未覆盖。
'''
doc = ROOT / 'docs/Pixal3D_硬件适配与可修复性判断_2026-10-19.md'
assert not doc.exists(), doc
doc.write_text(document, encoding='utf-8')
print(json.dumps(metrics, ensure_ascii=False, indent=2))
print(doc)
