# AI 3D 数字人开发工具链 —— 产品原型高保真页面描述清单

> **文档版本**：v2.0  
> **生成日期**：2026-09-01  
> **文档类型**：高保真原型设计规范（High-Fidelity Prototype Specification）  
> **适用范围**：UI/UX 设计、前端开发、视觉设计、产品评审  
> **关联文档**：《AI 3D 数字人开发工具链_PRD文档.md》、《AI_3D数字人开发工具链_产品原型线框图.md》

> **v2 视觉与实现对齐说明（2026-09-01）**：本版本将全站统一为「Moonlit Sakura / 月樱幻境」唯美浪漫动漫风。下文旧版规格中出现的蓝紫 SaaS 色值、纯白实色卡片和“会员/额度/第三方登录”等描述，均以本节及“实现边界”说明为准；涉及接口的交互必须按现有 FastAPI 路由实现，不得虚构后端能力。

### v2.0 视觉基调（覆盖全页面）

- **参考图转译**：沿用参考图的蓝紫天空、粉色樱花、城市灯火、居中半透明表单和白色描边控件；将其转译为可复用的 CSS token 和 Vue 组件状态，不直接依赖截图中的文字或第三方站点元素。
- **氛围**：夜樱、星尘、远山云雾与城市灯火的动漫插画作为环境层；内容层保持高对比和清晰的表单可读性。
- **背景**：默认使用 `#101A35` → `#172A52` → `#4B3B78` 的夜空渐变，页面内容区可叠加 `radial-gradient` 粉紫光晕；禁止大面积纯白背景。
- **卡片**：统一玻璃拟态：`background: rgba(255,248,252,0.10)`、`backdrop-filter: blur(18px)`、`border: 1px solid rgba(255,255,255,0.28)`、`box-shadow: 0 16px 48px rgba(16,26,53,.28), 0 0 24px rgba(233,169,197,.16)`。浅色内容卡只用于可读性要求高的表格，并保留樱花色边框。
- **品牌色**：夜樱蓝 `#172A52`、暮光紫 `#4B3B78`、樱花粉 `#E9A9C5`、云雾紫 `#A9A4D6`、星光白 `#FFF8FC`、深墨蓝 `#101A35`。主按钮使用樱花粉→云雾紫渐变，焦点环使用 `rgba(233,169,197,.42)`。
- **装饰**：每页最多 3 组低透明度月相、樱花瓣、星尘粒子；粒子仅做环境动画，不遮挡输入、表格和 3D 画布。图片不可用时使用 CSS 渐变占位，不依赖远程素材。
- **字体**：标题 `Noto Serif SC, Source Han Serif SC, serif`；正文 `Noto Sans SC, PingFang SC, Microsoft YaHei, sans-serif`；数值/状态 `Inter, JetBrains Mono, monospace`。
- **可访问性**：正文与背景对比度至少 4.5:1；所有图标按钮提供 `aria-label`；动画遵循 `prefers-reduced-motion`，减少粒子与 3D 自动旋转。

### v2.1 前端功能—后端接口映射（开发必读）

| 页面行为 | 方法与接口 | 前端契约 / 状态 |
|---|---|---|
| 注册、登录、刷新、当前用户 | `POST /api/v1/auth/register`、`POST /api/v1/auth/login`、`POST /api/v1/auth/refresh`、`GET /api/v1/auth/me` | Pydantic 校验；401/409 显示玻璃 Toast；当前接口返回 JSON Token，前端按安全存储策略保存（若改用 httpOnly cookie 需由网关/BFF 写入） |
| 项目列表/详情/编辑/删除 | `GET/POST /api/v1/projects`、`GET/PATCH/PUT/DELETE /api/v1/projects/{id}` | 空态、分页、404、204 删除确认；列表参数 `offset/limit` |
| 图片文件上传 | `POST /api/v1/uploads` | multipart 字段 `image`；PNG/JPG/JPEG/WEBP，最大 20MB；成功返回 MinIO URL/object_name |
| 图片 URL 上传 | `POST /api/v1/uploads/url` | JSON `{url}`；422 显示“链接不可访问或格式不支持” |
| 创建生成任务 | `POST /api/v1/tasks` | multipart 必填 `image/project_id`，或 JSON `source_image_url`；`task_type=anime_character/object_model`；提交后进入 Celery `generation` 队列 |
| 任务进度、取消、重试 | `GET/PATCH /api/v1/tasks/{id}`、`DELETE /api/v1/tasks/{id}`、`POST /api/v1/tasks/{id}/retry`、WebSocket `/api/v1/tasks/{id}/progress` | 状态：`pending/analyzing/retrieving/generating/evaluating/postprocessing/completed/failed`；取消使用 DELETE，不设计“暂停”按钮 |
| Agent 工作流 | `GET /api/v1/agents/workflow/{task_id}`、`POST /api/v1/agents/invoke` | 展示 LangGraph 节点、重试次数、质量分、错误信息；调试操作需二次确认 |
| 3D 模型结果 | `GET /api/v1/models/{task_id}`、`/download`、`/preview`、`POST /convert` | 仅任务完成且有 `output_model_url` 时启用；下载/预览使用预签名 URL；转换提交 `output_format` |
| RAG 检索与反馈 | `GET /api/v1/rag/search`、`POST /api/v1/rag/feedback`、`GET /api/v1/rag/styles`、`GET /api/v1/rag/materials` | 语义搜索失败时显示可重试；反馈提交 `entry_id/quality_score` |

### v2.2 当前实现边界

- 后端未提供会员计费、额度扣减、手机号绑定、第三方登录、站内消息、独立批量/风格迁移服务；相关控件只能标注“前端预留/后端待补充”，不可显示为已上线能力。
- 批量生成页可先循环调用 `/api/v1/tasks`，并发由前端限流；模型对比页读取多个 task ID 的模型接口；风格迁移页仅展示设计预览，提交按钮置为“即将支持”。
- WebSocket 当前返回一次基础进度后关闭，界面需提供轮询 `GET /api/v1/tasks/{id}` 的降级方案，并标注“实时流待接入”。

### v2.3 参考组件的转译规则（不使用 ikun-ui）

参考图中的组件库信息只作为视觉灵感，不作为依赖清单。Vue3 前端统一使用自研 CSS token、语义化 HTML 和可访问的无头交互原语（`button/input/dialog/tabs/slider/tooltip/toast`），不安装或引用 `ikun-ui`、Magic UI、DaisyUI、Radix UI、Mantine 等第三方 UI 组件库。

**可以吸收的组件特征**：

- **流光边框**：用于登录卡、上传 Dropzone、任务状态卡和选中模型卡；静态边框必须先可见，流光动画只在 hover/focus/processing 状态出现。
- **文字渐变与字距**：Hero 标题和页面 H1 可使用 `background-clip:text` 的星光白→樱花粉渐变；正文、错误信息和数据值不使用渐变，保证可读性。
- **玻璃层次**：前景卡片采用 12–20px 模糊，背景插画保持 8–12px 模糊；同一视图最多叠加两层玻璃，避免内容发灰。
- **动效组件**：采用小范围的 `fade-up`、`border-sheen`、`sakura-drift` 和 Spinner；不使用持续抖动、自动弹窗或大面积粒子，`prefers-reduced-motion` 时全部降级为静态。
- **粗边框/高对比**：仅用于开发模式的 Agent 调试面板和危险操作确认框，边框可加粗至 2px，但颜色仍使用夜樱色，不能破坏主站的浪漫基调。

**组件实现契约**：每个组件必须提供 default/hover/focus/active/disabled/loading/error/empty 状态、键盘操作和 `aria-*` 属性；动画不改变布局尺寸，不遮挡上传进度、任务日志或 3D 画布。

**推荐 CSS 变量**：

```css
:root {
  --moon-night: #101A35;
  --sakura-blue: #172A52;
  --twilight-violet: #4B3B78;
  --sakura-pink: #E9A9C5;
  --mist-violet: #A9A4D6;
  --starlight: #FFF8FC;
  --glass-fill: rgba(255,248,252,.12);
  --glass-border: rgba(255,255,255,.30);
  --glow-pink: 0 0 24px rgba(233,169,197,.42);
}
```

---

## 目录

1. [设计系统总览](#一设计系统总览)
2. [全局布局与导航](#二全局布局与导航)
3. [首页/仪表盘 (P1)](#三首页仪表盘-p1)
4. [登录页 (P2)](#四登录页-p2)
5. [注册页 (P3)](#五注册页-p3)
6. [动漫角色上传页 (P4)](#六动漫角色上传页-p4)
7. [物品建模上传页 (P5)](#七物品建模上传页-p5)
8. [任务详情页 (P6)](#八任务详情页-p6)
9. [3D 预览页 (P7)](#九3d-预览页-p7)
10. [项目列表页 (P8)](#十项目列表页-p8)
11. [项目详情页 (P9)](#十一项目详情页-p9)
12. [RAG 知识库页 (P10)](#十二rag-知识库页-p10)
13. [个人中心页 (P11)](#十三个人中心页-p11)
14. [批量生成页 (P13)](#十四批量生成页-p13)
15. [模型对比页 (P12)](#十五模型对比页-p12)
16. [风格迁移页 (P14)](#十六风格迁移页-p14)
17. [帮助中心页 (P15)](#十七帮助中心页-p15)
18. [全局组件规范](#十八全局组件规范)

---

## 一、设计系统总览

### 1.1 设计理念

以「月樱幻境」为核心设计哲学：用动漫夜景的深蓝、暮紫承载复杂工具，用樱花粉与星光白引导操作。视觉要浪漫，但信息架构必须像工具一样克制；3D 预览区域沉浸在月夜渐变中，表单和数据面板使用半透明玻璃卡片，保证层级、对比度与可读性。

### 1.2 色彩体系

#### 主色板

| 色彩名称 | 色值 | 用途 |
|---------|------|------|
| **主品牌色** | `#C77AA5` | 主按钮、链接、进度条、选中状态 |
| **主品牌色 Hover** | `#A95C8A` | 主按钮悬停状态 |
| **主品牌色 Active** | `#82436F` | 主按钮按下状态 |
| **次品牌色** | `#8F7CC7` | 强调元素、标签、会员标识 |
| **成功色** | `#72C8A6` | 成功状态、通过检测、完成标记 |
| **警告色** | `#E6B86A` | 警告提示、低质量图片提醒 |
| **错误色** | `#EF4444` | 错误提示、失败状态、删除操作 |
| **信息色** | `#8EA8D8` | 信息提示、加载状态、工作流进行中 |

#### 中性色板

| 色彩名称 | 色值 | 用途 |
|---------|------|------|
| **页面背景** | `#F6F0F7` | 全局页面底色 |
| **卡片背景** | `rgba(255,248,252,.12)` | 玻璃内容卡片、面板底色 |
| **卡片背景 Hover** | `rgba(233,169,197,.16)` | 卡片悬停底色 |
| **边框色** | `#D8CFE0` | 分割线、输入框边框、卡片边框 |
| **边框色 Hover** | `#C6BDD0` | 输入框聚焦前悬停边框 |
| **主文字** | `#101A35` | 标题、重要正文 |
| **次文字** | `#4A4560` | 次要说明、描述文字 |
| **辅助文字** | `#A9A4D6` | 占位符、禁用状态、时间戳 |
| **3D 画布背景** | `#101A35` | 3D 预览器默认背景 |
| **3D 画布网格** | `#172A52` | 3D 画布参考网格线 |

#### 深色模式色板（3D 预览区域专用）

| 色彩名称 | 色值 | 用途 |
|---------|------|------|
| **深色面板背景** | `#172A52` | 3D 预览页侧边栏、底部控制栏 |
| **深色卡片背景** | `#2C3F68` | 深色模式下卡片底色 |
| **深色文字** | `#F1EAF3` | 深色背景上的主文字 |
| **深色次文字** | `#C6BDD0` | 深色背景上的次要文字 |
| **深色边框** | `#4A4560` | 深色模式分割线 |

### 1.3 字体规范

| 层级 | 字号 | 字重 | 行高 | 用途 |
|------|------|------|------|------|
| **Display** | 36px / 2.25rem | 700 (Bold) | 1.2 | 首页主标题 |
| **H1** | 30px / 1.875rem | 700 (Bold) | 1.3 | 页面大标题 |
| **H2** | 24px / 1.5rem | 600 (SemiBold) | 1.35 | 区块标题 |
| **H3** | 20px / 1.25rem | 600 (SemiBold) | 1.4 | 卡片标题、面板标题 |
| **H4** | 18px / 1.125rem | 600 (SemiBold) | 1.4 | 子标题、对话框标题 |
| **Body Large** | 16px / 1rem | 400 (Regular) | 1.6 | 重要正文、按钮文字 |
| **Body** | 14px / 0.875rem | 400 (Regular) | 1.6 | 常规正文、描述 |
| **Caption** | 12px / 0.75rem | 400 (Regular) | 1.5 | 辅助说明、标签、时间戳 |
| **Caption Bold** | 12px / 0.75rem | 600 (SemiBold) | 1.5 | 状态标签、角标 |

**字体栈**：标题 `"Noto Serif SC", "Source Han Serif SC", serif`；正文 `"Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif`；数据 `"Inter", "JetBrains Mono", monospace`

### 1.4 间距系统

基于 4px 的间距基准单位；玻璃卡片内边距优先使用 24px/32px，避免内容贴边：

| Token | 值 | 用途 |
|-------|-----|------|
| `space-1` | 4px | 图标与文字间距、紧凑内联间距 |
| `space-2` | 8px | 表单元素间距、小按钮内边距 |
| `space-3` | 12px | 卡片内部小间距、列表项间距 |
| `space-4` | 16px | 标准卡片内边距、组件间距 |
| `space-5` | 20px | 中等区块间距 |
| `space-6` | 24px | 大卡片内边距、区块标题与内容间距 |
| `space-8` | 32px | 页面区块间距、左右页面边距（桌面端） |
| `space-10` | 40px | 大区块分隔间距 |
| `space-12` | 48px | 页面顶部安全区、大模块间距 |

### 1.5 圆角规范

| Token | 值 | 用途 |
|-------|-----|------|
| `radius-sm` | 6px | 小按钮、标签、输入框 |
| `radius-md` | 8px | 标准按钮、下拉菜单项、列表项 |
| `radius-lg` | 12px | 卡片、对话框、模态框、面板 |
| `radius-xl` | 16px | 大卡片、上传区域、预览容器 |
| `radius-2xl` | 24px | 首页 Hero 区域、特殊展示卡片 |
| `radius-full` | 9999px | 圆形按钮、头像、状态点 |

### 1.6 阴影规范

| Token | 值 | 用途 |
|-------|-----|------|
| `shadow-sm` | `0 4px 14px rgba(16,26,53,.18)` | 下拉菜单、小浮层 |
| `shadow-md` | `0 12px 28px rgba(16,26,53,.24)` | 卡片、悬浮面板 |
| `shadow-lg` | `0 18px 42px rgba(16,26,53,.30), 0 0 18px rgba(233,169,197,.16)` | 对话框、模态框、抽屉 |
| `shadow-xl` | `0 24px 64px rgba(16,26,53,.38), 0 0 28px rgba(233,169,197,.20)` | 全屏预览浮层、重要弹窗 |
| `shadow-glow` | `0 0 24px rgba(233,169,197,.42)` | 樱花粉发光效果（选中态、高亮） |

### 1.7 动效规范

| 动效类型 | 时长 | 缓动函数 | 用途 |
|---------|------|---------|------|
| **微交互** | 150ms | `ease-out` | 按钮状态切换、图标变化 |
| **标准过渡** | 200ms | `cubic-bezier(0.4, 0, 0.2, 1)` | 颜色变化、透明度变化 |
| **布局变化** | 300ms | `cubic-bezier(0.4, 0, 0.2, 1)` | 展开收起、尺寸变化 |
| **页面切换** | 400ms | `cubic-bezier(0.4, 0, 0.2, 1)` | 路由切换、模态框出现 |
| **复杂动画** | 600ms | `cubic-bezier(0.34, 1.56, 0.64, 1)` | 弹窗出现（带弹性） |
| **3D 旋转惯性** | 持续 | `ease-out` (衰减) | 3D 模型旋转释放后的惯性缓动 |

### 1.8 栅格系统

- **桌面端（>=1280px）**：12 列栅格，列宽自适应，间距 24px，左右边距 32px
- **平板端（768px - 1279px）**：8 列栅格，间距 20px，左右边距 24px
- **移动端（< 768px）**：4 列栅格，间距 16px，左右边距 16px
- **最大内容宽度**：1440px，居中显示


---

## 二、全局布局与导航

### 2.1 顶部导航栏

#### 视觉描述

- **高度**：64px，固定定位（`position: fixed; top: 0`），`z-index: 50`
- **背景**：`rgba(16,26,53,.72)`，底部 1px 边框 `rgba(255,255,255,.22)`，`backdrop-filter: blur(18px)`（滚动后背景透明度 88%）
- **阴影**：滚动超过 10px 后显示 `shadow-sm`
- **内容区**：最大宽度 1440px，水平居中，左右内边距 32px

#### 组件细节

**Logo 区域**
- 左侧放置，包含：3D 立方体图标（24x24px，渐变色 `#C77AA5` 到 `#8F7CC7`）+ 文字「AI 3D 数字人」
- 文字样式：`font-size: 18px`，`font-weight: 700`，`color: #FFF8FC`
- 右侧小字「开发工具链」：`font-size: 12px`，`font-weight: 400`，`color: #A9A4D6`，与主标题基线对齐
- 点击区域：Logo + 文字整体可点击，hover 时文字颜色变为 `#C77AA5`，过渡 150ms

**主导航项**
- 项：首页、生成、项目、知识库、帮助
- 样式：`font-size: 14px`，`font-weight: 500`，`color: #4A4560`，水平间距 24px
- Hover 状态：`color: #C77AA5`，底部出现 2px 下划线（`border-bottom: 2px solid #C77AA5`），从中心向两侧展开，时长 200ms
- Active 状态：`color: #C77AA5`，下划线常驻
- 「生成」项右侧有下拉小箭头（ChevronDown 图标，16px，颜色继承文字）

**生成下拉菜单**
- 触发：Hover 延迟 100ms 后展开，移出延迟 200ms 后收起
- 容器：`background: #FFFFFF`，`border-radius: 12px`，`shadow-lg`，`border: 1px solid #D8CFE0`
- 位置：导航项下方 8px，左对齐
- 尺寸：宽度 200px，内边距 8px
- 菜单项：
  - 每项高度 40px，内边距 `0 16px`，`border-radius: 8px`
  - 左侧图标 20px（角色图标为 User 样式，物品图标为 Box 样式），右侧文字
  - 默认状态：`color: #4A4560`，`font-size: 14px`
  - Hover 状态：`background: #F1EAF3`，`color: #101A35`
  - 选中状态：`background: #F4EAF3`，`color: #C77AA5`，左侧图标颜色同步变化
- 分割线：「物品 3D 建模」上方 1px 分割线 `#D8CFE0`，上下间距 4px

**右侧功能区**
- **消息图标（🔔）**：24px 图标按钮，`color: #4A4560`，Hover 时 `color: #C77AA5`
  - 未读角标：右上角 8px 圆点，`background: #EF4444`，有 2px 白色描边，数字角标时 `font-size: 10px`，白色文字
- **用户头像**：40px 圆形，`border: 2px solid #D8CFE0`，Hover 时边框变为 `#C77AA5`
  - 未登录状态：显示「登录」文字按钮（`ghost` 样式）+ 「注册」主按钮
- **用户下拉菜单**：与生成下拉菜单样式一致，增加用户信息显示区
  - 顶部信息区：头像（32px）+ 用户名（`font-weight: 600`）+ 邮箱（`color: #A9A4D6`，`font-size: 12px`）
  - 额度显示：进度条形式，高度 4px，圆角全满，已用部分 `#C77AA5`，剩余部分 `#D8CFE0`
  - 底部退出项：文字红色 `#EF4444`，Hover 背景 `#FEF2F2`

### 2.2 底部栏

- **背景**：`#101A35`，文字颜色 `#A9A4D6`
- **高度**：自动，内边距 `48px 32px 24px`
- **内容区**：最大宽度 1440px，水平居中
- **布局**：四列网格（桌面端），列间距 48px
  - 第一列：Logo + 产品简介（`font-size: 14px`，`color: #C6BDD0`，最大宽度 280px）
  - 第二列：「产品」链接组（生成、项目、知识库、定价）
  - 第三列：「支持」链接组（帮助中心、API 文档、反馈建议、联系我们）
  - 第四列：「法律」链接组（服务条款、隐私政策、版权声明）
- **链接样式**：`font-size: 14px`，`color: #A9A4D6`，Hover 时 `color: #FFFFFF`，过渡 150ms
- **底部版权区**：顶部 1px 分割线 `#2C3F68`，上间距 32px，居中对齐
  - 文字：`font-size: 12px`，`color: #817A9B`

### 2.3 页面壳层统一规则

- 登录/注册采用参考图式全屏动漫夜景；业务页采用固定夜空渐变底图 + 轻量星尘层，内容区卡片统一玻璃材质。页面切换只改变标题、插画焦点与数据，不改变色彩、圆角和阴影语言。
- 深色背景上的正文使用 `#FFF8FC`，次要说明使用 `#D8CFE0`；浅色表格区域使用 `#F6F0F7`，所有状态色仍需配文字而不能只靠颜色区分。
- 3D 画布统一使用 `#101A35`/`#172A52` 月夜渐变，网格线 `rgba(169,164,214,.20)`，模型高亮 `#E9A9C5`；加载时显示月光环形 Spinner，失败时显示可重试操作。
- 页面级错误、空态、加载态均使用同一套玻璃 Toast/骨架屏；接口错误保留后端 `detail` 的用户可读摘要，并在控制台记录 request id。

---

## 三、首页/仪表盘 (P1)

### 3.1 页面概述

首页采用「Hero + 功能亮点 + 内容区」的三段式布局，顶部 Hero 使用夜樱星空插画和月相光晕，下方内容区使用低透明度玻璃卡片保证可读性。整体传达「温柔、有创造力、可立即上手」的产品气质。两个 CTA 分别路由到 P4/P5，并在未登录时先跳转登录。

**实现注记**：最近项目调用 `GET /api/v1/projects?offset=0&limit=4`；卡片状态来自 `ProjectStatus`。统计数字只展示可由列表/任务数据计算的数量，不展示虚构的“累计额度”。

### 3.2 Hero 区域

**组件应用**：Hero 使用 `MoonlitShell + GradientHeading`。标题入场只播放一次 `fade-up`，CTA 按钮 hover 出现 1px 流光边，不使用参考图中的视频播放器、弹幕或第三方站点标识。

- **背景**：线性渐变 `linear-gradient(135deg, #101A35 0%, #172A52 50%, #4B3B78 100%)`，高度 520px
- **装饰元素**：
  - 右上角：半透明 3D 网格球体（使用 Three.js 轻量渲染，自动缓慢旋转，线框模式，颜色 `#2C3F68`，透明度 0.3）
  - 左下角：弥散光斑（`radial-gradient(circle, rgba(233,169,197,.18) 0%, transparent 70%)`，直径 400px）
- **内容区**：垂直居中偏上，水平居中，最大宽度 800px，文字居中对齐

**主标题**
- 文字：「让图片秒变 3D，让创意即刻立体」
- 样式：`font-size: 42px`（移动端 28px），`font-weight: 700`，`color: #FFFFFF`，`text-shadow: 0 2px 10px rgba(0,0,0,0.3)`
- 动效：页面加载后从下方 20px 处淡入上移，时长 600ms，缓动 `ease-out`

**副标题**
- 文字：「AI 驱动的 3D 数字人一站式开发平台，零建模经验也能在 3 分钟内生成专业级模型」
- 样式：`font-size: 16px`，`font-weight: 400`，`color: #C6BDD0`，上间距 16px，最大宽度 600px，水平居中
- 动效：主标题动画结束后 200ms 开始，同样淡入上移

**CTA 按钮组**
- 上间距 32px，两个按钮水平排列，间距 16px，居中对齐
- **主按钮「上传动漫角色图片」**：
  - 尺寸：`height: 52px`，`padding: 0 32px`
  - 背景：`#C77AA5`，`border-radius: 12px`
  - 文字：`font-size: 16px`，`font-weight: 600`，`color: #FFFFFF`
  - 左侧图标：Upload 图标，20px，白色
  - Hover：`background: #A95C8A`，`transform: translateY(-2px)`，`shadow-lg`，过渡 200ms
  - Active：`transform: translateY(0)`，`background: #82436F`
- **次按钮「上传物品照片」**：
  - 尺寸同主按钮
  - 背景：透明，`border: 1px solid rgba(255,255,255,0.3)`，`border-radius: 12px`
  - 文字：`color: #FFFFFF`
  - Hover：`background: rgba(255,255,255,0.1)`，`border-color: rgba(255,255,255,0.5)`

**信任标识**
- 位于按钮组下方 24px
- 文字：「支持 GLB/OBJ/FBX/STL 输出格式 | MinIO 安全存储」
- 样式：`font-size: 13px`，`color: #A9A4D6`
- 左侧有 ShieldCheck 图标，16px

### 3.3 功能亮点区

- **背景**：`#F6F0F7`，上内边距 80px，下内边距 80px
- **标题**：「为什么选择我们」，`font-size: 30px`，`font-weight: 700`，`color: #101A35`，居中对齐
- **副标题**：「四大核心能力，让 3D 创作从未如此简单」，`font-size: 16px`，`color: #4A4560`，上间距 8px，居中对齐

**四列卡片网格**
- 上间距 48px，4 列等宽，间距 24px（平板 2 列，移动端 1 列）
- 每张卡片：
  - 背景：`#FFFFFF`，`border-radius: 16px`，`shadow-md`，`border: 1px solid #D8CFE0`
  - 内边距：32px
  - Hover：`transform: translateY(-4px)`，`shadow-lg`，边框变为 `#C6BDD0`，过渡 300ms
  - 动效：页面滚动进入视口时依次从下方淡入，每张间隔 100ms

**卡片内部结构**
- 顶部图标区：64px x 64px 圆角容器，`background: linear-gradient(135deg, #F4EAF3 0%, #E8DDF5 100%)`，图标居中 32px，颜色 `#C77AA5`
- 标题：上间距 20px，`font-size: 20px`，`font-weight: 600`，`color: #101A35`
- 描述：上间距 8px，`font-size: 14px`，`color: #4A4560`，行高 1.6

### 3.4 最近项目区

- **背景**：`#FFFFFF`，上内边距 64px，下内边距 64px
- **标题行**：左侧「最近项目」（`H2` 样式），右侧「查看全部 ->」链接（`font-size: 14px`，`color: #C77AA5`，Hover 时带下划线）
- **项目卡片网格**：4 列（平板 2 列，移动端 1 列），间距 24px，上间距 24px

**项目卡片**
- 背景：`#FFFFFF`，`border-radius: 16px`，`shadow-md`，`border: 1px solid #D8CFE0`
- 封面图区域：宽高比 16:10，`border-radius: 16px 16px 0 0`，`object-fit: cover`
  - 状态角标：右上角，小圆角标签
    - 已完成：`background: rgba(114,200,166,.12)`，`color: #72C8A6`，`border: 1px solid rgba(114,200,166,.24)`
    - 进行中：`background: rgba(142,168,216,.14)`，`color: #8EA8D8`
    - 失败：`background: rgba(239,68,68,0.1)`，`color: #EF4444`
- 信息区：内边距 20px
  - 项目名称：`font-size: 16px`，`font-weight: 600`，单行截断
  - 元信息行：上间距 8px，`font-size: 13px`，`color: #A9A4D6`
    - 格式：类型图标 + 类型文字 + 竖线分隔 + 生成数量
  - 标签行：上间距 12px，标签样式
    - `background: #F1EAF3`，`color: #4A4560`，`font-size: 12px`，`padding: 4px 10px`，`border-radius: 6px`
- Hover：封面图 `transform: scale(1.03)`，容器 `shadow-lg`，过渡 300ms

### 3.5 使用统计区

- **背景**：`#F6F0F7`，内边距 32px，`border-radius: 16px`，最大宽度与内容区一致
- **布局**：三列等分，居中对齐
- **统计项**：
  - 数字：`font-size: 32px`，`font-weight: 700`，`color: #C77AA5`
  - 标签：`font-size: 14px`，`color: #4A4560`，上间距 4px
  - 数字动效：页面进入视口时从 0 计数增长到目标值，时长 1.5s，缓动 `ease-out`

---

## 四、登录页 (P2)

### 4.1 页面布局

**接口与状态**：提交 `POST /api/v1/auth/login`（`username_or_email/password`）。按钮 loading 时锁定表单；401 显示“账号或密码错误”，网络错误提供重试；成功保存 access/refresh token 后请求 `GET /api/v1/auth/me` 并跳转首页。当前后端没有忘记密码和第三方登录接口，相关入口标注“即将支持”并保持禁用。

- **整体背景**：全屏动漫夜景插画/渐变（蓝紫天空、樱花树、城市灯火、星尘），覆盖层 `linear-gradient(135deg,rgba(16,26,53,.38),rgba(75,59,120,.28))`；表单居中（移动端保持单列）。
- **环境层**：背景图使用 `object-fit: cover`，叠加 2 层模糊云雾和少量漂浮花瓣；装饰不参与交互，加载失败时回退到 `#101A35 → #4B3B78` 渐变。
- **品牌标识**：左上角月相 Logo +「AI 3D 数字人」，白色文字；右下角仅显示版权/版本信息，不放未实现的会员入口。

### 4.2 登录表单卡片

- **位置**：视口正中，垂直水平均居中
- **容器**：宽度 520px（移动端 92%，最大 520px），`background: rgba(109,139,190,.30)`，`backdrop-filter: blur(20px)`，`border: 1px solid rgba(255,255,255,.48)`，`border-radius: 18px`，`shadow-xl`，内边距 42px
- **顶部 Logo**：居中，56px 高度，下方 8px 间距后接产品名「AI 3D 数字人」，`font-size: 22px`，`font-weight: 700`

**输入框规范**
- 高度 54px，`border-radius: 28px`，`border: 1px solid rgba(255,255,255,.82)`，背景 `rgba(255,255,255,.06)`
- 内边距：`0 22px`，`font-size: 16px`，文字和占位符均为 `#FFF8FC`
- Focus 状态：`border-color: #E9A9C5`，`box-shadow: 0 0 0 3px rgba(233,169,197,.42)`，过渡 200ms
- 错误状态：`border-color: #EF4444`，`box-shadow: 0 0 0 3px rgba(239,68,68,0.1)`，下方显示错误文字（`font-size: 13px`，`color: #EF4444`，上间距 6px）
- 密码框右侧：眼睛图标按钮（20px），`color: #A9A4D6`，Hover `#4A4560`

**会话选项行（仅保留前端状态）**
- 左侧：Checkbox 组件
  - 尺寸：18px x 18px，圆角 4px
  - 未选中：`border: 2px solid #C6BDD0`
  - 选中：`background: #C77AA5`，`border-color: #C77AA5`，内部白色对勾图标（Check，12px）
  - 右侧文字：`font-size: 14px`，`color: #4A4560`
- 右侧「忘记密码？」：后端未提供接口，显示为禁用文字「忘记密码（即将支持）」

**登录按钮**
- 全宽，`height: 54px`，`border-radius: 28px`
- 背景：`linear-gradient(90deg,#FFF8FC,#E9A9C5)`，文字 `#4B3B78`，`font-size: 16px`，`font-weight: 700`
- Hover：增加 `0 0 24px rgba(233,169,197,.45)`，保持文字对比度
- Loading 状态：文字替换为 Spinner 图标（20px，白色，旋转动画），背景变为 `#C6B4D9`，禁用点击

**分割线**
- 「或」文字居中，两侧 1px 线条 `#D8CFE0`，文字 `font-size: 13px`，`color: #A9A4D6`，上下间距 24px

**第三方登录占位**
- 后端未提供微信、QQ、Google 登录路由；保留一行低对比度占位按钮，显示「第三方登录（即将支持）」并设置 `disabled`，避免产生不可兑现的交互。

**底部注册引导**
- 居中对齐，`font-size: 14px`，`color: #4A4560`
- 「立即注册」：`color: #C77AA5`，`font-weight: 600`，Hover 下划线

---

## 五、注册页 (P3)

### 5.1 页面布局

与登录页完全一致：使用同一张动漫夜景背景、月相 Logo、居中玻璃卡片和白色描边圆角输入框；仅字段内容和提交接口不同，禁止另起一套色彩或布局。

### 5.2 注册表单卡片

**接口与状态**：提交 `POST /api/v1/auth/register`（`username/email/password/avatar_url?`）。邮箱、用户名、密码由 Pydantic v2 校验；409 显示“用户名或邮箱已注册”，422 显示字段级错误。验证码、手机号绑定和第三方登录为后端待补充能力，不渲染为可提交控件。

**表单字段顺序**：
1. 邮箱输入框（带邮箱图标前缀）
2. 密码输入框（带锁图标前缀 + 眼睛切换后缀）
3. 密码强度指示器（密码框下方实时显示）
4. 确认密码输入框
5. （预留）验证码行：后端未提供验证码接口，默认不渲染
6. 注册按钮
7. （预留）分割线 + 第三方登录
8. 底部登录引导

**密码强度指示器**
- 位置：密码输入框下方 8px
- 样式：4 段进度条，每段宽 25%，高度 4px，圆角 2px，间距 4px
- 强度规则：
  - 弱（仅满足长度）：第 1 段 `#EF4444`，其余 `#D8CFE0`，右侧文字「弱」红色
  - 中（长度 + 字母/数字）：第 1-2 段 `#E6B86A`，其余 `#D8CFE0`，文字「中」橙色
  - 强（长度 + 大小写 + 数字）：第 1-3 段 `#8EA8D8`，其余 `#D8CFE0`，文字「强」樱花粉
  - 极强（+ 特殊字符）：全部 4 段 `#72C8A6`，文字「极强」绿色
- 过渡：颜色变化 200ms

**验证码按钮（预留）**
- 不渲染可点击按钮；若产品开启该能力，必须先新增后端验证码路由并补充契约测试。

**服务条款同意**
- 注册按钮下方 16px，Checkbox + 文字
- 文字：「注册即表示同意《服务条款》和《隐私政策》」
- 链接文字：`color: #C77AA5`，Hover 下划线


---

## 六、动漫角色上传页 (P4)

### 6.1 页面布局

**上传契约**：拖拽/粘贴文件调用 `POST /api/v1/uploads`；URL 模式调用 `POST /api/v1/uploads/url`。只接受 PNG/JPG/JPEG/WEBP，单文件最大 20MB；上传成功展示 MinIO `object_name` 和可访问 URL，失败（422）保留原图并给出重试。用户点击“开始生成”时，将返回 URL 作为 `source_image_url` 与 `project_id/task_type/generation_params/output_format` 一起提交 `POST /api/v1/tasks`。

- **背景**：`#F6F0F7`
- **顶部面包屑**：页面内边距上方 24px，`font-size: 14px`，`color: #A9A4D6`，当前页 `#4A4560`
- **主内容区**：两栏布局（桌面端 5:7），间距 32px，最大宽度 1200px，水平居中
  - 左侧：图片预览区（固定宽度，最大 480px）
  - 右侧：参数配置面板（自适应）

### 6.2 上传区域（未上传状态）

使用 `Dropzone` 原语：拖拽进入时仅改变边框和内层光晕，离开后恢复；键盘 Enter/Space 触发文件选择，粘贴事件读取剪贴板图片。文件校验失败时在 Dropzone 内显示字段错误，不弹出无法关闭的模态框。

- **容器**：左侧栏全高，`background: #FFFFFF`，`border-radius: 16px`，`shadow-md`，`border: 2px dashed #C6BDD0`
- 拖拽悬停状态：`border-color: #C77AA5`，`background: #F4EAF3`，过渡 200ms
- 内部内容垂直水平居中：
  - 上传图标：48px，颜色 `#A9A4D6`，悬停时 `#C77AA5`
  - 主文字：「拖拽图片到此处」，`font-size: 18px`，`font-weight: 600`，`color: #4A4560`
  - 次文字：「或 [点击选择] 或 [Ctrl+V 粘贴] 或 [输入图片URL]」，`font-size: 14px`，`color: #A9A4D6`
    - 其中链接文字：`color: #C77AA5`，Hover 下划线
  - 底部提示：「支持 PNG / JPG / WEBP | 最大 20MB」，`font-size: 12px`，`color: #A9A4D6`，上间距 16px
- **示例图片区**：上传区域下方 24px，横向排列 4 张示例缩略图
  - 每张：80px x 80px，`border-radius: 8px`，`object-fit: cover`，`border: 2px solid transparent`
  - Hover：`border-color: #C77AA5`，`transform: scale(1.05)`，过渡 200ms
  - 下方标签：`font-size: 12px`，`color: #4A4560`，居中对齐

### 6.3 图片预览区（已上传状态）

- **图片容器**：宽高比自适应，最大高度 480px，`border-radius: 12px`，`overflow: hidden`
- 图片：`object-fit: contain`，`background: #F1EAF3`
- **图片信息浮层**：底部叠加，渐变遮罩 `linear-gradient(transparent, rgba(0,0,0,0.6))`，内边距 16px
  - 文字：`font-size: 13px`，`color: #FFFFFF`
  - 显示：分辨率、文件大小
- **质量检测结果**：图片下方 12px，行内标签
  - 通过：绿色对勾图标 + 「质量检测通过」，`color: #72C8A6`
  - 警告：黄色感叹号 + 具体警告文字，如「分辨率较低，可能影响生成质量」，`color: #E6B86A`
- **操作按钮行**：图片下方 16px，两个文字按钮
  - 「删除」：`color: #EF4444`，左侧 Trash 图标，Hover 时背景 `#FEF2F2`，圆角 6px
  - 「更换」：`color: #4A4560`，左侧 RefreshCw 图标，Hover 时背景 `#F1EAF3`

### 6.4 参数配置面板

- **容器**：`background: #FFFFFF`，`border-radius: 16px`，`shadow-md`，内边距 32px
- **面板标题**：「生成参数配置」，`H3` 样式，下间距 24px

**参数表单组**
- 每组间距 20px
- 标签：`font-size: 14px`，`font-weight: 500`，`color: #101A35`，下间距 8px
- 部分标签右侧有 Tooltip 图标（Info，14px，`color: #A9A4D6`），Hover 显示提示浮层

**单选按钮组（输出格式、纹理分辨率、拓扑类型、生成模式）**
- 横向排列，间距 8px
- 每个选项：
  - 未选中：`background: #F6F0F7`，`border: 1px solid #D8CFE0`，`border-radius: 8px`，`padding: 10px 16px`，`font-size: 14px`，`color: #4A4560`
  - Hover：`border-color: #C6BDD0`，`background: #F1EAF3`
  - 选中：`background: #F4EAF3`，`border: 2px solid #C77AA5`，`color: #C77AA5`，`font-weight: 600`
  - 过渡：150ms

**面数控制（低/中/高/自定义）**
- 与单选按钮组样式一致
- 选中「自定义」时，下方展开滑块输入器
  - 滑块：`accent-color: #C77AA5`，轨道高度 6px，圆角 3px
  - 数值输入框：宽度 100px，右侧显示「面」单位

**PBR 材质开关**
- 使用 Toggle Switch 组件
  - 轨道：宽 44px，高 24px，圆角全满
  - 关闭：`background: #C6BDD0`
  - 开启：`background: #C77AA5`，圆点移至右侧（带动画 200ms）
  - 圆点：20px，白色，阴影

**RAG 智能推荐面板**
- 位置：参数表单下方，与表单间距 24px
- 容器：`background: linear-gradient(135deg, #F4EAF3 0%, #F1E8F8 100%)`，`border: 1px solid #D7B6D6`，`border-radius: 12px`，内边距 20px
- 左侧装饰条：4px 宽，`background: #C77AA5`，`border-radius: 2px`，绝对定位左侧
- 头部：机器人图标（20px）+ 「RAG 智能推荐参数」，`font-size: 16px`，`font-weight: 600`，`color: #82436F`
- 检测到的风格标签：「日式萌系 (相似度 94%)」，`background: rgba(233,169,197,.18)`，`color: #C77AA5`，圆角标签
- 推荐参数列表：每项左侧圆点（6px，樱花粉）+ 参数名 + 推荐值
- 「应用推荐参数」按钮：全宽，`height: 44px`，`background: #C77AA5`，白色文字，`border-radius: 10px`，Hover `#A95C8A`

**底部操作区**
- 面板最底部，上边框 1px `#D8CFE0`，上内边距 20px
- 「开始生成 3D 模型」按钮：全宽，`height: 52px`，`background: linear-gradient(90deg, #C77AA5, #8F7CC7)`，`border-radius: 12px`，`font-size: 16px`，`font-weight: 600`，白色文字，右侧火箭图标
  - Hover：`transform: translateY(-2px)`，`shadow-lg`
  - 点击时：背景亮度增加，按钮轻微缩小 `scale(0.98)`
- 预计耗时文字：按钮下方 8px，居中，`font-size: 13px`，`color: #A9A4D6`
- 额度提示：右侧浮动，「任务将进入 generation 队列」，`font-size: 13px`，`color: #E6B86A`（不足时）或 `#72C8A6`（充足时）

---

## 七、物品建模上传页 (P5)

### 7.1 页面布局

整体布局与角色上传页完全一致，左侧图片区 + 右侧参数面板。

### 7.2 差异点

物品建模沿用 P4 的上传与校验，仅将创建任务时的 `task_type` 设置为 `object_model`；提交仍调用 `POST /api/v1/tasks`，不新增“材质扫描”或“商品 SKU”接口。

**参数差异**
- 「复杂度」替代「面数控制」：简单 / 标准 / 复杂，三档单选
- 增加「3D 打印优化」选项组：
  - 使用 Checkbox 组，每项左侧方形 Checkbox（与登录页样式一致）
  - 选项：水密性检查、悬空检测、壁厚检查
  - 默认全选，文字说明：「建议开启以确保模型适合 3D 打印」
  - 文字：`font-size: 13px`，`color: #A9A4D6`

**上传区域提示差异**
- 主文字改为「拖拽物品照片到此处」
- 示例图片更换为物品类（电子产品、家具、手办等）

---

## 八、任务详情页 (P6)

### 8.1 页面布局

**数据来源**：进入页面先请求 `GET /api/v1/tasks/{task_id}`；随后连接 WebSocket `/api/v1/tasks/{task_id}/progress`，因当前服务只推送一次并关闭，必须每 2 秒轮询任务详情作为降级。取消使用 `DELETE /api/v1/tasks/{task_id}`，失败任务重试使用 `POST /api/v1/tasks/{task_id}/retry`。

- **背景**：`#F6F0F7`
- **内容区**：单栏居中，最大宽度 900px
- 页面分为三大区块：任务信息头、工作流可视化区、结果/日志区

### 8.2 任务信息头

- **容器**：`background: #FFFFFF`，`border-radius: 16px`，`shadow-md`，内边距 24px
- **第一行**：任务编号（`font-size: 14px`，`color: #A9A4D6`，等宽字体）+ 提交时间
- **第二行**：左侧任务类型标签 + 右侧状态标签
  - 类型标签：`background: #F1EAF3`，`color: #4A4560`，`font-size: 13px`，圆角 6px，内边距 4px 10px
  - 状态标签：
    - 生成中：`background: #F4EAF3`，`color: #C77AA5`，左侧 Spinner 图标（16px，旋转动画）
    - 已完成：`background: #ECFDF5`，`color: #72C8A6`，左侧 CheckCircle 图标
    - 失败：`background: #FEF2F2`，`color: #EF4444`，左侧 XCircle 图标
    - 已取消：`background: #F1EAF3`，`color: #A9A4D6`

### 8.3 进度条区域（生成中状态）

- 位于任务头下方 16px
- 进度条轨道：高度 8px，`background: #D8CFE0`，`border-radius: 4px`
- 进度条填充：`background: linear-gradient(90deg, #C77AA5, #8F7CC7)`，`border-radius: 4px`
- 进度动画：宽度变化使用 `transition: width 0.5s ease-out`
- 百分比文字：进度条右侧，`font-size: 14px`，`font-weight: 600`，`color: #C77AA5`
- 预计剩余时间：百分比文字右侧，`font-size: 13px`，`color: #A9A4D6`

### 8.4 智能体工作流可视化

节点数据来自 `GET /api/v1/agents/workflow/{task_id}` 的 `state`：分析、RAG 检索、生成、质量评估、后处理。调试按钮调用 `POST /api/v1/agents/invoke`，仅在开发模式显示，并记录请求与错误日志。

使用 `WorkflowTimeline`：节点连接线的流光只在当前节点 processing 时运行；完成后冻结为静态樱花粉线，避免长时间动画造成干扰。

- **容器**：`background: #FFFFFF`，`border-radius: 16px`，`shadow-md`，内边距 24px，上间距 24px
- **标题**：「智能体工作流状态」，`H3` 样式

**工作流节点列表（纵向排列）**
- 每个节点：左侧时间线 + 右侧内容卡片
- 时间线：
  - 竖线：宽 2px，颜色根据状态变化
  - 节点圆点：直径 12px，圆角全满，居中于竖线
  - 已完成节点：`background: #72C8A6`，竖线 `#72C8A6`
  - 进行中节点：`background: #8EA8D8`，有脉冲动画（`box-shadow` 扩散动画，2s 无限循环），竖线 `#8EA8D8`
  - 等待节点：`background: #C6BDD0`，竖线 `#D8CFE0`
- 内容卡片：
  - 已完成：左侧绿色对勾图标（16px）+ 节点名称 + 耗时（右侧，`font-size: 13px`，`color: #A9A4D6`）
  - 展开详情：点击节点可展开，显示输入/输出摘要
    - 展开区域：`background: #F6F0F7`，`border-radius: 8px`，内边距 12px，上间距 8px
    - 内容：`font-size: 13px`，`color: #4A4560`，等宽字体显示 JSON 摘要
  - 进行中：樱花粉信息图标 + 节点名称 + 「进行中」标签 + 进度文字（如「85s / 预计 120s」）
  - 等待：灰色时钟图标 + 节点名称 + 「等待中」文字

**连接线动画**
- 已完成节点之间的连线：绿色，有流光动画（渐变遮罩移动）
- 进行中的节点：连线从灰色渐变为樱花粉（从上到下）

### 8.5 实时日志区（生成中）

- **容器**：`background: #101A35`，`border-radius: 16px`，内边距 20px，上间距 24px
- **标题行**：左侧「实时日志」（`font-size: 16px`，`font-weight: 600`，`color: #F1EAF3`）+ 右侧「暂停/继续」按钮
- **日志内容区**：
  - 字体：`font-size: 13px`，等宽字体栈，行高 1.8
  - 时间戳：`color: #817A9B`，格式 `[HH:MM:SS]`
  - 普通日志：`color: #C6BDD0`
  - 成功日志：`color: #72C8A6`
  - 警告日志：`color: #E6B86A`
  - 错误日志：`color: #EF4444`
  - 区域最大高度 300px，溢出时自动滚动，新日志从底部追加，平滑滚动动画
  - 左侧 4px 边框装饰：`background: #2C3F68`

### 8.6 生成结果区（已完成状态）

**接口边界**：下载模型使用 `/api/v1/models/{task_id}/download`；纹理包若存在，仅展示 `TaskRead.texture_urls` 中的 URL，不新增下载接口。重新生成调用 `/api/v1/tasks/{task_id}/retry`（仅 failed）或回到上传页创建新任务；收藏、截图、联系客服为前端本地/外部流程，当前不提交后端。

- **3D 预览缩略区**：高度 400px，`background: #101A35`，`border-radius: 16px`，居中显示模型
  - 左上角：质量评分标签
    - 评分 >= 4.5：`background: rgba(114,200,166,.24)`，`color: #72C8A6`，左侧星星图标
    - 评分 3.5-4.5：`background: rgba(245,158,11,0.2)`，`color: #E6B86A`
    - 评分 < 3.5：`background: rgba(239,68,68,0.2)`，`color: #EF4444`
  - 右上角：「全屏预览」按钮（ArrowsMaximize 图标，24px，白色半透明背景圆形按钮）
  - 底部中央：操作按钮行（悬浮于模型上方，半透明背景条）
    - 自动旋转开关、重置视角、截图
- **模型信息网格**：4 列等分，间距 16px，上间距 20px
  - 每项：标签（`font-size: 12px`，`color: #A9A4D6`）+ 数值（`font-size: 16px`，`font-weight: 600`，`color: #101A35`）
- **操作按钮行**：上间距 24px，水平排列，间距 12px
  - 「下载模型」：主按钮样式，左侧 Download 图标
  - 「下载纹理包」：次按钮样式（白色背景，樱花粉边框）
  - 「重新生成」：次按钮样式
  - 「调整参数再生成」：文字按钮，`color: #4A4560`
  - 「导出其他格式」：下拉按钮（右侧 ChevronDown）
  - 「收藏到项目」：星形图标按钮，未收藏时轮廓，已收藏时填充黄色 `#E6B86A`
  - 「删除」：文字按钮，`color: #EF4444`

### 8.7 失败状态区

- **错误卡片**：`background: #FEF2F2`，`border: 1px solid #FECACA`，`border-radius: 12px`，内边距 24px
- 顶部：红色 XCircle 图标（32px）+ 「生成失败」标题（`H3`，`color: #DC2626`）
- 错误信息：`font-size: 14px`，`color: #7F1D1D`，上间距 8px
- 重试信息：`font-size: 13px`，`color: #991B1B`，上间距 4px
- 操作按钮行：上间距 16px
  - 「重新生成」：红色背景按钮（`background: #EF4444`，白色文字）
  - 「调整参数重试」：红色边框按钮
  - 「联系客服」：文字链接
  - 「复制错误日志」：文字按钮，点击后显示「已复制」Tooltip
- **调试信息折叠区**：
  - 标题：「调试信息 ▼」，`font-size: 13px`，`color: #A9A4D6`，点击展开
  - 展开内容：`background: #F6F0F7`，等宽字体，技术参数详情


---

## 九、3D 预览页 (P7)

### 9.1 页面布局

仅当任务返回 `output_model_url` 时启用预览与下载；预览/下载分别调用 `/api/v1/models/{task_id}/preview` 与 `/download`，格式转换调用 `POST /api/v1/models/{task_id}/convert`。接口 404/409 时显示空画布和明确原因。

- **背景**：`#101A35`（全页面深色模式）
- **布局**：三栏沉浸式布局
  - 左侧：模型信息面板（固定宽 280px，可收起）
  - 中央：3D 画布（自适应占满剩余空间）
  - 右侧：纹理列表面板（固定宽 200px，可收起）
  - 底部：控制栏（固定高 200px，可收起）

### 9.2 左侧模型信息面板

- **背景**：`#172A52`，`border-right: 1px solid #2C3F68`
- **头部**：高度 56px，内边距 `0 20px`，左侧「模型信息」标题（`font-size: 16px`，`font-weight: 600`，`color: #F1EAF3`），右侧收起按钮（ChevronLeft，20px）
- **内容区**：内边距 20px，纵向滚动
- **信息项**：每项下间距 16px
  - 标签：`font-size: 12px`，`color: #A9A4D6`，上间距 4px
  - 数值：`font-size: 15px`，`font-weight: 600`，`color: #F1EAF3`
- **操作按钮**：
  - 「截图」：全宽，`height: 40px`，`background: #2C3F68`，`border-radius: 8px`，白色文字，Hover `#4A4560`
  - 「下载」：全宽，主按钮样式（樱花粉渐变背景）
- **收起状态**：左侧只显示 48px 宽度的图标栏，垂直排列功能图标，Hover 显示 Tooltip

### 9.3 中央 3D 画布

使用 `ModelViewport`：工具条采用玻璃浮层，选中模型轮廓使用月光白描边；自动旋转默认关闭，用户点击后才开启，符合 reduced-motion 设置。

- **背景**：`#101A35`
- **参考网格**：地面网格线，`color: #172A52`，线宽 1px，网格间距 1 单位
- **模型加载状态**：
  - 加载中：中央 Spinner（40px，樱花粉）+ 「模型加载中...」文字（`color: #A9A4D6`）
  - 加载完成：模型淡入（opacity 0->1，300ms）
- **悬浮控制条**（画布底部中央）：
  - 背景：`rgba(16,26,53,.72)`，`backdrop-filter: blur(16px)`，`border: 1px solid rgba(255,255,255,.24)`，`border-radius: 16px`，内边距 8px 16px
  - 按钮组：自动旋转（播放/暂停图标）、全屏、重置视角、截图
  - 每个按钮：32px 圆形，`background: transparent`，Hover `background: rgba(255,255,255,0.1)`，图标白色 18px

### 9.4 右侧纹理列表面板

- **背景**：`#172A52`，`border-left: 1px solid #2C3F68`
- **头部**：「纹理贴图」标题 + 收起按钮
- **列表项**：每项高度 60px，内边距 `0 16px`，Hover `background: #2C3F68`
  - 左侧：64px x 64px 缩略图，`border-radius: 6px`
  - 右侧：贴图名称（`font-size: 13px`，`color: #F1EAF3`）+ 分辨率（`font-size: 11px`，`color: #A9A4D6`）
  - 最右侧：下载图标按钮（16px，灰色，Hover 白色）
- **收起状态**：同左侧面板

### 9.5 顶部快捷工具栏

- **位置**：画布顶部，水平居中
- **背景**：同底部悬浮条
- **内容**：显示模式下拉（实体/线框/材质/法线/UV）+ 背景下拉（纯色/HDRI）+ 自动旋转开关
- 下拉菜单：深色主题，`background: #172A52`，`border: 1px solid #4A4560`，圆角 8px

### 9.6 底部控制栏

- **背景**：`#172A52`，`border-top: 1px solid #2C3F68`，高度 200px（可收起为 48px 标签栏）
- **标签页**：PBR 材质调节 / 光照设置 / 操作提示
  - 标签样式：`font-size: 14px`，`color: #A9A4D6`，选中时 `color: #F1EAF3`，底部 2px 樱花粉指示线
- **PBR 材质调节面板**：
  - 布局：2 列网格，每项包含标签 + 滑块 + 数值
  - 滑块样式：轨道 `#2C3F68`，已填充部分 `#C77AA5`，滑块圆点 16px 白色
  - 数值输入框：宽 60px，`background: #2C3F68`，`border-radius: 6px`，文字居中，白色
- **光照设置面板**：
  - 光源类型标签页：主光/补光/轮廓光/环境光
  - 强度滑块 + 颜色选择器（小色块，点击展开取色器）
  - HDRI 选择：横向缩略图列表，4 张预设，选中带樱花粉边框
- **操作提示面板**：
  - 图标 + 文字列表，每项 32px 高
  - 图标白色，文字 `#C6BDD0`

### 9.7 底部固定操作栏

- **位置**：页面最底部，全宽
- **背景**：`#101A35`，上边框 1px `#2C3F68`，内边距 16px 32px
- **左侧**：「下载模型 GLB」主按钮 + 「下载纹理包」次按钮
- **右侧**：「重新生成」文字按钮 + 「格式转换」下拉按钮
- 按钮样式均为深色主题适配

---

## 十、项目列表页 (P8)

### 10.1 页面布局

项目数据来自 `GET /api/v1/projects`，新建调用 `POST /api/v1/projects`；编辑使用 `PATCH`（兼容 `PUT`），删除使用 `DELETE` 并在玻璃确认框中二次确认。未登录或无权限时回到登录页。

- **背景**：`#F6F0F7`
- **内容区**：最大宽度 1440px，水平居中，内边距 32px
- **标题行**：左侧「我的项目」（`H1`）+ 右侧「+ 新建项目」主按钮

### 10.2 筛选工具栏

- **容器**：`background: #FFFFFF`，`border-radius: 12px`，`shadow-sm`，内边距 16px 20px，下间距 24px
- **布局**：横向排列，间距 12px
- **搜索框**：宽 280px，`height: 40px`，左侧 Search 图标（16px，灰色），圆角 8px
- **下拉筛选器**：每个宽 140px，`height: 40px`，右侧 ChevronDown 图标
  - 样式：`background: #F6F0F7`，`border: 1px solid #D8CFE0`，圆角 8px
  - 下拉面板：白色背景，圆角 12px，阴影，每项 Hover `#F1EAF3`
- **视图切换**：右侧，列表视图图标 / 网格视图图标，选中时樱花粉背景

### 10.3 项目卡片网格

- 网格布局：4 列（平板 2 列，移动端 1 列），间距 24px
- **项目卡片**：
  - 背景：`#FFFFFF`，`border-radius: 16px`，`shadow-md`，`border: 1px solid #D8CFE0`
  - Hover：`transform: translateY(-4px)`，`shadow-lg`，过渡 300ms
  - **封面图区**：宽高比 16:10，圆角上 16px，溢出隐藏
    - 图片：`object-fit: cover`，Hover `transform: scale(1.05)`，过渡 400ms
    - 状态角标：右上角，内边距 4px 10px，圆角 6px，字体 12px
      - 已完成：绿色系
      - 进行中：樱花粉系，可带小型进度条
      - 失败：红色系
    - 悬浮操作层：默认隐藏，Hover 封面图时从底部滑入
      - 背景：`linear-gradient(transparent, rgba(0,0,0,0.6))`
      - 按钮：收藏（星形）、删除（垃圾桶），白色图标，32px 圆形半透明背景
  - **信息区**：内边距 20px
    - 项目名称：`font-size: 16px`，`font-weight: 600`，单行截断，`color: #101A35`
    - 元信息行：上间距 8px，图标 + 文字，灰色
    - 标签行：上间距 12px，横向排列，间距 8px
  - **新建项目卡片**：
    - 背景：`#F6F0F7`，边框虚线 `2px dashed #C6BDD0`
    - 内容：中央大加号图标（48px，灰色）+ 「新建项目」文字
    - Hover：`border-color: #C77AA5`，`background: #F4EAF3`，图标和文字变樱花粉

### 10.4 分页器

- 居中对齐，上间距 32px
- 按钮样式：宽 36px，高 36px，圆角 8px
  - 默认：`background: #FFFFFF`，`border: 1px solid #D8CFE0`
  - Hover：`background: #F1EAF3`
  - 选中：`background: #C77AA5`，白色文字
- 上一页/下一页：Chevron 图标按钮

---

## 十一、项目详情页 (P9)

### 11.1 页面布局

详情页先读取 `GET /api/v1/projects/{project_id}`，模型列表按任务 ID读取 `GET /api/v1/models/{task_id}`。不存在的项目/模型使用 404 空态；“继续生成”回到 P4/P5 创建新任务。

- **背景**：`#F6F0F7`
- **内容区**：最大宽度 1200px，水平居中

### 11.2 项目信息头

- **容器**：`background: #FFFFFF`，`border-radius: 16px`，`shadow-md`，内边距 24px
- **布局**：左侧封面图（120px x 120px，圆角 12px）+ 右侧信息区
- **信息区**：
  - 项目名称：`H2` 样式
  - 元信息行：类型标签 + 创建时间 + 竖线分隔 + 模型数量
  - 标签行：横向排列的哈希标签
  - 操作按钮行：上间距 12px
    - 主操作：「继续生成新变体」（樱花粉主按钮）
    - 次操作：「批量对比」、「项目设置」（齿轮图标）、「编辑信息」、「删除项目」（红色文字）

### 11.3 模型网格区

- **筛选栏**：左侧 Tab（全部/已完成/失败）+ 右侧排序下拉
  - Tab 样式：文字按钮，选中时底部 2px 樱花粉指示线
- **模型卡片网格**：4 列，间距 20px
  - 卡片尺寸比项目列表更小，宽高比 1:1（正方形预览图）
  - 预览图：`background: #F1EAF3`，中央显示模型缩略图（3D 渲染小图或默认占位图）
  - 状态覆盖层：
    - 进行中：半透明樱花粉遮罩 + 中央 Spinner + 进度百分比
    - 失败：半透明红色遮罩 + 刷新图标
  - 信息区：
    - 生成编号：`font-size: 13px`，`font-weight: 500`
    - 评分：星星图标 + 分数
  - 悬浮操作：收藏、查看、删除图标


---

## 十二、RAG 知识库页 (P10)

### 12.1 页面布局

搜索调用 `GET /api/v1/rag/search?query=...&collection_name=...&top_k=...`；风格和材质筛选分别读取 `/api/v1/rag/styles`、`/api/v1/rag/materials`。有用/无用反馈统一提交 `POST /api/v1/rag/feedback`（`entry_id/quality_score`）。

- **背景**：`#F6F0F7`
- **内容区**：最大宽度 1200px，水平居中
- **标题行**：左侧「RAG 知识库」（`H1`）+ 右侧「+ 添加知识」主按钮

### 12.2 搜索与筛选区

- **语义搜索框**：全宽（最大 800px 居中），`height: 52px`，`border-radius: 12px`
  - 左侧 Search 图标（20px）
  - 占位符：「输入自然语言描述检索... 例：银发双马尾萌系角色」，`color: #A9A4D6`
  - 右侧：语音输入图标（麦克风）+ 搜索按钮（樱花粉主按钮）
  - Focus：`border-color: #C77AA5`，`shadow-glow`
- **分类筛选标签**：横向排列，间距 8px，上间距 16px
  - 样式：类似单选按钮组，选中项樱花粉背景白色文字

### 12.3 知识条目列表

使用 `RagResultCard`：相似度以数值和文字双重呈现，反馈按钮采用 toggle 原语并在请求完成后锁定 500ms 防止重复提交；空结果显示下一步搜索建议。

- 纵向排列，间距 16px
- **知识条目卡片**：
  - 背景：`#FFFFFF`，`border-radius: 12px`，`shadow-md`，内边距 20px
  - 左侧类型图标区：48px 圆形，`background` 根据类型变化（风格-紫色渐变、参数-樱花粉渐变、材质-绿色渐变）
  - 中间内容区：
    - 标题行：类型标签（小圆角标签）+ 条目名称（`font-size: 16px`，`font-weight: 600`）+ 相似度标签（右侧，樱花粉）
    - 标签行：横向排列关键词标签
    - 参数摘要：`font-size: 13px`，`color: #4A4560`，等宽字体显示关键参数
    - 统计行：成功案例数 + 平均质量分，图标 + 文字，灰色
  - 右侧操作区：
    - 「查看详情」：文字按钮
    - 「应用到当前项目」：樱花粉边框按钮
    - 「有用/无用」：图标按钮组（ThumbsUp / ThumbsDown），选中时填充色
  - Hover：`border-left: 4px solid #C77AA5`（左侧出现樱花粉强调条），过渡 200ms

### 12.4 空搜索状态

- 中央显示：SearchX 大图标（64px，灰色）+ 「未找到相关知识」+ 「尝试更换关键词或添加新知识」

---

## 十三、个人中心页 (P11)

### 13.1 页面布局

个人信息只展示 `GET /api/v1/auth/me` 返回的用户名、邮箱和头像；当前后端没有资料更新、会员计费、额度扣减接口，保存/升级/购买按钮必须标注“后端待补充”并禁用。

- **背景**：`#F6F0F7`
- **内容区**：最大宽度 1200px，水平居中，两栏布局（左侧 240px 侧边栏 + 右侧自适应内容区），间距 24px

### 13.2 左侧侧边栏

侧边栏只保留“个人信息 / 我的项目 / 安全退出”三个已可实现入口；会员等级、升级和额度模块作为视觉占位，以“后端待补充”徽标呈现，不允许触发支付或额度扣减。

- **容器**：`background: #FFFFFF`，`border-radius: 16px`，`shadow-md`，内边距 16px 0
- **当前会员标识**：顶部内边距 20px，居中
  - 图标：Crown 图标，32px，金色 `#E6B86A`
  - 文字：「当前会员」+ 会员等级（免费版/Pro/企业），`font-size: 14px`
  - 升级按钮：上间距 8px，小尺寸主按钮
- **导航菜单**：
  - 每项：高度 44px，内边距 `0 20px`，左侧图标（20px）+ 文字（`font-size: 14px`）
  - 默认：`color: #4A4560`
  - Hover：`background: #F6F0F7`，`color: #101A35`
  - 选中：`background: #F4EAF3`，`color: #C77AA5`，左侧 3px 樱花粉强调条（绝对定位）
  - 图标颜色跟随文字颜色
- **底部退出**：底部边框上方，文字红色，Hover 背景淡红

### 13.3 个人信息面板

- **容器**：`background: #FFFFFF`，`border-radius: 16px`，`shadow-md`，内边距 32px
- **头像区**：居中，头像 96px 圆形，`border: 3px solid #D8CFE0`，下方「更换头像」文字按钮
- **表单区**：上间距 24px，最大宽 480px 居中
  - 每项：标签（`font-size: 14px`，`font-weight: 500`，下间距 6px）+ 输入框
  - 手机号未绑定时：输入框右侧显示「绑定」樱花粉文字按钮
  - 保存按钮：上间距 24px，主按钮样式，居中

### 13.4 我的额度面板

本面板默认展示“额度服务未接入”空态。下方旧版额度数字、重置时间和购买按钮仅作为未来设计稿，不得绑定点击事件或伪造统计。

- **容器样式**：同上
- **额度卡片**：
  - 背景：`linear-gradient(135deg, #F4EAF3 0%, #F1E8F8 100%)`，`border-radius: 16px`，内边距 24px
  - 顶部：「本月免费额度」`font-size: 14px` + 右侧「额度重置时间」
  - 中央大数字：「3/5 次」，`font-size: 48px`，`font-weight: 700`，`color: #C77AA5`
  - 进度条：高度 8px，圆角全满，已用部分樱花粉，剩余部分灰色
  - 底部提示：额度不足时显示警告文字（橙色）
- **操作按钮行**：上间距 20px，「升级会员」主按钮 + 「购买加油包」次按钮
- **会员权益对比表**：上间距 32px
  - 表头：三列（免费 / Pro / 企业），Pro 和企业列顶部有「推荐」角标（金色小标签）
  - 每行：左侧功能名 + 右侧三列对比（对勾/横线/具体数值）
  - 对勾图标：绿色 `#72C8A6`，横线：灰色 `#C6BDD0`
  - 当前用户所在列：整列背景淡樱花粉 `#F4EAF3`

---

## 十四、批量生成页 (P13)

### 14.1 页面布局

批量页是前端编排：逐个调用 `POST /api/v1/tasks`，并发数由前端限流，逐项显示 task_id 和状态。后端暂无批量事务接口，提交前提示部分任务可能排队失败，支持逐项重试。

- **背景**：`#F6F0F7`
- **内容区**：最大宽度 1000px，水平居中，单栏布局
- **步骤指示器**：页面顶部，横向三步（上传图片 -> 参数配置 -> 确认提交）
  - 样式：每步包含圆形序号（32px，选中时樱花粉填充白色文字，未完成时灰色边框）+ 步骤名称
  - 步骤间连接线：选中部分樱花粉，未完成部分灰色

### 14.2 步骤 1：上传图片

- **上传区域**：`border: 2px dashed #C6BDD0`，`border-radius: 16px`，高度 200px，中央内容
  - 拖拽悬停：`border-color: #C77AA5`，`background: #F4EAF3`
- **已选图片网格**：上间距 20px，横向排列，间距 12px，可横向滚动
  - 每张缩略图：80px x 80px，圆角 8px，相对定位
  - 删除按钮：右上角 16px 圆形，红色背景白色 X 图标，Hover 放大
  - 图片名称：下方 `font-size: 11px`，居中，最大宽度 80px 截断

### 14.3 步骤 2：统一参数配置

- **容器**：`background: #FFFFFF`，`border-radius: 16px`，内边距 24px
- 参数控件与角色上传页一致，横向紧凑排列（2 列布局）
- 「应用 RAG 智能推荐」按钮：文字按钮，樱花粉，基于第一张图分析

### 14.4 步骤 3：确认提交

- **信息汇总卡片**：
  - 左侧：统计信息（图片数量、预计耗时、并行数）
  - 右侧：任务队列提示（显示预计并发数，不显示额度扣减）
- **提交按钮**：全宽月樱渐变主按钮；请求失败时按单项任务显示错误并允许重试
- **队列提示**：当前后端没有额度接口，不渲染“额度不足/升级会员”文案

---

## 十五、模型对比页 (P12)

### 15.1 页面布局

对比页接收多个 task ID，分别调用模型预览/元数据接口；“同步视角”仅为前端 Three.js 行为。下载使用各任务 `/download`，删除其他模型需回到项目页逐个执行，不调用未实现的批量删除接口。

- **背景**：`#F6F0F7`
- **内容区**：全宽，内边距 24px
- **顶部工具栏**：左侧「模型对比」标题 + 右侧「返回项目」按钮 + 同步控制开关

### 15.2 对比网格

- 2/3/4 列等分布局（根据选中模型数量自适应），间距 16px
- **对比卡片**：
  - 背景：`#FFFFFF`，`border-radius: 12px`，`shadow-md`
  - 顶部信息栏：高度 48px，内边距 `0 16px`，左侧评分 + 右侧单选框（圆形，选中时樱花粉填充）
  - 3D 预览区：宽高比 4:3，`background: #101A35`，圆角下 0
    - 每个预览器独立，但开启同步时视角联动
    - 底部悬浮操作条：自动旋转、全屏
  - 信息区：内边距 12px 16px，4 行统计（顶点/面数/纹理/耗时）
  - 操作区：内边距 12px 16px，两个按钮（下载、重生成）
- 选中卡片：`border: 2px solid #C77AA5`，有樱花粉外发光 `shadow-glow`

### 15.3 底部操作栏

- 固定底部，全宽，背景白色，上边框
- 左侧：「下载选中模型」主按钮（禁用直到选中一个）
- 中间：「收藏选中」次按钮
- 右侧：「删除其他」红色文字按钮（危险操作，需二次确认）


---

## 十六、风格迁移页 (P14)

### 16.1 页面布局

风格迁移目前仅提供视觉预览和参数草稿；风格列表可读取 `/api/v1/rag/styles`，但没有独立迁移 API，主按钮显示“即将支持”，不得创建伪任务。

- **背景**：`#F6F0F7`
- **内容区**：最大宽度 1200px，水平居中
- **步骤式布局**：纵向三步，每步一个卡片

### 16.2 步骤 1：选择源模型

- **容器**：`background: #FFFFFF`，`border-radius: 16px`，`shadow-md`，内边距 24px
- **模型选择下拉**：全宽，`height: 48px`，显示当前选中模型名称和缩略图
- **预览区**：两栏布局
  - 左侧：源模型 3D 预览（300px 高，`background: #101A35`，圆角 12px）
  - 右侧：风格预览（同尺寸，初始显示「请选择风格」占位文字）

### 16.3 步骤 2：选择目标风格

- **风格模板网格**：横向排列，间距 12px，可横向滚动
  - 每个模板：120px x 120px，圆角 12px，相对定位
  - 缩略图：`object-fit: cover`，圆角继承
  - 风格名称：底部绝对定位，全宽，`background: linear-gradient(transparent, rgba(0,0,0,0.7))`，文字白色居中
  - 选中状态：`border: 3px solid #C77AA5`，右上角樱花粉对勾图标
  - Hover：`transform: scale(1.05)`，过渡 200ms

### 16.4 步骤 3：调节强度

- **滑块组**：
  - 风格强度：0-100%，默认 70%
  - 保留原色：0-100%，默认 40%
  - 滑块样式同角色上传页
- **应用按钮**：全宽主按钮，文字「应用风格迁移」，左侧 Wand2 魔法图标
- **说明文字**：按钮下方，「预计耗时约 30 秒，仅替换材质不重新生成几何体」，`font-size: 13px`，`color: #A9A4D6`

---

## 十七、帮助中心页 (P15)

### 17.1 页面布局

帮助中心的静态教程与 FAQ 可离线渲染；反馈表单目前没有专用后端路由，提交按钮显示“反馈接口待接入”，不得假装提交成功。

- **背景**：`#F6F0F7`
- **内容区**：最大宽度 1200px，水平居中，两栏布局（左侧 200px 侧边栏 + 右侧自适应），间距 32px

### 17.2 左侧侧边栏

- **容器**：`background: #FFFFFF`，`border-radius: 16px`，`shadow-md`，内边距 16px 0
- **搜索框**：顶部内边距 16px，左右 16px，高度 40px，圆角 8px，左侧 Search 图标
- **导航菜单**：
  - 每项：高度 40px，内边距 `0 16px`，左侧图标（18px）+ 文字（`font-size: 14px`）
  - 默认：`color: #4A4560`
  - Hover：`background: #F6F0F7`
  - 选中：`color: #C77AA5`，左侧 3px 樱花粉强调条
- **热门标签**：底部，标题「热门标签」+ 横向标签云

### 17.3 使用教程面板

- **容器**：`background: #FFFFFF`，`border-radius: 16px`，`shadow-md`，内边距 32px
- **快速开始指南**：
  - 标题：`H3` 样式
  - 步骤列表：每项左侧圆形序号（24px，樱花粉背景白色文字）+ 右侧标题 + 描述
  - 步骤间连接线：左侧竖线，灰色
  - 「查看详细图文教程」按钮：樱花粉文字按钮，右侧 ArrowRight 图标

### 17.4 常见问题面板

- **FAQ 列表**：纵向排列，间距 8px
- **FAQ 项**：
  - 容器：`background: #F6F0F7`，`border-radius: 10px`，内边距 16px 20px
  - 问题行：`font-size: 15px`，`font-weight: 500`，左侧 Q 图标（樱花粉）
  - 展开按钮：右侧 ChevronDown，展开时旋转 180 度，过渡 200ms
  - 答案区：默认隐藏，展开时从上滑入，`font-size: 14px`，`color: #4A4560`，上间距 12px，左边距 28px
  - Hover：`background: #F1EAF3`

### 17.5 问题反馈面板

- **表单区**：
  - 问题类型下拉：`height: 44px`，圆角 8px
  - 描述文本域：最小高度 120px，`border-radius: 10px`，占位符灰色
  - 图片上传区：`border: 2px dashed #C6BDD0`，高度 100px，中央 Upload 图标 + 「上传截图（可选）」
  - 提交按钮：主按钮样式
- **提交成功状态**：表单区域替换为成功动画（绿色对勾 + 「感谢您的反馈，我们会尽快处理」）

---

## 十八、全局组件规范

### 18.0 月樱材质覆盖

以下规则覆盖本章后续组件中仍出现的旧版实色樱花粉描述：

- Primary 使用 `linear-gradient(135deg, #E9A9C5 0%, #A9A4D6 100%)`；Hover 提高亮度并增加粉紫柔光，Active 轻微缩放 `scale(.98)`。
- Secondary/Ghost 使用透明玻璃底和白色细边框；Hover 叠加 `rgba(233,169,197,.14)`，文字变为 `#FFF8FC`。
- Danger 保留 `#EF4444`，Success 使用 `#72C8A6`，Warning 使用 `#E6B86A`；状态标签同时显示文字和图标。
- 标准卡片默认玻璃材质；只有数据密集型表格允许 `rgba(255,248,252,.92)`，并用 `#D7B6D6` 描边。
- 所有输入焦点统一 `border-color: #E9A9C5; box-shadow: 0 0 0 3px rgba(233,169,197,.42)`；错误态保持红色并提供字段说明。

### 18.1 按钮规范

**主按钮（Primary）**
- `height: 44px`（标准）/ `52px`（大型）
- `padding: 0 24px`
- `background: linear-gradient(135deg,#E9A9C5 0%,#A9A4D6 100%)`，`border-radius: 10px`
- 文字：`font-size: 14px`（标准）/ `16px`（大型），`font-weight: 600`，白色
- Hover：提高渐变亮度，`transform: translateY(-1px)`，增加樱花柔光 `shadow-md`
- Active：`transform: translateY(0) scale(.98)`
- Disabled：`background: #C6BDD0`，`cursor: not-allowed`，无 Hover 效果

**次按钮（Secondary）**
- 尺寸同主按钮
- `background: rgba(255,248,252,.10)`，`border: 1px solid rgba(255,255,255,.38)`
- 文字：`color: #FFF8FC`
- Hover：`background: rgba(233,169,197,.14)`，`border-color: #E9A9C5`

**文字按钮（Ghost）**
- 无边框无背景，内边距 `8px 12px`
- 文字：`color: #4A4560`，`font-size: 14px`
- Hover：`background: #F1EAF3`，`border-radius: 6px`

**危险按钮（Danger）**
- 主按钮样式，但 `background: #EF4444`
- Hover：`background: #DC2626`

**图标按钮（Icon）**
- 宽高等高 36px（标准）/ 44px（大）
- `border-radius: 8px`（方形）/ `9999px`（圆形）
- `background: transparent`，Hover `background: #F1EAF3`

### 18.2 输入框规范

**文本输入框**
- `height: 48px`，`border-radius: 10px`，`border: 1px solid #D8CFE0`
- `padding: 0 16px`，`font-size: 15px`，`color: #101A35`
- 占位符：`color: #A9A4D6`
- Focus：`border-color: #E9A9C5`，`box-shadow: 0 0 0 3px rgba(233,169,197,.42)`
- 错误：`border-color: #EF4444`，`box-shadow: 0 0 0 3px rgba(239,68,68,0.1)`
- 禁用：`background: #F1EAF3`，`color: #A9A4D6`

**文本域**
- 最小高度 120px，`padding: 12px 16px`
- 其他样式同文本输入框

**搜索框**
- 左侧内嵌 Search 图标（16px，灰色）
- 右侧可配置清除按钮（X 图标，有内容时显示）

### 18.3 下拉选择器规范

**触发器**
- `height: 48px`，`border-radius: 10px`，`border: 1px solid #D8CFE0`
- 左侧文字，右侧 ChevronDown 图标（16px）
- Hover：`border-color: #C6BDD0`
- Focus：`border-color: #C77AA5`

**下拉面板**
- `background: #FFFFFF`，`border-radius: 12px`，`shadow-lg`，`border: 1px solid #D8CFE0`
- 最大高度 280px，可滚动
- 每项：高度 40px，`padding: 0 16px`，Hover `background: #F1EAF3`
- 选中项：`background: #F4EAF3`，`color: #C77AA5`，左侧 Check 图标

### 18.4 标签/角标规范

**状态标签**
- `height: 24px`，`padding: 0 10px`，`border-radius: 6px`
- `font-size: 12px`，`font-weight: 600`
- 成功：`background: rgba(114,200,166,.12)`，`color: #72C8A6`
- 警告：`background: rgba(245,158,11,0.1)`，`color: #E6B86A`
- 错误：`background: rgba(239,68,68,0.1)`，`color: #EF4444`
- 信息：`background: rgba(142,168,216,.14)`，`color: #8EA8D8`

**哈希标签**
- `height: 28px`，`padding: 0 12px`，`border-radius: 6px`
- `background: #F1EAF3`，`color: #4A4560`，`font-size: 13px`
- Hover：`background: #D8CFE0`，`color: #C77AA5`

### 18.5 卡片规范

**标准卡片**
- `background: #FFFFFF`，`border-radius: 16px`，`shadow-md`
- `border: 1px solid #D8CFE0`
- Hover：`transform: translateY(-2px)`，`shadow-lg`，过渡 300ms

**深色卡片**
- `background: #172A52`，`border-radius: 16px`
- `border: 1px solid #2C3F68`

**选中卡片**
- 标准卡片 + `border: 2px solid #C77AA5` + `shadow-glow`

### 18.6 对话框/模态框规范

**容器**
- 居中定位，`background: #FFFFFF`，`border-radius: 20px`，`shadow-xl`
- 最大宽度 480px（确认框）/ 640px（大对话框）
- 动画：从上方 20px 淡入，时长 300ms，弹性缓动

**头部**
- 高度 64px，内边距 `0 24px`，左侧标题（`H4`），右侧关闭按钮（X 图标，24px，灰色，Hover 黑色）
- 底部 1px 分割线 `#D8CFE0`

**内容区**
- 内边距 24px

**底部操作区**
- 内边距 `16px 24px`，右侧对齐，按钮间距 12px
- 主操作在右，取消在左

### 18.7 Toast 通知规范

**容器**
- 固定定位，顶部 24px 居中，或右上角
- `background: #FFFFFF`，`border-radius: 12px`，`shadow-lg`
- 最小宽度 320px，最大宽度 480px
- 动画：从上方滑入，时长 300ms

**内容**
- 左侧状态图标（20px）：成功-绿色对勾、错误-红色X、警告-黄色感叹号、信息-樱花粉i
- 中间文字：`font-size: 14px`，`color: #101A35`
- 右侧关闭按钮（X 图标，16px，灰色）
- 自动消失：4 秒后淡出，时长 300ms

### 18.8 加载/骨架屏规范

**Spinner**
- 尺寸：16px（小）/ 24px（中）/ 40px（大）
- 颜色：主品牌色或白色（深色背景）
- 动画：360 度旋转，1s 线性无限循环

**骨架屏**
- `background: linear-gradient(90deg, #F1EAF3 25%, #D8CFE0 50%, #F1EAF3 75%)`
- `background-size: 200% 100%`
- 动画：背景位置从左到右移动，1.5s 无限循环
- 圆角根据内容类型：文字行 4px，卡片 16px，头像 9999px

### 18.9 进度条规范

**线性进度条**
- 轨道高度：8px（标准）/ 4px（细），`border-radius: 4px`
- 轨道背景：`#D8CFE0`
- 填充：`background: linear-gradient(90deg, #C77AA5, #8F7CC7)`，`border-radius: 4px`
- 动画：`transition: width 0.5s ease-out`

**圆形进度条**
- 用于小区域，直径 40px
- 轨道：2px，灰色
- 填充：2px，樱花粉，SVG stroke-dasharray 动画

### 18.10 Tooltip 规范

**容器**
- `background: #101A35`，`color: #FFFFFF`，`font-size: 13px`
- `border-radius: 8px`，`padding: 8px 12px`
- `shadow-md`
- 动画：淡入 150ms
- 箭头：4px 三角形，与触发元素间距 8px

### 18.11 组件落地清单（Vue3 自研原语）

| 组件 | 视觉润色 | 使用页面 | 行为与接口约束 |
|---|---|---|---|
| `MoonlitShell` | 夜空渐变、云雾层、月相/花瓣装饰 | 全站 | 装饰层 `pointer-events:none`；支持 reduced-motion |
| `GlassCard` / `GlowBorder` | 半透明玻璃 + hover 流光边框 | P1、P4、P6、P7、P9 | processing 时显示动画；错误态改红色边框，不吞掉错误文案 |
| `GradientHeading` | Noto Serif SC + 星光白→樱花粉渐变 | P1、P2、P3、P10 | 仅标题使用，正文不渐变；超长标题换行不溢出 |
| `Dropzone` | 虚线转流光边框、拖拽光晕、缩略图胶囊 | P4、P5、P13 | 调用 `/api/v1/uploads`；限制 PNG/JPG/JPEG/WEBP、20MB；支持 URL 分支 `/api/v1/uploads/url` |
| `StatusBadge` / `ProgressRail` | 月相节点、樱花粉进度线、成功/警告/错误图标 | P6、P9 | 映射任务状态枚举；取消走 `DELETE /api/v1/tasks/{id}`，重试走 `POST /api/v1/tasks/{id}/retry` |
| `WorkflowTimeline` | LangGraph 节点时间线 + 流光连接线 | P6 | 数据来自 `/agents/workflow/{task_id}`；WebSocket 断开后轮询 |
| `ModelViewport` | 月夜 3D 画布、柔光选中轮廓、工具条玻璃浮层 | P7、P9、P12、P14 | 预览/下载/转换分别调用 models 路由；无 URL 时显示空态 |
| `CommandTabs` / `FilterChip` | 胶囊标签、细线选中态、键盘左右切换 | P8、P9、P10 | 筛选参数必须映射 projects/rag 查询参数 |
| `RagResultCard` | 左侧樱花色强调条、相似度徽标、反馈按钮 | P10 | 搜索 `/rag/search`；反馈 `/rag/feedback`；反馈后更新 usage_count |
| `GlassDialog` / `Toast` | 背景模糊、细边框、柔和入场 | 全站 | 统一呈现 401/404/409/422/500；危险操作需确认 |
| `Skeleton` / `EmptyState` | 星尘 shimmer、月相空态插画 | 全站 | 不使用假数据；空态提供下一步动作或重试 |

组件命名、样式和交互由前端项目内部维护；如需引入第三方库，只允许引入无样式的功能性依赖，并须在评审中说明可访问性和体积影响。

**关键组件 Props/Events 约定**：

- `Dropzone`: `accept=['image/png','image/jpeg','image/webp']`、`maxSize=20*1024*1024`、`sourceMode='file|url'`；触发 `upload-success({url,object_name,size})`、`upload-error({status,detail})`。
- `GlowBorder`: `tone='sakura|success|warning|danger'`、`active`、`animated`；只负责视觉，不包裹业务请求。
- `StatusBadge`: `status` 必须是后端任务枚举；未知值显示“未知状态”并记录 warning 日志。
- `ModelViewport`: `taskId`、`previewUrl`、`outputFormat`；触发 `convert(format)`、`download()`、`load-error(error)`，没有 `previewUrl` 时禁用操作。
- `Toast`: `type`、`title`、`detail`、`duration`；错误 Toast 不自动消失，用户关闭后才移除。

### 18.12 视觉与交互验收清单

- 首屏可辨识夜樱蓝紫渐变、樱花粉主操作和玻璃层；不得出现默认蓝色 SaaS 按钮或大面积纯白背景。
- 登录/注册、上传、任务、模型、RAG 页面均能在 loading、empty、error、success 四类状态下完成闭环；错误信息来自真实接口状态码。
- 所有可操作元素可用键盘访问并有焦点样式；动画在 `prefers-reduced-motion: reduce` 下关闭或降速。
- Dropzone 拒绝超 20MB 或不支持格式；任务状态只使用后端枚举；取消/重试/转换按钮分别命中已定义路由。
- 构建产物中不得出现 `ikun-ui` 或其他未批准 UI 组件库依赖；组件样式来自项目 token 和 Vue 单文件组件。

---

## 附录：响应式断点适配速查

| 断点 | 宽度范围 | 关键适配规则 |
|------|---------|-------------|
| **桌面大屏** | >= 1440px | 最大内容宽度 1440px，左右边距 32px，4 列网格 |
| **桌面标准** | 1280px - 1439px | 内容区自适应，左右边距 32px，4 列网格 |
| **平板横屏** | 1024px - 1279px | 左右边距 24px，3 列网格，部分两栏变单栏 |
| **平板竖屏** | 768px - 1023px | 左右边距 24px，2 列网格，导航栏保持，侧边栏变抽屉 |
| **移动端** | < 768px | 左右边距 16px，单列布局，导航栏变汉堡菜单，底部固定操作栏 |

---

> **文档结束**  
> 本高保真原型设计规范基于 PRD v1.0 和线框图文档编制，覆盖全部 P0 及核心 P1 功能页面的详细视觉、交互和动效规范。所有尺寸基于 1440px 桌面端标准，实际开发需配合响应式断点进行适配。视觉设计阶段可在此规范基础上进行创意发挥，但核心交互逻辑和组件状态必须保持一致。



