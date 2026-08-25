# 产物、模拟与提交引擎

本引擎保留产物与模拟方法；scoped completion、Gate 实例化和真实性 basis 遵守 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`。面向中文用户时，用中文解释“仅模拟”“未执行媒体 QA”、真实项目需要的输入与产物，以及下一步如何推进；机器状态码保持英文。

## 六条完成轴不能合并

同一项目可以是 `spec_status = SPEC_READY`，同时执行尚未开始、媒体仍待观察、QA 未执行、发布未就绪且没有真实数据。某一份文字规格若完整，只对该对象和版本创建 `spec_completion_record`；禁止用一个“完成”覆盖整个项目或其他五条轴。

真实性层级仍为：

`SPECIFICATION < REAL_ARTIFACT < OBSERVED_ARTIFACT < VALIDATED_ARTIFACT < LOCKED/COMMITTED_ARTIFACT`

文字写得完整不会提高媒体真实性等级。

## 提交与锁定规则

- 文字资产说明不等于真实资产文件；
- Prompt 列表不等于已经生成的媒体；
- 分镜文字不等于已经审看的真实镜头；
- 计划中的 QA 不等于已经观察并执行的 QA；
- 发布前预测不等于真实表现学习；
- 缓解方案不等于风险已经降低；
- 模型自审不等于用户审阅或外部验证；
- 受影响版本仍有开放 blocker 时，不能提交或锁定；
- 每个真实性声明都要回答：产物是否存在、是否实际观察、是否按命名范围验证。

## 新文字产物与覆盖率必须可审计

- 新增或改写的简报、剧本、分镜、Prompt 包、字幕、配音计划、后期方案和发布文案，必须登记为带版本的 Artifact，并保存当前文件 SHA-256；只在聊天中声称“已写好”不能进入文字完成范围。
- `spec_completion_record.scope_ids` 只能引用已登记且哈希对应当前内容的文字产物；文件发生有效变化后，旧完成记录不得继续授权新版本。
- 镜头、对白、字幕、配音与 Prompt 的覆盖率分别计算。某一层为 `FULL` 不代表其他层完整，更不代表媒体已经生成或 QA 已通过。
- 只测量部分对白、只生成部分语音或只检查部分时间码时，必须显示 `PARTIAL` 并点名缺失项；不得把样本时长称为“全片配音时长”。
- 模拟模式可以完成上述文字登记与覆盖核对，但真实媒体、声音听感、字幕对轴和最终成片仍保持未执行状态。

## 生成资格与验收资格分离

`GENERATION_READINESS_GATE / MICRO_PILOT` 的目的正是允许在没有最终媒体时开始最小试制。它只要求：目标与范围可执行、必要输入存在、权限与预算可用、风险与停止条件明确、没有安全或授权阻断。

第一轮 Pilot 不需要先通过 `ASSET_GATE` 或 `SHOT_GATE`；这些关卡要等真实产物出现后才能执行。只有进入 `BATCH_PRODUCTION` 时，才要求代表性 Pilot、完整资产与镜头引用、Prompt coverage、供应商可用性和产能证据。禁止形成“没有媒体所以不能生成、不能生成所以永远没有媒体”的循环。

## Gate 状态真实性

- 媒体尚不存在或不可访问：不实例化对应媒体 Gate，只在状态轴和 `next_action` 说明待观察/待 QA；
- 已检查真实媒体且不合格：创建同 scope Gate，记录 `EXECUTED + FAILED`；
- 只有真实适用证据和 typed `scope_bindings` 才能支持 `EXECUTED + PASSED`；
- `PROPOSED` 和 `UNKNOWN` 决定不能成为强制 Gate requirement；
- 自由文本 scope 或另一版本的观察不能授权当前对象。

## 用户排除步骤不属于模拟

`delivery_mode = TEXT_ONLY_ECO_TEST` 且用户明确排除生图、视频、音频、配音、剪辑或渲染时：

```yaml
excluded_step_status: EXCLUDED_BY_USER
delivery_mode: TEXT_ONLY_ECO_TEST
execution_status: NOT_EXECUTED
observation_status: NOT_EXECUTED
qa_status: QA_NOT_EXECUTED
production_validation: NOT_TESTED
```

被排除能力不创建/执行媒体任务，不实例化媒体 Gate，不写 `SIMULATED_EXTERNAL_STEP` 或 `SIMULATED_ONLY`。文字产物只按精确 ID、版本、hash 与 scope 建立 `spec_completion_record`；可见终点仅为累计代表 Prompt 达标后的 `TEXT_PILOT_COMPLETE`，或点名文字范围完整后的 `TEXT_SPEC_COMPLETE`。

每轮以 `RUN_SUMMARY` 分别报告文字完成范围、`EXCLUDED_BY_USER`、未执行真实性轴、开放问题和恢复指针。禁止把“未要求执行”改写为“已模拟执行”，也禁止由文字完整性倒推出媒体、QA、发布或学习状态。

## 模拟模式

基准测试或线路测试可以模拟后续阶段，但必须保存：

```yaml
execution_mode: SIMULATION
workflow_status:
  spec_status: SPEC_READY
  execution_status: SIMULATED_ONLY
  observation_status: OBSERVATION_PENDING
  qa_status: QA_NOT_EXECUTED
  publication_status: RELEASE_NOT_READY
  learning_status: NO_REAL_DATA
  status_basis:
    execution_artifact_ids: []
    observation_ids: []
    qa_gate_ids: []
    release_gate_ids: []
    publication_ids: []
    learning_ids: []
real_artifact_present: false
terminal_markers: []
spec_completion_records:
  - 仅列本轮确实完整的文字对象与版本，并明确 does_not_claim
```

跳过外部步骤时记录：

```yaml
external_step_status: SIMULATED_EXTERNAL_STEP
requested_action: ...
skip_reason: ...
real_inputs_required: []
real_outputs_expected: []
observation_status: OBSERVATION_PENDING
qa_status: QA_NOT_EXECUTED
ncs: NOT_SCORED
nrs: NOT_SCORED
```

然后继续下一项逻辑步骤。模拟可以完成规格与路线压力测试，但不能把观察、NCS/NRS、视觉 QA、剪辑验收、发布或真实表现学习写成真实闭环。

模拟走到底时，用户可见结论必须明确具体 scope：

> 已点名的文字规格已经完成；真实制作尚未完成，媒体观察、QA、发布和性能学习按实际证据状态分别记录；`terminal_markers` 为空。

若本轮确实只有文字线路完整、全部外部制作均为模拟，末端摘要固定逐轴显示：本轮点名文字范围 `TEXT_SPEC_COMPLETE`、执行 `SIMULATED_ONLY`、媒体 QA `QA_NOT_EXECUTED`、发布 `RELEASE_NOT_READY`、学习 `NO_REAL_DATA`。这五项必须分别解释，不能压缩成“全流程已完成”，也不能让 `TEXT_SPEC_COMPLETE` 看起来像项目级真实终点。

## 两种终点

- 文字模拟不创建终点标签：具体文字对象由 scoped completion 表达，外部步骤由模拟记录表达；
- `REAL_PRODUCTION_COMPLETE`：真实资产、镜头、序列、最终成片和发布前交付按命名范围通过。若声称已发布，另需 `PUBLICATION_EVIDENCE_GATE` 的真实证据；若声称学习有效，另需 `LEARNING_GATE`。
