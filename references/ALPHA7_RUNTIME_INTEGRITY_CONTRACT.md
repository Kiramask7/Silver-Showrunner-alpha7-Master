# Alpha.7 运行时完整性契约

本文件是 Alpha.7 关于状态、范围、证据、关卡、Prompt、纠错轨迹和用户呈现的当前规范源。各阶段与引擎负责说明“怎样工作”；机器字段与跨记录真实性以本契约、Alpha.7 Schema 和验证器为准。历史输入与本文件冲突时，以本文件为准。

## 0. 唯一总调度与四类顶层记录

银幕总控是唯一调度者，只维护一份 Project State、决定账本和证据链。模型、浏览器、API、本地脚本、剪辑器及第三方 Skill 都是被路由能力，不能另建平行状态、私自批准决定或用自己的“完成”覆盖项目六轴。

### `project_route`

每个项目必须有一个当前路由，明确项目类型、`FICTION / NONFICTION / MIXED`、叙事规模、目标交付件、来源忠实要求和主要来源产物。非虚构与混合项目必须启用来源忠实保护。`USER_APPROVED` 路由回链明确决定，`VALIDATED` 路由回链适用证据；模型推荐只能保持 `PROPOSED`。

### `task_graph`

任务图是有向无环图。任务输入输出均绑定产物版本，并按需要回链前置任务、批准、Provider、导演母版、内部转换计划、中性执行稿、Provider 编译 Prompt、回执、阻断项和恢复检查点。对 `IMAGE_GENERATION / VIDEO_GENERATION / IMAGE_TO_VIDEO / VIDEO_TO_VIDEO`，进入 `READY / RUNNING / EXECUTED_FAILED / EXECUTED_SUCCEEDED` 时必须写非空结构化 `generation_targets[]`；每项绑定 `target_type + target_id + generation_role + generation_medium + provider_prompt_ids[]`，全部 Prompt 展平后必须与任务级 `provider_prompt_ids` 完全相等。`ASSET` 目标不得伪造 `shot_id`；`SHOT` 目标的派生 `shot_ids` 必须与其目标集合一致。同一叙事镜头需要“先首帧、后图生视频”时，分别登记 `SHOT_KEYFRAME / SHOT_START_FRAME` 的 `IMAGE` 目标与 `SHOT_MOTION` 的 `VIDEO` 目标，并让后者显式消费已登记的上游图像 artifact/version。`task_scope` 只作人读说明，不能解析为执行对象、补足结构化目标或扩大授权；执行回执与 compiled Prompt 的回链仍分别严格核验。下游不能消费未完成上游；某个任务 `EXECUTED_SUCCEEDED` 只证明该任务成功，不自动改变项目执行、观察、QA 或发布状态。当前任务类型不包含自动发布。

### `execution_receipts`

真实或模拟的外部动作分别记回执，并与任务双向引用。新回执显式写 `execution_domain = PRODUCTION_MEDIA | LOCAL_VALIDATION | LOCAL_TEXT_TOOL`；旧回执只按 task type 做窄范围兼容推断。真实本地预检或文字工具成功只证明该动作，不能输出 `MEDIA / PACKAGE`，也不能升级项目媒体执行、Observation、媒体 QA 或 release。生产媒体成功才要求真实媒体输出。

生成任务处于 `RUNNING / EXECUTED_FAILED / EXECUTED_SUCCEEDED` 时只能引用 `PROVIDER_COMPILED`，并分别绑定真实 `RUNNING / FAILED / SUCCEEDED` 生产媒体回执；task、route、provider snapshot、compiled Prompt 与 source spec version 必须一致，失败还须有结束时间、失败证据和原因。`PLANNED / BLOCKED / READY` 才可尚无执行回执。`SIMULATED_ONLY` 不得引用真实输出，也不能触发 Observation、NCS/NRS 或媒体 Gate。登录、验证码、支付、账号授权和不可逆动作必须记录授权边界；未经明确授权不得继续。

### `fourfold_preflight_records`

三阶段四重预检使用 `EARLY / IN_PROCESS / FINAL`，分别检查自然表达、内容规范、素材许可与传播准备。每条记录绑定明确产物版本；`FINAL` 还必须绑定 SHA-256 并以真实模式执行。内容规范或素材许可阻断不能被自然表达分、传播分或总分抵消；传播检查的边界固定为 `READINESS_NOT_OUTCOME_PROBABILITY`。

## 1. 完成必须指向明确对象

项目级 `workflow_status.spec_status` 只表示规格体系是否仍有缺口：

```yaml
spec_status: SPEC_DRAFT | SPEC_READY
```

`TEXT_SPEC_COMPLETE` 不是项目级终点。只有一个被点名、带版本的规格对象完成时，才创建 `spec_completion_records`：

```yaml
completion_id: SC-###
scope_type: REVIEW_PACKAGE_ARTIFACT | STORY_ARTIFACT | ASSET_REGISTRY_SPEC | SHOT_PLAN | MASTER_PROMPT_PACKAGE | PROVIDER_COMPILED_PROMPT_PACKAGE | RELEASE_SPEC_ARTIFACT
scope_ids: []
source_spec_version: string
status: TEXT_SPEC_COMPLETE
does_not_claim: []
protected_unknown_ids: []
open_blocking_issue_ids: []
validation_attempt_id: VA-###
completed_at: timestamp
```

规则：

- `scope_ids` 非空、唯一且全部解析到同一 `source_spec_version` 的当前对象；
- 本 scope 的文字 blocker 为零；开放未知项可保留，但必须被准确反链且没有被偷偷具体化；
- `does_not_claim` 明确排除范围外事实。所有文字完成记录至少排除 `MEDIA_EXECUTION`、`MEDIA_OBSERVATION`、`MEDIA_QA`、`PUBLICATION` 与 `LEARNING`；
- 生成前评审包和 MASTER Prompt 包还必须排除 `PROVIDER_COMPILATION`、`REAL_INPUT_AVAILABILITY` 与 `GENERATION_READINESS`；
- 完成记录必须回链同一版本最终通过的验证尝试；
- 文字完整不等于用户批准、真实输入齐备、可以生成、真实媒体存在、QA 通过、发布或学习完成。

## 2. 六条工作流轴各自取证

规格、执行、观察、QA、发布和学习不得压成一个“完成”。`workflow_status.status_basis` 分别列出：

```yaml
execution_artifact_ids: []
observation_ids: []
qa_gate_ids: []
release_gate_ids: []
publication_ids: []
learning_ids: []
```

当对应轴仍处于初始或未执行状态时，其 basis 必须为空。声称真实执行、观察、QA、发布或学习前，相应 ID 必须非空、可解析、版本一致且覆盖同一对象范围。计划、Prompt、自审、模拟记录和其他项目案例都不能充当真实 basis。

## 3. Gate 只记录真实发生过的评估

`gate_evaluations` 不是流程待办表。只有系统已经对明确对象执行关卡评估时才实例化 Gate；尚未评估的未来 Gate 不创建占位对象，不创建对应 `gate_requirements`，只写入 `next_action` 或开放问题。

Alpha.7 持久 Gate 必须是 `evaluation_status = EXECUTED`，结果只使用：

```text
PASSED | FAILED | BLOCKED | ACCEPTED_WITH_DEBT | NOT_APPLICABLE
```

`NOT_APPLICABLE` 需要适用性证据，不能表示“还没做”。无真实媒体时，依赖媒体的 Gate 数组保持为空；这是未评估，不是失败。

### Typed scope 是授权边界

`scope` 只供中文显示；真正参与授权、证据适用性和跨记录核对的是 `scope_bindings`。它按 Gate 类型绑定当前对象，例如：

```yaml
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
```

所有 ID 与版本必须解析。自由文本相似、同名或“属于这个项目”都不能替代 typed scope。至少满足：

- `MICRO_PILOT`：绑定 provider、当前选中的 3—5 个非空代表性生成目标、这些目标的 `PROVIDER_COMPILED` Prompt、任务与版本；资产参考图 Pilot 可不绑定尚不存在的 shot plan；
- `BATCH_PRODUCTION`：绑定本批格式、本批全部生成目标的 `PROVIDER_COMPILED` Prompt coverage，以及作为本批非空子集的代表性 Pilot；Pilot 必须覆盖本批 provider/snapshot、format、task、medium/role、quality/adapter 与高风险类别，但不要求包含整批全部 Prompt，并须保留至少一个普通目标的批次抽审；
- 资产、镜头、序列和成片 Gate：绑定各自真实 artifact/version、plan 与 observation；
- 发布前 Gate：绑定精确成片版本与 release package；
- 发布证据 Gate：绑定真实 publication；
- 学习 Gate：绑定同一链上的 publication、learning 与真实数据证据。

每项 `requirement_result.evidence_ids` 必须是 Gate `evidence_ids` 的子集。`VERIFIED_EVIDENCE` 或 `APPLICABLE_RULE` 的 `source_id` 还必须出现在该项结果证据中。`PASSED` 需要每条强制要求均有适用真实证据；一条无关证据不能让整个 Gate 通过。

## 4. 真实产物、观察与修复闭环

真实产物必须有可访问位置、版本、执行证据和 `execution_mode = REAL`。文字说明、Prompt、文件名、计划或 `real_artifact_present` 的自报不能单独证明媒体存在。

每条 observation 都必须显式保存 `artifact_version`；尚无可核版本的用户报告使用 `null`。真实观察必须绑定精确 `artifact_id + artifact_version`、可访问媒体、观察时间和 evidence。`basis = DIRECT_MEDIA_ACCESS | MEASURED_DATA` 才能支持 `OBSERVED`、NCS/NRS 和媒体 Gate。`USER_REPORTED` 只能作线索：媒体不可访问、无系统时间码、NCS/NRS 为 `NOT_SCORED`，不得进入观察 basis。

供应商 Pilot 标为 `PASSED` 时，每条支撑观察还必须绑定同一 `provider_registry_id`、非空 `task_scope` 与 `observed_at`，并指向真实可访问产物。

修复验证使用不可拆散的闭环：

```yaml
closure_links:
  - new_artifact_id: ART-NEW
    new_observation_id: OBS-NEW
    re_evaluated_gate_id: G-RECHECK
```

新观察必须指向新产物；重评 Gate 必须覆盖该版本且结果为 `PASSED` 或经明确批准的 `ACCEPTED_WITH_DEBT`；观察与 Gate 至少共享一条适用证据。只有修复计划、改 Prompt 或重剪说明时，不得写 `REPAIR_VERIFIED`。

## 5. 语义完整性仍是跨版本硬边界

- `protected_unknowns` 在 `UNKNOWN` 时不得被任何 artifact、shot、MASTER 或 Provider 编译 Prompt 具体化；需要具体值时先回链明确批准或适用证据，并审计全部受影响 ID；
- 每个精确量先登记 quantity type、单位、reference frame、basis、来源与 precision。`RATE`、`OFFSET`、`DURATION`、`COUNT`、`PROBABILITY`、`RATIO`、`CURRENCY`、`SAMPLE_SIZE` 与 `THRESHOLD` 不得混用；
- 比较结论若声称使用单独校准基准，必须有校准链、控制样本、观察窗口、替代解释和批准/证据；同一异常系统里的另一设备不会因被命名为“基准”就自动成为有效基准；
- 只能保持相关性的关系必须登记 causal boundary，并审计时间相邻、声音耦合、视线/空间指向、造型相似和台词字幕；一句“非因果”不能抵消镜头已经表达的因果；
- Reference Registry 的 ID、版本、控制职责与禁止控制项必须解析；参考图不能越权改写身份、服装、空间、道具或世界状态；
- `canonical_duration`、shot-local dependencies、格式变体和 Prompt coverage 都按当前版本重算，不接受旧汇总、默认容差或“其余类推”。

具体工作方法保留在生产可行性、精细分镜和 Prompt 编译阶段；本节只定义不能被下游状态跳过的边界。

## 6. 四层 Prompt 合同

当前 Prompt 使用四层账本。内部转换说明、可复制的中性执行稿和绑定具体供应商的成品是三种不同对象，不得继续共用一个含义不清的 DRAFT：

1. `PROVIDER_NEUTRAL_MASTER`：ID 为 `MP-###`，正文键为 `master_prompt_text`。它来自当前镜头、资产、参考、受保护未知项、数量与因果边界；不绑定供应商，是可审计的权威叙事与制作意图。
2. `TRANSFORM_PLAN`：ID 为 `TP-###`，正文键为 `transform_plan_text`。它只说明重排、引用映射、声音责任、必要分段及 MUST 语义保护；不是可提交提示词，也不得冒充执行稿。
3. `NEUTRAL_EXECUTION_PROMPT`：ID 为 `NEP-###`，正文键为 `neutral_execution_prompt_text`。它是完整、自包含、可复制的供应商中性执行稿，必须含实际逐镜执行内容，但不得声称某个供应商能力已经可用，也不能进入生成 Gate、执行任务或执行回执。
4. `PROVIDER_COMPILED`：ID 为 `PP-###`，正文键为 `prompt_text`。它必须回链同一目标与版本的 MP、TP、NEP，并绑定当前 `provider_registry_id`、具体 provider/surface/model/version/region、参考和执行语言。

链路固定为 `MP → TP → NEP → PP`。四层 coverage、hash、目标和版本分别计算；MP 与 NEP 不得同文，TP 不得携带最终执行正文，NEP 不得只是转换说明。旧 `PROVIDER_NEUTRAL_DRAFT / PD-###` 只在明确旧合同读取分支中保留：旧 ProjectState 中的 PD 迁移为 TP，旧 longform 中的 DRAFT 迁移为 NEP；缺失的另一层必须重新创作，迁移不得继承旧终点通过状态。

`PROVIDER_COMPILED` 还必须区分 `MANUAL_COPY_TEXT_SPEC_ONLY` 与 `GENERATION_EXECUTABLE`。前者只是在用户自报网页入口上可手工复制的文字规格，不得携带能力主张，也不能进入 Pilot、Generation Readiness、READY/RUNNING/EXECUTED 生成任务或真实执行；只有后者可以成为这些范围的候选。完成 MP、TP 或 NEP 不等于供应商适配完成，完成 PP 也不等于生成资格或真实媒体存在。参考 ID 必须解析到当前 Reference Registry，且它控制什么、不得控制什么都要明确。

涉及年龄保护角色时，MASTER 与编译记录必须保留来源中的 `age_years` 和 `is_minor`。`minor_compilation_mode = EXACT | LIFE_STAGE | REFERENCE_BOUND` 只表示三种安全编译方式，年龄事实始终保持。年龄保护角色与成年角色同镜时必须保存 `minor_adult_same_shot_strategy = COMPOSITE | DECOMPOSITION`；缺少安全策略时不得进入 `PROVIDER_COMPILED`。

## 6A. 对白、TTS、字幕与文字产物覆盖

- `dialogue_inventory` 是对白的唯一范围账本；每条保存 `dialogue_id / shot_plan_id / shot_id / text / source_spec_version`。
- `tts_coverage_records` 以 `scope_dialogue_ids`、`covered_dialogue_ids` 与 `dialogue_audio_bindings` 计算 `NOT_APPLICABLE | NONE | PARTIAL | FULL`。仅完成 TTS 文字规格时必须为 `NONE`，covered、bindings 与 output refs 均为空；`PARTIAL / FULL` 中每条 covered dialogue 必须有且只有一个同版本 `artifact_class = MEDIA` 绑定，`FULL` 还要求 covered 与 scope 完全相等。真实、带哈希与证据的音频及其实测时长另由 `measurement_coverage_status` 计算；两类 coverage 都不证明听感 QA 通过。
- `subtitle_cues` 必须逐条回链同一 `dialogue_id / shot_plan_id / shot_id`，满足 `start_seconds < end_seconds`，且起止时间位于当前镜头范围内。镜头时长或时间规格版本变化后必须重新对轴。
- 所有新增文字规格都进入唯一 `artifacts[]`，使用 `artifact_class = TEXT_SPEC`、当前版本和 `content_locator.sha256`。`spec_completion_records.scope_ids` 只能覆盖当前哈希可核的已登记文字产物；聊天回复、未登记文件或旧哈希不能支撑 `TEXT_SPEC_COMPLETE`。

## 7. 验证拒绝与修正不能被抹掉

`state_cleanup` 保存本轮真实验证轨迹，而不是只写“最终通过”：

```yaml
audit_status: EXECUTED
history_completeness: COMPLETE | LEGACY_UNKNOWN
validation_attempts: []
correction_records: []
unresolved_violation_ids: []
final_validation_attempt_id: VA-###
checked_at: timestamp
```

每次尝试保存稳定 ID、严格递增序号、验证层、`REJECTED | PASSED`、violation IDs、消息、subject digest 与时间。subject digest 只排除会造成自引用的 `state_cleanup.validation_attempts`、`correction_records` 与最终尝试指针，其余当前项目内容都必须进入摘要。violation ID 使用稳定格式，同一 violation 只能进入一条修正记录或未解决列表；修正必须从较早的拒绝指向较晚、同一当前 subject 的通过复验。最终通过不能覆盖或删除本轮曾发生的拒绝。旧状态无法证明历史完整时使用 `LEGACY_UNKNOWN`，不伪造往次轨迹。

## 8. CREATOR 默认简洁呈现

内部账本完整，不等于把账本倾倒给用户。顶层 `output_complexity_profile` 使用：

| 档位 | 默认主视图 |
|---|---|
| `CREATOR_SIMPLE` | 结论、推荐、当前状态自然中文摘要、真正需要用户处理的 1—4 件事 |
| `CREATOR_STANDARD` | 可增加紧凑分镜/资产/状态表，完整机器审计仍放附件 |
| `PRO_AUDIT` | 可展开 ID、Evidence、Gate、Prompt、Schema 与验证轨迹 |

默认是 `CREATOR_SIMPLE / source = DEFAULT / inline_machine_detail = STATUS_SUMMARY_ONLY`。只有用户明确要求时才升级档位并保存原话。主产物与审计附件分开登记；默认主视图不能只给一份完整机器包，也不逐项展示尚未实例化的 Gate。

## 9. 四重预检与发布准备终点

`FINAL` 总结为 `PASS` 时，四项检查都必须为 `PASS`，且内容规范、素材许可各有适用证据。它只是进入 `RELEASE_READINESS_GATE` 的必要证据之一：只有通过的最终预检与发布准备 Gate 覆盖同一精确产物和发布包，`publication_status` 才能到 `RELEASE_READY`。

Alpha.7 的自动化到 `RELEASE_READY` 即停止，可以生成发布包与检查报告，但不自动上传或发布，也不创建发布任务。`PUBLISH_PENDING / PUBLISHED / PUBLICATION_FAILED` 只用于用户在系统外操作后登记真实外部事实；必须有对应 publication 和关卡证据，不能由“继续”、计划、按钮截图或模拟回执生成。

## 10. 当前规范源与历史文件

- 当前运行时总契约：本文件；
- 项目类型、唯一总调度与任务路由：`ALPHA7_PROJECT_TYPE_AND_ORCHESTRATION.md`；
- 外部动作、人工授权边界与执行回执：`ALPHA7_EXTERNAL_EXECUTION_CONTRACT.md`；
- 三阶段四重预检：`ALPHA7_CHINESE_COPY_AND_FOURFOLD_PREFLIGHT.md`；
- 语言与五类用途：`LANGUAGE_AND_PRESENTATION_CONTRACT.md`；
- 证据、供应商、发布与学习的领域方法：`EVIDENCE_PROVIDER_RELEASE_LEARNING_CONTRACT.md`；
- NCS/NRS 方法：`NCS_NRS_BASELINE.md`；
- 历史总契约与版本史已移入外部开发档案，不随 Alpha.7 运行包加载；
- 迁移旧状态时可以查阅开发档案，但不能把其中的项目级 `TEXT_SPEC_COMPLETE`、未执行 Gate 占位或单层 Prompt 语义写回 Alpha.7。

出现文档歧义时，先以 Alpha.7 Schema 与验证器检查；若验证器拒绝，记录拒绝与修正，不用自然语言解释掩盖结构错误。
