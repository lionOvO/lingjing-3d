# AI 3D 数字人开发工具链 —— Codex 项目生成提示词

> 本提示词用于在 Codex / Cursor / GitHub Copilot 等 AI 编程工具中一键生成完整可运行的全栈项目。

---

## 一、项目概述

开发一个 **AI 3D 数字人开发工具链** Web 平台，核心功能：

1. **动漫角色 3D 化**：上传动漫/二次元角色图片，系统通过多模态 AI 智能体识别角色特征（发型、服装、配饰、姿态等），生成带 PBR 纹理的高精度 3D 模型（GLB/OBJ 导出）。
2. **物品 3D 建模**：上传任意物品照片，生成可用于游戏/3D 打印/AR 的 3D 网格模型。
3. **RAG 知识智库**：基于 Milvus 向量数据库构建 3D 生成参数知识库、角色风格模板库，支持检索增强生成，持续优化输出质量。

**项目定位**：AI 智能体 + RAG 检索增强的 3D 内容创作平台，面向游戏开发者、虚拟偶像创作者、3D 打印爱好者。

---

## 二、技术栈（精简版，每个大块至少一种）

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| **前端** | Vue 3 + TypeScript + Three.js | Composition API，3D 预览与交互 |
| **后端** | FastAPI + LangGraph + LangChain + DeepAgents | 异步 API + 多智能体工作流编排 |
| **关系数据库** | MySQL 8.0 + SQLAlchemy 2.0 (async) | 用户、项目、任务、模型元数据 |
| **向量数据库** | Milvus 2.3+ | RAG 知识库：角色风格向量、生成参数向量 |
| **缓存/队列** | Redis + Celery | 任务状态缓存、异步 3D 生成队列 |
| **文件存储** | MinIO | 3D 模型文件、纹理贴图、源图片 |
| **3D 生成引擎** | TRELLIS-2（主）+ TripoSR（快速预览模式） | 开源图片转 3D，支持 GLB/OBJ/PLY |
| **视觉分析** | Qwen2-VL（本地部署或 API） | 动漫角色特征多模态识别 |
| **大语言模型** | DeepSeek-V3 / Qwen2.5-72B | 智能体推理、提示词优化、参数调优 |
| **部署** | Docker + Docker Compose | 全栈容器化一键启动 |

---

## 三、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    前端层 (Vue3 + Three.js)                  │
│  上传页面 │ 3D 预览器 │ 项目管理 │ RAG 知识库检索 │ 任务进度  │
└────────────────────────┬────────────────────────────────────┘
                         │ REST API / WebSocket
┌────────────────────────▼────────────────────────────────────┐
│                  API 网关层 (FastAPI)                        │
│  认证授权 │ 文件上传 │ 任务管理 │ 模型下载 │ RAG 检索接口    │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│           智能体编排层 (LangGraph + DeepAgents)               │
│                                                              │
│   MasterAgent（主控）                                        │
│     ├─→ CharacterAnalysisAgent（多模态视觉分析）              │
│     ├─→ RAGRetrievalAgent（Milvus 向量检索增强）             │
│     ├─→ ModelGenerationAgent（3D 模型生成调度）               │
│     ├─→ QualityCheckAgent（Mesh 质量评估）                   │
│     └─→ PostProcessAgent（后处理：格式转换、纹理优化）        │
│                                                              │
│   工作流状态机：INIT → ANALYZE → RETRIEVE → GENERATE        │
│                 → EVALUATE → POSTPROCESS → COMPLETE          │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                     服务层                                    │
│  TRELLIS-2 服务 │ Qwen2-VL 服务 │ Milvus 客户端 │ Celery Worker │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                     数据层                                    │
│  MySQL（关系数据）              │  Milvus（向量数据）           │
│  users / projects / tasks     │  character_style_collection   │
│  model_metadata / rag_entries │  generation_params_collection │
└─────────────────────────────────────────────────────────────┘
```

---

## 四、核心功能模块

### 4.1 图片上传与预处理
- 支持拖拽上传、粘贴上传、URL 拉取
- 格式：PNG / JPG / WEBP（最大 20MB）
- 可选自动背景移除、尺寸归一化
- 生成唯一 task_id，进入 Celery 异步队列

### 4.2 角色分析智能体 (CharacterAnalysisAgent)
**输入**：动漫角色图片  
**输出**：结构化角色特征 JSON

```json
{
  "character_type": "anime_humanoid",
  "gender": "female",
  "hair": {
    "color": "silver_white",
    "style": "long_straight_with_bangs",
    "length": "waist_length",
    "accessories": ["hair_ribbon"]
  },
  "face": {
    "eye_color": "amber",
    "eye_shape": "large_round",
    "expression": "neutral_calm"
  },
  "outfit": {
    "top": "school_uniform_blazer",
    "bottom": "pleated_skirt",
    "colors": ["navy_blue", "white"],
    "accessories": ["necktie", "knee_high_socks"]
  },
  "pose": "standing_frontal",
  "style_tags": ["anime", "moe", "school_life"]
}
```

**实现**：LangChain PromptTemplate + Qwen2-VL 多模态调用，输出结构化数据。

### 4.3 RAG 检索增强 (RAGRetrievalAgent)
**Milvus 集合设计**：

| 集合名 | 维度 | 用途 |
|--------|------|------|
| `character_style_collection` | 1024 | 角色风格特征向量库 |
| `generation_params_collection` | 768 | 最优生成参数向量库 |
| `material_reference_collection` | 512 | PBR 材质参考向量库 |

**RAG 流程**：
```
用户上传图片 → 角色分析 Agent 提取特征 → 特征文本向量化
→ Milvus 相似度检索(top_k=5) → 检索结果注入生成提示词
→ 3D 生成 Agent 调用优化参数 → 输出 3D 模型
```

### 4.4 3D 生成智能体 (ModelGenerationAgent)
**LangGraph 工作流状态机**：

```
INIT        → 接收任务，加载图片
ANALYZE     → CharacterAnalysisAgent 分析角色特征
RETRIEVE    → RAGRetrievalAgent 检索相似参数
GENERATE    → 调用 3D 引擎（TRELLIS-2 或 TripoSR）
EVALUATE    → QualityCheckAgent 评估 Mesh 质量
  ├─ 通过 → POSTPROCESS
  └─ 不通过 → 回到 GENERATE（参数调优重试，最多 3 次）
POSTPROCESS → 网格修复、纹理优化、格式转换
COMPLETE    → 存储结果，WebSocket 通知前端
```

**引擎策略**：
- 动漫角色高质量模式 → TRELLIS-2（~3 秒，4B 参数，GLB/OBJ/PLY）
- 快速预览模式 → TripoSR（<500ms，6GB VRAM）
- 物品建模 → TRELLIS-2 或 Hunyuan3D-2.1

**输出格式**：GLB（默认）、OBJ、FBX、STL（3D 打印）

### 4.5 质量评估智能体 (QualityCheckAgent)
检查项：
- 水密性（watertight）
- 流形性（manifold）
- 面数范围：100 ~ 500,000
- 退化面检测
- 纹理分辨率 >= 1024
- 综合评分 >= 0.8 通过，否则触发重试与参数自动调优

### 4.6 3D 预览与交互（前端）
- Three.js Web 端 3D 查看器
- 旋转 / 缩放 / 平移 / 线框模式 / 材质切换
- PBR 材质实时预览、光照调节、背景切换
- 一键下载模型文件 + 纹理贴图包

---

## 五、数据库 Schema

### MySQL 表结构

```sql
-- 用户表
CREATE TABLE users (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    avatar_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- 项目表
CREATE TABLE projects (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    project_type ENUM('anime_character', 'object_model') NOT NULL,
    status ENUM('draft', 'processing', 'completed', 'failed') DEFAULT 'draft',
    source_image_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 生成任务表
CREATE TABLE generation_tasks (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    project_id BIGINT NOT NULL,
    task_type ENUM('anime_character', 'object_model') NOT NULL,
    status ENUM('pending', 'analyzing', 'retrieving', 'generating', 'evaluating', 'postprocessing', 'completed', 'failed') DEFAULT 'pending',
    celery_task_id VARCHAR(100),
    analysis_result JSON,
    retrieved_params JSON,
    generation_params JSON,
    quality_score FLOAT,
    output_model_url VARCHAR(500),
    output_format ENUM('glb', 'obj', 'fbx', 'stl') DEFAULT 'glb',
    texture_urls JSON,
    error_message TEXT,
    retry_count INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

-- 角色特征表（动漫角色专用）
CREATE TABLE character_features (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    task_id BIGINT NOT NULL,
    character_type VARCHAR(50),
    gender VARCHAR(20),
    hair_color VARCHAR(50),
    hair_style VARCHAR(100),
    eye_color VARCHAR(50),
    outfit_description TEXT,
    pose VARCHAR(50),
    style_tags JSON,
    feature_vector_id VARCHAR(100),
    FOREIGN KEY (task_id) REFERENCES generation_tasks(id)
);

-- 模型元数据表
CREATE TABLE model_metadata (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    task_id BIGINT NOT NULL,
    vertex_count INT,
    face_count INT,
    texture_resolution VARCHAR(20),
    has_pbr BOOLEAN DEFAULT FALSE,
    file_size_mb FLOAT,
    bounding_box JSON,
    FOREIGN KEY (task_id) REFERENCES generation_tasks(id)
);

-- RAG 知识库条目管理表
CREATE TABLE rag_knowledge_entries (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    collection_name VARCHAR(100) NOT NULL,
    milvus_id VARCHAR(100) NOT NULL,
    entry_type ENUM('character_style', 'generation_params', 'material_reference') NOT NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT,
    tags JSON,
    source VARCHAR(200),
    usage_count INT DEFAULT 0,
    avg_quality_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Milvus 集合设计

```python
# character_style_collection
fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="style_embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
    FieldSchema(name="style_name", dtype=DataType.VARCHAR, max_length=100),
    FieldSchema(name="tags", dtype=DataType.VARCHAR, max_length=500),
    FieldSchema(name="generation_params", dtype=DataType.VARCHAR, max_length=2000),
    FieldSchema(name="reference_image_url", dtype=DataType.VARCHAR, max_length=500),
    FieldSchema(name="created_at", dtype=DataType.INT64),
]

# generation_params_collection
fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="param_embedding", dtype=DataType.FLOAT_VECTOR, dim=768),
    FieldSchema(name="object_type", dtype=DataType.VARCHAR, max_length=50),
    FieldSchema(name="model_type", dtype=DataType.VARCHAR, max_length=50),
    FieldSchema(name="best_params", dtype=DataType.VARCHAR, max_length=2000),
    FieldSchema(name="success_rate", dtype=DataType.FLOAT),
    FieldSchema(name="avg_quality_score", dtype=DataType.FLOAT),
]

# material_reference_collection
fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="material_embedding", dtype=DataType.FLOAT_VECTOR, dim=512),
    FieldSchema(name="material_type", dtype=DataType.VARCHAR, max_length=50),
    FieldSchema(name="pbr_params", dtype=DataType.VARCHAR, max_length=1000),
    FieldSchema(name="preview_url", dtype=DataType.VARCHAR, max_length=500),
]
```

---

## 六、API 接口设计

### 认证
```
POST /api/v1/auth/register
POST /api/v1/auth/login
POST /api/v1/auth/refresh
GET  /api/v1/auth/me
```

### 项目
```
GET    /api/v1/projects              # 项目列表（分页）
POST   /api/v1/projects              # 创建项目
GET    /api/v1/projects/{id}         # 项目详情
PUT    /api/v1/projects/{id}         # 更新项目
DELETE /api/v1/projects/{id}         # 删除项目
```

### 生成任务
```
POST   /api/v1/tasks                 # 提交生成任务（上传图片 + 参数）
GET    /api/v1/tasks/{id}            # 获取任务状态
WS     /api/v1/tasks/{id}/progress   # WebSocket 实时进度推送
POST   /api/v1/tasks/{id}/retry      # 重试失败任务
DELETE /api/v1/tasks/{id}            # 取消任务
```

### 3D 模型
```
GET    /api/v1/models/{id}           # 模型元数据
GET    /api/v1/models/{id}/download  # 下载模型文件
GET    /api/v1/models/{id}/preview   # 预览图
POST   /api/v1/models/{id}/convert   # 格式转换
```

### RAG 知识库
```
GET    /api/v1/rag/search            # 语义相似度检索
POST   /api/v1/rag/feedback          # 检索结果反馈（优化 RAG）
GET    /api/v1/rag/styles            # 风格列表
GET    /api/v1/rag/materials         # 材质列表
```

### 智能体调试
```
GET    /api/v1/agents/workflow/{task_id}  # 查看智能体工作流状态
POST   /api/v1/agents/invoke              # 手动触发智能体
```

---

## 七、智能体详细实现

### 7.1 MasterAgent（主控智能体）

使用 LangGraph 构建状态机工作流：

```python
from langgraph.graph import StateGraph, END
from typing import TypedDict, Optional

class GenerationState(TypedDict):
    task_id: str
    project_id: int
    task_type: str  # "anime_character" | "object_model"
    source_image_url: str
    character_features: Optional[dict]
    retrieved_context: Optional[list]
    generation_params: Optional[dict]
    generated_model_url: Optional[str]
    generated_textures: Optional[list]
    quality_score: Optional[float]
    evaluation_result: Optional[str]  # "pass" | "retry" | "fail"
    retry_count: int
    error_message: Optional[str]

class MasterAgent:
    def __init__(self):
        self.workflow = self._build_workflow()

    def _build_workflow(self):
        workflow = StateGraph(GenerationState)

        workflow.add_node("init", self._init_task)
        workflow.add_node("analyze", CharacterAnalysisAgent().run)
        workflow.add_node("retrieve", RAGRetrievalAgent().run)
        workflow.add_node("generate", ModelGenerationAgent().run)
        workflow.add_node("evaluate", QualityCheckAgent().run)
        workflow.add_node("postprocess", PostProcessAgent().run)

        workflow.set_entry_point("init")
        workflow.add_edge("init", "analyze")
        workflow.add_edge("analyze", "retrieve")
        workflow.add_edge("retrieve", "generate")

        workflow.add_conditional_edges(
            "generate",
            lambda s: "evaluate" if s.get("generated_model_url") else "fail",
            {"evaluate": "evaluate", "fail": END}
        )

        workflow.add_conditional_edges(
            "evaluate",
            self._route_after_evaluate,
            {"pass": "postprocess", "retry": "generate", "fail": END}
        )

        workflow.add_edge("postprocess", END)
        return workflow.compile()

    def _route_after_evaluate(self, state: GenerationState):
        if state["evaluation_result"] == "pass":
            return "pass"
        elif state["retry_count"] < 3:
            state["retry_count"] += 1
            return "retry"
        else:
            return "fail"
```

### 7.2 CharacterAnalysisAgent

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage

class CharacterAnalysisAgent:
    """基于 Qwen2-VL 的动漫角色特征提取"""

    async def run(self, state: GenerationState) -> GenerationState:
        image_url = state["source_image_url"]

        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content="你是一个专业的动漫角色分析专家。\n请分析图片中的动漫角色，提取以下特征并以严格 JSON 返回：\n{
  \"character_type\": \"anime_humanoid\",\n  \"gender\": \"female|male|unknown\",\n  \"hair\": {\"color\": \"...\", \"style\": \"...\", \"length\": \"...\", \"accessories\": []},\n  \"face\": {\"eye_color\": \"...\", \"eye_shape\": \"...\", \"expression\": \"...\"},\n  \"outfit\": {\"top\": \"...\", \"bottom\": \"...\", \"colors\": [], \"accessories\": []},\n  \"pose\": \"...\",\n  \"style_tags\": []\n}\n只输出 JSON，不要其他内容。"),
            HumanMessage(content=[{"type": "image_url", "image_url": {"url": image_url}}])
        ])

        # 调用 Qwen2-VL
        model = ChatQwenVL(model="qwen2-vl-72b")
        response = await model.ainvoke(prompt.format_messages())

        features = json.loads(response.content)
        state["character_features"] = features

        # 特征向量化存入 Milvus
        embedding = await self._embed_features(features)
        await self._save_to_milvus(embedding, features, state["task_id"])

        return state
```

### 7.3 RAGRetrievalAgent

```python
from pymilvus import MilvusClient

class RAGRetrievalAgent:
    """基于 Milvus 的向量检索增强"""

    def __init__(self):
        self.client = MilvusClient(uri="http://milvus-standalone:19530")

    async def run(self, state: GenerationState) -> GenerationState:
        features = state["character_features"]
        query_text = self._features_to_text(features)
        query_embedding = await self._embed_text(query_text)

        # 多路检索
        style_results = self.client.search(
            collection_name="character_style_collection",
            data=[query_embedding],
            limit=5,
            output_fields=["style_name", "generation_params", "tags"]
        )

        param_results = self.client.search(
            collection_name="generation_params_collection",
            data=[query_embedding],
            filter=f'object_type == "{state["task_type"]}"',
            limit=3,
            output_fields=["best_params", "success_rate", "avg_quality_score"]
        )

        material_results = self.client.search(
            collection_name="material_reference_collection",
            data=[query_embedding],
            limit=3,
            output_fields=["material_type", "pbr_params"]
        )

        # 融合检索结果
        retrieved = self._merge_results(style_results, param_results, material_results)
        state["retrieved_context"] = retrieved
        state["generation_params"] = self._build_enhanced_params(features, retrieved)

        return state

    def _features_to_text(self, features: dict) -> str:
        """将特征 JSON 转为检索文本"""
        parts = []
        parts.append(f"角色类型: {features.get('character_type', '')}")
        parts.append(f"性别: {features.get('gender', '')}")
        hair = features.get("hair", {})
        parts.append(f"头发: {hair.get('color', '')} {hair.get('style', '')} {hair.get('length', '')}")
        outfit = features.get("outfit", {})
        parts.append(f"服装: {outfit.get('top', '')} {outfit.get('bottom', '')}")
        parts.append(f"风格: {', '.join(features.get('style_tags', []))}")
        return "; ".join(parts)
```

### 7.4 ModelGenerationAgent

```python
class ModelGenerationAgent:
    """3D 模型生成调度器"""

    ENGINES = {
        "trellis2": Trellis2Service,
        "triposr": TripoSRService
    }

    async def run(self, state: GenerationState) -> GenerationState:
        engine_name = self._select_engine(state)
        engine = self.ENGINES[engine_name]()

        config = {
            "input_image": state["source_image_url"],
            "output_format": state.get("output_format", "glb"),
            "texture_resolution": state["generation_params"].get("texture_resolution", "2048"),
            "mesh_density": state["generation_params"].get("mesh_density", "medium"),
            "pbr_enabled": state["generation_params"].get("pbr_enabled", True),
            "character_params": state["character_features"] if state["task_type"] == "anime_character" else None
        }

        result = await engine.generate_async(config)

        state["generated_model_url"] = result["model_url"]
        state["generated_textures"] = result.get("texture_urls", [])
        state["generation_metadata"] = result.get("metadata", {})

        return state

    def _select_engine(self, state: GenerationState) -> str:
        if state["task_type"] == "anime_character":
            return "trellis2"
        return "trellis2"
```

### 7.5 QualityCheckAgent

```python
import trimesh

class QualityCheckAgent:
    """3D Mesh 质量评估"""

    async def run(self, state: GenerationState) -> GenerationState:
        model_path = state["generated_model_url"]

        # 加载 mesh
        mesh = trimesh.load(model_path)

        checks = {
            "watertight": mesh.is_watertight,
            "manifold": mesh.is_watertight and mesh.is_winding_consistent,
            "face_count_ok": 100 < mesh.faces.shape[0] < 500000,
            "no_degenerate": len(mesh.faces) == len(mesh.faces),
        }

        score = sum(checks.values()) / len(checks)
        state["quality_score"] = score

        if score >= 0.8:
            state["evaluation_result"] = "pass"
        elif state["retry_count"] < 3:
            state["evaluation_result"] = "retry"
            state["generation_params"] = self._adjust_params(state["generation_params"], checks)
        else:
            state["evaluation_result"] = "fail"
            state["error_message"] = f"质量检查未通过: {checks}"

        return state
```

---

## 八、前端页面设计

### 8.1 首页 / 仪表盘
- 顶部导航：Logo、功能入口、用户头像
- 核心 CTA：「上传图片生成 3D」大按钮
- 功能卡片：动漫角色 3D 化 | 物品 3D 建模 | RAG 知识库
- 最近项目列表（缩略图 + 状态标签）
- 统计卡片：本月生成数、成功率、平均耗时

### 8.2 上传与生成页
- 左侧：图片上传区（拖拽/粘贴/URL），上传后预览
  - 可选：自动背景移除开关
  - 可选：生成模式（快速预览 / 高质量）
- 右侧：参数配置面板
  - 输出格式：GLB / OBJ / FBX / STL
  - 纹理分辨率：1K / 2K / 4K
  - 面数控制：低/中/高/自定义
  - 拓扑类型：三角面 / 四边面
  - PBR 材质：开/关
- 底部：提交生成 → 跳转任务详情

### 8.3 任务详情页（实时进度）
- 顶部：任务状态指示器 + 步骤进度条
  - 图片分析 → 知识检索 → 3D 生成 → 质量检查 → 完成
- 中部：实时日志（WebSocket 推送）
- 右侧：智能体工作流可视化（LangGraph 状态流转图）
- 完成后：Three.js 3D 预览器自动加载模型

### 8.4 3D 预览器（核心页面）
- 主区域：Three.js 画布
  - 自动旋转展示
  - 鼠标左键旋转、右键平移、滚轮缩放
  - 线框/实体/材质 三种显示模式
- 左侧面板：
  - 模型信息：顶点数、面数、纹理分辨率
  - 材质球预览（PBR 参数调节）
  - 光照设置：方向光/点光源/环境光
  - 背景切换：纯色/HDRI/透明
- 右侧面板：纹理贴图列表（可单独下载）
- 底部工具栏：下载模型 / 分享链接 / 重新生成 / 格式转换

### 8.5 RAG 知识库管理
- 搜索框：语义检索（输入描述找相似风格/参数）
- 结果卡片：相似度分数、风格预览图、生成参数详情、使用次数/成功率
- 管理功能：添加新知识条目、编辑参数

### 8.6 项目库
- 网格/列表双视图
- 筛选：按类型（角色/物品）、状态、时间
- 批量操作：下载、删除
- 对比模式：2-4 个模型并排 3D 预览

---

## 九、RAG 知识库预置数据

### character_style_collection

| 风格名 | 标签 | 推荐参数 |
|--------|------|---------|
| 日式萌系 | anime, moe, kawaii, large_eyes, pastel_colors | mesh_density=high, texture=4K, pbr=true, face_count=30000-50000 |
| 赛博朋克 | cyberpunk, neon, sci_fi, mechanical, dark | mesh_density=high, texture=4K, pbr=true, emission=true |
| 古风/和服 | traditional, kimono, ancient, floral, elegant | mesh_density=medium, texture=2K, pbr=true, alpha_test=true |
| Q版/SD | chibi, super_deformed, cute, cartoon | mesh_density=low, texture=1K, pbr=false, face_count=5000-10000 |

### generation_params_collection

| 对象类型 | 最优参数 | 成功率 |
|---------|---------|--------|
| 动漫角色-女性-长发 | guidance_scale=7.5, steps=50, simplification=0.3 | 92% |
| 物品-电子产品 | guidance_scale=8.0, steps=60, simplification=0.2 | 88% |
| 物品-家具 | guidance_scale=7.0, steps=45, simplification=0.4 | 95% |

---

## 十、Docker Compose 部署

### 服务清单
- `frontend`：Vue3 + Nginx
- `backend`：FastAPI
- `mysql`：MySQL 8.0
- `milvus-standalone`：Milvus（含 etcd + minio 依赖）
- `redis`：Redis
- `minio`：对象存储
- `celery-worker`：异步任务执行
- `trellis2-service`：3D 生成引擎（GPU 容器，nvidia-docker）

### 环境变量
```env
# MySQL
MYSQL_HOST=mysql
MYSQL_PORT=3306
MYSQL_DATABASE=ai_3d_toolchain
MYSQL_USER=root
MYSQL_PASSWORD=your_password

# Milvus
MILVUS_HOST=milvus-standalone
MILVUS_PORT=19530

# Redis
REDIS_HOST=redis
REDIS_PORT=6379

# 3D 引擎
TRELLIS2_MODEL_PATH=/models/trellis2
TRIPOSR_MODEL_PATH=/models/triposr

# LLM
QWEN_API_KEY=your_key
DEEPSEEK_API_KEY=your_key

# 存储
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=your_key
MINIO_SECRET_KEY=your_key
```

---

## 十一、代码生成规范

1. **完整可运行**：`docker-compose up` 直接启动
2. **类型安全**：后端 Pydantic v2 全链路校验，前端 TypeScript
3. **异步优先**：后端所有 IO 使用 async/await
4. **错误处理**：异常捕获、重试机制、降级策略
5. **结构化日志**：JSON 格式，支持链路追踪
6. **测试覆盖**：pytest 单元测试 + API 测试
7. **自动文档**：FastAPI 原生 OpenAPI
8. **代码规范**：PEP8（Python）+ ESLint + Prettier（Vue）

---

## 十二、额外功能要求

1. **智能体工作流可视化**：前端实时展示 LangGraph 状态流转图
2. **生成参数推荐**：基于 RAG 检索自动填充最优参数
3. **批量生成**：同时提交多个图片任务
4. **模型对比**：同一源图不同结果并排 3D 预览
5. **风格迁移**：3D 模型应用不同风格材质
6. **实时推流**：WebSocket 推送生成进度
