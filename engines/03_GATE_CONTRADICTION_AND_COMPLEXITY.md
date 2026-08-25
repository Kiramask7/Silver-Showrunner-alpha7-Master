# 关卡、矛盾与复杂度引擎

本引擎保留矛盾诊断方法；Gate 实例化、typed scope、scoped completion 与用户档位遵守 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`。用户可见的矛盾说明、关卡结论和修复建议遵守 `interaction_language`，机器码保持英文。

## 关卡链与结果结构

按顺序使用：

`GENERATION_READINESS_GATE → ASSET_GATE → SHOT_GATE → SEQUENCE_CONTINUITY_GATE → FINAL_ARTIFACT_GATE → RELEASE_READINESS_GATE → PUBLICATION_EVIDENCE_GATE → LEARNING_GATE`

这是一张依赖图，不是预建清单。只有对明确对象真实执行评估时才创建 Gate，并同时记录：

```yaml
scope_bindings: typed current objects and versions
evaluation_status: EXECUTED
outcome: PASSED | FAILED | BLOCKED | ACCEPTED_WITH_DEBT | NOT_APPLICABLE
```

尚未评估的未来 Gate 不实例化，只写入 `next_action`。`FAILED` 才表示已经检查且不合格；无媒体而无法评估不是失败。返工、先测试、请求用户决定或回滚写在用户可见 `recommendation` / `next_action` 中，不添加到 Gate 对象，也不能替代 Gate 结果。

## 要求来源审计

只有以下来源可以建立强制 Gate 要求：

- `SYSTEM_INVARIANT`；
- `USER_APPROVED_DECISION`；
- `VERIFIED_EVIDENCE`；
- `APPLICABLE_RULE`。

每项要求必须带 `source_id`。`PROPOSED`、`UNKNOWN`、系统偏好、示例值或未核验的行业说法不能成为必过要求；若它阻碍路线选择，应记录为开放问题或 `HUMAN_DECISION`，不能伪装成失败。

## 矛盾检查

每项新提案与以下信息交叉核对：

- 不可妥协项、`core_claims` 与已批准决定；
- 仍为 `UNKNOWN` 的内容和授权边界；
- 目标受众、故事和世界规则；
- 已核验且适用的平台与内容规范限制；
- 用户真实可用的团队、工时、预算、硬件、账号、供应商权限和额度；
- 当前资产、镜头、Prompt、剪辑和发布包版本；
- 唯一权威 `canonical_duration` 与逐镜重算值；
- 资产数量、稳定 ID、shot-local dependencies 与 Prompt coverage；
- 横竖格式的机位、动作调度、信息层级与安全区证据；
- 尚未关闭的阻断问题及其影响范围。

## 会阻止锁定或推进的矛盾

在对应 Gate 已实际执行且 `scope_bindings` 覆盖目标对象后，以下情况通常产生 `FAILED` 或 `BLOCKED`，并在用户可见建议中说明需要返工、先测试或请求用户决定：

- `canonical_duration` 与镜头时长之和不一致，且没有有来源、已批准的容差规则；
- 声称双画幅只需裁切，却需要不同机位、人物位置或动作调度，或没有安全区证据；
- 工具、团队、范围、排期或预算记录彼此冲突；
- 资产/镜头目标 ID、生成角色、Prompt coverage 或上游版本不完整；
- 受影响产物仍有未解决的阻断问题；
- 缓解或修复只有计划，没有新产物与新观察，却被标记为已解决；
- 把未执行的媒体检查写成失败或通过；
- 把未批准提案升级为强制要求。

项目没有定义容差时，必须报告精确差异并请求修订或批准，不得自动套用任何默认百分比。精确阈值须记录依据、来源和 `precision_status`。

如果矛盾触及创作者明确保护的核心事实，且不存在不改动该事实的内容规范方案，则在 `next_action` 请求用户决定，不得替用户静默改写。

## 上游完整性检查

在 Provider 编译、批量生成或创建 scoped completion 前，按当前范围检查：真实 `target_type + target_id + generation_role + generation_medium`、资产/镜头依赖、MP→TP→NEP 回链、`PROVIDER_COMPILED` coverage、Prompt Quality PASS、中文意图说明、Reference Registry、上游版本、`canonical_duration` 重算、对白/字幕/TTS 覆盖与开放 blockers。`ASSET_REFERENCE` 不得伪造镜头；`SHOT_MOTION` 的 I2V 输入必须回链上游图像 Artifact/version。MICRO_PILOT 只要求选中的代表性目标完整，批量范围才要求本批次全覆盖。缺一项时只能缩小可安全范围、保持草案或在已执行评估中记录阻断，不能让下游状态覆盖上游缺口。TP 与 NEP 不能被计入可执行 Prompt coverage。

## 复杂度控制

系统内部可以复杂，用户界面必须保持克制：

- 先读取 `output_complexity_profile`，默认 `CREATOR_SIMPLE`；
- 只展示当前相关的宏阶段和已经实例化、真正影响推进的 Gate；
- 除非用户选择 `PRO_AUDIT` 或确有必要，不展开全部内部模块；
- 不为了证明工作流全面而制造额外工作；
- 优先交付一个真正有用的产物，而不是多份重复报告；
- 先给结论、证据边界和下一步；完整 Gate、Evidence、Prompt 与验证轨迹进入附件。
