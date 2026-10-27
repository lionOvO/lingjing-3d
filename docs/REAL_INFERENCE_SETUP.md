# 真实图片转 GLB 部署

仓库中的 `services/trellis` 已经不再生成球形演示模型。它会把上传图片下载到 GPU 容器，执行 `TRELLIS_INFERENCE_COMMAND`，再把 runner 写出的模型交给后端保存到 MinIO。

## 必须准备

1. 一台可用 NVIDIA GPU 主机，并安装 NVIDIA Driver、NVIDIA Container Toolkit 和支持 GPU 的 Docker Compose。
2. TRELLIS-2 或 TripoSR 的官方推理代码及模型权重。权重放在宿主机 `TRELLIS_MODEL_DIR` 指向的目录中。
3. 一个可执行 runner。runner 必须接收输入图片路径，并在 `{output_file}` 路径写出非空的 GLB 文件。
4. 一个真实的 Qwen2-VL 兼容服务（本地部署或云端 OpenAI-compatible API），用于从图片提取角色特征。

## `.env` 示例

```dotenv
TRELLIS_MODEL_DIR=/opt/models/trellis
TRELLIS2_MODEL_PATH=/models/trellis2
TRELLIS_INFERENCE_COMMAND=python /models/run_trellis.py --input {input_image} --output {output_file} --model /models/trellis2
TRELLIS_INFERENCE_TIMEOUT=1800
# Qwen2-VL adapter: use the complete /v1/chat/completions URL.
QWEN2VL_PROVIDER_URL=https://your-provider.example.com/v1/chat/completions
QWEN2VL_API_KEY=replace-with-provider-key
QWEN2VL_MODEL=qwen-vl-max
# Optional OpenAI-compatible embedding endpoint. Its model must support the
# requested dimensions (1024/768/512), otherwise retrieval is marked degraded.
EMBEDDING_URL=https://your-embedding.example.com/v1
EMBEDDING_API_KEY=replace-with-embedding-key
EMBEDDING_MODEL=text-embedding-3-large
```

命令模板支持 `{input_image}`、`{output_file}`、`{output_format}`、`{task_id}`、`{engine}`、`{mode}`、`{texture_resolution}`、`{mesh_density}` 和 `{job_id}` 占位符。不要把用户输入直接拼接进命令模板。

## 启动前检查

```powershell
docker run --rm --gpus all nvidia/cuda:12.1.1-base-ubuntu22.04 nvidia-smi
docker compose build trellis api worker
docker compose up -d
docker compose logs -f trellis worker
```

如果未设置 `TRELLIS_INFERENCE_COMMAND`，生成任务会失败并显示明确错误；系统不会再把假模型标记为完成。`qwen2vl` 服务现在是可配置适配器：未设置 `QWEN2VL_PROVIDER_URL` 时 `/analyze` 返回 503，不会返回伪造的 `unknown` 结果。视觉服务应返回角色特征 JSON；工作流会执行规范化、低置信度标记和多集合检索重排。未设置 `EMBEDDING_URL` 时会使用明确标记为降级的确定性向量，仅适合联调，不适合生产语义检索。
