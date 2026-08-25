# 总体架构 — Alpha.7

## 核心原则

银幕总控不是线性的步骤清单，而是一张由唯一总调度管理的创意制作图：

`ROUTE → DISCOVER → DECIDE → CREATE ARTIFACT → VALIDATE → COMMIT → ADVANCE / REWORK / ROLLBACK / ACCEPT_WITH_DEBT`

每次转换分别核对：

- **授权**：谁允许哪些精确字段改变；
- **证据**：什么真实来源或可访问产物支持当前主张；
- **范围**：决定、完成、Gate 与证据究竟覆盖哪个对象和版本；
- **语言**：机器结构保持稳定，用户可见层遵守 `language_profile`；
- **真实性**：文字规格、执行、观察、QA、发布与学习分别记账。

Alpha.7 的状态、typed scope、Prompt 分层、纠错轨迹与用户呈现以 `references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md` 为唯一运行时总契约。阶段文件保留工作方法，不重复定义平行状态。

## 内部系统

### A. 项目智能

- 入口路由、首次发现与项目简报；
- 短片、长篇、非虚构、文化、科研、教育、品牌和展示项目分类；
- `FICTION / NONFICTION / MIXED` 事实模式与来源忠实保护；
- 市场、趋势、平台、机会与风险；
- 传播叙事基因与创意方向。

### B. 故事智能

- 故事引擎与必要范围的故事设定集；
- 人物、季/集或单片结构与注意力架构；
- 剧本室、魔鬼审稿与版本复核。

### C. AI 制作智能

- 生产可行性与 Generation Readiness；
- Production Alternative Engine；
- 资产需求、视觉实验室、资产注册表与高风险单元预检。

### D. 导演与生成

- 导演图、镜头/转场/节奏契约；
- Reference Registry；
- `PROVIDER_NEUTRAL_MASTER` Prompt 权威源稿；
- `TRANSFORM_PLAN` 内部转换计划；
- `NEUTRAL_EXECUTION_PROMPT` 可复制的供应商中性执行稿；
- 动态供应商注册表与 `PROVIDER_COMPILED` 唯一执行 Prompt；
- 最小 Pilot 与真实生成批次。
- 浏览器、API、本地工具与人工路线的任务回执和恢复点。

MP 负责保留供应商中立的叙事与制作意图；TP 只说明内部转换；NEP 是可复制但不具生成资格的中性执行稿；只有绑定当前 provider/surface/model/version/region 的 `PROVIDER_COMPILED` 才能进入真实执行或 Gate。四层 coverage 与完成状态分别计算。

### E. 质量控制

- Observed State、NCS 连续性、NRS 节奏；
- 带时间码的真实发现；
- 诊断驱动的最低成本修复；
- 新产物 → 新观察 → 重过关的修复闭环；
- Edit Commit 与 Edited State。

### F. 后期与发行

- 配音、声音、音乐、字幕和剪辑；
- 标准时间线、转码/渲染后端与可选剪辑器适配；
- 包装、自然中文、当前内容规范、素材许可与传播准备核验；
- 发布前结构预演；
- 只有真实发布与真实数据存在时才进入性能学习。

发布前资格与发布后事实必须分开：`RELEASE_READINESS_GATE` 在上传前评估；真实链接只进入 `PUBLICATION_EVIDENCE_GATE`。
当前版本不执行自动上传或发布，默认在 `RELEASE_READY` 停止。用户手工发布后仍可只读登记真实 publication 和数据。

### G. 横向引擎

- 决策绑定、用户约束记忆与矛盾检查；
- 证据与置信度、银幕盲点、银幕洞察；
- Simulation Guard、Accept With Debt 与 Core Claims Guard；
- 数量语义、时长、资产、格式和跨文档校验；
- typed scope、证据适用性、状态 basis 与验证纠错轨迹。

### H. 唯一总调度

- 把目标编译为带依赖、版本、权限与恢复点的 `task_graph`；
- 按当前能力选择内部推理、本地工具、浏览器、API、人工或显式模拟；
- 每次真实外部动作写 `execution_receipt`，失败保留检查点；
- 长项目使用全局设计、来源追踪、连续性状态、约 5 单元 Pilot 与约 10 单元可恢复批次；
- 调用外部能力但不允许它们覆盖总账本或另建平行控制器。

### I. 三阶段四重总检

- `EARLY`：概念、脚本和传播主张的轻量预检；
- `IN_PROCESS`：资产、分镜、Prompt 或粗剪变化后的范围复检；
- `FINAL`：对精确产物版本与哈希做最终检查。

四项为自然表达、内容规范、素材许可来源和传播准备度。内容规范与素材许可分别作为阻断项；传播分只表示准备度，不是结果概率。

## 标准关卡依赖图

`GENERATION_READINESS_GATE → ASSET_GATE → SHOT_GATE → SEQUENCE_CONTINUITY_GATE → FINAL_ARTIFACT_GATE → RELEASE_READINESS_GATE → PUBLICATION_EVIDENCE_GATE → LEARNING_GATE`

这是一张依赖图，不是预先创建八个 Gate 对象的命令。只有明确对象已经被真实评估时才实例化 Gate；未来关卡只写入 `next_action`。无媒体时不创建媒体 Gate 占位记录，也不把“尚未评估”写成失败。

上游不完整时，下游可以继续写草案，但只能对明确对象和版本建立 scoped `TEXT_SPEC_COMPLETE` 记录，不能宣布项目整体“文本全部完成”、批量生产就绪或真实完成。

## 用户界面保持简单

默认 `output_complexity_profile.tier = CREATOR_SIMPLE`。普通创作者主视图只看到：结论、推荐、当前真实状态摘要和需要自己处理的少量事项。完整 ID、Evidence、Gate、Prompt coverage、Schema 与验证轨迹放在附件或机器状态中；只有用户明确要求或进入专业审计时才升级为 `CREATOR_STANDARD` / `PRO_AUDIT`。
