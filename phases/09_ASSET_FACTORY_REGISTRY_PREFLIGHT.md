# Stage 8 — 资产工厂、注册表与风险镜头预检

面向用户的资产状态、缺口、预检结论和下一步遵守 `interaction_language`；资产 ID、版本、哈希和机器字段保持英文或 ASCII。本阶段遵守 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`；年龄受保护角色、复杂同镜和能力 coverage 遵守 `../references/AGE_SAFETY_PROVIDER_AND_COVERAGE_CONTRACT.md`。不能把 Pilot、资产锁定和批量生产资格合并。

## 资产注册表（Asset Registry）

每项至少记录：

- 稳定 ID、版本、类型和真实文件位置；
- 来源与溯源信息（provenance）；
- 锁定特征与可变特征；
- 已批准视角、状态和格式变体；
- 空间位置、归属与接触状态；
- 依赖项与使用该资产的 `shot_id`；
- 观察、QA 与 evidence IDs；
- 已弃用版本和替代关系。

年龄或来源尚不能判定时，在资产层记录 `subject_age_class = UNKNOWN`，不创建 minor profile，也不预设年龄类别。已经判定为年龄受保护角色时，在 `minor_safety_profiles[]` 统一保存 `profile_id / asset_id / source_spec_version / is_minor=true / age_years / source_life_stage / age_source_ids / majority_age_years / age_rule_basis / age_rule_source_or_evidence_ids / minor_compilation_mode / compiled_age_years / compiled_life_stage / reference_asset_ids / compatibility_alternative / safety_review_status`。`compiled_*` 只属于 Prompt 表达层，不能回写覆盖年龄事实；参考资产也不能越权覆盖年龄事实。

随机种子、Prompt、文件名或相似描述都不能单独证明身份一致。身份锁定需要真实产物、跨所需视角/状态的观察和明确验收证据。

## 角色设定集（Character Bible）

记录叙事身份、行为规律、minor profile 的年龄/规则事实字段、视觉 DNA、服装、表情和状态范围，以及哪些特征必须锁定、哪些可以变化。年龄与生命阶段属于受保护身份事实，表达层不得改变。设定集是约束规格，不是 `ASSET_GATE` 的通过证据。

## 年龄受保护角色和复杂同镜预检

含年龄受保护角色与成年角色同镜、多人遮挡、严格身份连续、复杂肢体交互、长动作链或口型要求时，不默认单次生成可行。若当前 provider/model/version/surface/task 没有适用能力证据，记录 `minor_adult_same_shot_strategy = DECOMPOSITION | COMPOSITE`：前者拆为可核验镜头，后者把分离图层/镜头交给后期合成。两种方案都保留年龄、叙事功能、状态继承与素材许可来源。

## `MICRO_PILOT` 预检

角色定妆、服装、场景、道具或风格静态参考图可以在精细分镜之前进入 Prompt Pilot，使用 `target_type = ASSET`、真实 `target_id = asset_id`、`generation_role = ASSET_REFERENCE` 与 `generation_medium = IMAGE`；确需验证转身、步态或表演的资产参考视频改用 `generation_role = ASSET_MOTION_REFERENCE` 与 `generation_medium = VIDEO`。二者都不伪造 `shot_id`，也不计入成片 canonical duration。四层 Prompt 与质量检查仍调用 `../references/PROMPT_QUALITY_CORE.md`，供应商编译调用 Stage 11。输出媒体只有在真实可访问、登记版本/hash 并完成观察后，才能升级资产状态或成为后续 I2V 的输入参考。

批量生成前，优先测试最具代表性的高风险单元：

- 身份辨识要求高的视角切换；
- 多角色或人与道具交互；
- 困难环境、材质、VFX、文字或动作；
- 双画幅共享方案赖以成立的安全区与构图；
- 整套生产方法赖以成立的关键镜头。

Pilot 必须预先定义假设、输入、输出、观察方法和停止条件。固定生成次数、成功率或阈值若无依据，只能标 `HEURISTIC` 或 `TUNABLE`，不能自动成为失败线。

涉及供应商能力的 Pilot 还必须绑定当前 `provider_registry_id` 及其 provider/model/version/surface/region/task、输入方式和 `capability_evidence_ids`。不把“15 秒”写成通用时长；计划超出已证实能力时先拆镜、换用有证据的入口或路由后期组合。

## 资产 Gate 与生产资格

- 没有真实资产：不实例化 `ASSET_GATE`；资产规格可标 `SPEC_READY`，并在本 scope 文字完整时创建 `ASSET_REGISTRY_SPEC` completion record，但不能把资产标为 `LOCKED`；
- 有真实资产且已检查失败：`ASSET_GATE` 记录 `evaluation_status = EXECUTED`、`outcome = FAILED`；
- 只锁定经过观察并按明确要求通过的精确版本；
- 通过少量资产 Pilot 不自动使 `GENERATION_READINESS_GATE` 的 `BATCH_PRODUCTION` scope 通过；还要检查完整 registry、镜头依赖、Prompt coverage、供应商、预算和修复负担；
- 第一轮 Pilot 不需要先通过最终资产 Gate，避免生成资格循环。

已执行的 `ASSET_GATE` 必须在 `scope_bindings` 中绑定被检查的资产 artifact/version 与观察记录；另一资产或旧版本的通过结论不能迁移。

若 preflight 发现失败，只记录观察到的 Failure 与影响范围，不把“未测试的其他资产”一并判失败。

本阶段新建或实质改写的资产注册表、角色设定集和预检报告，只要会被下游引用，都登记为当前 `TEXT_SPEC` Artifact，保存 `status + version + content_locator.sha256`。创建 `ASSET_REGISTRY_SPEC` completion record 前，必须先有这些当前状态与哈希。
