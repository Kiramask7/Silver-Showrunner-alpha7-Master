# 项目状态、决定账本与用户约束

本文件说明项目记录的方法与用户授权边界。Alpha.7 的字段关系、scoped completion、typed Gate scope、Prompt 分层与验证轨迹统一遵守 `references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`；本文件不另造平行状态。

## 1. 语言档案（current）

Project State 必须把五种语言用途分开记录：

```yaml
language_profile:
  interaction_language: zh-CN
  creative_artifact_language: zh-CN
  dialogue_language: PROJECT_DEPENDENT
  provider_prompt_language: PROVIDER_OPTIMAL_WITH_ZH_EXPLANATION
  release_copy_language: TARGET_DEPENDENT
language_policy:
  effective_output_locale: zh-CN
  source: DEFAULT | USER_EXPLICIT
  user_quote: null
```

导入没有语言记录的旧状态时，迁移层可以先按 `DEFAULT / zh-CN` 读取，但必须补写 `language_policy` 与 `language_profile` 后再进入严格 Schema 校验。`validate_state.py --allow-legacy-import` 只用于迁移前审计，不能替代持久化迁移。只有用户明确要求改变交互语言时，才可使用 `USER_EXPLICIT`，同时逐字保存 `user_quote`。英文资料、模型名、英文 Prompt、海外平台或英文字幕都不能自动改变交互语言。

机器 ID、枚举、JSON/YAML key、Schema、代码和路径保持规范英文；中文属于显示层与创作内容层。

## 2. Project State 必须追踪什么

- `creator_profile`：创作者与协作偏好；
- `entry_state`：进入流程时已有的材料；
- `project_route`：当前唯一项目路由，明确项目类型、事实模式、规模、目标交付件与来源忠实要求；
- `project_brief`：项目简报；
- `non_negotiables`：不可妥协项；
- `target_audience`：目标受众；
- `distribution_target`：发行目标；
- `success_definition`：成功定义；
- `market_snapshot`：市场证据快照；
- `viral_genome`：传播叙事基因；
- `creative_direction`：创意方向；
- `story_bible`、`character_bible`：故事与角色设定集；
- `episode_architecture`：集数与单集结构；
- `script_versions`：剧本版本；
- `production_feasibility`：AI 制作可行性；
- `style_bible`：视觉风格设定集；
- `asset_registry`：资产登记表；
- `artifacts`：所有真实媒体、文字规格与数据产物的唯一版本账本；文字产物使用 `artifact_class = TEXT_SPEC` 并保存 SHA-256；
- `shot_contracts`：镜头契约；
- `provider_registry`：按 provider/model/version/region 建立的当前能力快照；
- `master_prompts`：`prompt_layer = PROVIDER_NEUTRAL_MASTER` 的权威意图源；
- `transform_plans`：`prompt_layer = TRANSFORM_PLAN` 的内部转换计划，不可提交；
- `neutral_execution_prompts`：`prompt_layer = NEUTRAL_EXECUTION_PROMPT` 的完整中性执行稿，可复制但不可进入生成 Gate；
- `provider_prompts`：回链 MP、TP、NEP 并以 `prompt_layer = PROVIDER_COMPILED` 绑定当前供应商、入口、模型/版本与地区的唯一可执行 Prompt；
- `reference_registry`：Prompt 所用参考及其版本、职责与禁止控制项；
- `dialogue_inventory`：按对白、镜头计划、镜头和规格版本建立的全片 speech unit 账本；
- `tts_coverage_records`：对明确对白范围记录 `NONE | PARTIAL | FULL` 的 MEDIA Artifact 绑定覆盖，和真实音频测量、听感 QA 分开；
- `subtitle_cues`：逐条回链对白与镜头，并保存当前时间规格版本的字幕 cue；
- `generation_runs`：生成批次；
- `observed_states`、`edited_states`：真实媒体中观察到的内容状态与剪辑后承接状态；
- `qa_reports`：质量检查记录；
- `postproduction`：后期状态；
- `release_state`：发布准备状态，以及用户手工发布后可核实的外部状态；
- `publication_records`：真实发布后的平台内容 ID、链接、作品版本与核查证据；
- `performance_data`：真实表现数据；
- `technical_debt`：技术债；
- `user_constraints`：持续有效的用户约束；
- `core_claims`：受保护的事实与创意主张；
- `approval_events`：用户批准事件；
- `flow_events`：流程推进事件；
- `evidence_registry`：证据登记表；
- `open_issues`：未解决问题；
- `capacity_snapshot`：当前工具、人员、预算与时间能力；
- `language_profile`、`language_policy`：语言用途和当前交互语言来源；
- `stage_results`：当前阶段的用户可见结果摘要；
- `task_graph`：唯一总调度维护的有向无环任务图；
- `execution_receipts`：本地工具、浏览器、API、人工或模拟动作的可核执行回执，并以 `execution_domain` 区分生产媒体、本地验证和本地文字工具；
- `fourfold_preflight_records`：`EARLY / IN_PROCESS / FINAL` 三个检查点的自然表达、内容规范、素材许可与传播准备记录；
- `workflow_status`：规格、执行、观察、QA、发布与学习六条状态轴；
- `workflow_status.status_basis`：执行、观察、QA、发布与学习各轴的精确事实依据；
- `spec_completion_records`：只对被点名对象和版本声明文字规格完成；
- `output_complexity_profile`：用户主视图与审计附件的呈现档位；
- `terminal_markers`：文字模拟终点与真实制作终点；
- `gate_evaluations`：只保存已经真实评估过的关卡记录；
- `gate_requirements`：只为已实例化关卡保存必过要求及合法来源；
- `observations`：对真实媒体的审计记录，或有来源且不冒充直接观察的用户报告；
- `repair_records`：根因、修复动作、新产物、新观察和重过关记录；
- `canonical_duration`：当前唯一权威总时长及其逐镜求和依据；
- `learning_records`：真实假设、干预、样本、结果与可复用判断；
- `state_cleanup`：本轮验证拒绝、修正、未解决违规和最终复验轨迹。

### Alpha.7 四类顶层记录

银幕总控是唯一总调度者：它维护同一份 Project State、决定账本和证据链；外部 Skill、模型、浏览器、脚本与剪辑工具只是任务能力，不能另建平行状态或第二套批准逻辑。

- `project_route` 每个项目只有一个当前对象。非虚构或混合项目必须开启来源忠实保护；路由若为 `USER_APPROVED`，要回链明确决定；若为 `VALIDATED`，要回链适用证据。
- `task_graph` 把工作拆成有依赖、无循环的任务。任务输入输出都绑定产物版本，批准、Provider、四层 Prompt、阻断项和恢复点按实际需要回链；任务完成只证明该任务，不覆盖项目六轴状态。
- `execution_receipts` 与任务双向引用。新回执明确写 `execution_domain = PRODUCTION_MEDIA | LOCAL_VALIDATION | LOCAL_TEXT_TOOL`。真实本地预检或文字工具成功只证明该检查/文件动作，不会把项目媒体 `execution_mode`、执行轴、Observation、媒体 QA 或 release 升级为真实生产；本地域也不得声称输出 `MEDIA / PACKAGE`。生产媒体成功才必须产生真实媒体产物。
- 生成任务处于 `RUNNING / EXECUTED_FAILED / EXECUTED_SUCCEEDED` 时只能引用 `PROVIDER_COMPILED`，并分别绑定真实 `RUNNING / FAILED / SUCCEEDED` 生产媒体回执；回执必须与 task、route、provider snapshot、compiled Prompt 和 source spec version 一致。失败还要保存失败证据和原因。只有 `PLANNED / BLOCKED / READY` 可以尚无执行回执。
- `fourfold_preflight_records` 对被检查产物逐版本登记。`FINAL` 必须绑定精确版本与 SHA-256，并以真实模式执行；内容规范或素材许可阻断不能被自然表达分或传播准备度抵消。

当前版本没有自动发布任务。任务图只推进到发布包、最终四重总检与 `RELEASE_READY`；用户之后手工发布并提供可访问证据时，才可只读登记 `publication_records` 与真实表现数据。

### Prompt、对白、字幕与文字产物完整性

- 四层 Prompt 使用唯一机器字段 `prompt_layer`。MP 保存权威意图，TP 保存转换计划，NEP 保存完整中性执行稿，PP 才绑定并提交供应商；任一层都不能冒充下一层。
- 年龄受保护角色的 Prompt 保存真实 `age_years`、`is_minor` 和 `minor_compilation_mode = EXACT | LIFE_STAGE | REFERENCE_BOUND`。编译方式可以调整表达，但不得改变年龄事实。与成年角色同镜时，必须明确 `minor_adult_same_shot_strategy = COMPOSITE | DECOMPOSITION`，否则保持阻断。
- 仅完成 TTS 文字规格时，`covered_dialogue_ids` 与 `dialogue_audio_bindings` 必须为空，`tts_coverage_status = NONE`。`PARTIAL / FULL` 中每个 covered dialogue 都必须有且只有一个同版本 `artifact_class = MEDIA` 绑定，且 `output_artifact_refs` 精确匹配；`FULL` 要求 covered 与 scope 完全相等。真实、带哈希与证据的音频及其实测时长另由 `measurement_coverage_status` 计算，两种 coverage 都不等于听感 QA 通过。
- 每条字幕必须解析到当前 `dialogue_id + shot_plan_id + shot_id`，且起止时间落在该镜头时间范围内；分镜时长或版本改变后，旧 cue 失效并重新对轴。
- 新增文字文件只有在 `artifacts[]` 登记当前版本、位置与 SHA-256，并被同版本 `spec_completion_record.scope_ids` 覆盖后，才可声明该文字范围完成。

## 3. 多轴状态与终点

以下状态不得压缩成一个通用 `status`：

```yaml
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
```

`workflow_status` 还必须保存 `status_basis`，让真实执行、观察、QA、发布和学习逐轴回链对应 artifact、observation、Gate、publication 与 learning。轴处于初始或未执行状态时，相应 basis 为空；不能让陈旧 ID 残留。

Alpha.7 不写入 `PIPELINE_SIMULATION_COMPLETE`。文字线路走到末端只更新实际轴状态并保持 `terminal_markers: []`；`REAL_PRODUCTION_COMPLETE` 仍只表示真实产物与所需关卡已经成立。

自动化终点是 `RELEASE_READY`，不是 `PUBLISH_PENDING` 或 `PUBLISHED`。这些发布后状态只用于记录用户在系统外完成且已有证据的事实，不能由“继续”、发布计划或模拟回执生成。

### 有范围的文本完成

`TEXT_SPEC_COMPLETE` 只出现在 `spec_completion_records`，并且必须点名 `scope_type`、`scope_ids`、`source_spec_version`、排除声明、受保护未知项、开放 blocker 与最终通过的验证尝试。它不再是项目级 `spec_status`。

同一项目可以拥有“剧本 v0.3 文本完整”，同时资产规格、Provider 编译 Prompt 或发布规格仍未完成。用户可见层应说清“哪一份、哪个版本完成”，不能缩写成“整个项目已完成”。完整字段与最低排除集合见 Alpha.7 运行时契约。

### 用户输出复杂度

顶层 `output_complexity_profile.tier` 使用 `CREATOR_SIMPLE | CREATOR_STANDARD | PRO_AUDIT`。默认 `CREATOR_SIMPLE`：主视图只给结论、推荐、自然中文状态摘要和当前需要用户处理的少量事项；完整状态 JSON、Gate inventory、Prompt 与验证历史进入附件。只有用户明确要求升级时才保存 `source = USER_EXPLICIT` 与原话。

## 4. 决定账本（Decision Ledger）

每个实质性决定都使用以下结构：

```yaml
id: D-###
topic: string
value: any
status: DRAFT | PROPOSED | USER_APPROVED | VALIDATED | LOCKED | DEPRECATED
source: USER | SYSTEM_RECOMMENDATION | VERIFIED_EVIDENCE | USER_REPORTED_EVIDENCE | TEST_ASSUMPTION
question_id: optional
rationale: string
impacts: []
created_at: timestamp_or_stage
supersedes: optional
approval_event_id: optional
evidence_ids: []
validation_basis: []
lock_event_id: optional
lock_scope: optional
open_blocking_issue_ids: []
```

中文显示可使用“草案、待确认提案、用户已批准、已验证、已锁定、已弃用”，但持久化枚举不得翻译。

## 5. 决定绑定协议

- 每个会影响路线的问题必须有 `Q-###`。
- 每个选项都要明确它控制哪些决定字段。
- 用户的简短回答只绑定这些字段，不能顺手批准相邻建议。
- “继续、下一步、照你的建议推进”等导航语只改变流程状态，不改变决定状态。
- 沉默或没有反对不构成批准。
- 为模拟或测试临时采用的方向保持 `PROPOSED`，来源记为 `TEST_ASSUMPTION`。
- 用户修改已锁定决定时，继续前必须计算会失效的下游产物与决定。
- 用户可见输出若写“已锁定”或 `LOCKED`，必须同时给出 `locked_decision_ids`；每个 ID 都要真正处于 `LOCKED`，不能把 `USER_APPROVED` 包装成锁定。

## 受保护未知项

对会改变故事真相、制作基准、供应商、精确数值或因果边界的未知项建立 `protected_unknowns`。每条记录必须双向登记受影响与已审计的 artifact、shot、MASTER Prompt 和 Provider 编译 Prompt ID。`UNKNOWN` 期间禁止在下游静默给出具体型号、日期、数值、装置或原因；需要具体值时，先用明确批准或已核验证据把该项升为 `RESOLVED`。当前完整结构见 `references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`。
- `PROPOSED` 不能被显示、叙述或推断成 `LOCKED`。

## 6. 批准事件（Approval Event）

```yaml
id: A-###
actor: USER
user_quote: exact relevant words
question_id: optional
approved_decision_ids: []
approved_fields: []
approved_values: {}
explicit: true
created_at: timestamp_or_stage
```

决定升为 `USER_APPROVED` 前，必须输出范围差异：

```yaml
changed: []
unchanged_neighbors: []
still_unknown: []
downstream_impacts: []
```

`user_quote` 保存用户原话，不做润色、翻译或扩大解释。

## 7. 核心主张保护

把创作者明确给出的事实、世界规则、主题意图和不可妥协项，与系统建议分开保存。每条 `core_claim` 都要记录当前状态，以及修改是否需要用户明确批准。

重点保护事实、因果、适用范围、触发条件、世界规则和创作者声明的未知项。任何仅被描述为相关、怀疑或角色推测的内容都不能升级为因果结论；用户尚未说明的条件和范围必须保持 `UNKNOWN`。

在立项评估、故事锁定、剧本锁定及重大市场化调整前，对照检查新的产物。若出现冲突，必须触发 `HUMAN_DECISION` 或提出不破坏核心的替代方案，绝不能静默改写。

## 8. 用户约束记忆

以下约束一经明确，就持续有效，直到用户亲自修改：

- 无法上传图片；
- 不要旁白；
- 只能使用指定工具；
- 不使用 3D；
- 截止时间或预算上限；
- 不模仿受版权保护的特定风格；
- 交互语言和有明确范围的语言覆盖；
- 其他会影响制作、伦理、内容规范或发行的限制。

后续阶段不得遗忘这些约束。“继续 / 下一步”不改变语言策略。用户只要求英文字幕时，只更新字幕产物或 `release_copy_language`，对话仍遵循 `interaction_language`。

## 9. 关卡要求来源

每条强制关卡要求必须来自：

- `SYSTEM_INVARIANT`；
- `USER_APPROVED_DECISION`；
- `VERIFIED_EVIDENCE`；
- `APPLICABLE_RULE`。

并保存对应 `source_id`。`PROPOSED`、`UNKNOWN`、模型推荐和未验证的临时工具选择不能成为强制 Gate Requirement；它们只能是候选、开放问题或阻断项。

Gate 只有在对明确对象真实执行评估时才实例化。`scope` 是用户可读摘要；授权与证据适用性只认 `scope_bindings` 中可解析的对象、版本、provider、Pilot、shot plan、Prompt、observation、format 与任务范围。尚未执行的未来 Gate 只写在 `next_action`，不创建占位对象或空 requirement。

## 10. 带已知问题继续（Accept With Debt）

如果用户知情选择在未解决问题下继续：

```yaml
status: ACCEPTED_WITH_DEBT
debt:
  issue: ...
  risk: ...
  downstream_impacts: [...]
  revisit_trigger: ...
```

记录后可以继续，不要在触发条件出现前反复重问同一件事。但 `ACCEPTED_WITH_DEBT` 只代表用户接受风险，不代表相关决定已被证明、验证或锁定。安全、适用规则阻断项，以及让下一阶段事实上无法执行的依赖，不能作为普通技术债跳过。

## 11. 验证与纠错轨迹

最终清账不能只留下“最后通过”。`state_cleanup.validation_attempts` 记录本轮每次结构、invariant、完整或 package 验证；被拒尝试保留 violation IDs、消息、subject digest 与时间。每个 violation 必须进入一条 `correction_record` 或 `unresolved_violation_ids`，最终复验再由 `final_validation_attempt_id` 回链。

旧状态无法证明历史完整时使用 `history_completeness = LEGACY_UNKNOWN`，不得伪造早先验证轨迹。验证器拒绝后修正并通过，用户主视图只需自然说明“已发现并修正”，完整轨迹放审计附件；不能把拒绝记录删除成“首次即通过”。
