# 第三方来源

项目包含自主实现的应用代码，也集成第三方推理、网格和前端组件。模型和运行环境通过上游渠道单独获取；本仓库不重新分发推理权重。

| 内容 | 上游来源 | 本仓库处理 |
| --- | --- | --- |
| ComfyUI | https://github.com/Comfy-Org/ComfyUI | 提供版本，不内嵌整个引擎 |
| Trellis2 / Pixal3D GGUF 节点 | https://github.com/Aero-Ex/ComfyUI-Trellis2-GGUF | 保存版本与本地修改补丁；原 MIT 许可见 `engine/UPSTREAM_LICENSE.txt` |
| Pixal3D | https://github.com/TencentARC/Pixal3D | 图片转 3D 上游项目 |
| Pixal3D GGUF 权重 | https://huggingface.co/Aero-Ex/Pixal3D-GGUF | 量化发布者的下载链接 |
| DINOv3 | https://huggingface.co/facebook/dinov3-vitl16-pretrain-lvd1689m | 遵守其单独许可及访问条件 |
| MoGe | https://github.com/microsoft/MoGe | 通过作者发布的权重仓库下载 |
| NAF | https://github.com/valeoai/NAF | 代码及检查点均由上游下载 |
| TripoSR | https://github.com/VAST-AI-Research/TripoSR | 保留历史适配源码及其 `models/triposr/LICENSE` |
| rembg | https://github.com/danielgatis/rembg | 抠图依赖及模型下载来源 |

各组件、权重、示例素材和依赖的许可分别适用；上表不是对所有内容统一授权。量化发布者和原始模型作者不是同一主体，模型使用或商业用途应查看相应模型卡和上游许可。
