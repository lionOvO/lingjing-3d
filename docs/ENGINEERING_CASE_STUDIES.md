# 工程案例与代码导读

这份文档从 Python 后端与 AI 应用工程的角度，说明灵境造物怎样把图生 3D 工作流接入业务系统。每个案例给出问题、实现、取舍和测试入口，便于对照源码阅读。

范围为当前公开仓库。基础模型和训练方法来自上游；这里讨论的是接口、任务编排、推理集成、诊断及交付工程。

## 1. 耗时 GPU 推理怎样成为可追踪的业务任务

**问题**：图生 3D 执行时间长，普通 HTTP 请求不适合一直等待。用户刷新、服务重启或引擎失败后，页面仍然需要知道任务进行到哪里。

**实现**：

- FastAPI 创建业务任务并投递 Celery，数据库记录任务编号、队列编号、参数和执行状态。
- Worker 调用 LangGraph，使用节点前的状态回调和 `astream(..., stream_mode="values")` 回写阶段及诊断结果，避免长节点执行期间一直显示前一个阶段。
- 前端通过 WebSocket 读取状态变化；连接异常时回退到 HTTP 查询。最终错误与产物入口保存在业务记录中，不依赖浏览器页面存活。
- 生成队列使用延迟确认、Worker 丢失后重新投递和单任务预取；本地 GPU 消费配置为串行，减少多个大模型任务争抢资源。

**设计取舍**：Celery 负责消息与消费，LangGraph 负责单次任务内部的节点和分支。数据库中的业务记录用于页面查询，Celery result backend 不能代替业务状态库。

**边界**：延迟确认可能带来重复执行，尚无覆盖全链路的幂等协议、事务 outbox 或持久化图检查点。取消业务任务也不保证中止已提交给 ComfyUI 的 GPU 作业。当前百分比表示业务阶段，不是采样步级进度。

代码：[任务接口](../backend/app/routers.py)、[Worker](../backend/app/worker.py)。测试：[阶段与 Worker 配置](../backend/tests/test_agents.py)、[上传与队列](../backend/tests/test_upload_queue.py)。

## 2. 同步 Celery 与异步数据库的生命周期如何配合

**问题**：Celery 的同步入口通过 `asyncio.run()` 执行异步流程。如果全局连接池保留了上一次事件循环创建的 aiomysql 连接，后续任务可能跨循环复用连接。

**实现**：`worker_db_session()` 在当前任务内创建异步引擎和会话，使用 `NullPool`，退出时关闭会话并 `dispose()`。节点状态保存与最终归档共用当前任务的会话；异常路径先回滚，再记录失败。

**设计取舍**：长时间 GPU 任务中，建立数据库连接的开销相对较小。这里优先明确连接所属的事件循环，而不是在 Worker 中维持跨任务连接池。API 进程的会话生命周期与 Worker 分开管理。

**边界**：这是连接生命周期治理，不是业务事务与消息投递的原子性保证。后者需要另外设计。

代码：[worker.py](../backend/app/worker.py) 中的 `_worker_engine_options()`、`worker_db_session()`、`run_generation_task()`。测试：[test_agents.py](../backend/tests/test_agents.py) 中的 `test_worker_does_not_reuse_aiomysql_connections_across_event_loops`。

## 3. 页面上的参数怎样对应真实模型工作流

**问题**：选择了高质量、纹理尺寸或随机种子，并不代表推理节点实际用了这些参数。平台和引擎各自预处理图片，也可能造成重复抠图、裁剪或主体缩放。

**实现**：

1. 业务层使用 Pydantic 定义 `GenerationRequest` / `GenerationResult`，把任务模式、参数、元数据和产物协议集中起来。
2. 能力查询接口约束页面开放的模式、输出格式和可用参数，避免显示无法执行的组合。
3. HTTP 适配服务将参数写入 ComfyUI 工作流的对应节点，发起执行并解析输出；用户确认的预处理输入带标记传递，避免再次处理。
4. Worker 只读取配置产物目录内的文件，将模型归档到 MinIO，再返回受业务权限约束的内容接口。

**设计取舍**：业务层围绕任务和工件编程，具体节点编号、运行器连接和工作流格式留在适配层。增加引擎时首先明确协议与能力，不直接把引擎所有选项暴露给用户。

**边界**：纹理尺寸与几何采样分辨率不同；6GB 环境验证过的配置不代表任意参数都能运行。暂态 HTTP 失败的有限重试，也不等于 GPU 作业可以安全重复提交。协议测试使用替身，不能证明真实模型的外观保真度。

代码：[generation.py](../backend/app/generation.py)、[适配服务](../services/trellis/app.py)、[本地工作流](../services/trellis/workflow_6gb.json)。测试：[生成协议](../backend/tests/test_generation.py)、[能力约束](../backend/tests/test_generation_capabilities.py)、[适配服务测试](../services/trellis/test_app.py)、[输入准备测试](../services/trellis/test_prepare_image.py)。

## 4. 为什么把参考图确认放在 GPU 任务之前

**问题**：复杂背景会被模型一起重建，自动分割又可能误删头发、衣袖或建筑底座。盲目采用“抠图成功”的返回值，会把输入损伤传到后续生成。

**实现**：图片预处理提供原图与结果预览、裁剪与留白、可选分割、原像素恢复/擦除，以及画笔大小、形状、撤销和缩放。视觉服务可以辅助识别主体、建议分割路线及复核遗漏，但最终使用的图片由用户确认。

后端检查图片格式和实际输入风险；外部视觉调用缺少配置、超时或返回不完整时，明确返回不可用或未通过，不伪装成成功。确认后的输入进入生成链路，默认不为每次生成强制执行角色文字分析。

**设计取舍**：先保证主体完整，再减少背景干扰。保留原像素的操作优先于重绘；“移除背景”和“补出不存在的部位”是两种能力，不能混为一谈。

**边界**：像素阈值与视觉复核都可能漏判；预处理不能可靠补全遮挡，也不能保证人物身份还原。

代码：[ImagePreparation.vue](../frontend/src/components/ImagePreparation.vue)、[reference_tools.py](../backend/app/reference_tools.py)、[deepseek_vision.py](../backend/app/deepseek_vision.py)。测试：[预处理](../backend/tests/test_input_preparation.py)、[构图](../backend/tests/test_foreground_crop.py)、[视觉接口](../backend/tests/test_deepseek_vision.py)、[像素诊断](../backend/tests/test_reference_tools.py)。

## 5. RAG 与规则应放在哪里

**问题**：直接从参考图生成 3D 时，额外的文字识别与风格检索未必改善几何；而失败任务需要能够解释“依据是什么、建议是否适用”。

**实现**：

- LangGraph 保留分析、归一化、检索和重排节点；默认已确认图片的直接生成路线可以跳过分析及生成前检索。
- 结构质检使用确定性检查；失败后才查询修复参考知识，保留来源及降级信息。检索建议与实际执行的修复区分展示。
- 故障诊断单独使用版本化 JSON 知识，按错误类型、引擎、提供方和适用条件筛选，并结合只读运行状态探测生成报告。
- 报告区分“失败时记录的错误”和“现在探测到的状态”。例如连接拒绝只说明服务不可达，不能直接推断发生了 GPU 显存耗尽。

**设计取舍**：能够明确分类的故障优先用规则检索，给出可核对的证据。向量搜索用于需要语义匹配的参考知识，而不是给每个任务固定增加一次大模型调用。

**边界**：当前 SHA 确定性降级向量不具备语义表达能力，不能按向量距离宣称高置信度；正式语义检索需要统一嵌入模型、重建知识索引并建立相关性评测。主流程由代码定义，公开快照没有自主规划修复工具的通用 Agent。

代码：[agents.py](../backend/app/agents.py)、[failure_diagnosis.py](../backend/app/failure_diagnosis.py)、[故障知识](../backend/app/knowledge_data/generation_failures.json)、[Milvus 集合](../backend/app/milvus_schema.py)。测试：[工作流与降级](../backend/tests/test_agents.py)、[诊断与资源隔离](../backend/tests/test_failure_diagnosis.py)。

## 6. 如何避免“修复”损坏原模型

**问题**：有 UV 的模型可能为贴图接缝拆分顶点，直接按未焊接网格统计会误报破洞；简单封孔也可能损伤贴图或丢失动画。

**实现**：

- 加载前校验 GLB 头、大小、外部资源引用和面数，拒绝无效坐标；自动修复限制在静态网格，拒绝骨骼、动画和形态键。
- 仅在诊断副本中合并同位置顶点，检查边界和非流形边；不为了统计而重写原模型 UV 接缝。
- 对支持的模型清理重复面、退化面和未引用顶点，修正绕序；基础封孔遇到 UV 时跳过并说明原因。
- 修复后再次检查并保存独立 `ModelRevision`，保留原模型、前后报告及警告。接口按当前用户核对任务归属。

**设计取舍**：结构清理采用可解释、保守的操作；原文件可回退，修复结果可对照。结构通过比例与外观相似度分别说明。

**边界**：这套工具没有实现通用大洞补全、缺件重建或稳定纹理重绘。基础封孔只适合有限的小孔，不能替代生成式几何修复。

代码：[mesh_tools.py](../backend/app/mesh_tools.py)、[creation_tools.py](../backend/app/creation_tools.py)、[ModelRevision](../backend/app/models.py)。测试：[test_creation_tools.py](../backend/tests/test_creation_tools.py) 覆盖 UV/材质/场景保留、小孔、非法文件、动画拒绝、版本持久化及其他用户隔离。

## 7. 验证记录与如何阅读测试

2026-11-06，在本地 Python 环境对本公开源码副本执行：

```powershell
python -m pytest backend/tests -q
```

结果：**122 passed、14 skipped**，耗时约 184 秒；有两条第三方依赖弃用警告。14 个跳过项未计入通过。本次结果不包含真实 GPU 推理验收，也不证明全新机器能够复现同样外观。

测试入口按目标组织：

| 目标 | 测试入口 |
| --- | --- |
| 认证、账号与持久化 | [账号](../backend/tests/test_account.py)、[数据库](../backend/tests/test_database.py)、[验证码](../backend/tests/test_sms_auth.py) |
| 工作流、引擎协议与能力 | [agents](../backend/tests/test_agents.py)、[generation](../backend/tests/test_generation.py)、[capabilities](../backend/tests/test_generation_capabilities.py) |
| 输入完整性与外部视觉失败 | [input preparation](../backend/tests/test_input_preparation.py)、[DeepSeek vision](../backend/tests/test_deepseek_vision.py) |
| 检查、版本和数据隔离 | [creation tools](../backend/tests/test_creation_tools.py)、[studio](../backend/tests/test_studio.py) |
| 失败原因与建议适用性 | [failure diagnosis](../backend/tests/test_failure_diagnosis.py) |

进一步的工程方向包括任务幂等与投递一致性、GPU 作业取消和资源租约、持久化工作流恢复、真实进度采集，以及带标准输入和评价指标的生成质量回归。它们是后续设计方向，不作为当前已完成能力。

返回 [README](../README.md) · [完整技术文档](灵境造物_项目技术文档.md) · [引擎复现条件](引擎下载与复现.md)
