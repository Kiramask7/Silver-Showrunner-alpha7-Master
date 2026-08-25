# Alpha.7 Master 年龄保护、供应商编译与覆盖完整性合同

本合同补充 Alpha.7 的运行文档层，并统一资产、分镜、Prompt 编译和后期之间容易漂移的字段与执行边界。状态、Gate、Artifact 与真实性语义继续以 `ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md` 和当前 Schema 为准。

## 目录

1. 固定机器词汇
2. 年龄保护编译
3. 四层 Prompt
4. 供应商能力证据
5. 复杂同镜路由
6. 对白、字幕与 TTS 覆盖
7. 新文字产物登记
8. 文字模拟末端
9. 跨阶段检查顺序

## 1. 固定机器词汇

以下名称在运行文档中保持唯一，不创建别名：

```yaml
prompt_layer: PROVIDER_NEUTRAL_MASTER | TRANSFORM_PLAN | NEUTRAL_EXECUTION_PROMPT | PROVIDER_COMPILED
minor_compilation_mode: EXACT | LIFE_STAGE | REFERENCE_BOUND
tts_coverage_status: NOT_APPLICABLE | NONE | PARTIAL | FULL
minor_adult_same_shot_strategy: DECOMPOSITION | COMPOSITE
```

四层各有唯一持久化位置：`master_prompts[]`、`transform_plans[]`、`neutral_execution_prompts[]`、`provider_prompts[]`。四者统一使用 `prompt_layer`；转换计划和中性执行稿都不混入 `provider_prompts[]`，也不能只用一个 Artifact 条目代替结构化记录。旧 `provider_neutral_drafts[]` 仅供明确旧合同读取。

## 2. 年龄保护编译

只要已经判定 `is_minor = true` 就创建 `minor_safety_profiles[]` 并启用本节。年龄或来源尚不能判定时，只在资产层保持 `subject_age_class = UNKNOWN`，不创建 minor profile，也不得把未知当成成年人继续编译。

每个受影响人物至少保留：

```yaml
profile_id: MIN-001
asset_id: CHAR-001
source_spec_version: v1
is_minor: true
age_years: 12
source_life_stage: CHILD
age_source_ids: [D-AGE-001]
majority_age_years: 18
age_rule_basis: PROJECT_CANON
age_rule_source_or_evidence_ids: [D-MAJORITY-001]
minor_compilation_mode: EXACT
compiled_age_years: 12
compiled_life_stage: null
reference_asset_ids: []
compatibility_alternative: null
safety_review_status: REQUIRED
```

这是可按当前 minor profile Schema 实例化的对象形状。`age_years / source_life_stage / age_source_ids / is_minor / majority_age_years / age_rule_basis / age_rule_source_or_evidence_ids` 是事实与判定层，任何编译模式都不得改写。`compiled_age_years / compiled_life_stage` 只是执行 Prompt 的表达层：

- `EXACT`：`compiled_age_years = age_years`，`compiled_life_stage = null`；执行 Prompt 直接保留准确年龄。
- `LIFE_STAGE`：`compiled_age_years = null`，`compiled_life_stage` 使用与真实年龄一致的生命阶段描述，例如儿童或青少年；不得写成成年人、年轻成人或其他更高年龄段。
- `REFERENCE_BOUND`：年龄表现绑定到已批准、许可清楚且当前入口真实支持的参考资产；没有实际写入年龄文字时两个 compiled 字段可为 `null`，参考不得越权改写年龄、身份或身体特征。

硬边界：

- 编译必须沿用已登记的年龄与阶段；供应商不接受时，暂停该路线并改用安全构图、拆镜、合成或转入复核；
- 不得删除年龄、成年规则或其来源，把真实年龄改成营销年龄，或让参考图覆盖年龄事实；
- 供应商拒绝或能力不足时，改用同层可核验入口、拆镜、后期合成或人工路线；不能篡改人物年龄；
- 使用 `compatibility_alternative` 时必须同时保存 `preserves_source_age_fact = true`、`review_bypass_forbidden = true` 与 `review_status = REQUIRED | PASSED`；它不能跳过安全复核；
- 涉及真实年龄保护对象时，继续核对同意、肖像、声音、个人信息、目标范围与用途；Prompt 编译通过不代表这些许可已经齐备。

## 3. 四层 Prompt

### 3.1 `PROVIDER_NEUTRAL_MASTER`

- ID 沿用 `MP-###`；
- 一对一回链当前 `target_type + target_id + generation_role + generation_medium`，并回链相关资产、镜头、参考、对白、状态变化、受保护未知项、数量与因果边界；
- 保存不可被供应商适配改写的叙事与制作真值；
- 不包含某家产品的入口、私有语法、时长上限或未经核实的能力。

### 3.2 `TRANSFORM_PLAN`

- ID 使用 `TP-###`，持久在顶层 `transform_plans[]`；
- 从当前 MASTER 派生，只说明重排、引用映射、声音责任、合法分段及 MUST 保护；
- 不绑定 provider/model/version/surface，不得写供应商专有参数，不得包含最终执行正文，也不得提交给外部模型；
- 结构化记录至少包含 `prompt_layer`、`master_prompt_id`、目标四元组、兼容 `shot_id`、`source_spec_version`、`transform_plan_text` 与 `intent_summary_zh`。

### 3.3 `NEUTRAL_EXECUTION_PROMPT`

- ID 使用 `NEP-###`，持久在顶层 `neutral_execution_prompts[]`；
- 同时回链当前 `master_prompt_id` 与 `transform_plan_id`，形成完整、自包含、可复制的供应商中性执行稿；
- 逐镜落实动作、表演、摄影、声音、入口和出口，不得只是转换说明；
- 不绑定具体供应商，不得写未经当前证据支持的供应商能力，也不能进入生成 Gate、执行任务或执行回执。

### 3.4 `PROVIDER_COMPILED`

- ID 沿用 `PP-###`；
- 必须同时回链同目标、同角色、同媒介、同版本的 `master_prompt_id / transform_plan_id / neutral_execution_prompt_id`，并从这条链忠实编译；
- 自身只保存 Schema 规定的 `provider`、`provider_registry_id`、`provider_snapshot_id` 与 `capability_evidence_ids`；model、version、surface、region、task 和输入方式由该 Registry 快照与证据解析，不在 PP 重抄；
- 只有这一层可以进入真实执行、`MICRO_PILOT` 和 `GENERATION_READINESS_GATE`。

四层按当前 ASSET/SHOT target keys 分别核对 coverage。MP 完整不代表 TP、NEP、供应商编译、真实输入或生成资格完整；NEP 完整不代表已经适配供应商；`PROVIDER_COMPILED` 完整也不代表媒体已经生成或 QA 通过。禁止用“其余类推”“同上”或一份 Prompt 覆盖多个分离目标/角色。局部 Pilot 可以只覆盖明确选中的目标，不强迫全片预建空 Prompt。

角色、服装、场景、道具或风格参考图在分镜前使用 `target_type = ASSET / target_id = asset_id / generation_role = ASSET_REFERENCE`，兼容 `shot_id = null`。镜头关键帧、首尾帧和运动视频使用 `target_type = SHOT` 及各自 generation role；同一镜头可有多种生成角色。静态组件不参与成片时长求和；I2V 的运动任务必须结构化绑定上游 IMAGE artifact/version，不能只靠人读文字。

## 4. 供应商能力证据

任何供应商时长、模型版本、入口、地区、输入方式或功能主张都必须回链当前 `capability_evidence_ids`。证据至少限定下列维度；这是字段清单，不是 `provider_prompts[]` 对象：

```yaml
provider: string
model: string
version: string | UNKNOWN
surface: string
region: string
task: string
input_mode: string
capability_evidence_ids: []
checked_at: timestamp_or_date
```

规则：

- 不硬编码“15 秒”或任何统一时长；只使用当前官方证据、当前入口实测选项或项目 Pilot 支持的值；
- 网页入口、桌面端与 API 是不同 `surface`，一个入口的能力不能自动迁移到另一个入口；
- 营销名、显示名、API model ID 与固定版本分别记录，不能互相替代；
- 计划镜头时长超出已证实能力时，先拆镜、改用经核验入口或进入后期组合，不把超限规格写成可直接执行；
- 缺少适用证据时将能力保持 `UNKNOWN`，`PROVIDER_COMPILED` 只能保持草案或阻断，不得凭记忆补写版本、入口或时长上限；
- 切换 provider/model/version/surface/region/task 后，旧 capability evidence 与旧 Pilot 均不自动继承。

`claim_kind = EXACT_DURATION` 且 `status = VERIFIED` 还必须满足更严格的当前性：每条支撑证据的 classification 只能是 `VERIFIED_OFFICIAL / VERIFIED_PRIMARY_RESEARCH / PLATFORM_SAMPLE`，claim class 只能是 `FACT / SAMPLE_OBSERVATION`，不得使用 `SYSTEM_INFERENCE`、启发式、未知或用户口述。证据 scope 必须显式且精确匹配当前 provider registry ID、provider、model、version、region、surface、snapshot 和 provider `checked_at`；provider、capability 与 evidence 的 `checked_at` 必须相等，并落在声明为 `CURRENT` 的 `freshness.valid_from / valid_until` 内。最终验证时间不得晚于 `valid_until`。多条证据中只要任一条过期、缺 scope 或分类不合格，整个 `VERIFIED` 精确时长主张就不成立；保持 `UNKNOWN` 或重新核验，不能靠另一条新证据掩盖过期来源。

## 5. 复杂同镜路由

含年龄保护角色与成年角色同镜、多人遮挡、严格身份连续、多方肢体交互、长动作链、复杂口型或当前供应商没有适用能力证据的镜头，不默认要求单次生成完成。记录：

```yaml
minor_adult_same_shot_strategy: DECOMPOSITION
strategy_reason: 当前入口缺少复杂同镜的适用能力证据。
source_shot_id: SH-001
derived_shot_ids: [SH-001-A, SH-001-B]
```

- `DECOMPOSITION`：拆为安全、可核验的分离镜头、反应镜头、动作前后态或插入镜头，同时保留原叙事功能与状态继承。
- `COMPOSITE`：分别取得可核验图层或镜头，再在标准时间线中做后期合成；必须登记各层资产、位置、遮罩/边缘、时长、来源、素材许可、版本与哈希。

采用任一策略后，原始同镜只保留为叙事或剪辑聚合目标：`generation_required = false`，填写 `no_generation_reason`，且 `master_prompt_ids / transform_plan_ids / neutral_execution_prompt_ids / provider_prompt_ids` 均为空。真实生成只发生在拆出的 SHOT 目标或单独的 `SHOT_COMPOSITE_LAYER`；不得一边声明拆镜/合成，一边仍给原始同镜编译并执行 Prompt。可执行生成任务的 `generation_targets[]` 必须与 `provider_prompt_ids` 的目标四元组完全相等；`shot_ids` 只作为其中 SHOT 目标的派生视图，`task_scope` 即使提到原聚合镜头也不能改变结构化执行对象。

拆镜或合成后必须重新计算 `canonical_duration`、shot-local dependencies、四层 Prompt coverage、字幕时间码和 TTS coverage。后期合成不得冒充供应商一次生成成功；拆镜也不得改变人物年龄或删除关键叙事功能。

## 6. 对白、字幕与 TTS 覆盖

### 6.1 对白库存

先从当前剧本与 `shot plan` 建立唯一 `dialogue_inventory`。每个最小可对轴话语单元使用稳定 `dialogue_id`，至少登记说话人、原文、`shot_plan_id`、`shot_id`、`subtitle_required`、`tts_required` 与来源版本。分镜拆分、合并或对白修改后，先更新库存，再让字幕和 TTS 重算。

### 6.2 字幕必须回链 shot plan

每条 `subtitle_cues` 至少保存：

```yaml
cue_id: SUB-001
dialogue_id: DLG-001
shot_plan_id: SP-001
shot_id: SH-001
start_seconds: 0
end_seconds: 1
text: 示例台词
dialogue_text_sha256: ca897589124062c41dc98a6ad0d7312ffa1052fb13ff2db82866ca33b3969bc7
source_spec_version: v1
timing_spec_version: v1
```

对当前版本执行集合与时间检查：

```text
expected subtitle dialogue IDs = dialogue_inventory 中 subtitle_required=true 的 dialogue_id
covered subtitle dialogue IDs = subtitle_cues 中的 dialogue_id
missing dialogue IDs = expected - covered
orphan dialogue IDs = covered - dialogue_inventory
```

只有 `missing dialogue IDs`、`orphan dialogue IDs` 和重复 cue 均为空，且每条 cue 的 `shot_plan_id / shot_id / timing_spec_version` 与当前分镜一致、时间范围落在对应镜头内，字幕 coverage 才完整。时间码合法仍不等于语义正确；最终还要对当前音轨人工核对人名、术语、数字、否定词、说话人与断句。

### 6.3 TTS 覆盖状态

每个 `tts_coverage_records` 使用 `scope_dialogue_ids`、`covered_dialogue_ids` 与逐条 `dialogue_audio_bindings` 计算 MEDIA Artifact 绑定覆盖，不凭文字规格摘要判断：

- `NOT_APPLICABLE`：当前 scope 没有 `tts_required=true` 的对白；
- `NONE`：需要 TTS，但只完成文字规格或尚无 MEDIA Artifact 绑定；此时 covered、bindings 与 output refs 均为空；
- `PARTIAL`：覆盖集合是所需集合的真子集，且每条 covered dialogue 都有且只有一个同版本 `artifact_class = MEDIA` 绑定；
- `FULL`：两个集合完全相等、没有越界或重复 ID，且每条 scope dialogue 都有且只有一个同版本 `MEDIA` Artifact 绑定。

真实音频测量覆盖另用 `measured_dialogue_ids`、`measured_duration_seconds` 与 `measurement_coverage_status = NONE | PARTIAL | FULL`：只有 binding 指向真实、带哈希和匹配证据的音频 Artifact/version 且取得正实测时长的 dialogue 才进入 measured 集合。`measurement_coverage_status = FULL` 要求 `measured_dialogue_ids == scope_dialogue_ids`，总实测时长由这些 binding 确定性求和；真子集只能是 `PARTIAL`。

合法结构示例（MEDIA Artifact 绑定只覆盖一部分，实测也只覆盖这一部分）：

```yaml
coverage_id: TTS-001
source_spec_version: v1
scope_shot_plan_ids: [SP-001]
scope_dialogue_ids: [DLG-001, DLG-002]
covered_dialogue_ids: [DLG-001]
tts_coverage_status: PARTIAL
dialogue_audio_bindings:
  - dialogue_id: DLG-001
    artifact_id: AUDIO-001
    artifact_version: v1
    measured_duration_seconds: 1.2
measurement_coverage_status: PARTIAL
measured_dialogue_ids: [DLG-001]
measured_duration_seconds: 1.2
output_artifact_refs:
  - artifact_id: AUDIO-001
    version: v1
evidence_ids: [E-TTS-001]
```

`tts_coverage_status = FULL` 只证明全片所需话语单元都有逐条 `MEDIA` Artifact 绑定；若 `measurement_coverage_status = PARTIAL`，真实、已测音频仍只是部分覆盖。即使两者都为 `FULL`，也不证明声音许可清楚、口型同步、混音或媒体 QA 已通过；这些仍需来源/同意、execution receipt、当前哈希、观察与 Gate 证据。只有文字规格而没有这些 MEDIA bindings 时必须保持 `tts_coverage_status = NONE`。

## 7. 新文字产物登记

任何新建或实质改写并被下游引用的 Markdown、JSON、YAML、剧本、分镜、Prompt 包、字幕稿、时间线规格或报告，都必须先进入现有 `artifacts[]`，不能只留在聊天或文件名中：

```yaml
id: ART-001
type: NEUTRAL_EXECUTION_PROMPT
artifact_class: TEXT_SPEC
status: SPEC_READY
real_artifact_present: true
version: v1
content_locator:
  uri: build/NEP-001.md
  media_type: text/markdown
  sha256: 0000000000000000000000000000000000000000000000000000000000000000
dependencies: []
evidence_ids: []
open_blocking_issue_ids: []
execution_mode: REAL
protected_unknown_ids: []
quantity_ids: []
causal_boundary_ids: []
benchmark_case_id: null
```

这是可按现有 Artifact Schema 实例化的 `TEXT_SPEC` 文件对象；示例哈希仅表示合法字段形状，实际登记必须换成该文件最终字节的 SHA-256。只要文字文件真实落盘并登记为 `TEXT_SPEC`，其 `artifact.execution_mode = REAL`；这只表示文件存在，不表示任何媒体或外部生产已执行。若文件根本未落盘，就不创建该 Artifact。工作流或外部步骤可以另记为 `SIMULATION`，不得把两条状态轴混为一谈。

保存最终字节后再计算 `content_locator.sha256`。文字内容改变就升级版本并重算哈希；依赖旧版本的 completion、Prompt、预检或 Gate 不能自动继承。只有本 scope 文字完整、验证通过且开放文字 blocker 为零时，才另建现有 `spec_completion_records`，并准确填写 `scope_ids / source_spec_version / does_not_claim`。Artifact 登记、`SPEC_READY` 与 `TEXT_SPEC_COMPLETE` 是三个不同事实。

## 8. 文字模拟末端

只有用户明确要求线路模拟，且确实记录了 `SIMULATED_EXTERNAL_STEP` 时，文字模拟末端使用：

```yaml
execution_mode: SIMULATION
workflow_status:
  spec_status: SPEC_DRAFT | SPEC_READY
  execution_status: SIMULATED_ONLY
  observation_status: OBSERVATION_PENDING
  qa_status: QA_NOT_EXECUTED
  publication_status: RELEASE_NOT_READY
  learning_status: NO_REAL_DATA
terminal_markers: []
```

如果只是写完文字规格、从未执行或模拟外部步骤，`execution_status = NOT_EXECUTED`，不能为了“跑到末端”改成 `SIMULATED_ONLY`。两种情况都允许登记真实存在的文字 Artifact 与对应哈希，但都不得创建媒体 Observation、NCS/NRS、媒体 QA、发布或学习证据，不得写 `REAL_PRODUCTION_COMPLETE`、`RELEASE_READY` 或 `PUBLISHED`。未来 Gate 仍只写入 `next_action`，不建占位对象。

## 9. 跨阶段检查顺序

1. 资产阶段登记年龄、来源、同意、参考职责和可变边界；
2. 分镜阶段选择安全编译模式，识别复杂同镜并决定拆镜或合成；
3. Prompt 阶段按四层生成，并对供应商能力证据、版本、入口和时长逐项绑定；
4. 后期阶段从当前 `dialogue_inventory` 重算字幕与 TTS coverage；
5. 每次保存新文字产物，先写 Artifact 状态与哈希，再允许下游引用；
6. 真实执行、文字模拟与未执行分别落到对应六轴状态，不用文字完成替代媒体事实。
