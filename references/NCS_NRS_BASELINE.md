# NCS / NRS 基线说明（Alpha.7 适用）

本文件保留评分方法；真实观察、artifact/version、typed scope 与 Gate 时机遵守 `ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`。

NCS 与 NRS 是**项目内质量控制框架**，不是普遍科学评分，不能脱离项目目标宣称模型或作品具有确定性能优势。

面向中文用户时，维度说明、发现、严重度、修复建议和局限使用中文；NCS/NRS 缩写、时间码、指标字段与配置 key 保持原值。

## 规范状态（相关字段摘录）

```yaml
ncs: NOT_SCORED | scored_object
nrs: NOT_SCORED | scored_object
workflow_status:
  observation_status: OBSERVATION_PENDING | OBSERVED
  qa_status: QA_NOT_EXECUTED | QA_FAILED | QA_PASSED | QA_ACCEPTED_WITH_DEBT
```

没有可访问真实媒体时，NCS 与 NRS 必须是 `NOT_SCORED`。不得用 0 分代替，因为 0 分意味着已经测量且表现为零；也不得给预测分、模拟分、虚构时间码或通过结论。

评分必须属于一条真实 observation，绑定被实际查看的 `artifact_id + artifact_version`、观察时间和 evidence。每条 observation 都显式保存 `artifact_version`；无法核验版本的用户报告使用 `null`。`basis = USER_REPORTED` 的记录不能评分，也不能进入工作流 observation basis。

## NCS 候选维度

- 人物身份一致性；
- 设定与世界规则一致性；
- 叙事状态连续性；
- 空间连续性；
- 动作连续性；
- 视觉风格一致性；
- 对白完整性；
- 参考素材遵循情况；
- 技术有效性。

## NRS 候选维度

- 节拍是否完整；
- 动作开始、峰值与反应的时序；
- 信息释放节奏；
- 动作与反应的平衡；
- 镜头进入与退出质量；
- 情绪曲线；
- 无效停顿控制。

## 评分配置

若项目需要实际分数，必须预先记录：

```yaml
metric_id:
scope:
dimensions: []
weights: []
pass_threshold: null
basis:
source_or_evidence_ids: []
precision_status: USER_STATED | VERIFIED | EXPERIMENT_DESIGN | HEURISTIC | TUNABLE
```

权重、阈值与容差必须根据项目需求和人工复核校准。`HEURISTIC` 或 `TUNABLE` 不能冒充当前事实，也不能自动成为 Gate 失败线。没有预先合法配置时，优先给带证据的定性诊断，不强行造分。

真实评分写入 observation 时使用：

```yaml
ncs_or_nrs:
  value: number
  scale: string
  scoring_config_id: string
  evidence_ids: [E-###]
```

不得只给一个脱离量表、配置和证据的裸分数。

## 使用边界

- 每项发现关联真实可观察证据，视频问题尽量使用时间码；
- 分数只用于同一项目内诊断、版本比较和修复优先级；
- 一个镜头的分数不能外推整批、成片或市场表现；
- 用户报告可作线索，不能冒充系统已观察；
- 模拟线路只列“有媒体时会检查什么”，状态仍为 `NOT_SCORED`；
- 没有真实对比测试时，不得发布性能优越性结论。

## 与 Gate 的关系

NCS/NRS 可以为 `SHOT_GATE` 或 `SEQUENCE_CONTINUITY_GATE` 提供证据，但不会自动决定 Gate。只有实际开始检查时才实例化 Gate，并在 `scope_bindings` 中覆盖同一 artifact/version、shot plan 与 observation；评分 evidence 必须是 observation evidence 的非空子集。Gate 仍需结合项目 requirements、关键 Failure、批准的带债条件和其他真实证据分别评估。
