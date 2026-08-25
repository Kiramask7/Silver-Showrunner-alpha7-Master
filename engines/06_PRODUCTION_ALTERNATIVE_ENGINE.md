# 生产替代引擎（Production Alternative Engine）

本引擎的方法单独维护；替代规格、真实执行、观察、scoped completion 与验证范围统一遵守 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`。

## 目标

当当前 AI 工具让某场戏或镜头成本过高、稳定性不足或难以保持连续时，先保护它的**叙事功能、目标时长与首尾状态**，再提出更安全、更经济的等价表达。

不能因为场面难做就直接删除、缩小或削平其意义，也不能把“换更强模型”当作唯一答案。替代方案必须覆盖原段落的完整目标时长；若主动压缩或扩展，必须说明信息、节奏和情绪后果并取得相应批准。

面向中文用户时，原始节拍、叙事功能、难点、备选、损失、收益和推荐全部使用中文。供应商正式名称、机器字段、ID 与参数保持原样。

## 分析模板

```yaml
alternative_id: PAE-###
source_type: PROJECT | BENCHMARK_ONLY
benchmark_case_id: null
original_beat:
target_duration:
canonical_duration_source_id:
narrative_functions: []
state_in:
state_out:
production_risks: []
why_it_is_hard:
options: []
recommended_option:
replacement_shot_ids: []
replacement_duration_total:
function_coverage: []
story_loss:
consistency_gain:
expected_retry_reduction:
verification_plan:
```

- `narrative_functions`：逐项记录规模、危险、信息、情绪、因果、人物状态或节奏任务；
- `target_duration`：引用当前权威时长，不凭印象估算；
- `replacement_duration_total`：从替代镜头逐项重算；
- `function_coverage`：对每项原始叙事功能写 `PRESERVED | PARTIAL | LOST` 及实现镜头；
- `story_loss`：明确替代后失去什么，不能只写收益；
- `expected_retry_reduction`：没有实测时只能标 `HEURISTIC` 或 `TUNABLE`，不得伪造百分比；
- `verification_plan`：说明哪些部分必须通过真实 Pilot、镜头或序列观察验证。

## 常见转换方法

- 连续复杂动作 → 动作前状态、关键局部交互、结果状态、人物反应与声音共同完成；
- 超大人群 → 建立规模的远景、受控前景交互、反应镜头、环境后果与声音；
- 高难手部或物件交接 → 插入镜头、归属反应、首尾状态与剪辑切换；
- 需要清晰阅读的界面 → 后期设计的图形插入镜头；
- 大量镜面动作 → 非反射机位配合有动机的切出镜头；
- 高风险长镜头 → 用动作匹配、首尾状态和可剪切点组成镜头链；
- 高成本变形或特效 → 剪影、光线、局部揭示、环境反应与结果镜头；
- 多人持续身体接触 → 拆分空间层级、局部交互、反应、环境变化和首尾状态；
- 不可稳定呈现的过程 → 远景建立、局部证据、声音、结果痕迹和节奏剪辑共同形成 Narrative Equivalent。

## 等价验收

替代方案进入分镜前逐项核对：

1. 原始叙事功能是否都有映射；
2. `state_in` 与 `state_out` 是否保持；
3. 替代镜头总时长是否与目标时长一致，或差异是否有批准；
4. 规模、危险、情绪后果、信息变化和人物状态是否仍然成立；
5. 是否把困难静默转移到声音、后期或补拍而未登记依赖；
6. 是否需要真实 Pilot 才能判断，而不是在文字阶段声称已解决。

## Benchmark 隔离

压力测试案例只能以 `source_type: BENCHMARK_ONLY` 和单独的 `benchmark_case_id` 存在。它们用于验证引擎能力，不得自动写入真实项目的故事、资产、预算、镜头、Prompt 或 Gate requirements。测试结束后只沉淀可复用的方法与 Failure，不沉淀测试案例事实。
