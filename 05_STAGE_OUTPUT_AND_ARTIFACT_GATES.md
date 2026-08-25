# 阶段输出、完成范围与产物关卡

本文件说明阶段交付与关卡使用方法。Alpha.7 的规范字段、typed scope、scoped completion 和真实性关系统一以 `references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md` 为准；年龄受保护角色、四层 Prompt、供应商能力、字幕/TTS coverage 与文字模拟补充规则见 `references/AGE_SAFETY_PROVIDER_AND_COVERAGE_CONTRACT.md`。

## 用户可见输出

先读取 `output_complexity_profile`，不要机械展示固定十一栏。

- `CREATOR_SIMPLE`（默认）：结论、当前真实状态、推荐方案、真正需要用户处理的 1—4 件事；
- `CREATOR_STANDARD`：可增加紧凑的分镜、资产、状态或风险表；
- `PRO_AUDIT`：可展开完整 ID、Evidence、Gate、Prompt coverage、Schema 与验证轨迹。

银幕盲点允许 0—3 个，银幕洞察允许 0—1 条；没有合格候选就不输出。面向中文用户的标题、解释、问题与行动使用自然简体中文，机器 key、ID 和枚举保持英文。

## 阶段结果对象

阶段结果是当前状态的用户可见摘要，不是另一套状态账本。它至少要与顶层六轴、basis、终点和引用记录一致：

```yaml
stage:
result:
output_locale: zh-CN
execution_mode: REAL | SIMULATION
workflow_status:
  spec_status: SPEC_DRAFT | SPEC_READY
  execution_status: NOT_EXECUTED | EXECUTION_PENDING | EXECUTING | EXECUTED_FAILED | EXECUTED_SUCCEEDED | SIMULATED_ONLY
  observation_status: NOT_APPLICABLE | OBSERVATION_PENDING | OBSERVED
  qa_status: NOT_APPLICABLE | QA_NOT_EXECUTED | QA_FAILED | QA_PASSED | QA_ACCEPTED_WITH_DEBT
  publication_status: NOT_PLANNED | RELEASE_NOT_READY | RELEASE_READY | PUBLISH_PENDING | PUBLISHED | PUBLICATION_FAILED
  learning_status: NO_REAL_DATA | DATA_COLLECTION_PENDING | DATA_AVAILABLE | LEARNING_DRAFT | LEARNING_VALIDATED
  status_basis:
    execution_artifact_ids: []
    observation_ids: []
    qa_gate_ids: []
    release_gate_ids: []
    publication_ids: []
    learning_ids: []
terminal_markers: []
evidence_ids: []
real_artifact_count: 0
unknowns: []
recommendation:
gate_ids: []
decisions: []
decision_scope_diff:
artifacts: []
open_blocking_issue_ids: []
blindspots: []
insight:
next_action:
```

`gate_ids` 只能引用已实例化且真实执行过的 Gate。`real_artifact_count` 从当前真实 artifact 确定性重算。状态、basis、终点或计数与顶层不一致时，阶段结果无效；不能用用户叙述字段覆盖机器事实。

`project_route`、`task_graph`、`execution_receipts` 与 `fourfold_preflight_records` 始终保留在顶层规范记录中，不复制成阶段内的平行账本。阶段结果只能摘要它们已经证明的事实：任务成功不自动等于项目执行完成，回执成功不自动等于媒体已观察，预检通过也不自动等于发布准备关卡通过。所有任务由唯一总调度排依赖、授权和恢复点，外部能力不得自行推进项目状态。

## 新文字产物先登记

任何新建或实质改写、并被下游引用的文字产物都先登记到现有 `artifacts[]`：使用 `artifact_class = TEXT_SPEC`，保存稳定 ID、`status = SPEC_DRAFT | SPEC_READY`、版本、依赖和 `content_locator.sha256`。哈希在最终字节保存后计算；内容改变即升级版本并重算，旧 completion、Prompt、预检或 Gate 不自动继承。只在聊天中出现的文字、没有哈希的文件名或旧版本摘要不能成为下游规范输入。

## 范围化文字完成（Scoped completion）

项目级 `spec_status` 不使用 `TEXT_SPEC_COMPLETE`。某份剧本、资产规格、分镜、MASTER Prompt 包、Provider 编译 Prompt 包或发布规格文字完成时，创建指向明确 `scope_ids + source_spec_version` 的 `spec_completion_record`，并写清它不声称哪些执行、观察、QA、发布或学习事实。

同一份完成记录不能跨版本或顺带覆盖相邻产物。它必须回链当前对象最终通过的验证尝试；开放的本 scope 文字 blocker 会阻止该记录，但“还没有真实媒体”应写入 `does_not_claim`，不伪装成文字 blocker。

创建 completion 前还要确认 `scope_ids` 对应的文字 Artifact 已有当前 `status + version + content_locator.sha256`。Artifact 登记、`SPEC_READY` 与 `TEXT_SPEC_COMPLETE` 分别表示“对象存在”“规格可继续使用”“被点名 scope 已完整”，不得互相代替。

## 标准关卡依赖链

1. `GENERATION_READINESS_GATE`：能否开始 `MICRO_PILOT`，以及是否具备 `BATCH_PRODUCTION` 资格；
2. `ASSET_GATE`：真实资产及其身份、结构、来源、版本与状态；
3. `SHOT_GATE`：真实镜头的动作、物理、叙事功能、技术质量与起止状态；
4. `SEQUENCE_CONTINUITY_GATE`：真实剪接序列的连续性、节奏、状态继承、声音视点与总时长；
5. `FINAL_ARTIFACT_GATE`：最终成片和必需交付件；
6. `RELEASE_READINESS_GATE`：发布前素材许可、内容规范、标识、包装、账号、授权与回滚条件；
7. `PUBLICATION_EVIDENCE_GATE`：发布后真实链接、平台呈现、时间、版本和可访问证据；
8. `LEARNING_GATE`：真实数据达到预先定义的样本、窗口与口径后，验证学习结论。

这是一张依赖图，不是 Gate inventory。只有已经对明确对象执行评估时才创建记录。未来可能进入的 Gate 只写在 `next_action`；没有真实媒体时，不实例化依赖媒体的 Gate，不创建空 requirement，也不写“未执行 Gate 失败”。

四重预检不是新 Gate：它在 `EARLY / IN_PROCESS / FINAL` 三个检查点保存自然表达、内容规范、素材许可和传播准备记录。`FINAL` 必须绑定最终产物的精确版本与 SHA-256；内容规范或素材许可为 `BLOCKED` 时，总结论必须保持 `BLOCKED`。四项 `PASS` 仍只为同 scope 的 `RELEASE_READINESS_GATE` 提供证据，不能直接写成 `RELEASE_READY`。

## 已执行 Gate 对象

```yaml
gate_id: G-###
gate_type: GENERATION_READINESS_GATE | ASSET_GATE | SHOT_GATE | SEQUENCE_CONTINUITY_GATE | FINAL_ARTIFACT_GATE | RELEASE_READINESS_GATE | PUBLICATION_EVIDENCE_GATE | LEARNING_GATE
readiness_scope: null | MICRO_PILOT | BATCH_PRODUCTION
scope: 中文显示摘要
scope_bindings:
  artifact_ids: []
  artifact_versions: []
  release_package_ids: []
  provider_registry_ids: []
  pilot_ids: []
  shot_plan_ids: []
  prompt_ids: []
  observation_ids: []
  task_scope: null
  format_scope: null
  version_scope: null
evaluation_status: EXECUTED
outcome: PASSED | FAILED | BLOCKED | ACCEPTED_WITH_DEBT | NOT_APPLICABLE
requirement_ids: []
requirement_results: []
evidence_ids: []
publication_ids: []
learning_ids: []
blocking_issue_ids: []
evaluated_at: timestamp
acceptance_debt: null
```

`scope` 不参与授权；真正的授权、版本和证据适用性只认 `scope_bindings`。所有 ID 必须解析，且 Gate 类型要求的对象范围非空。`GENERATION_READINESS_GATE` 使用 `MICRO_PILOT | BATCH_PRODUCTION`，其他 Gate 的 `readiness_scope = null`。

- `PASSED`：每条强制要求均被适用真实证据满足；
- `FAILED`：已检查且证据表明要求不满足；
- `BLOCKED`：评估已经发生，但必要依赖或决定阻断结论；
- `ACCEPTED_WITH_DEBT`：有精确风险、影响、批准事件与重访条件；
- `NOT_APPLICABLE`：有证据证明该 Gate 对当前 scope 不适用，不是“尚未做”。

返工、先测试、请求决定或回滚属于 `recommendation / next_action`，不是额外 Gate 结果码。

## 关卡要求的合法来源

```yaml
requirement_id: GR-###
gate_id: G-###
description: string
requirement_source: SYSTEM_INVARIANT | USER_APPROVED_DECISION | VERIFIED_EVIDENCE | APPLICABLE_RULE
source_id: string
invariant_id: INV-... | null
mandatory: true
```

`SYSTEM_INVARIANT` 只能引用当前不变量注册表。`PROPOSED`、`UNKNOWN`、系统偏好、未验证推荐和示例参数不能成为强制 requirement。

执行关卡时，`requirement_results` 与 `requirement_ids` 逐项覆盖。每项结果 evidence 是 Gate evidence 的子集；要求来自 `VERIFIED_EVIDENCE` 或 `APPLICABLE_RULE` 时，`source_id` 必须进入该项结果证据。`PASSED` 时所有 mandatory requirement 都为 `SATISFIED`，不能用一条无关证据证明整关。

`PUBLICATION_EVIDENCE_GATE` 通过时必须绑定同一 scope 的 publication。`LEARNING_GATE` 通过时同时绑定 learning 与 publication，并覆盖学习记录的真实数据证据。

## 上游完整性检查

进入 Provider 编译、批量生成或创建任何 scoped completion 前，按目标 scope 重新计算：

- 每个镜头有稳定 `shot_id`；
- 镜头引用的角色、场景、道具、声音、图形、参考和格式 ID 均已登记且版本存在；
- 当前 Gate scope 中每个 ASSET/SHOT 生成目标与 generation role 有同目标版本的 MP、TP 与 NEP；需要真实执行时还有同时回链三者并绑定当前 provider 的 `PROVIDER_COMPILED`；
- 每个不生成镜头有真实 `no_generation_reason`；
- 当前 Pilot/批次 target keys、MP/TP/NEP coverage 与 Provider 编译 coverage 分别按本 scope 核对；局部 Prompt Pilot 不强迫全片目标预建四层空壳，任何中间层都不能冒充编译层；
- `PROVIDER_COMPILED` 使用的时长、版本、入口、地区、task 与输入方式都有适用 `capability_evidence_ids`，不继承其他 provider/surface 的限制，也不硬编码“15 秒”；
- 涉及已判定的年龄受保护角色时，`minor_safety_profile_ids` 解析到 `is_minor=true` 的当前 profile，并使用唯一 `minor_compilation_mode = EXACT | LIFE_STAGE | REFERENCE_BOUND`；`compiled_age_years / compiled_life_stage` 不回写事实层，表达层不得改变年龄事实。年龄未判定时保持资产 `subject_age_class = UNKNOWN`，不得预设年龄类别；
- 复杂年龄受保护角色/成年角色同镜已选择 `minor_adult_same_shot_strategy = DECOMPOSITION | COMPOSITE`，并重新计算派生镜头、依赖、时长与 Prompt coverage；
- 受保护未知项、数量语义与因果边界双向登记并审计；
- 逐镜时长之和与当前 `canonical_duration` 一致，或有来源、批准和适用范围明确的容差；
- 下游引用上游当前版本；
- 没有被下游状态掩盖的开放 blocker；
- Reference Registry 中所有引用均能解析且控制职责没有越界。

进入后期 scoped completion 前，还要从当前 `dialogue_inventory` 核对 `subtitle_cues` 的 `dialogue_id / shot_plan_id / shot_id / timing_spec_version`，确保漏句、孤立句和重复 cue 均为空。仅完成 TTS 文字规格时必须写 `tts_coverage_status = NONE`；`PARTIAL / FULL` 的每个 `covered_dialogue_id` 都必须逐条绑定同版本 `MEDIA` Artifact，且 `FULL` 要求 covered 与 scope 完全相等。真实音频、实测时长和聚合值另由 `measured_dialogue_ids / measured_duration_seconds` 计算 `measurement_coverage_status = NONE | PARTIAL | FULL`；任一真子集都不能写成全片覆盖。

不满足时保持 `SPEC_DRAFT` 或缩小可安全完成的 scope。已获准且只是排队等待执行才使用 `EXECUTION_PENDING`。不要为了显示流程进度而实例化未来 Gate。

## 生成资格不是媒体验收

- `MICRO_PILOT` 评估开始最小代表性试制所需的规格、输入、provider、权限、预算、安全条件、观察方法和停止条件；它不要求先拥有最终媒体；
- `BATCH_PRODUCTION` 需要与 typed scope 匹配的代表性 Pilot、完整资产/镜头依赖、Provider 编译 Prompt coverage、可用供应商、格式、预算与修复负担证据；
- 第一轮 Pilot 不需要先通过 `ASSET_GATE` 或 `SHOT_GATE`；这些 Gate 等真实媒体出现并被检查后才实例化；
- Pilot、资产、镜头、序列、成片、发布准备、真实发布与学习是不同事实，不能互相代替。

## 产物真实性层级

`SPEC_DRAFT → SPEC_READY → REAL_ARTIFACT_AVAILABLE → OBSERVED → VALIDATED → LOCKED`

并非每种产物都要锁定。真实产物不能跳过存在、观察和适用范围验证。剧本、资产表、分镜、MASTER 或 Provider 编译 Prompt 包只能证明其文字规格，不证明媒体、视觉 QA、剪辑、发布或学习。

## 时长与多格式护栏

- 项目只保留一个当前权威 `canonical_duration`，镜头变化后重新求和；
- 供应商单次时长、可选档位或上限只从绑定当前 provider/model/version/surface/region/task 的能力证据读取；没有证据时保持 `UNKNOWN`；
- 禁止把“15 秒”或任一平台曾经显示的时长写成跨供应商、跨版本或跨入口默认值；
- 没有已批准且有来源的容差时，不设默认百分比；
- “每镜可调整 N 秒”必须逐镜计算总范围；
- 共享一次渲染需要安全区、构图、动作和可读性的同 scope 证据；
- 不同格式若需要不同机位、人物位置、动作或信息层级，就建立单独变体与必要 Pilot。

## 模拟与终点真实性

线路测试跳过外部步骤时记录 `SIMULATED_EXTERNAL_STEP`，写明请求动作、跳过原因、真实输入与预期产物。只有确实执行了这类模拟，阶段 `execution_mode = SIMULATION` 且 `execution_status = SIMULATED_ONLY`；如果只是写完文字、从未模拟外部步骤，执行仍为 `NOT_EXECUTED`。模拟可以继续逻辑设计，但不能创建媒体观察、NCS/NRS、视觉 QA、发布或学习证据。

文字线路走到末端时，用带状态、版本和哈希的文字 Artifact 与 scoped completion 说明哪些对象完整，并保持 `terminal_markers: []`。若确有模拟，其他轴保持 `OBSERVATION_PENDING / QA_NOT_EXECUTED / RELEASE_NOT_READY / NO_REAL_DATA`；若没有模拟，除 `execution_status = NOT_EXECUTED` 外边界相同。`REAL_PRODUCTION_COMPLETE` 只在真实资产、镜头、序列、成片和发布前交付按命名范围通过时成立；真实发布与学习仍需各自证据链。

本版本的自动化终点是 `RELEASE_READY`：可以产出发布包、标题、封面文案与检测报告，但不会创建自动上传或发布任务。用户之后手工发布时，只有可访问的链接、内容版本和平台证据完成核对，才可只读登记 publication；发布计划、按钮可见或模拟回执都不能产生 `PUBLISHED`。

## 必须阻止声明或锁定的情况

- 无真实证据却声称 `PASSED`、`VALIDATED` 或 `REAL_PRODUCTION_COMPLETE`；
- 用户只说“继续”却创建批准；
- 把 `PROPOSED` 或 `UNKNOWN` 写成强制 requirement；
- Gate 只靠自由文本 scope、无关 evidence 或相邻版本通过；
- 有开放 blocker，或下游引用错误上游版本；
- 资产、镜头、Reference 或 Prompt coverage 对不上；
- 保存了新的文字产物，却没有当前 Artifact 状态、版本和 SHA-256；
- MASTER 被直接当成 Provider 执行 Prompt；
- TP 或 NEP 被当成可执行 Prompt，或 Provider 编译没有适用的版本/入口/时长能力证据；
- 年龄受保护角色的年龄事实被改变，或年龄来源被丢弃；
- 复杂同镜未拆解/合成且没有适用能力证据，却被标为可直接单次生成；
- 字幕与当前 shot plan 对不上、存在漏句，或 TTS 部分覆盖被写成 `FULL`；
- `canonical_duration` 与逐镜重算冲突且无合法容差；
- 多格式需要不同机位却声称只裁切；
- 计划中的修复、QA、发布或学习被写成已执行；
- 验证器曾拒绝但 `state_cleanup` 删除了拒绝与修正轨迹。
