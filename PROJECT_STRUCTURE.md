# 项目结构与代码阅读顺序

对应当前公开源码快照。本地高质量路线由 ComfyUI / Pixal3D 实际执行，历史适配器是否开放以服务能力接口为准。

```text
.
├── frontend/                      Vue 3 + TypeScript + Three.js
│   └── src/
│       ├── views/                 首页、生成、任务、资产、对比与修复页面
│       ├── components/            图片预处理器与 3D 检视器等组件
│       ├── services/              API 请求及业务数据访问
│       └── stores/                登录、任务与图片草稿状态
├── backend/
│   ├── app/
│   │   ├── main.py                API 路由、异常处理与启动初始化
│   │   ├── models.py              用户、项目、任务、资产、检查与版本等实体
│   │   ├── schemas.py             Pydantic 请求/响应协议
│   │   ├── database.py            异步数据库引擎与会话
│   │   ├── security.py            密码哈希、JWT 与当前用户
│   │   ├── routers.py             项目、上传、任务与状态订阅等接口
│   │   ├── account.py             账号设置与权限
│   │   ├── sms_auth.py            验证码认证相关流程
│   │   ├── studio.py              资产标签、回收站、参数预设
│   │   ├── worker.py              Celery、阶段持久化与产物归档
│   │   ├── agents.py              LangGraph 节点、条件路由与质量重试
│   │   ├── generation.py          推理请求/结果协议及异步客户端
│   │   ├── storage.py             MinIO 文件与对象管理
│   │   ├── reference_tools.py     实际输入及构图的像素诊断
│   │   ├── deepseek_vision.py     可选预处理视觉观察与双图复核
│   │   ├── failure_diagnosis.py   错误分类、知识检索与状态探测
│   │   ├── creation_tools.py      检查、修复版本与人工复核接口
│   │   ├── mesh_tools.py          GLB 结构检查与静态网格修复
│   │   ├── milvus_schema.py       向量集合定义
│   │   ├── knowledge_seed.py      示例知识导入
│   │   └── knowledge_data/        版本化故障与建模规则
│   └── tests/                     隔离数据库及外部服务的 pytest 回归
├── services/
│   ├── trellis/                   图生 3D HTTP 适配与服务测试
│   │   └── workflow_6gb.json      当前公开的本地高质量工作流
│   └── qwen2vl/                   可选角色视觉分析适配
├── engine/                        来源、版本清单与公开差异补丁
├── models/triposr/                历史适配源码，不含大模型权重
├── scripts/                       本地配置、启停与发布检查
├── docs/                          技术文档、工程案例、复现与公开截图
├── 功能业务分析/                  分模块说明与 Mermaid 图
├── docker-compose.yml             应用与数据服务编排
├── docker-compose.local.yml       本地提供方与运行覆盖配置
├── .env.example                   环境变量占位模板
├── local-stack.example.json       运行器配置示例
├── SECURITY.md                    发布范围与敏感数据保护
└── THIRD_PARTY_NOTICES.md          第三方来源说明
```

## 推荐的后端阅读顺序

1. 从[任务接口](backend/app/routers.py)看上传、创建任务与状态订阅。
2. 在 [worker.py](backend/app/worker.py) 跟踪队列消费、状态回写与文件归档。
3. 在 [agents.py](backend/app/agents.py) 看状态字段、条件分支与质量重试。
4. 对照 [generation.py](backend/app/generation.py) 和[推理适配服务](services/trellis/app.py)，看业务参数如何进入引擎。
5. 看[故障诊断](backend/app/failure_diagnosis.py)如何区分历史错误、当前状态、建议与未知项。
6. 从[检查接口](backend/app/creation_tools.py)和[网格工具](backend/app/mesh_tools.py)看修复边界及版本保存。
7. 阅读 [backend/tests](backend/tests) 中对应的正常、失败、权限与降级测试。

运行步骤见 [README](README.md#7-本地运行) 和[引擎复现说明](docs/引擎下载与复现.md)。完整设计见[技术文档](docs/灵境造物_项目技术文档.md)，取舍见[工程案例](docs/ENGINEERING_CASE_STUDIES.md)。
