# Blender 修饰符 Agent 建模规范

## 来源和边界

- 权威来源：[Blender 5.2 LTS 修饰符简介](https://docs.blender.org/manual/en/latest/modeling/modifiers/introduction.html)
- 资料类型：官方软件行为和界面规则。
- 可信度：高。
- 适用范围：人物图片到 3D 的建模规划、修饰符堆栈记录、应用决策和生成后验收。
- 不包含：人体测量、图片版权、生成引擎成功率、角色面数预算和纹理分辨率的实测结论。

## Agent 必须遵守的规则

### 1. 默认保持非破坏性

修饰符一般只影响对象的显示和渲染结果，不直接改写可编辑的基础几何体。Agent 默认保留基础网格和修饰符堆栈，并记录每个修饰符的类型、顺序、参数、对象名和 Blender 版本。

只有在导出目标要求烘焙、下游软件不支持修饰符或必须交付最终拓扑快照时，才建议应用。应用前保存版本，应用后重新检查拓扑、UV、材质、法线、骨骼和导出结果。

### 2. 堆栈顺序是结果的一部分

修饰符从堆栈上到下计算，调换顺序可能改变模型结果。Agent 输出建模方案时必须同时输出：

```json
{
  "ordered_stack": [
    {"type": "MIRROR", "purpose": "保持基础网格左右对称"},
    {"type": "SUBSURF", "purpose": "平滑曲面"}
  ],
  "order_is_verified": false,
  "verification_scope": "目标角色、目标 Blender 版本和目标导出格式"
}
```

## 网格结构知识（官方来源）

- 权威来源：[Blender 5.2 LTS 网格结构](https://docs.blender.org/manual/en/latest/modeling/meshes/structure.html)
- 资料类型：网格元素、法线、着色和拓扑概念。
- 可信度：官方软件行为为高；由此形成的人物建模取舍仍需项目实测。

### 6. 记录网格的三类基本元素

网格由顶点、边和面构成。顶点是三维坐标点，边连接两个顶点，面构成可渲染表面。Agent 验收时应分别记录顶点数、边数和面数，并确认需要显示的区域确实有面覆盖；物体原点不能当作顶点。

### 7. 动画与细分优先审查四边面流

官方手册指出三角形始终平面且便于计算，四边形通常更适合变形和细分。人物面部、肩膀和膝盖等高变形区域可以把连续四边面流设为项目优先策略，但这不是硬性规则；三角形或 n 边形的存在本身不等于失败，必须通过姿势、细分和导出结果判断。

### 8. 法线和着色属于生成结果的一部分

法线影响光照和阴影。平面着色与平滑着色的意图应随资产记录，并在目标材质和渲染器中检查阴影伪影。对于游戏或低多边形资产，可考虑自定义分割法线，但必须记录法线数据粒度、导出格式、导入器和 Blender 版本，不能假设所有格式都保留它。

自由法线是对象空间方向向量，评估高效且不依赖拓扑，但不会在修改器或动画变形时自动更新。因此动态人物默认不采用自由法线，除非明确是静态展示并完成渲染验证。

### 9. 用边环、面环和极点审查人物变形

边环和面环描述连续的拓扑流，合理的边环有助于有机建模、细分和角色动画。极点是连接三条、五条或更多边的顶点，可能使环终止。Agent 应审查脸部、嘴部、眼周、肩膀和膝盖的环连续性、极点位置、细分表现和姿势变形；不能仅因存在极点就判定模型失败。

新增结构化条目：`blender.mesh.elements.v1`、`blender.mesh.quad_animation.v1`、`blender.mesh.normals_shading.v1`、`blender.mesh.custom_normals_pipeline.v1`、`blender.mesh.free_normals_static_only.v1`、`blender.mesh.loops_poles_character.v1`。上述条目均以官方页面为来源，项目化判断标记为 `project_strategy` 或 `needs_validation`。

## 网格索引扩展知识（官方来源）

- 来源：[Blender Meshes 索引](https://docs.blender.org/manual/en/latest/modeling/meshes/index.html)
- 资料类型：网格建模流程、工具行为、验收工具、UV、属性和绑定前置条件。
- 可信度：官方软件行为为高；涉及人物流程取舍的项目策略仍标记为 `project_strategy`。
- 本次新增条目前缀：`blender.mesh.*`。

### 10. 阶段化网格流程

网格建模通常先用基础体阻塞外形，再增加细节。Object Mode 管对象、合并和属性层，Edit Mode 做多边形编辑，Sculpt Mode 用笔刷变形。Agent 必须把阶段和模式写入生成计划；雕刻结果不能未经清理和重拓扑就直接进入绑定。

### 11. 基础体与重网格的边界

基础体选择应记录类型、分段、封口、尺寸和是否生成 UV。Quad Sphere 适合雕刻和细分候选，UV Sphere 要检查极点，Icosphere 是均匀三角网格，Plane/Grid 是无厚度表面。

Voxel 重网格适合雕刻准备、打印清理或物理替身；Quadriflow 更适合细分或多分辨率准备。重网格只处理原始网格，会忽略修改器和 Shape Key，也不能用于 MultiResolution 对象。官方手册明确自动重网格不适合需要变形的动画人物拓扑；这类资产必须手动重拓扑。

### 12. 分析、清理和非流形检查

Mesh Analysis 主要面向 3D 打印，不能把 Overhang/Thickness 通过当作人物渲染或绑定通过。Agent 按用途检查 Intersections、Distortion、Sharp Edges、拓扑流和变形。

清理前必须保存拓扑快照。Delete Loose、Decimate、Degenerate Dissolve、Merge by Distance、Fill Holes 等操作要按问题类型选择；使用自定义分割法线和平滑着色时，Merge by Distance 需检查 Sharp Edges 保持。清理后复查非流形、孤立几何、退化面、孔洞、法线、UV 和 Shape Key/绑定。

非流形要分类计数：Wire、Boundary、Multiple Faces、Non Contiguous、Loose Geometry 和 Interior Faces。未预期的 Wire、Multiple Faces 和 Interior Faces 是阻断项；Boundary 或 Pole 可以是设计结果，不能仅凭存在判失败。

### 13. 法线、着色、对称和拓扑编辑

法线修复先处理面朝向，再处理自定义分割法线。Flip 和 Recalculate Outside/Inside 不影响 Custom Split Normals。平滑/平面着色与 Sharp 标记应按脸部、皮肤、服装、硬表面等区域记录。

对称工具要区分用途：小漂移用 Snap to Symmetry，缺半边用 Symmetrize，可编辑流程优先考虑 Mirror Modifier。Interactive Mirror 可能翻转法线；Topology Mirror 需要至少一个镜像轴，且简单网格可能不稳定。

Loop Cut、Subdivide 和 Bridge Edge Loops 都会改变拓扑或连接关系。Agent 必须记录选择模式、目标环/边/面、参数、UV 修正、新增拓扑和法线/材质影响；Bridge 会删除选中面。

### 14. Shape Key、顶点组与几何数据安全

Propagate to Shapes 会把选中顶点位置覆盖到所有 Shape Key，只适合共享结构修正；表情专属区域必须逐形状复核。Blend from Shape 要记录 Blend 值和 Add 模式。

顶点组权重范围是 0-1；Deform Groups 通常要求变形权重相加为 1。绑定前检查骨骼映射、未分组顶点、锁定组和关键关节权重。

Color Attribute 有 Vertex/Face Corner 域和 Color/Byte Color 类型。空间重排顶点不改变可见几何，但会改变顶点和面索引，可能破坏 Shape Key、UV、外部脚本和绑定；动画资产默认禁止。

### 15. UV 和 UDIM

网格默认不自带 UV，应在几何基本稳定后展开。一个网格可以有多张 UV 图，Active Render 图用于渲染和未显式指定时的默认采样。Agent 记录 UV 图名称、用途、覆盖面和 Active Render 状态。

接缝越多通常拉伸越小，但纹理绘制更难；目标是少接缝、少拉伸、藏在低可见区域。对称人物可沿镜像轴接缝以共享纹理空间。复杂模型可分区展开、Pack Islands、检查拉伸；UDIM 只在目标渲染器、引擎和导入导出链路确认支持后使用。

新增条目包括：`blender.mesh.workflow_modes.v1`、`blender.mesh.primitive_selection.v1`、`blender.mesh.remesh_policy.v1`、`blender.mesh.retopology_pipeline.v1`、`blender.mesh.mesh_analysis_policy.v1`、`blender.mesh.cleanup_pipeline.v1`、`blender.mesh.non_manifold_review.v1`、`blender.mesh.normal_repair_policy.v1`、`blender.mesh.shading_edges_policy.v1`、`blender.mesh.symmetry_policy.v1`、`blender.mesh.topology_edit_operations.v1`、`blender.mesh.mesh_edit_tool_settings.v1`、`blender.mesh.shape_key_edit_policy.v1`、`blender.mesh.vertex_groups_rigging.v1`、`blender.mesh.uv_timing_and_maps.v1`、`blender.mesh.uv_seams_stretch.v1`、`blender.mesh.uv_layout_and_udims.v1`、`blender.mesh.geometry_data_policy.v1`。

Mirror 和 Subdivision Surface 的相对顺序必须用目标结果验证，不能把示例顺序当成普适定律。

### 3. 先判断是否改变拓扑

官方分类可以作为决策入口：

| 分类 | Agent 关注点 |
|---|---|
| Edit | 顶点组等数据是否满足后续权重和变形要求 |
| Generate | 是否增加或改变网格拓扑，是否影响 UV、Shape Key、绑定和导出 |
| Deform | 通常只改变形状，可作为 Shape Key 或绑定流程候选，但仍要检查结果 |
| Simulation | 视为物理或粒子模拟依赖，单独记录模拟状态和烘焙要求 |

只要拓扑影响未知，就按“需要人工复核”处理，不自动假设拓扑保持不变。

### 4. Shape Key 需要拓扑前置检查

只有不影响拓扑的修改器结果，才允许自动保存或应用为 Shape Key。以下情况必须阻止自动保存：顶点数变化、面连接变化、修改器拓扑影响未知。面部表情和身体校正应先做拓扑快照对比。

### 5. 区分编辑模式、视口和渲染状态

生成验收必须记录并比较 `show_in_editmode`、`show_viewport`、`show_render` 和 `show_on_cage`。视口中看到的结果不能直接等同于最终渲染或导出结果。

## 人物候选模板

下面是项目起始策略，不是 Blender 官方规定，必须用项目模型做实测后才能升级为“已验证模板”。

```json
{
  "body_candidate": ["MIRROR", "SUBSURF", "ARMATURE"],
  "clothing_candidate": ["MIRROR", "SOLIDIFY", "BEVEL", "WEIGHTED_NORMAL", "ARMATURE"],
  "evidence_status": "project_template_pending_empirical_validation"
}
```

服装模板需要重点检查实体厚度、穿插、非流形、法线、骨骼变形和导出兼容性。身体模板需要重点检查对称、拓扑、面数、骨骼变形和视口/渲染一致性。

## 生成后验收清单

1. 堆栈顺序与生成记录一致。
2. 视口、编辑模式和渲染开关符合目标。
3. 拓扑变化符合预期，Shape Key 和绑定没有被破坏。
4. 不存在未处理的非流形、退化面和明显穿插。
5. 法线、UV、材质、面数、纹理分辨率和导出格式满足任务配置。
6. 缺少检查数据时返回 warning 和人工复核状态，不能声称模型已通过。

## 给生成 Agent 的输出约束

Agent 每次引用本知识时，应在结果中区分：

- `official_rule`：来自 Blender 官方手册的规则。
- `project_strategy`：本项目候选模板，必须标记验证状态。
- `empirical_result`：只有来自项目真实生成和验收记录时才允许填写。
- `unknown`：资料不足时保留未知，不编造参数或成功率。

推荐的引用字段：

```json
{
  "knowledge_source": "blender.modifier.stack_order.v1",
  "source_url": "https://docs.blender.org/manual/en/latest/modeling/modifiers/introduction.html",
  "evidence_type": "official_rule",
  "confidence": "high",
  "requires_validation": true
}
```
