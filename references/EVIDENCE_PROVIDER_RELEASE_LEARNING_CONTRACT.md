# Alpha.7 Master 证据、供应商、发布与学习合同

本文件负责证据、供应商、适用规则、发布与学习的方法和领域字段；当前状态、typed scope、Gate 实例化、Prompt 分层与完成语义以 `ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md` 为准。历史状态只可作为迁移输入，不能覆盖当前合同。

用户可见解释使用 `language_profile.interaction_language`；机器字段、ID 和枚举保持英文。

## 1. 主张类型与证据等级是两条轴

每条会影响决定的外部主张必须同时记录 `claim_kind`、`claim_class` 与 `classification`，不得互相替代。

- `claim_kind`：`GENERAL | LEGAL_OR_PLATFORM | PRECISION_METRIC`，用于触发结构化字段要求；
- `claim_class`：`FACT | SAMPLE_OBSERVATION | SYSTEM_INFERENCE | HEURISTIC | UNKNOWN`
- `classification`：`VERIFIED_OFFICIAL | VERIFIED_PRIMARY_RESEARCH | INDUSTRY_DATA | PLATFORM_SAMPLE | CREATOR_SIGNAL | USER_REPORTED | SYSTEM_INFERENCE | HEURISTIC | UNKNOWN`

事实是来源能够直接支持的内容；样本观察只描述其样本；推断必须展示从证据到结论的推理；经验规则必须可调且可证伪。`VERIFIED_OFFICIAL` 只证明来源身份和原文内容，不自动证明它适用于当前主体、地区、版本或时间。

最低记录：

```yaml
evidence_id: E-###
claim: ...
claim_kind: GENERAL | LEGAL_OR_PLATFORM | PRECISION_METRIC
claim_class: FACT | SAMPLE_OBSERVATION | SYSTEM_INFERENCE | HEURISTIC | UNKNOWN
classification: VERIFIED_OFFICIAL | VERIFIED_PRIMARY_RESEARCH | INDUSTRY_DATA | PLATFORM_SAMPLE | CREATOR_SIGNAL | USER_REPORTED | SYSTEM_INFERENCE | HEURISTIC | UNKNOWN
source:
  publisher: ...
  title: ...
  url: ...
published_at: YYYY-MM-DD | UNKNOWN
effective_at: YYYY-MM-DD | NOT_APPLICABLE | UNKNOWN
checked_at: YYYY-MM-DD
scope:
  jurisdiction: ... | NOT_APPLICABLE | UNKNOWN
  platform: ... | NOT_APPLICABLE | UNKNOWN
  region: ... | UNKNOWN
  audience_or_sample: ... | UNKNOWN
  provider_model_version: ... | NOT_APPLICABLE | UNKNOWN
status: EFFECTIVE | DRAFT | SUPERSEDED | PLATFORM_SPECIFIC | NOT_APPLICABLE | UNKNOWN
basis: ...
metric_definition: ... | NOT_APPLICABLE | UNKNOWN
sample_or_base: ... | NOT_APPLICABLE | UNKNOWN
confidence: LOW | MEDIUM | HIGH
limitations: ...
```

当前性主张必须有 `checked_at`。不能访问原始来源时，明确记录二手来源与局限，不得把摘要升级成原文。

## 2. 适用规则与平台要求必须拆分承担方

凡结论含“必须、禁止、需要登记、需要标识、可发布、不能发布”等要求词，除通用证据字段外，必须记录：

```yaml
actor: CREATOR | PUBLISHER | PLATFORM | SERVICE_PROVIDER | MODEL_PROVIDER | ADVERTISER | OTHER | UNKNOWN
duty: ...
trigger: ...
exceptions_or_conditions: ... | NONE_FOUND | UNKNOWN
```

先识别要求由谁承担，再识别什么事件触发要求。服务提供者、平台、创作者、广告主与发行方的要求归属不得合并。规则适用性不明时，使用 `classification = UNKNOWN` 并创建需要复核的开放问题，不能为了顺畅推进而补全。

核心 Skill 不硬编码某个平台的临时规则、商业激励、登记例外或发布日期结论。项目运行时用当前官方来源建立证据记录；历史示例不得升级为当前规则。

## 3. 精度护栏（Precision Guard）

出现百分比、金额、时长、帧数、样本量、排名、预测日期、估算工期、阈值或“最佳值”时，必须写明：

```yaml
precision:
  value: ...
  unit: ...
  basis: ...
  source_or_evidence_ids: []
  precision_status: USER_STATED | VERIFIED | EXPERIMENT_DESIGN | HEURISTIC | TUNABLE
```

规则：

1. `VERIFIED` 必须能回链当前证据与口径；项目实测必须链接真实观察；公式结果必须在 `basis` 保存公式和可追溯输入。
2. 用户明确给出的预算、截止时间或目标值可记为 `USER_STATED`，但不是市场事实。
3. 试验样本量或门槛可记为 `EXPERIMENT_DESIGN`，同时说明选择依据、预算影响和调整条件。
4. 设计参数可记为 `TUNABLE`，同时标出验证方法；它不是成功阈值。
5. 缺少 `basis + source_or_evidence_ids + precision_status` 时，删除伪精确数字，或把 `precision_status` 降为 `HEURISTIC` 或 `TUNABLE`。
6. 不得凭经验发明“通过率、黄金时长、最佳发布时间、爆款概率、评论提及率、生死线”等门槛。

## 4. 动态供应商注册表

每个候选模型至少包含：

```yaml
provider_id: PRV-###
provider: ...
model: ...
version: ... | UNKNOWN
region: ... | UNKNOWN
access: AVAILABLE | LIMITED | NOT_AVAILABLE | UNKNOWN
access_source_ids: []
price:
  value: ... | UNKNOWN
  currency: ... | UNKNOWN
  billing_unit: ... | UNKNOWN
  tier_or_plan: ... | UNKNOWN
  status: VERIFIED_CURRENT | USER_REPORTED | ESTIMATE | UNKNOWN
  basis: ...
  source_or_evidence_ids: []
  precision_status: USER_STATED | VERIFIED | EXPERIMENT_DESIGN | HEURISTIC | TUNABLE
source:
  publisher: ...
  title: ...
  url: ...
  source_type: OFFICIAL | THIRD_PARTY | USER_REPORTED
checked_at: YYYY-MM-DD | UNKNOWN
project_pilot_status: NOT_RUN | PLANNED | RUN_PARTIAL | PASSED | FAILED | INCONCLUSIVE
classification: VERIFIED_OFFICIAL | USER_REPORTED | SYSTEM_INFERENCE | HEURISTIC | UNKNOWN
modalities: []
capabilities:
  - capability_id: ...
    name: ...
    status: VERIFIED | USER_REPORTED | INFERRED | UNKNOWN
    source_or_evidence_ids: []
    version_scope: ...
    region_scope: ...
strengths: []
weaknesses: []
cost_latency_notes: UNKNOWN
project_observations: []
```

`provider + model + version + region` 共同定义一个能力记录。版本或地区不同不得静默合并。来源必须包含发布者、标题、完整 URL 与来源类型；第三方资料或用户报告不得标为 `VERIFIED_OFFICIAL`。每项 `VERIFIED` 能力都要有该供应商、版本和地区的单独证据，不能从另一家供应商或笼统对比表继承。价格必须带币种、计费单位、套餐、依据、证据、精度状态和核查状态；没有当前来源时保持 `UNKNOWN`。普通 `published_at`、`effective_at` 与 `checked_at` 属于来源追踪日期，不需要重复包装成 precision；只有预测日期、估算工期或会改变决定的数值日期才进入精度护栏。

选择模型必须按资产或镜头任务路由。官方能力说明不是项目 Pilot；关键能力未实测时，供应商条目的 `project_pilot_status` 保持 `NOT_RUN`，或在已安排试验时使用 `PLANNED`，并禁止相应 `GENERATION_READINESS_GATE` 的 `BATCH_PRODUCTION` 资格通过。`project_observations` 只接受真实观察记录的 `OBS-` ID。若供应商 Pilot 标为 `PASSED`，每条支撑观察还必须回链同一 `provider_registry_id`、写明非空 `task_scope` 与 `observed_at`，实际观察可访问的真实产物，且 `basis` 为 `DIRECT_MEDIA_ACCESS` 或 `MEASURED_DATA`。固定 seed 只是一项可复现实验参数，不是人物身份一致性的证据或保证；身份一致性必须由参考资产、约束方式和项目媒体观察共同验证。

核心 Skill 禁止设置永久默认工具栈。示例模型必须明确写为“仅为示例，使用前核查当前版本”，不得据此声称“最新、最强、最便宜或最稳定”。

## 5. 发布前资格与发布后证据

根契约定义的两道关卡不可倒置：

```text
RELEASE_READINESS_GATE（发布前） -> 授权发布动作 -> PUBLICATION_EVIDENCE_GATE（发布后）
```

`RELEASE_READINESS_GATE` 只检查发布前可验证项目：最终媒体、素材许可来源、AI 标识计划、平台格式、文案一致性、必要批准与当前规则核查。未通过时不得把“先公开再看结果”当作验证方法。

`PUBLICATION_EVIDENCE_GATE` 只在实际发布后记录：平台、post/content ID、可访问 URL、发布时间、可见状态、实际标识/metadata、上传结果证据与核查时间。没有这些证据不能使用 `PUBLISHED`。发布页面存在不反向证明发布前内容规范检查已通过。

每条发布记录还必须保存 `artifact_id / artifact_version / release_package_id / release_readiness_gate_id`。`release_readiness_gate_id` 必须指向已经通过、且覆盖同一成片与发布包的 `RELEASE_READINESS_GATE`；发布后证据不能补写或替代发布前资格。

`SIMULATED_EXTERNAL_STEP` 只能证明线路继续；它不能成为 `RELEASE_READY`、`PUBLISHED` 或真实表现学习的证据。

## 6. 真实表现学习记录

每个学习单元必须完整记录：

```yaml
learning_id: L-###
publication_ids: []
analytics_artifact_ids: []
hypothesis: ...
intervention: ...
context:
  platform: ...
  audience: ...
  release_window: ...
  competing_changes: ...
sample:
  unit: ...
  size: ...
  inclusion_rule: ...
outcome:
  metric_definition: ...
  baseline_or_comparator: ...
  observed_value: ...
confidence: LOW | MEDIUM | HIGH
conclusion: INCONCLUSIVE | SUPPORTED | NOT_SUPPORTED | MIXED
reusable: YES | NO | CONDITIONAL | UNKNOWN
real_data_evidence_ids: []
status: LEARNING_PLAN | DATA_COLLECTION_PENDING | DATA_AVAILABLE | LEARNING_DRAFT | LEARNING_VALIDATED
limitations: ...
next_test: ...
```

`publication_ids` 必须回链真实发布记录；`analytics_artifact_ids` 必须回链真实存在的 `DATA` 产物。两者与 `real_data_evidence_ids` 共同约束 `LEARNING_VALIDATED`，不能用计划、模拟数据或无关平台证据替代。

以下都不能单独等同于“成功”：评论提到某元素、点赞增长、单条高播放、一次完播变化或个别用户主观反馈。评论提及只能记为 `CREATOR_SIGNAL` 或 `PLATFORM_SAMPLE` 范围内的定性或计数信号；除非预先定义目标、样本、基线和判定依据，否则不能升级为成功率或因果结论。

没有真实发布和真实数据时，`learning_status = NO_REAL_DATA`；本阶段的执行可另记 `execution_status = NOT_EXECUTED`。有数据但样本或归因不足时，结论为 `INCONCLUSIVE`。这些状态都不是失败，也不能输出可复用规律。

记录级状态与项目级学习轴的映射：有计划无数据时，`learning_record.status = LEARNING_PLAN`、`workflow_status.learning_status = NO_REAL_DATA`；数据收集时，两者相应使用 `DATA_COLLECTION_PENDING`；数据已经可得但归因不足时，记录的 `status` 可为 `DATA_AVAILABLE` 或 `LEARNING_DRAFT`，同时 `conclusion = INCONCLUSIVE`；只有证据、样本、结果与归因达到既定要求时，记录与项目学习轴才可使用 `LEARNING_VALIDATED`。

`LEARNING_VALIDATED` 还必须形成同一证据链：学习记录的 `publication_ids` 已由通过的 `PUBLICATION_EVIDENCE_GATE` 覆盖；`analytics_artifact_ids` 指向真实 `DATA` 产物；这些数据产物与 `real_data_evidence_ids` 有交集；通过的 `LEARNING_GATE` 在 `learning_ids` 中点名该记录，在 `publication_ids` 中覆盖该记录的全部发布，并把该记录的真实数据证据纳入 Gate `evidence_ids`。
