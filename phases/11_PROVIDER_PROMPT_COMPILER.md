# Stage 10 — MASTER 与供应商 Prompt 编译器

四层正文的 section 区间不得人工计数。先准备有序 section 内容和语义引用，再运行 `scripts/compile_prompt_sections.py` 生成唯一正文、`prompt_sections[]` 与摘要；模型只负责导演内容和适配判断。

本阶段把当前 ASSET/SHOT 生成目标真值编译成可执行 Prompt。typed scope、Reference Registry 与完成边界见 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`；剧本、对白、分镜和最终 Prompt 的全量交接见 `../references/ALPHA7_CONTINUUM_CREATIVE_FIDELITY_ENGINE.md`；对白连续排程、动作因果、参考单一职责、镜头交接和制作登记见 `../references/ALPHA7_MASTER_PRODUCTION_CONTROL.md`；导演密度、供应商能力边界、四层关系、唯一质量记录、coverage、section spans、最终槽位、adapter 保真和 Prompt Quality 检查统一见 `../references/PROMPT_QUALITY_CORE.md`。只有本 scope 涉及年龄受保护角色、复杂年龄受保护角色/成年角色同镜，或需要联动对白/字幕/TTS coverage 时，才额外加载 `../references/AGE_SAFETY_PROVIDER_AND_COVERAGE_CONTRACT.md`；本文件只规定阶段路由。

中文用户获得自然简体中文说明。目标模型 Prompt 可使用当前有效语言；非中文成品同时提供简短中文意图，但不重复整份翻译。

## 输入

- 当前 ASSET/SHOT 目标、`SHOT_PLAN`、Prompt-ready 导演源与 `canonical_duration`；
- 当前资产、Reference Registry、Style/Sound Bible、格式和连续性；
- 决定、未知项、数量、因果、年龄受保护角色和素材许可/内容规范边界；
- `dialogue_inventory` 与当前 fragments；
- 当前镜头的动作因果合同、逐字声音排程、参考职责和相邻镜头交接；
- Dynamic Provider Registry 当前快照与适用 `capability_evidence_ids`；
- 上游 Artifact 版本/hash、Prompt Pilot 范围和开放 blocker。

上游语义不完整时只编译安全范围，不用模型记忆或旧 Prompt 补齐。

## 四层职责

1. `PROVIDER_NEUTRAL_MASTER`（`MP-###`）：详细、权威、供应商中立的导演合同；覆盖参考/资产、入口状态、全部导演节拍、动作/表演/接触/材质/环境、对白声音、出口、边界与验收。
2. `TRANSFORM_PLAN`（`TP-###`）：简洁的内部转换计划；说明重排、引用映射、声音责任、必要分段和 MUST 保护，不复制 MASTER 全文，不可提交模型。
3. `NEUTRAL_EXECUTION_PROMPT`（`NEP-###`）：完整、自包含、可复制的供应商中性执行稿；含真实逐镜执行内容，不绑定供应商，不得进入生成 Gate 或执行任务。
4. `PROVIDER_COMPILED`（`PP-###`）：绑定当前供应商的完整成品；不得照抄 NEP 或压成摘要。它还必须用 `execution_contract` 区分仅供人工复制的文字规格与当前可执行候选。

四层分别只在 `master_prompt_text / transform_plan_text / neutral_execution_prompt_text / prompt_text` 保存唯一正文。每层 `prompt_sections[]` 只保存 section 位置与 atom/beat 引用，不复制文本；span 必须无缝覆盖对应正文。所有字段与枚举直接使用质量核心定义。

## 唯一质量记录

每个 `target_type + target_id + source_spec_version + generation_role` 恰有一条顶层 `prompt_quality_record`，可绑定一个 MP、一个 TP、一个 NEP 和多个 `provider_prompt_ids[]`。MP/TP/NEP/PP/PQ 必须在目标、角色、媒介和版本上完全一致；每个 PP 在 `adapter_integrity[]` 中恰有一条同 ID 记录，不同 provider 不能共用 PASS。`ASSET` 目标不要求伪造 `shot_id`：静态参考使用 `ASSET_REFERENCE / IMAGE`，转身、步态或表演参考使用 `ASSET_MOTION_REFERENCE / VIDEO`。同一 SHOT 可分别有关键帧 IMAGE 与运动 VIDEO。`IMAGE` 编译为单帧构图，不添加伪时间线；`VIDEO` 才编译连续阶段、动作、声音和出口状态。

质量记录保存 canonical beats/atoms、四层绑定、对白、每 PP adapter、逐拍编译锚、Prompt Soul、必要的 `longform_source_bindings[]`、hash 绑定的 `two_pass_reviews[]` 与质量结论，不复制四层正文。创建 MP 时初始化；TP/NEP/PP 形成后补 ID 和状态；任一上游、Soul 或正文实质变化使当前记录失效到重检完成。

## 编译步骤

### 1. 上游与参考检查

确认本 scope 所有 ASSET/SHOT 目标具有唯一 target key；资产、镜头、参考、声音、图形、格式和版本可解析；canonical 时长只由真实成片 SHOT_MOTION 目标承担；开放 blocker 不影响本 scope；未知项、数量、因果、年龄和对白均已登记。每项参考只允许一个主要职责，原始标签逐字保留，并同时声明不得带入的身份、服装、环境、标识、摄影、动作或声音。动作/摄影参考不得覆盖 canonical 身份和已接受连续性；已接受上一支素材的真实末态优先于原计划。Reference Registry 的 `IDENTITY/COSTUME/SCENE/COMPOSITION/STYLE/MOTION/PROP_OWNERSHIP/STATE/FORMAT` 职责不得越权：风格不能改身份，构图不能重写服装、道具、拓扑或世界状态。

### 2. 建立 MASTER

从当前目标与质量记录写详细导演合同。`master_prompt_text` 必须实质覆盖全部适用 director beats 与 MUST atoms；“动。”“保持连续”、标题清单或剧情概述均失败。MASTER 不含供应商私有参数、未经验证能力或新剧情事实。

### 3. 建立 TP 与 NEP

先用简洁中性文字说明如何把 MASTER 转成执行成品。TP 只能使用 `TRANSFORM_PLAN` section，`atom_ids` 必须逐项覆盖全部 MUST，说明原样保留、引用映射、声音责任或分段承接；“全部保留”不能替代映射。再形成完整可复制的 NEP，把导演节拍落实为供应商中性的执行文字；NEP 不得包含计划专用 section，不得与 TP 同文，也不得声称具体供应商能力已经可用。

### 4. 绑定 Provider 与安全表达

Registry 分开保存 provider、展示名/别名、surface、API model ID、snapshot、model/version/region/access/availability、价格来源、核查时间、Pilot 状态与能力证据。候选种子见 `../references/PROVIDER_REGISTRY_SEED_2026-08-14.md`，真实执行前按当前官方来源刷新；不得混淆供应商主体、营销名、网页入口与 API ID，也不得声称永久“最好/最稳”。

若用户已自行确认网页入口可用，本轮只要可复制文字，且 Prompt 不依赖当前模型版本、价格、精确时长、参考语法或专有能力，可使用 `MANUAL_COPY_TEXT_SPEC_ONLY`：只登记用户自报的 surface 与 `SURFACE_MANAGED_UNKNOWN`，不扩搜、不登记 capability claim，不填写请求时长或裁切承诺。它不能进入 Generation Readiness 或任何 READY/执行态生成任务。

若要把 PP 用于真实生成资格评估，则使用 `GENERATION_EXECUTABLE`；版本、入口、task、输入方式和请求时长必须有同范围能力证据，未知时不完成可执行 PP。`requested_output_duration_seconds` 与剪辑目标分开，只有明确 `trim_to_editorial = true` 才可后期裁切。

已判定的年龄受保护角色使用 `EXACT | LIFE_STAGE | REFERENCE_BOUND`，保留真实年龄/阶段与来源，表达层不得改变年龄事实。复杂年龄受保护角色/成年角色同镜缺能力证据时退回 Stage 9 做 `DECOMPOSITION/COMPOSITE`，不生成聚合镜头 PP。

### 5. 编译 PP 与适配保真

按质量核心把 MP 经 TP 与 NEP 编译成供应商成品，并形成不同于 NEP 的 section spans。每个 VIDEO 节拍都要在每个 PP 的正向 `DIRECTOR_TIMELINE` 中留下单独、实质、不可复用的 camera/action/exit 编译锚。adapter 只转换目标语言/语法、引用槽位、多模态关系、声音责任或合法分段；不得删节拍、事件、身份、逐字对白、动作终态、表演、接触物理、材质环境、摄影、声音、连续性或保护边界。默认交付是 `FULL_FIDELITY` 完整版，不设置通用字数目标；入口不足时带完整 handoff 分段，不把“适配”写成摘要。

最终 PP 只编译当前镜头：从真实或计划入口开始，完成一个主要动作链和一个主要摄影任务，逐字对白只出现于实际发生的时间段，并停在交接表登记的可见终态。跨镜续句保持同一声音，不重新起句；下一说话者只能在当前句完成后进入。提示词不带对白游标、成本、进度、内部状态或未来镜头计划，也不得用占位语让用户另行拼装。

每个 PP 记录真实 `adapter_operations[]`。没有 `LANGUAGE_TRANSLATION` 时，逐拍 camera/action/exit 锚必须与 canonical 字面一致；跨语言 PP 必须声明真实翻译 operation，并由绑定 MASTER/PP/Soul hash 的两遍审阅验证事件与终态保真。只有已核验入口限制或用户要求才允许有序压缩；仍无法承载时 `SEGMENT_WITH_HANDOFF`，不得删除 MUST。目标 PP 的 adapter record 必须为 `PASS`。

引用编辑或参考派生还要生成 `REFERENCE_DELTA_MAPPING`：从已登记参考的 `controls` 与对应资产 `locked_features / variable_features` 解析源元素，逐项声明保持、改变、允许新增和最终输出。保持/改变/新增三组必须互斥并闭合输出；禁止新增时不得在 PP 中要求源输入没有锁定的物件、人物、文字或拓扑。只写“其余不变”不能替代这份映射，基础图没声明的元素也不能在编辑图里被当成既有元素。所有 `reference_delta != null` 的 PP 都必须做当前 hash 绑定的只读二审：记录 `reference_delta_sha256`，实际逐项核对 PP 与 delta，并令 `reference_delta_check = PASS`；任何正文或 delta 变化都要重审。

生成任务使用结构化 `generation_targets[]` 精确绑定 target、role、medium 与 PP；自由 `task_scope` 只作人读说明，不能授权执行对象。`IMAGE_TO_VIDEO` 的 SHOT_MOTION 任务必须把上游 IMAGE 输出 artifact/version 列入输入并回链产生它的任务；进入 RUNNING/EXECUTED 前该输入必须为真实可访问媒体。只写“参考上一张图”不得放行。

### 6. Coverage、质量与四重检查

分别核对当前 Prompt Pilot 或批次的精确 target keys：本 scope 集合 = 当前 MP 集合 = 当前 TP 集合 = 当前 NEP 集合 = 目标 provider PP 集合。局部 Pilot 只覆盖选中的 3—5 个代表目标，不强迫同一 SHOT_PLAN 其余目标提前生成四层空壳；批量 Generation Readiness 再按其明确 scope 要求完整覆盖。Pilot 必须是批次的非空代表性子集，覆盖 provider/snapshot、format、task、medium/role、quality/adapter 与高风险类别，不能反向要求 Pilot 包含整批全部 Prompt。非生成镜头必须有真实 `no_generation_reason`，禁止“同上/其余类推”。

再对每个目标 PP 运行质量核心 Gate：详细 MP、MUST 完整 TP、完整可复制的 NEP、完成真实适配且不同于 NEP 的 PP、按媒介适用的静态/动态合同、逐拍编译锚、资产与边界、逐字对白、sections 无缝覆盖、adapter 无损、无内部工程泄漏。所有 Pilot 样本、高风险目标和含 `reference_delta` 的目标做 hash 绑定两遍审阅，每批再抽至少一个普通目标；普通 HERO 镜头不因此自动全量二审。字符数和时间线占比只作诊断，不能放行语义薄 Prompt；“动。”必须失败。

每个 Prompt Pilot 的视频 PP、所有含对白/人物非词汇发声或未授权压缩风险的 PP，以及每批抽取的普通视频 PP，准备 `VIDEO_PROMPT` 模式预检 JSON，并只通过包根目录的 `运行银幕总控.cmd 创作预检 <创作预检.json> --output <机器报告.json>` 运行。首个静态图 PP 使用 `IMAGE_PROMPT` 模式。任何来源漏项、对白变化/重复、说话人或顺序漂移、时间线断裂、必需 section 缺失、静态/视频混用或静默压缩都阻断文字规格完成。工具检查通过仍不替代两遍导演审阅或真实生成 QA。

视频 Prompt 还必须通过表演可行性预检：阻断嘴部占用与同一角色发声冲突、以隐藏口型掩盖矛盾、幻想开口与现实声源错配、动作和摄影整段重复、缺少可见结束画面及通用声音占位。修复必须把动作顺序、道具承接、唯一声源和终态直接写入可复制正文，不能只在检查说明里承诺。

首次编译、切换 provider/surface/model/version/region，或改变参考职责、年龄表达、对白、负向或传播承诺后，对当前四层、质量记录、Registry 与精确 hash 执行 `IN_PROCESS` 四重检查。内容规范/素材许可阻断停止真实执行；无真实媒体时只证明文字规格通过预检。

四层新建或实质改写后登记当前 `TEXT_SPEC` Artifact、版本与 `content_locator.sha256`。Prompt Pilot 先完成 3—5 个身份关键或高风险 ASSET/SHOT 目标；未通过前不批量铺满全项目。

## 最小绑定片段（`binding_fragment`）

```yaml
id: PQ-001
target_type: SHOT
target_id: SH-001
generation_role: SHOT_MOTION
generation_medium: VIDEO
source_spec_version: v1
master_prompt_id: MP-001
transform_plan_id: TP-001
neutral_execution_prompt_id: NEP-001
provider_prompt_ids: [PP-001]
```

该片段只展示目标与四层 ID 的绑定关系，不是可单独落盘的完整 PQ 对象，也不是可提交 Prompt。完整记录必须使用质量核心与当前 Schema 的全部必填字段；不要给省略字段补默认 `PASS`。

## 输出、停止条件与用户交付

输出当前 MP、TP、NEP、每 provider 的 PP、唯一质量记录、目标 coverage、Artifact 与四重检查记录。以下任一项阻止目标 PP 进入 Generation Readiness：`execution_contract != GENERATION_EXECUTABLE`；目标/角色/媒介/版本不一致；上游不完整；能力证据缺失；年龄/因果/内容规范/素材许可阻断；MUST 或对白丢失；section 断裂；adapter/quality 非 PASS；Prompt 只是摘要、占位或内部记录。manual-copy PP 仍可作为清楚标注的文字交付，不因此冒充可执行。

默认 `CREATOR_SIMPLE` 只向普通用户显示一句中文导演判断/阻断、目标 provider 的完整可复制 PP，以及最短必要上传/入口步骤。MP、TP、NEP、sections、质量记录、adapter loss 与字符诊断后台落盘；只有审计、调试或专业交接时展开。

文字质量通过不等于真实输入可用、生成成功或媒体 QA 通过。没有真实生成证据时不实例化 `SHOT_GATE`，Production Validation 保持 `NOT_TESTED`。
