# Stage 12 — 诊断驱动的最小修复与剪辑提交

本阶段的修复三元闭环、typed scope 与证据适用性遵守 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`。

修复原因、保留项、成本、范围和复验要求遵守 `interaction_language`；修复路由状态码、镜头 ID 和时间码保持规范形式。

## 先诊断，后选路由

修复不是固定阶梯，也不得为了“流程完整”遍历所有方法。以下代码是**无顺序候选集**，不是执行链：

`{TRIM, RETIME, EDIT, CUTAWAY, INSERT, PICKUP, PROMPT_PATCH, LOCAL_REGEN, FULL_REGEN, OTHER}`

先根据真实观察确定根因和最小有效作用域，再从可选方法中直接选择成本最低、预计有效且不破坏已通过部分的一项或组合：

- `TRIM`：问题只在可删除区间且不损害叙事功能；
- `RETIME`：动作与信息完整，但时序可通过速度或停顿调整；
- `EDIT` / `CUTAWAY`：可通过重剪或真实可用的切出镜头隐藏缺陷并保留连续性；
- `INSERT`：缺少可读信息、状态或反应；
- `PICKUP`：需要补拍/补生成一个明确小单元；
- `PROMPT_PATCH`：根因确实来自 Prompt 约束缺失，且仍需真实再生成验证；
- `LOCAL_REGEN`：局部真实媒体需重新生成；
- `FULL_REGEN`：根因贯穿整份产物且局部修复无效；
- `OTHER`：例如设计本身不可执行，需要回到上游决策或 Production Alternative；必须在理由中写明具体方法。

更便宜不等于有效；更强模型也不是默认答案。每个选择都要说明为什么能触及根因、会保留什么、可能损失什么和如何复验。

## 修复记录

```yaml
repair_id: R-###
failure_ids: []
root_cause:
diagnostic_evidence_ids: []
selected_method:
selection_rationale:
status: REPAIR_PLANNED | REPAIR_EXECUTION_PENDING | REPAIR_EXECUTED | REPAIR_VERIFIED | REPAIR_FAILED
source_artifact_ids: []
new_artifact_ids: []
new_observation_ids: []
re_evaluated_gate_ids: []
closure_links: []
```

若只有修复说明、剪辑计划或 Prompt patch，状态最多是 `REPAIR_PLANNED` 或 `REPAIR_EXECUTION_PENDING`。Prompt 变了不证明媒体修好。

## 真实修复也必须进入任务图

凡修复会真正改动媒体、重新生成、补拍、转码、重剪、替换声音或导出新版本，都必须在 `task_graph` 创建单独修复任务，并遵守 `../references/ALPHA7_EXTERNAL_EXECUTION_CONTRACT.md`。任务绑定 `repair_id`、Failure、源 Artifact/version、所选方法、批准范围、执行路线与预期输出；执行后创建与任务双向回链的 `execution_receipt`。

只有 `execution_receipt.result = SUCCEEDED` 且指向可核对的新 Artifact，修复记录才可升为 `REPAIR_EXECUTED`。只改 Prompt、写命令、打开编辑器、模拟外部步骤或收到用户口述，仍停在计划/待执行；不得生成虚假新版本。登录、验证码、费用、账号授权或不可逆边界按契约阻断并从检查点恢复，而不是重跑已通过任务。

## 关闭 Failure 的硬条件

关闭一项真实媒体 Failure 必须形成完整链：

每个关闭链条必须作为一个不可拆散的三元组写入：

```yaml
closure_links:
  - new_artifact_id: ART-NEW
    new_observation_id: OBS-NEW
    re_evaluated_gate_id: G-RECHECK
```

兼容数组 `new_artifact_ids`、`new_observation_ids`、`re_evaluated_gate_ids` 仍保留，但不能靠数组位置猜配对；`closure_links` 中每个 ID 都必须出现在对应数组中。

1. 产生新的真实产物或可审计的新版本；
2. 对该版本进行新的真实观察；
3. 用原要求重新执行对应 Gate；
4. 只有结果为 `EXECUTED + PASSED` 或经明确批准的 `ACCEPTED_WITH_DEBT`，才能把修复标为 `REPAIR_VERIFIED`。

每个 `closure_link` 还必须证明：新观察的 `artifact_id` 就是该新产物；重过关的 `evaluation_status = EXECUTED`，且 `outcome` 为 `PASSED` 或 `ACCEPTED_WITH_DEBT`；新观察与重过关至少共享一条适用 evidence ID。否则三份记录只是同时存在，不能证明修复闭环。

没有新媒体证据时，不能标 `REPAIR_VERIFIED`、`QA_PASSED` 或关闭 Failure。若 Gate 再次失败，保留新观察，更新根因假设，而不是假装已完成。

## 剪辑后的状态继承

用户或剪辑师接受一个剪辑区间后，从真实接受的 cut-out 建立 `EDITED_STATE`，不要继续沿用原始片段的结束状态。后续镜头、声音与连续性检查必须引用新版本。

## 带债接受（`ACCEPTED_WITH_DEBT`）

带债接受必须记录：风险、影响范围、批准事件、为什么当前可接受、触发重访的条件和到期/复查点。它不是隐藏 Failure 的快捷方式，也不能由系统自行替用户批准。
