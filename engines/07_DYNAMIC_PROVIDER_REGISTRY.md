# 动态供应商注册表（Dynamic Provider Registry）

本引擎保留供应商研究与任务路由方法；typed scope、Prompt 分层、Pilot 与 Gate 关系遵守 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`，领域证据结构继续参考 `../references/EVIDENCE_PROVIDER_RELEASE_LEARNING_CONTRACT.md`。实际使用的候选记录必须覆盖当前地区、入口和模型版本；旧项目记录只能作为历史线索，未失效的同范围证据可复用。

## 为什么需要动态注册表

供应商能力、模型版本、可用入口与相对优势变化很快。静态工具清单会迅速过时，也无法代表用户当前真正拥有的权限、额度与实践结果。

因此每个项目或会话只为**当前任务的实际候选**建立最小注册表，不做全行业模型盘点，也不把某一套生成工具写成全局默认。当前能力核查遵守 `../references/ON_DEMAND_RESEARCH_ROUTER.md`：用最少查询确认会改变分镜、Prompt、预算或执行路线的字段，并把结果压缩为可缓存 Evidence Capsule；未失效时复用，不重复读取整份产品手册。

供应商能力解释和选择理由遵守 `interaction_language`。产品名、版本、参数、能力字段与来源原文保持正式名称，不为了中文化而翻译模型名或控制参数。

## 每个项目或会话的记录结构

每个供应商或模型至少使用：

```yaml
provider_id: PRV-###
provider: 供应商主体
display_name: 当前官方产品名
marketing_aliases: []
surface: API / 网页产品 / 地区入口
api_model_id: null
snapshot_id: null
availability_kind: API_AND_SURFACE | API_ONLY | SURFACE_ONLY | UNKNOWN
model: 正式模型名或当前可核验标识
version: UNKNOWN
region: UNKNOWN
access: AVAILABLE | LIMITED | NOT_AVAILABLE | UNKNOWN
access_source_ids: []
price:
  value: UNKNOWN
  currency: UNKNOWN
  billing_unit: UNKNOWN
  tier_or_plan: UNKNOWN
  status: VERIFIED_CURRENT | USER_REPORTED | ESTIMATE | UNKNOWN
  basis: 尚未核验；不得作为预算事实
  source_or_evidence_ids: []
  precision_status: HEURISTIC
source:
  publisher:
  title:
  url:
  source_type: OFFICIAL | THIRD_PARTY | USER_REPORTED
checked_at: UNKNOWN
project_pilot_status: NOT_RUN | PLANNED | RUN_PARTIAL | PASSED | FAILED | INCONCLUSIVE
classification: VERIFIED_OFFICIAL | USER_REPORTED | SYSTEM_INFERENCE | HEURISTIC | UNKNOWN
modalities: []
capabilities:
  - capability_id:
    name:
    status: VERIFIED | USER_REPORTED | INFERRED | UNKNOWN
    source_or_evidence_ids: []
    version_scope:
    region_scope:
strengths: []
weaknesses: []
cost_latency_notes: UNKNOWN
project_observations: []
```

- `provider + surface + api_model_id/snapshot_id + version + region` 共同定义不可变能力快照，任一变化都创建新的 `PRV-` 记录，不能静默改写旧记录；
- 营销别名、产品显示名和 API model ID 必须分列；产品已上线不等于 API 已开放，只有网页入口时使用 `SURFACE_ONLY`，不得臆造 API ID；
- `checked_at` 记录能力、入口和价格信息的核验日期；
- `classification` 区分官方资料、用户报告、系统推断、经验规则与未知；项目实测另由 `project_observations` 中的 `OBS-` 记录及其所链接的 evidence IDs 证明；
- `access` 记录用户现在是否真的可用，而不是理论上存在；
- `price` 必须带币种、计费单位、套餐和核查状态，不可只写一个金额；
- `capabilities` 按能力逐条记录；`VERIFIED` 必须有该供应商、版本和地区的证据，不能把一家模型的能力外推给全部候选；
- `project_pilot_status` 单独记录本项目是否真实试制；
- `project_observations` 只保存这个项目真实观察记录的 `OBS-` ID，不接受自评文字、Prompt 或计划；每条观察还应写 `provider_registry_id` 与 `task_scope`。这些观察不得外推成普遍能力。

无法核验的字段保持 `UNKNOWN`。用户报告自己可用某个当前无法核验的版本时，记录为 `USER_REPORTED`；不要否认用户，也不要把它升级为全球事实。

时长、分辨率、参考图数量、音频能力、并发量、计费、内容限制和入口差异都属于**精确能力主张**。每条都必须绑定同一 `provider + surface + model/version + region + snapshot + checked_at` 的当前证据，并保存数值单位与适用条件。精确时长标为 `VERIFIED` 时，每条来源都必须是合格的官方、主要研究或平台实测分类，claim class 为事实或样本观察，且 provider/capability/evidence 的 `checked_at` 相等并处于显式 `CURRENT` freshness 窗口内；`SYSTEM_INFERENCE` 或任一过期、缺 scope 的来源都会使该 VERIFIED 主张失效。没有当前证据时只能保留 `UNKNOWN` 或可验证假设；不得把旧版本、另一入口、用户记忆或其他供应商的限制写成当前硬门槛，也不得硬编码任何厂商数值。

第三方或用户报告来源不得标为 `VERIFIED_OFFICIAL`。来源对象缺发布者、标题、完整 URL 或核验日期时，只能降级，不能用“官方资料显示”代替证据。

## 任务级路由

供应商选择必须针对具体任务，并用中文解释：

- 当前镜头或资产究竟需要什么；
- 哪项模型能力决定成败；
- 为什么推荐工具在当前版本、当前权限和当前任务下适合；
- 如果不可用或试制失败，采用什么替代路线。

若用户已明确指定可用供应商和入口，不为“完整比较”扩展候选池；只核查当前任务真正依赖、且可能变化的能力。若用户尚未指定，先按任务所需能力筛出最小候选与一个可行回退，再核查当前版本、入口、地区和权限。官方资料能缩小候选，但最终批量资格仍由本项目代表性 Pilot 决定。

供应商检索按轻量检索路由的默认预算执行；证据足以支持继续、保持 `UNKNOWN` 或安排微型 Pilot 时即停止。供应商 Evidence Capsule 过期、版本/入口/地区/权限变化或出现冲突来源时，只刷新受影响能力，不重做整个注册表。

高风险能力没有项目实测时，供应商条目保持 `project_pilot_status = NOT_RUN`，或在试验已经排定时使用 `PLANNED`；此时 `GENERATION_READINESS_GATE` 在 `readiness_scope = BATCH_PRODUCTION` 下不得 `PASSED`。若上游规格、权限、预算与安全条件已满足，可以另行评估同一 Gate 的 `readiness_scope = MICRO_PILOT`，让最小试制合法开始。供应商选择和详细提示词只是制作规格，不证明批量可行性。

Prompt 分四层记账：MP 是权威意图源；TP 是内部转换计划；NEP 是完整可复制的中性执行稿；只有同时回链 MP、TP、NEP，并绑定当前 `provider_registry_id` 与具体 surface/model/version/region 的 `PROVIDER_COMPILED` 才能真实提交。MP、TP、NEP 都不能进入供应商执行或 Generation Readiness Gate；已编译 Prompt 也不能从另一 provider/version 继承证据。

涉及年龄受保护角色时，编译记录必须保存真实 `age_years`、`is_minor` 与 `minor_compilation_mode = EXACT | LIFE_STAGE | REFERENCE_BOUND`。模式只改变安全表达方式，不改变角色事实。若供应商在符合内容规范的表达下仍不接受，记录结果并改走安全构图、分层合成或另一已核验供应商；不得改变年龄事实，也不得声称某个供应商必然接受。

官方能力页、排行榜、他人案例和用户过往经验都不能替代本项目 Pilot。`project_pilot_status: PASSED` 必须链接可访问真实产物的观察记录；观察的 `provider_registry_id` 必须等于该供应商条目，`task_scope` 与 `observed_at` 非空，`basis` 必须为 `DIRECT_MEDIA_ACCESS` 或 `MEASURED_DATA`。不能仅因“成功生成一次”就推断可批量生产。

固定 seed 只是一项可复现实验参数，不是角色身份一致性的证明。身份一致性仍需参考资产、身份锚点、镜头约束以及真实跨镜媒体观察共同支持。

## 任务级候选比较

比较结果至少包含：

- 任务 ID 与所需能力；
- 候选模型的精确版本、地区和可用入口；
- 能力主张所引用的 evidence IDs；
- 当前价格状态与未知成本；
- 本项目 Pilot 状态；
- 选择理由、失败回退和重新核查条件。

不得把任何供应商或模型设为永久默认。`Seedance`、`Kling` 这类系列名不足以绑定执行，必须继续记录版本、变体、入口和地区；营销别名不能代替 API ID。示例模型必须用中文明确说明“仅为日期快照，使用前核查当前版本”。没有当前证据时，不得声称某模型“最新、最强、最便宜、淘汰或最稳定”。

若执行提示词使用非中文，必须同时提供 `intent_summary_zh`，并保持引用 ID、参数、控制 token 与专有语法不变。
