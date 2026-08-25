# Stage 14 — 包装、FINAL 四重总检与发布准备

本阶段的 Gate、typed scope 与发布链遵守 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`，领域证据方法继续参考 `../references/EVIDENCE_PROVIDER_RELEASE_LEARNING_CONTRACT.md`。自动化边界到 `RELEASE_READY` 为止：系统完成包装、FINAL 四重总检与 `RELEASE_READINESS_GATE`，不自动上传、不自动发布，也不把普通“继续”解释成对外授权。用户之后是否手工发布是另行选择。

工作对话和内容规范说明遵守 `interaction_language`。标题、简介、字幕和营销文案遵守 `release_copy_language`；目标市场需要外语时，不得顺带把整个工作流切换成外语。外语发布稿必须标明是否经过母语复核。

当目标地区或平台规则可能已经变化时，必须重新核查当前要求。

复核：

- 标题和封面承诺是否与实际内容一致；
- 著作权、商标和参考表达相似风险；
- AI 内容标识规则；
- 音乐与媒体素材许可；
- 字幕与无障碍说明；
- 高风险内容与平台规则；
- 平台格式要求；
- 当前有效的发布和 metadata 做法。

不要硬编码“最佳发布时间”。有当前证据时记录证据；没有时，把 `precision_status` 标为 `HEURISTIC` 或 `TUNABLE`，并把结论写成待测试假设。

对每项重要规则，优先记录官方来源、发布日期、生效日期、核查日期、适用地区或平台范围，以及 `DRAFT / EFFECTIVE / SUPERSEDED / PLATFORM_SPECIFIC / UNKNOWN`。要求主张还必须记录 `actor / duty / trigger / exceptions_or_conditions`。不得混淆创作者、发行方、平台、服务提供者、模型提供者或广告主分别承担的要求，也不得把草案、行业文章或平台传闻升级成普遍有效的适用要求。

核心流程不硬编码临时平台结论、商业激励、例外或收益规则。每个真实项目发布前按当前日期与目标入口重新建立证据记录；适用性不明时使用 `classification = UNKNOWN`，并创建需要复核的开放问题。

## FINAL 四重总检

对**实际准备交付的最终媒体与发布包精确版本**执行 `checkpoint = FINAL`，记录 artifact/version/SHA-256、目标平台与地区、证据和四项结论：

1. **自然中文 / 去人工智能味**：标题、简介、字幕、旁白、台词和屏幕文字自然、具体、口径一致；
2. **内容规范**：以当前官方规则与适用范围检查内容、标识、声明、格式及受众风险；
3. **素材许可与来源**：核对素材、角色/肖像、品牌、参考表达、字体、音乐、声音与生成来源；
4. **传播准备度**：检查承诺一致、信息入口、理解成本、标题/封面/开场与行动设计，只给 readiness 诊断，不预测真实结果。

FINAL 记录必须绑定最终成片与发布包的精确哈希；任一文件或有效内容改变后必须重检。内容规范或素材许可为 `BLOCKED` 时，传播准备度分数不能抵消，`RELEASE_READINESS_GATE` 不得通过。四重总检通过只表示发布准备规格成立，不表示已经发布、会爆款或产生任何真实表现。

## 发布前：Release Readiness

以下是 `RELEASE_READINESS_GATE` 的单独 requirement，不是新的平行完成状态。每项使用 `GR-###`、合法 `requirement_source` 和 `source_id`；全部满足后，Gate 才能 `EXECUTED + PASSED`，项目的 `publication_status` 才可升为 `RELEASE_READY`。

只有实际开始发布前评估时才实例化该 Gate。它的 `scope_bindings` 必须精确绑定最终媒体 `artifact_id + version`、release package、目标格式和当前规则证据；另一成片、旧版本或只写“本项目发布包”的自由文本 scope 不能授权本次发布。

发布准备至少需要：

- 可访问且已观察的最终媒体版本；
- 与成片一致的标题、封面、字幕和 metadata；
- 素材、音乐、字体、肖像和参考表达的许可来源记录；
- 面向目标平台与地区的当前规则证据；
- AI 标识和必要声明的执行计划；
- 未关闭的阻断项为零，或存在被明确批准的债务记录；
- 绑定同一最终媒体与发布包哈希、无内容规范/素材许可阻断项的 FINAL 四重总检记录；
- 已向用户明确手工发布边界、目标入口和不得遗漏的标识/metadata。
- 最终字幕逐条回链当前对白与镜头，所有 cue 均位于对应镜头时间范围，且没有漏项或陈旧时间码；
- `tts_coverage_status = FULL` 时每条 scope dialogue 均有同版本 `MEDIA` Artifact 绑定；最终配音还必须由 `measurement_coverage_status` 与真实、带哈希音频逐条核验，并另有听感、对轴和混音 QA 证据；
- 当前发布包内新增文字产物均已登记版本与 SHA-256，并由本版本 scoped completion 覆盖，不能引用聊天里未落盘的“已完成”文档。

模拟媒体、模拟上传、文字 QA 或发布计划不能通过上述关卡。

通过后，项目只升为 `publication_status = RELEASE_READY`，并在此停止自动化。Skill 不创建 `PUBLISH` 任务，不代替用户登录、点击发布、上传、付费或接受平台条款。

## 可选后续：用户手工发布证据

只有用户自行发布并愿意回传或授权只读核对时，才另存 Publication Evidence：

实际发布后，另存：

```yaml
publication_id: PUB-###
platform:
content_or_post_id:
url:
artifact_id:
artifact_version:
release_package_id:
release_readiness_gate_id: G-###
published_at:
visibility: PUBLIC | UNLISTED | PRIVATE | REMOVED | UNKNOWN
actual_labels_and_metadata:
evidence_ids: []
checked_at:
```

这些字段用于只读证明外部状态，不用于补做发布前复核，也不授权系统继续发布、改帖或删除内容。

没有真实最终媒体、用户手工上传结果或发布页面证据时，不能标记为 `PUBLISHED`。`publication_status = PUBLISHED` 与 `PUBLICATION_EVIDENCE_GATE = EXECUTED + PASSED` 必须通过 Gate 的 `publication_ids` 引用同一条有效 `publication_record`；该记录的 `release_readiness_gate_id` 还必须指向已经通过并覆盖同一成片与发布包的发布前关卡。后续 `LEARNING_GATE` 只能引用已进入通过的发布证据关卡的这些 `publication_ids`。

发布动作尚未发生时不创建 `PUBLICATION_EVIDENCE_GATE` 占位记录；发布页面真实可访问并开始核对后再实例化，并在 typed scope 中绑定同一 publication、artifact version 与 release package。

`SIMULATED_EXTERNAL_STEP` 只能让线路继续；它不能把 `workflow_status.publication_status` 升为 `RELEASE_READY` 或 `PUBLISHED`，也不能把 `workflow_status.learning_status` 升为 `DATA_AVAILABLE`。
