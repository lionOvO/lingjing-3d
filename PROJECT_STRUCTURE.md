# AI 3D 数字人开发工具链

```text
.
├── docker-compose.yml
├── .env.example
├── frontend/                 # Vue 3 + TypeScript + Three.js + Nginx
├── backend/                  # FastAPI 网关、LangGraph 工作流、Celery Worker
│   └── app/
│       ├── models.py          # SQLAlchemy 2.0 async ORM: 6 个 Schema 表
│       ├── schemas.py         # Pydantic v2 请求/响应模型
│       ├── database.py         # async engine、session、schema 初始化
│       ├── routers.py          # 用户、项目、任务、特征、元数据、RAG CRUD
│       ├── agents.py           # MasterAgent LangGraph、分析/RAG/生成/质检节点
│       ├── generation.py       # TRELLIS-2/TripoSR Pydantic 协议、异步客户端和重试
│       ├── storage.py          # MinIO 图片上传、URL 拉取、大小/类型校验
│       ├── worker.py           # Celery 异步任务与 GenerationTask 结果回写
│       ├── exceptions.py       # 统一 404/409/422/数据库错误处理
│       ├── logging_config.py   # stdout 日志配置
│       ├── milvus_schema.py     # 三个 Milvus RAG 集合定义与显式初始化
│       └── security.py          # PBKDF2 密码哈希、JWT access/refresh、当前用户依赖
├── backend/tests/              # pytest + SQLite async 单元测试
│   ├── test_database.py         # ORM、认证和 API 持久化测试
│   ├── test_agents.py           # Agent 节点、质量重试、服务降级测试
│   ├── test_generation.py       # 3D 引擎协议、引擎选择、HTTP 重试测试
│   └── test_upload_queue.py     # MinIO 上传和上传接口测试
└── services/
    ├── trellis/              # TRELLIS-2 / TripoSR HTTP 适配层
    └── qwen2vl/              # Qwen2-VL 视觉分析 HTTP 适配层
```

## 启动

```bash
cp .env.example .env
docker compose up -d --build
```

访问 `http://localhost:8080`；API 健康检查可通过 `docker compose exec api curl -fsS http://localhost:8000/healthz` 检查。
模型适配服务当前为可替换的轻量占位实现，生产环境可在对应目录替换为实际 GPU 推理镜像与权重挂载。

认证接口：`POST /api/v1/auth/register`、`POST /api/v1/auth/login`、`POST /api/v1/auth/refresh`、`GET /api/v1/auth/me`。
文件上传接口：`POST /api/v1/uploads`（PNG/JPG/WEBP，最大 20MB）、`POST /api/v1/uploads/url`；任务创建支持 multipart 图片或 `source_image_url`，成功后通过 Redis/Celery `generation` 队列异步执行。
生产部署前请将 `.env` 中的 `JWT_SECRET`、数据库密码和 MinIO 密钥替换为随机强密钥。

数据库模块单元测试（需 Python 3.11+）：

```bash
cd backend
pytest -q
```

若构建时需要代理，请在 `.env` 中设置 `HTTP_PROXY` 与 `HTTPS_PROXY`。Docker Desktop 构建容器建议使用 `http://host.docker.internal:7897`；Docker Desktop 自身的镜像拉取代理仍使用宿主机 IPv4 地址。Compose 会仅将它们作为构建参数传入，不会保存到生成镜像中。
