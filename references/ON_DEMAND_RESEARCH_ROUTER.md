# Alpha.7 Master 轻量按需检索路由

本路由只为**会改变当前决定的外部事实**取证。漫剧、短剧的故事开发默认不联网；推广、科研科普、文化、教育、品牌等项目也只检索当前步骤真正依赖的事实，不把整站、整份手册或通用资料库灌入上下文。

## 1. 何时触发

出现以下任一情况时，创建当前任务所需的 `RESEARCH` 任务：

- 当前适用要求、平台规则、AI 标识、登记要求、许可、比赛规则或发布日期声明；
- 当前供应商的模型版本、入口、地区、权限、价格或精确能力；
- 非虚构/混合项目中的学术结论、统计数字、人物身份、引文、文物或需要核实的事实主张；
- 用户明确要求“最新、核实、检索、官方来源”；
- 市场、趋势或平台判断将实质改变题材、形式、预算或发行路线。

以下内容默认不触发检索：纯虚构创意选择、人物情绪、对白润色、审美偏好、用户已明确给出的项目约束、本地文件结构检查，以及必须依靠真实媒体完成的生产 QA。若外部事实与这些任务无关，直接继续创作。

### 1.1 可复制 Prompt 的低算力短路

当用户已经自行确认某个网页入口可用、本轮只要求手动复制 Prompt，且文字不依赖当前模型版本、价格、精确时长、参考语法或专有能力时，不创建供应商研究任务，也不加载额外模型手册。登记范围仅限用户报告的 surface，model/version 保持 `SURFACE_MANAGED_UNKNOWN`，Pilot 为 `NOT_RUN`，PP 使用 `execution_contract = MANUAL_COPY_TEXT_SPEC_ONLY`。该 PP 不能进入 Generation Readiness 或真实生成任务。

只要成品声称或依赖当前能力、版本、地区、价格、输入格式、原生声音、精确时长、API ID 或供应商专有引用语法，就不能走该短路；改用最小官方证据 Capsule，编译为 `GENERATION_EXECUTABLE` 候选。用户报告只能证明“用户说入口可用”，不能证明模型能力。

## 2. 最小检索预算

每次只回答一个明确的 `decision_question`：

- 默认使用 **1—3 个聚焦查询**；
- 默认保留 **3—8 条直接相关的一手来源**；
- 适用规则、平台要求、供应商能力和科研事实优先官方原文或原始研究；
- 搜索结果页、媒体转述和聚合榜单只作定位线索，不能替代可得的一手来源；
- 找到足以改变或保持当前决定的证据后停止，不为“调研完整”继续扩张范围。

若只有一条权威原文且已完整覆盖问题，或一手来源客观不足，可以少于 3 条，但必须写明原因与局限。若 3 个查询仍无法覆盖，先产出 `UNKNOWN / LIVE_MARKET_DATA_UNAVAILABLE` 或提出新的单独研究任务，不在同一任务中无限扩搜。

## 3. Evidence Capsule

检索结果保存为紧凑研究附件，不直接复制长网页：

```yaml
capsule_id: EC-###
decision_question: 当前证据要帮助决定什么
trigger: LAW_PLATFORM | PROVIDER_CURRENT | NONFICTION_FACT | MARKET_TREND | COMPETITION_CURRENT | USER_REQUESTED_CURRENT
project_route_types: []
queries: []
sources:
  - publisher: 来源发布者
    title: 来源标题
    url: 直接 URL
    source_type: OFFICIAL | PRIMARY_RESEARCH | OTHER
evidence_ids: []
conclusion_zh: 一段中文结论
largest_unknown_zh: 最大未知项
recommended_action_zh: 最小可逆行动
checked_at: timestamp
freshness_basis: 为什么在当前时间范围内可用
valid_until: timestamp | UNKNOWN
stale_conditions: []
status: CURRENT | STALE | SUPERSEDED | INCONCLUSIVE
limitations: []
```

Capsule 作为 `TEXT_SPEC` 研究附件登记版本与哈希；真正参与决定、Gate、供应商能力或发布判断的主张，仍须拆成现有 `E-###` evidence 记录并满足 typed scope。`evidence_ids` 必须解析到已登记证据；Capsule 中的来源索引不能用摘要文字代替来源对象。

## 4. 缓存与失效

`status = CURRENT` 且未触发失效条件时，优先复用 Capsule，不重复检索。不要设置跨领域通用保鲜天数；按主张变化速度写 `freshness_basis`，并至少给出 `valid_until` 或可判定的 `stale_conditions`。

以下情况必须标为 `STALE` 并重新核查相关部分：官方页面或规则更新、模型/版本/入口/地区变化、适用日期到达、项目发布地或平台改变、用户权限改变、出现相冲突的一手来源，或当前决定超出原 typed scope。只刷新受影响的主张，不重做整个研究包。

## 5. 真相与授权边界

- 检索回执只证明检索动作发生；网页存在不自动证明主张真实或规则适用。
- Evidence Capsule 与 evidence 可以支持提案或适用性判断，但不创建 `USER_APPROVED / LOCKED`。
- 供应商官方能力、排行榜和案例不能替代本项目 Pilot；研究不能创建媒体 Observation、NCS/NRS、生产 QA 或 `GENERATION_READINESS_GATE` 的批量资格。
- 市场或传播证据不能静默改写 `core_claims`；冲突时提出兼容实验或请求明确决定。
- 中文用户先看中文结论、最大未知项和下一步；原始标题、URL、字段名和必要短引文保留原语。

## 6. 与唯一总调度衔接

由银幕总控创建一个最小 `task_graph` 记录：`task_type = RESEARCH`，按实际能力使用 `BROWSER / API / LOCAL_TOOL / MANUAL`，并保存真实回执。只创建当前研究任务和必要的紧邻后续；辅助项目类型不得因此加载漫剧主链之外的全部模块。
