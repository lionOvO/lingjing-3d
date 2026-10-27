# 本机 Trellis2 接入

项目已经支持通过 `services/trellis` 调用本机 ComfyUI 的 Trellis2 工作流。模型权重继续由 E 盘的 ComfyUI 管理，项目不会复制模型文件。

## 1. 让 ComfyUI 可被 Docker 访问

在 ComfyUI 启动参数中增加：

```text
--listen 0.0.0.0 --port 8188
```

Windows Docker Desktop 使用 `host.docker.internal:8188` 访问宿主机。只监听 `127.0.0.1` 时，Docker 容器无法连接。

## 2. 启用本地 provider

在项目根目录 `.env` 设置：

```dotenv
TRELLIS_PROVIDER=local_comfyui
TRELLIS_COMFY_ENABLED=true
TRELLIS_COMFY_URL=http://host.docker.internal:8188
TRELLIS_COMFY_WORKFLOW=/app/workflow_6gb.json
TRELLIS_COMFY_TIMEOUT=2400
```

然后重建适配器：

```powershell
docker compose build trellis api worker
docker compose up -d trellis api worker
```

## 3. 请求流程

高质量任务会按以下流程执行：

1. 项目上传图片到 ComfyUI `/upload/image`。
2. 提交 `workflow_6gb.json` 到 `/prompt`。
3. 轮询 `/history/{prompt_id}`，等待节点完成。
4. 从 `/view` 下载 GLB 到共享 artifact 目录。
5. 后端 worker 将 GLB 写入 MinIO，并通过项目模型接口提供下载/预览。

默认工作流使用已经在 RTX 3060 6GB 上验证过的 `512` 形状生成、`1024` 双轮廓后处理、`2048` 贴图和约 50 万面目标。

## 4. 当前限制

- 本地 ComfyUI provider 当前只输出 GLB。
- 一次只处理一个生成任务，和本机 GPU 的实际能力一致。
- `TRELLIS_COMFY_ENABLED=false` 时，项目行为不变；可继续使用命令模板或 Hugging Face Space provider。
- 不要在敏感图片上启用 Hugging Face Space；本机 provider 不会把图片发送到第三方服务。

## 5. Docker 代理排查

容器运行时和 Docker Desktop 拉取镜像使用的是两套网络路径。可以分别检查：

```powershell
docker info | Select-String "HTTP Proxy|HTTPS Proxy"
Test-NetConnection 127.0.0.1 -Port 7897
docker pull pytorch/pytorch:2.1.2-cuda12.1-cudnn8-devel
```

如果 `docker pull` 的错误仍指向旧的局域网地址（例如 `192.168.x.x:7897`），请在代理软件中开启“允许局域网连接”，或在 Docker Desktop 的 Resources / Proxies 中改为当前代理地址，然后重启 Docker Desktop。项目容器内访问本机 ComfyUI 不依赖该外网代理。

### Windows 页面文件（错误 1455）

Trellis2 解码器加载时如果出现 `页面文件太小，无法完成操作 (os error 1455)`，请把页面文件配置在内部磁盘 `D:`，不要配置在外置 `E:` 盘。以管理员身份运行：

```powershell
powershell -ExecutionPolicy Bypass -File D:\月樱工坊\scripts\configure_windows_pagefile.ps1
```

脚本会把 `D:\pagefile.sys` 设置为初始 24576 MB、最大 32768 MB。配置后必须重启 Windows。ComfyUI 启动脚本还包含 `--high-ram --cache-none --disable-mmap`，用于降低模型加载时的提交内存峰值。
