# M1-F7 API 用户创建

| 项目 | 内容 |
| --- | --- |
| 所属模块 | 01 · 用户系统 |
| 清单来源 | 当前源码补充 |
| 优先级 | 源码补充 |
| 当前状态 | **仅后端 API** |
| 分析基准 | 工作区根目录 frontend / backend / services 当前源码；2026-10-18 |

## 功能范围与实现边界

需求：提供密码哈希直写的用户创建接口，无前端入口。

当前边界：提供密码哈希直写的用户创建接口，无前端入口。

图中无“设计”标记的是当前源码行为；标有“[设计]”及虚线/设计分支的部分是尚未落地的需求补充。

关键差异与限制：本接口不会调用 hash_password，不是公开注册表单的执行路径；路由没有显式身份保护，应按当前能力如实区分。

## 参与方、调用与数据

U=用户、F=前端页面与 Pinia、A=后端 FastAPI、D=关系数据库。

输入、输出与存储由下列两张图中的箭头逐步标注。`A` 表示 FastAPI；`W` 表示 Worker/Agent；两者属于不同进程。图中 `F → F`、`V → V` 表示前端内部处理，`W → W` 表示后端内部处理。

涉及的现有接口或复用边界（设计路径另见图中标记）：

- `POST /api/v1/users`

## 业务流程图

节点直接标注前端、后端、服务或存储角色；箭头上的缩写表示调用方与接收方，具体请求、返回数据写在目标节点内。蓝色为前端、绿色为后端、紫色为存储；设计补充使用橙色虚线。

```mermaid
flowchart TB
    n1(["功能开始"])
    n2["前端页面与 Pinia：集成调用方准备 user payload"]
    n3["说明：F 在此表示集成客户端，当前页面未调用本接口"]
    n4["后端 FastAPI：POST /api/v1/users：username、email、password_hash、avatar_url"]
    n5["后端 FastAPI：UserCreate 校验结构"]
    n6{"数据库可提交且唯一约束通过？"}
    n7["满足：数据库可提交且唯一约束通过"]
    n8["另一分支：不满足或处理失败"]
    n9["关系数据库：直接保存调用方给定 password_hash"]
    n10["后端 FastAPI：返回用户"]
    n11["前端页面与 Pinia：201 UserRead"]
    n12["用户：返回新用户 ID"]
    n13["前端页面与 Pinia：409 唯一约束冲突；422 参数错误；503 数据库异常"]
    n14["用户：展示错误并结束本次操作；允许用户修正后重试"]
    n15(["本次操作结束或等待后续任务"])
  n1 -->|"U → F"| n2
  n2 -->|"边界说明"| n3
  n3 -->|"F → A"| n4
  n4 -->|"A → A"| n5
  n5 -->|"判断"| n6
  n6 -->|"是"| n7
  n6 -->|"不满足或处理失败"| n8
  n7 -->|"A → D"| n9
  n9 -->|"D → A"| n10
  n10 -->|"A → F"| n11
  n11 -->|"F → U"| n12
  n8 -->|"A → F"| n13
  n13 -->|"F → U"| n14
  n12 -->|"结果 / 状态"| n15
  n14 -->|"结果 / 状态"| n15
  classDef user fill:#f8fafc,stroke:#64748b
  class n1,n12,n14,n15 user
  classDef frontend fill:#eff6ff,stroke:#2563eb
  class n2,n3,n7,n8,n11,n13 frontend
  classDef backend fill:#ecfdf5,stroke:#059669
  class n4,n5,n6,n10 backend
  classDef storage fill:#f5f3ff,stroke:#7c3aed
  class n9 storage
```

## 时序图

```mermaid
sequenceDiagram
  autonumber
  actor U as 用户
  participant F as 前端页面与 Pinia
  participant A as 后端 FastAPI
  participant D as 关系数据库
  U->>F: 集成调用方准备 user payload
  Note over F: F 在此表示集成客户端，当前页面未调用本接口
  F->>A: POST /api/v1/users：username、email、password_hash、avatar_url
  A->>A: UserCreate 校验结构
  alt 数据库可提交且唯一约束通过
    A->>D: 直接保存调用方给定 password_hash
    D-->>A: 返回用户
    A-->>F: 201 UserRead
    F->>U: 返回新用户 ID
  else 不满足或处理失败
    A-->>F: 409 唯一约束冲突；422 参数错误；503 数据库异常
    F->>U: 展示错误并结束本次操作；允许用户修正后重试
  end
```

## 异常与结束条件

图内列出了该功能的关键校验、失败或降级路径。实际经过 FastAPI 的请求还可能返回 422 参数错误、409 数据冲突、503 数据库暂不可用或 500 未预期错误；前端经 Axios 的请求会显示统一错误，401 会清理登录状态。浏览器直连文件、WebSocket 和纯本地操作不经过同一个 Axios 错误拦截器。

需求验收目标（来自 PRD，不代表本次已验证达标）：按本文所列实际行为核对；本次未运行业务性能验收。

## 源码依据

- [backend/app/routers.py · create_user](D:/灵境造物/backend/app/routers.py:72)
- [backend/app/schemas.py · class UserCreate](D:/灵境造物/backend/app/schemas.py:95)

需求来源：[docs/AI_3D数字人开发工具链_PRD文档.md](D:/灵境造物/docs/AI_3D数字人开发工具链_PRD文档.md:1)。业务请求的通用边界参考 [frontend/src/services/api.ts](D:/灵境造物/frontend/src/services/api.ts:1) 与 [backend/app/exceptions.py](D:/灵境造物/backend/app/exceptions.py:1)。

[返回总目录](../README.md) · [返回本模块](README.md)
