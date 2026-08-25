# Stage 5 — AI 生产可行性与生成资格

本阶段的任务方法保留；Gate 实例化、typed scope、Prompt 分层和真实性 basis 遵守 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`。可行性、成本、失败模式、替代方案、试制建议与资格结论遵守 `interaction_language`；工具名、版本、参数和来源保留正式名称。

## 风险负担扫描

至少检查：

- 高频重复角色与身份一致性；
- 群演和多人场面；
- 手部、身体接触、道具归属和复杂交互；
- 长对白与口型同步；
- 可读屏幕和 UI；
- 镜面与反射；
- 水体、透明材质和湿润状态；
- 车辆、动物；
- 变形和 VFX；
- 破坏前后状态连续性；
- 大量地点、服装和角色状态切换；
- 长时间动作编排；
- 跨镜头连续性、人工复核与局部修复负担；
- 双画幅是否实际需要分别构图或分别生成。

每项重要风险输出：叙事必要性、具体难点、当前证据、定性风险、Production Alternative、最小 Pilot、停止条件和仍需验证项。没有测量数据时，不给出精确成功率、重试次数或降本百分比；若必须提出数字，按精确数字护栏记录 `basis`、来源和 `precision_status`。

物理可行性不是“换个机位就看不见”的问题。嘴部被道具占用、手部同时承担互斥动作、身体失去支撑却继续发力、道具无承接消失、现实声源与幻想开口不一致时，必须把可见的释放、承接、受力、反作用和终态排进动作顺序。遮挡只能服务安全呈现或信息控制，不能被写成物理修复；改变发声方式或剧情事实前先取得用户确认。

任何进入制作判断的数字还必须登记 `quantity_type`。特别是 `RATE` 与 `OFFSET` 分开：速率若要转成观众可见位移，必须说明观察窗口、单独校准基准、推导和 `display_mapping`。比较基准使用 `baseline_specs`，记录校准链、控制样本、历史基线和替代解释；不能把另一只未校准设备直接称为单独校准基准。

## Production Alternative 约束

面对高风险戏剧段落，先运行 Production Alternative Engine，再讨论供应商或更强模型。拆镜、远景、局部交互、反应镜头、声音、环境、插入镜头、首尾状态、剪辑和选择性补拍必须共同保留原段落的叙事功能。

替代方案还必须：

- 引用原段落权威目标时长；
- 逐镜重算替代总时长；
- 映射每项叙事功能为 `PRESERVED | PARTIAL | LOST`；
- 登记新增的声音、后期、补拍和资产依赖；
- 未经真实试制时保持 `MITIGATION_PLANNED`，不能声称风险已解决；
- Benchmark 案例使用 `BENCHMARK_ONLY` 与单独的 `benchmark_case_id`，不得进入真实项目资产、镜头、Prompt、依赖或预算。

## 生成准备关卡（`GENERATION_READINESS_GATE`）

生成资格分两个 scope，不能与资产、镜头、成片或发布资格混为一谈。

### 最小试制（`MICRO_PILOT`）

用于开始最小代表性试制。检查：

- Pilot 的具体假设、范围、输入、输出与停止条件；
- 必需资产/参考和当前 `PROVIDER_COMPILED` Prompt 可用；
- 当前供应商、地区、账号、权限和预算允许执行；
- 安全、素材许可和不可逆操作没有阻断；
- 观察与验收方法已经定义。

没有最终媒体不是失败，正是此 Gate 要批准最小生成的原因。只有真的完成本次资格评估时才实例化 Gate；符合条件时记录 `gate_type = GENERATION_READINESS_GATE`、`readiness_scope = MICRO_PILOT`、`evaluation_status = EXECUTED`、`outcome = PASSED`，并在 `scope_bindings` 绑定 provider、当前选中的 3—5 个代表性 `generation_targets`、这些目标的 `PROVIDER_COMPILED` Prompt、任务和当前版本。角色/场景资产参考图可以在尚无 shot plan 时单独试制；已有分镜目标再绑定 shot plan。若尚未开始评估，只把它写为下一步，不创建占位 Gate。不得要求先通过 `ASSET_GATE` 或 `SHOT_GATE` 才允许生成第一份测试媒体，也不得要求整个项目 Prompt 全覆盖后才允许小范围 Pilot。

### 批量生产（`BATCH_PRODUCTION`）

批量生成前额外检查：

- `pilot_assessment.status = PASSED`，包含真实产物、观察、连续核心理解链与无提示复述证据；
- 资产注册表与 shot-local dependencies 完整；
- 本批次所有计划生成目标（资产参考、静态关键帧、视频运动或合成层）都有当前 `PROVIDER_COMPILED` Prompt coverage；
- 供应商版本、权限、额度与项目实测状态有效；
- 团队人数、工时、预算、硬件与审修负担可承受；
- `canonical_duration`、镜头数量、格式变体与开放 blocker 已协调。

满足后才可让 `GENERATION_READINESS_GATE` 在 `readiness_scope = BATCH_PRODUCTION` 下记录 `EXECUTED + PASSED`。Gate typed scope 必须与通过的 Pilot 在 provider、shot plan、format、task 和版本上匹配，并覆盖本批次的 `PROVIDER_COMPILED` Prompt；“项目里存在一个 Pilot”不够。只有计划而无匹配 Pilot 证据时，已执行检查应根据实际情况记录 `FAILED` 或 `BLOCKED`；不要把它写成资产或镜头 QA 失败。

## Gate 记录

只有已执行的关卡才写入账本，并使用：

```yaml
scope_bindings: typed current provider / plan / pilot / prompt / task / format scope
evaluation_status: EXECUTED
outcome: PASSED | FAILED | BLOCKED | ACCEPTED_WITH_DEBT | NOT_APPLICABLE
```

强制 requirement 只能来自 `SYSTEM_INVARIANT`、`USER_APPROVED_DECISION`、`VERIFIED_EVIDENCE` 或 `APPLICABLE_RULE`。`PROPOSED` 工具、路线、时长或预算建议不能直接造成 Gate 失败。未执行的未来 Gate 保持不存在，只出现在 `next_action`。
