# Stage 6 — 粗粒度镜头与资产需求图

本阶段的范围完成、Gate 时机与 typed scope 遵守 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`。

资产名称、用途、依赖、缺口与风险说明遵守 `creative_artifact_language`；资产 ID、镜头 ID、文件名和引用 key 保持英文或 ASCII。

## 从已批准内容推导需求

只从 `USER_APPROVED_DECISION`、已锁定创意事实和系统不变量推导强制资产。`PROPOSED` 与 `UNKNOWN` 内容可列为候选或缺口，但不能静默变成必做资产或 Gate requirement。

从当前剧本与粗镜头检查：

- 角色必需视角和身份锚点；
- 服装、情绪、伤势、淋湿和破损状态变体；
- 场景布局、空间拓扑、昼夜、天气和损坏变体；
- 道具归属、持有者、位置、接触和状态变化；
- 生物、车辆、机甲、VFX、图形与声音依赖；
- 变形前后状态；
- 每张参考图承担的控制角色及禁止覆盖项；
- 必须先做 preflight 的高风险镜头；
- 不同画幅是否需要单独的资产视角或构图变体。

不要为“以后也许有用”生成所有可想象资产。只建立叙事确实需要、镜头实际引用或有明确复用价值的资产。

## 稳定 ID 与 shot-local dependencies

每个资产分配稳定 ID，并至少记录：类型、版本、来源、状态、空间位置/归属、使用该资产的 `shot_id`、所需状态变体和依赖。每个镜头反向记录它需要的角色、场景、道具、声音、图形、参考与格式变体 ID。

资产数量必须从 registry 条目重新计算，不得从标题、旧汇总或人工印象推断。进入 preflight 前检查：

- 缺失、重复或悬空 ID；
- 镜头引用了未注册的局部道具、背景人物、UI、声音或图形；
- 同一资产在不同文档中的空间、归属或状态冲突；
- 资产版本与镜头引用版本不一致；
- 计划淘汰的资产仍被下游引用。

## 上游完整性输出

本阶段交付 `asset_registry_spec` 和 `shot_dependency_map`。只要存在未登记引用、重复 ID 或数量冲突，记录 `workflow_status.spec_status = SPEC_DRAFT`；只有已获准且排队等待执行时才记录 `workflow_status.execution_status = EXECUTION_PENDING`。若本 scope 文本完整，可创建 `scope_type = ASSET_REGISTRY_SPEC` 的 completion record；它不能覆盖后续分镜、MASTER、Provider 编译 Prompt 或生产计划。只有真实执行过对应资格评估时，blocker 才进入 `EXECUTED + BLOCKED` Gate；否则只记开放问题与下一步。

资产需求图是规格，不是实际资产。没有真实文件时不实例化 `ASSET_GATE`，也不声称失败或通过；待真实资产可访问并开始评估后再创建同 scope Gate。
