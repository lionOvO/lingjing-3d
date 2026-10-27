# 灵境造物 · 图片转 3D 创作平台

将参考图片经过交互预处理、本地 3D 推理、质量检查，保存为可在网页预览的 GLB 资产。前端使用 Vue 3、TypeScript、Three.js，后端使用 FastAPI、SQLAlchemy、MySQL，异步任务由 Celery / Redis 执行，LangGraph 编排处理节点，文件存储使用 MinIO。

![首页预览](docs/images/project-blog-20261027/home-desktop.png)

## 核心流程

上传参考图 → 裁剪、抠图与人工修补 → 确认并提交生成任务 → LangGraph 调用 ComfyUI / Pixal3D → Trimesh 网格检查与有限重试 → MinIO 保存产物 → Three.js 预览、调整展示与资产管理。

当前网页接入的是本地高质量生成路线。视觉分析和生成前语义检索是可选路径；质量失败后的知识检索会提供建议，当前重试参数按规则调整。Trimesh 负责网格处理与检查，图片转 3D 推理由 Pixal3D 完成。完整实现与边界见 [项目技术文档](docs/灵境造物_项目技术文档.md)。

## 文档导航

- [项目技术文档与业务流程](docs/灵境造物_项目技术文档.md)
- [引擎来源、权重下载与安装版本](docs/引擎下载与复现.md)
- [功能业务分析与 Mermaid 图](功能业务分析/README.md)
- [公开仓库的敏感文件保护](SECURITY.md)
- [第三方来源说明](THIRD_PARTY_NOTICES.md)

## 本地启动

本仓库是可公开的源码快照，不附带用户数据库、上传图片、生成历史、模型权重或 Python 环境。以下步骤用于本地开发；不是经过公网安全加固的生产部署方案。

1. 安装 Docker Desktop、Python，并按 [引擎说明](docs/引擎下载与复现.md) 准备 ComfyUI、节点、依赖和模型。
2. 在项目根目录执行下面命令。路径替换成自己的实际目录；非便携版可使用 `--comfy-python` 指定解释器。

```powershell
python scripts/configure_local.py --comfy-root "E:\ComfyUI\ComfyUI"
git config core.hooksPath .githooks
```

配置工具在 `.env` 不存在时生成随机数据库、对象存储和 JWT 密钥，并创建本机 `local-stack.json`；不会打印密钥、覆盖已有 `.env` 或关联作者机器的数据容器。DeepSeek、短信和向量接口密钥按需填写，只保存在 `.env`。

3. 双击 `一键启动.bat`，或运行：

```powershell
python scripts/start_local.py --build
```

首次构建与下载依赖需要联网，并可能耗时较长。首次完整推理需要 GPU、对应 CUDA 扩展及足够的系统内存/页面文件。当前代码保留历史 TripoSR 适配，不表示快速/平衡生成已接入网页。已核对的是作者本机版本和源码快照，本公开副本尚未在全新机器完整跑通 GPU 推理。

## 提交前检查

```powershell
python scripts/check_publication.py
```

配置 Git 钩子后，提交时自动检查暂存内容。检查器会阻止常见密钥、敏感文件类型和大文件进入提交，但不能替代人工检查。首页 `frontend/public/showcase/` 内的小型展示模型为应用静态资源，保留在仓库；推理权重和业务生成产物单独存放。
