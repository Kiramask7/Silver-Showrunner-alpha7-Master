# Stage 11 — 生成观察与双重 QA

观察记录、证据、NCS/NRS 解释、Failure 与建议遵守 `interaction_language`；时间码、ID 和规范指标字段保持原值。本阶段遵循 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`，必须区分“尚未实例化评估”和“已执行评估失败”。

## 真实生成入口与回执

任何真实生图、生视频、配音或其他外部生成，必须同时遵守 `../references/ALPHA7_EXTERNAL_EXECUTION_CONTRACT.md`：

1. 在 `task_graph` 建立有依赖、有输入版本和可恢复点的具体任务；
2. 任务只绑定当前 `PROVIDER_COMPILED`，以及对应 `provider_registry_id`、执行路线（`LOCAL_TOOL | BROWSER | API | MANUAL`）和批准范围；进入 `READY / RUNNING / EXECUTED_FAILED / EXECUTED_SUCCEEDED` 的图像/视频生成任务还必须写非空 `generation_targets[]`，逐项绑定目标类型、目标 ID、生成角色、媒介与 compiled Prompt，展平集合必须与任务级 `provider_prompt_ids` 完全相等；`ASSET` 不伪造镜头，`SHOT` 才派生 `shot_ids`；`task_scope` 不能提供或扩大执行授权；MP、TP、NEP 不得进入可执行任务；
3. `RUNNING / EXECUTED_FAILED / EXECUTED_SUCCEEDED` 分别创建真实 `RUNNING / FAILED / SUCCEEDED` 的 `PRODUCTION_MEDIA` 回执，绑定 task、route、provider snapshot、compiled Prompt 与 source spec version；失败回执也必须保存结束时间、失败证据和原因；
4. 任务与回执双向引用，成功的生成任务必须指向真实 Artifact；
5. Artifact 实际可访问并完成来源/版本核对后，才进入观察与 QA。

提交给供应商的 Prompt 必须是当前 `PROVIDER_COMPILED`。MP、TP 与 NEP 只能作为权威意图、转换计划或中性执行稿；把 NEP 复制到某个网页并不让它自动升级为已编译 Prompt。编译记录还要与本次回执的 provider、surface、model/version、region、目标四元组、source spec version 和参考资产完全一致。`IMAGE_TO_VIDEO` 还必须回链已登记的上游图像 Artifact/version；只有到真实执行阶段才要求该输入实际可访问。

只有 Prompt、页面已打开、命令已编译、用户口述或模拟回执，都不能记为生成成功。遇到登录、验证码、付费、账号权限或不可逆动作时，在检查点诚实阻断并保留恢复信息；不跳过检查，也不代替用户授权。用户手工生成的产物先记 `USER_REPORTED`，实际可访问并核对后才能升级为系统观察。

## 进入与无媒体状态

只有拿到可访问的真实生成媒体，才能执行真实观察和媒体 QA。

没有真实媒体或媒体不可访问时，在本阶段的 `stage_result` 中分别更新相关轴；其他轴保持其真实现值，持久化时仍须提供完整 `workflow_status`：

- `workflow_status.observation_status = OBSERVATION_PENDING`
- `workflow_status.qa_status = QA_NOT_EXECUTED`
- `ncs = NOT_SCORED`
- `nrs = NOT_SCORED`

此时不实例化媒体 Gate，也不创建空 requirement；把“取得并观察当前媒体版本”写入 `next_action`。这不是媒体失败。只有真实媒体已经被检查且不符合要求时，才创建绑定该 artifact/version 与 observation 的 Gate，记录 `evaluation_status = EXECUTED`、`outcome = FAILED` 与 `workflow_status.qa_status = QA_FAILED`。只有 `execution_mode = SIMULATION` 时，`workflow_status.execution_status` 才能使用 `SIMULATED_ONLY`。

用户描述的问题可以记为 `USER_REPORTED`，但不能冒充系统已观看媒体、伪造时间码或直接产生 `OBSERVED`。

仅写完语音文字规格时，`covered_dialogue_ids / dialogue_audio_bindings / output_artifact_refs` 保持空且 `tts_coverage_status = NONE`。只有每条声明 covered 的 speech unit 都有且只有一个同版本 `MEDIA` Artifact 绑定时，才能写 `PARTIAL / FULL`；`FULL` 还要求 scope 全覆盖。真实音频与时长测量另由 `measurement_coverage_status` 计算；两类 coverage 都不代表听感、角色音色、口型、响度或字幕对轴已经通过。字幕 cue 必须回链对白单元和镜头，并落在该镜头的时间范围内；旧分镜改时长后要重新核对，不能沿用陈旧时间码。

## 观察记录

对每份真实媒体记录：

- `artifact_id`、版本、可访问位置和 provenance；
- 来自供应商 Pilot 时，记录 `provider_registry_id` 与明确的 `task_scope`；
- 观察者、观察时间与使用的媒体版本；
- 开始状态、事件/动作状态、结束状态；
- 身份、服装、道具、空间、世界设定、风格、对白和参考约束；
- 带时间码的时序、运动、物理与节奏证据；
- 预期状态与实际状态的差异；
- Failure 的范围、严重度、置信度和 evidence IDs。

观察只适用于被实际查看的版本和范围，不能从一个镜头外推整批通过。

## NCS — 叙事连续性评分（Narrative Continuity Score）

候选维度可包括身份、世界设定、叙事状态、空间、动作、风格、对白、参考约束和技术有效性。权重与阈值必须按项目配置，并记录依据、来源与适用范围；不能包装成普遍科学真值。

## NRS — 叙事节奏评分（Narrative Rhythm Score）

比较计划与真实媒体中的动作起点、峰值、反应、空转、信息释放和可剪切点。评分不能替代带时间码的观察，也不能自动代表市场表现。

没有真实媒体时，NCS/NRS 的唯一规范结果是 `NOT_SCORED`。不得给零分，因为零分意味着实际测量后表现为零；也不得给预测分、虚构时间码或通过结论。

## Gate 映射

- 真实资产版本 → `ASSET_GATE`；
- 单个真实镜头 → `SHOT_GATE`；
- 已剪接真实序列 → `SEQUENCE_CONTINUITY_GATE`。

每个已执行 Gate 都用 `scope_bindings` 绑定被观察的 artifact/version、shot plan 与 observation。`SHOT_GATE` 通过不自动让序列、成片或发布资格通过；未检查的后续 Gate 不预先实例化。

## 模拟推进

线路测试遇到外部生成步骤时，可以记录 `SIMULATED_EXTERNAL_STEP`，说明原本要求、跳过原因、真实输入和真实预期产物，然后继续逻辑步骤。后续分别保持 `workflow_status.observation_status = OBSERVATION_PENDING`、`workflow_status.qa_status = QA_NOT_EXECUTED`、`workflow_status.execution_status = SIMULATED_ONLY`，且 NCS 与 NRS 都是 `NOT_SCORED`；不能声称真实 QA 完成。
