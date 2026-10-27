# Agent 知识库

这里存放可以被 Agent 检索和人工审核的知识资产。

- `Blender修饰符-Agent建模规范.md`：人类可读的规则、边界和验收清单。
- `backend/app/knowledge_data/blender_modifier_rules.json`：与当前 Milvus 三个集合字段对应的结构化种子数据。
- `blender.mesh.*` 条目：来自 Blender 官方“网格结构”页面，覆盖网格元素、面类型、法线、拓扑流和动态资产兼容性。
- 网格索引扩展：来自 Blender 官方 Meshes 索引，覆盖建模模式、基础体、重网格/重拓扑、网格分析与清理、非流形、法线/着色、对称、拓扑编辑、Shape Key、顶点组、UV/UDIM 和几何数据安全。

结构化数据通过 `python -m app.knowledge_seed` 导入 MySQL 和 Milvus。每条记录包含 `seed_key`、来源、证据类型、适用范围和验证状态；导入器按标题与来源幂等，重复运行会跳过已经存在的条目。
