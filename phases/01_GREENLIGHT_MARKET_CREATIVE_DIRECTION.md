# Stage 0B — 立项、市场与创意方向

研究方法见本阶段；证据适用性、scoped completion 与用户呈现遵守 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`。

面向中文用户时，用自然简体中文呈现市场证据、受众假设、评分依据、关卡结论、最大未知项、推荐路线和反证测试。来源原题、主体名称、指标名和规范状态码可保留原语。

## 目标

判断当前版本是否值得投入下一阶段生产资源，并在不覆盖创意核心的前提下确定定位。不要用一个高总分掩盖定位、内容、可行性或风险关卡中的致命问题。

## 执行步骤

- 查询并记录当前可验证的市场、平台、受众和规则证据；无法联网时，明确降级为 `classification = SYSTEM_INFERENCE` 或 `UNKNOWN`。
- 映射 Viral Narrative Genome，区分稳定的叙事机制与会变化的平台信号。
- 评估机会、风险和证据覆盖率，同时记录最大不确定性。
- 只有路线确实会导向不同作品时，才提出题材、形式或定位选项。
- 根据目标地区和平台提出适配方案，但不得静默改写创意 DNA。
- 不确定性高时，设计成本最低、最能推翻当前假设的验证实验。
- 当核心概念、事实主张和传播承诺已经形成时，运行一次 `EARLY` 四重预检：自然中文、明显内容规范风险、初始素材许可缺口和传播理解链。结果用于低成本纠偏，不预测播放量，也不替代最终检查。

## 立项建议码（不是 Gate outcome）

立项研究可以在阶段结果中另存一个 `recommendation_code`：

- `recommendation_code = STRONG_GO`
- `recommendation_code = GO_WITH_FIXES`
- `recommendation_code = TEST_FIRST`
- `recommendation_code = RESTRUCTURE`
- `recommendation_code = NO_GO_YET`

这些值只表达研究建议，不得写进 Gate 的 `outcome`。只有真的执行过评估才创建 Gate，结果只使用 `PASSED | FAILED | BLOCKED | ACCEPTED_WITH_DEBT | NOT_APPLICABLE`；例如 `TEST_FIRST` 只是建议先设计试验，不等于任何关卡已经执行或失败。

只要结论会改变创意方向，就必须保持 `PROPOSED`，直到用户对明确字段作出批准。市场适配不得在没有显式、限定范围的 `approval_event` 时修改任何 `core_claim`。证据薄弱时，优先提出最小反证测试，不要输出虚假的精确胜率或自信的 Greenlight 分数。

若 `EARLY` 内容规范或素材许可检查出现阻断，先修正概念或来源再继续高成本开发；传播准备度再高也不能抵消。完整方法见 `../references/ALPHA7_CHINESE_COPY_AND_FOURFOLD_PREFLIGHT.md`。
