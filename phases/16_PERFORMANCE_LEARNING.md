# Stage 15 — 真实表现学习

本阶段的 Gate、发布/数据/学习链遵守 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`，领域证据方法继续参考 `../references/EVIDENCE_PROVIDER_RELEASE_LEARNING_CONTRACT.md`。真实表现学习是**用户手工发布后的可选证据活动**，不是发布计划的延伸，也不是 `RELEASE_READY` 后自动运行的任务。

分析和行动建议遵守 `interaction_language`。平台原始指标名、图表字段和来源标题可以保留原语，但必须用中文解释统计口径、适用范围和局限。

## 进入条件

只有用户已经自行发布，并主动提供真实 analytics/公开表现数据或明确授权只读核对时，才可进入本阶段。必须同时存在通过 `PUBLICATION_EVIDENCE_GATE` 的可核验证据、真实已发布内容，以及真实 analytics 或可核验的公开表现数据。没有这些输入时 `learning_status = NO_REAL_DATA`，本阶段可另记 `execution_status = NOT_EXECUTED`；这不是失败，也不得模拟补全、自动抓取、登录平台或把 `RELEASE_READY` 当作已发布。

用户不发布、不回传数据或不希望继续学习时，流程合法停在 `RELEASE_READY`，无需创建学习计划、Gate 或占位数据。后续学习只读取用户提供/授权的数据，不自动改帖、投放、再次发布或触发任何对外动作。

输入不足时不实例化 `LEARNING_GATE`。未来的数据收集与核对写入 `next_action`，不能用空 Gate inventory 表示“流程已走到学习阶段”。

可用输入包括：

- 留存与观看时长曲线；
- 完播；
- 重看；
- 能取得时的标题或封面 CTR；
- 点赞、评论、分享和关注；
- 搜索流量；
- 流失时刻；
- 生成与重试成本；
- 实际制作时间；
- 修复频率和失败类型。

## 学习循环

`hypothesis → intervention → context/sample → real outcome → confidence → reusable/not reusable`

每个学习单元至少保存：

- `publication_ids`：该结论对应的真实发布记录；
- `analytics_artifact_ids`：真实存在且类别为 `DATA` 的分析产物；
- `hypothesis`：发布前可证伪假设；
- `intervention`：实际改变了什么；
- `context`：平台、受众、发布窗口和同时发生的其他变化；
- `sample`：分析单位、样本量与纳入规则；
- `outcome`：指标定义、基线或对照、真实观察值与 evidence IDs；
- `confidence`：`LOW | MEDIUM | HIGH`；
- `reusable`：`YES | NO | CONDITIONAL | UNKNOWN`，并说明限制和下一次测试。
- `status` 与真实数据 evidence IDs；记录级状态与项目级 `workflow_status.learning_status` 分别记账。

状态映射：有计划但无真实数据时，记录为 `LEARNING_PLAN`、项目轴为 `NO_REAL_DATA`；数据收集中使用 `DATA_COLLECTION_PENDING`；有数据但归因不足时，记录状态可为 `DATA_AVAILABLE` 或 `LEARNING_DRAFT`，结论允许 `INCONCLUSIVE`；只有发布记录、真实 `DATA` 产物、真实证据、样本与归因同时成立时才使用 `LEARNING_VALIDATED`。

把真实结果与以下内容比较：

- 市场假设；
- 传播叙事基因（Viral Genome）；
- 注意力契约（Attention Contract）；
- 节奏契约（Rhythm Contract）；
- 标题和封面假设；
- 单集时长；
- 生产假设。

不要把一次成功或一次失败普遍化。只有在口径、样本和情境足以支持时，才谨慎更新下一集或下一项目。有数据但样本、对照或归因不足时标 `INCONCLUSIVE`，而不是强行产出规律。

评论提到某角色、镜头、台词或设定，只能证明该元素在该评论样本中被提及。它不自动等于理解、喜欢、转化或项目成功。若没有预先定义目标、样本、基线和判定依据，不得发明“提及率阈值”或把评论计数升级为因果结论。

点赞、单条高播放、完播变化或主观反馈也不能单独证明假设成立。必须回到 `hypothesis / intervention / context / sample / outcome` 核对竞争解释。

任何数值决策规则都必须保留指标定义、样本与情境、基线、置信度、反证以及 `basis / source_or_evidence_ids / precision_status`。没有真实分析数据（analytics）时，相关结论只能保持 `classification = HEURISTIC` 或 `UNKNOWN`，不能声称已经完成真实表现学习（Performance Learning）。没有当前证据时，不设置通用“成功线”“最佳发布时间”或商业转化阈值。

## Learning Gate 关系链

`LEARNING_GATE` 通过时，Gate 顶层 `learning_ids` 和 `publication_ids` 必须显式覆盖同一条链上的学习与发布记录，`scope_bindings` 则绑定相关 artifact 与精确版本。被引用的学习记录必须是 `LEARNING_VALIDATED`，其全部 `publication_ids` 已经由通过的 `PUBLICATION_EVIDENCE_GATE` 覆盖；其 `analytics_artifact_ids` 指向真实 `DATA` 产物，且数据产物 evidence 与 `real_data_evidence_ids` 有交集；Gate `evidence_ids` 还必须覆盖该学习记录的真实数据证据。只有这样，发布、数据、学习记录与关卡才构成同一条可审计链。
