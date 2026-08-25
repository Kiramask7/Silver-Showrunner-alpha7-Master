# Alpha.7 长内容连续制作引擎

本文件是银幕总控的按需 Longform 引擎合同。它只在长剧本、长篇叙事、多集内容、跨场景连续工程，或用户要求 `FULL_PROJECT` 时加载。根调度、决定账本、证据边界、中文输出与真实媒体状态仍由银幕总控负责；本引擎不能成为第二个总控。连续生产的 Prompt 编译统一加载 `PROMPT_QUALITY_CORE.md`；纯文字省算力 Pilot 则以 `TEXT_ONLY_ECO_WORKFLOW.md` 为唯一工作流真值，本文件不复制它的命令、overlay 形状或状态派生规则。

## 目录

1. 激活与边界
2. 来源审计与继承范围
3. 外部一键与内部安全分批
4. 全文冻结与 `compile_target`
5. 全局真值与哈希
6. Unit、连续性与提示词追踪
7. Pilot、批次与最小工作集
8. Checkpoint 与恢复
9. Unit/Batch 双层交接
10. 负向条款边界
11. 与 Alpha.7 状态及真实性合同对接
12. 确定性验证

## 1. 激活与边界

满足任一条件时激活：

- 输入包含完整长剧本、小说、连续分集大纲或多场景纪实文本；
- 输出需要跨多个生成单元保持人物、空间、道具、声音与因果连续；
- 用户要求“整部做完”“全文转视频”“一键完整项目”或 `FULL_PROJECT`；
- 已有长项目需要从可信检查点继续、审计或局部重编。

短片或单镜头可以复用来源追踪与连续性字段，但不要强制建立长项目批次。科学、文化、教育和纪实内容同样可以使用本引擎；不要把“长内容”误写成“长剧专用”。

本引擎只负责长内容编译与恢复，不获得以下权力：

- 改写用户已批准的核心主张；
- 把 `PROPOSED` 或 `UNKNOWN` 变成剧情/事实真值；
- 选择、购买或调用供应商而不经过银幕总控的权限边界；
- 把文字规格、模拟步骤或检查点写成真实媒体完成；
- 用旧批次状态覆盖真实观察产生的 `OBSERVED_STATE`。

## 2. 来源审计与继承范围

本合同从经用户提供并单独审阅的长篇连续性协议中抽取稳定运行规则。精确来源身份保存在审计专用归属记录中；模型可读合同不暴露历史制品名。

```text
source_archive_sha256: EBF490A31D5B72B369680E8BF49815B3F0C3448CADDFF82F6368F585574D35A1
manifest_payload_count: 56
manifest_hash_and_size_mismatches: 0
zip_path_traversal_findings: 0
production_validation: NOT_TESTED
```

继承：

- 全文先读完、冻结，再建立全局骨架；
- 来源分类、`compile_target` 与全文/成片双覆盖；
- `prompt_source_trace` 逐 claim 追踪；
- `global_state_sha256` 冻结 Phase-A 长内容真值；
- `FULL_PROJECT` 外部一键、内部仍安全分批；
- 约 5 个 Unit 的首批 Pilot，后续约 10 个但动态限制在 4—10 个；
- checkpoint、哈希链、最小工作集与断点恢复；
- Unit→Unit 与 Batch→Batch handoff 严格分离；
- Continuity Snapshot 与不可逆状态；
- 负向约束整句库存与完整性校验。

不复制或不继承：

- 原包脚本、ONEFILE、示例项目、测试角色、地点、道具或平台名称；
- 原包的固定 Prompt 字符长度，作为 Alpha.7 所有供应商的普遍质量指标；
- 4%—5% 负向比例及 5.5% 上限，作为跨供应商硬门；
- 任何旧模型清单、具体供应商能力或未经本项目 Pilot 验证的结论；
- 原包设计分数对真实制作状态的替代；
- 项目专属词表、旧测试攻击文本和历史 Bug 兼容代码。

原包未附单独许可证文件。本次融合因此采用“重写协议 + 本项目另行编写的轻量验证器”，不整包再分发源代码。

## 3. 外部一键与内部安全分批

用户界面允许一个简单入口：

```text
FULL_PROJECT
```

内部规范化：

```text
FULL_PROJECT -> FULL_EXPORT
SAFE_BATCH | CHAT_BATCH -> ONEFILE_SAFE_BATCH
```

`FULL_EXPORT` 只表示用户一次发起、最后一次性交付。内部仍执行：

```text
SOURCE_FROZEN
→ GLOBAL_SKELETON
→ GLOBAL_GATE
→ B001_PILOT
→ CHECKPOINT_COMMITTED
→ B002...
→ FINAL_QC
→ COMPLETE
```

任何批次失败时停在该批，保留此前 `COMMITTED` 成果。不得因为用户要求“一次做完”而取消 Pilot、检查点、验证或真实状态边界。

能力未知、没有可靠文件写入、不能运行验证器或没有足够安全余量时，使用 `ONEFILE_SAFE_BATCH`。不要虚构上下文窗口或剩余 token。

`delivery_mode` 与 `FULL_EXPORT / ONEFILE_SAFE_BATCH` 正交：

- `MEDIA_ENABLED` 使用上述完整生产路线；
- `TEXT_ONLY_ECO_TEST` 读取 `TEXT_ONLY_ECO_WORKFLOW.md` 中的当前合同，只运行来源摄取、场景窗口编译、Global Truth、Sequence/Shot 分流与 Prompt Quality Pilot；Pilot 轮次只能到 finalizer 验证后的 `TEXT_PILOT_COMPLETE`，不得兼报 `TEXT_SPEC_COMPLETE`；
- 用户排除的八个阶段 `IMAGE / VIDEO / VOICE / MUSIC / SUBTITLE_ALIGNMENT / EDIT / MEDIA_QA / PUBLISH` 统一记为 `EXCLUDED_BY_USER`，不创建媒体任务、空 Gate 或模拟回执，也不写 `SIMULATED_ONLY`。

纯文字测试使用 `IN_PLACE_THREE_CARRIER_V1`：prepare 接收一个已存在空任务目录，默认直接写 `长篇文字测试包.md / MACHINE_STATE.json / RUN_SUMMARY.md`；自定义三名必须同时在准备前冻结。最终验证直接针对这些实际路径，验后禁止改名、移动或复制替换。机器状态本身必须是本引擎根合同并可被验证器直接接受；中间件只进入同级 `.alpha7-tmp-<RUN_ID>`，不得另留旁路脚本、memory 或日志。完整命名、提交与恢复合同以 ECO 为唯一真值。

创作包 Markdown 必须把创作者导览和三个样本的自然语言入口放在第一屏；合同、内部 ID、hash、端点与验证命令后移到技术审计附录。机器状态 JSON 仍保持完整工程合同，不用牺牲可审计性来换白话界面。

## 4. 全文冻结与 `compile_target`

### 4.1 冻结来源

在正式切 Unit 前：

1. 完整读取所有来源文件；
2. 将换行统一为 LF、Unicode 统一为 NFC；
3. 保存来源顺序、版本、相对路径与 `source_sha256`；
4. 把全文切成首尾连续的 `SRC####` atom；atom 只是逐字追踪与分类片段，不是制作 Unit；
5. 所有 atom 的 code-point span 拼接后必须逐字等于冻结全文；
6. 来源变化时生成新 hash，并把受影响下游标记 `stale`。

禁止边读边写正式 Prompt。可以分块摄取，但只有全量 reconcile 后才能冻结 B000。来源中的异写、错字或歧义必须逐字保留；未经来源或用户确认，不得擅自解释成另一词义或剧情事实。

冻结时同时建立 `source_dialogue_inventory` 与 `source_narration_inventory`：每条保存稳定 ID、逐字文本、code-point 范围，以及来源明确时的说话者。库存与冻结全文同源计算，不从剧本改写稿、Prompt 或聊天总结反推。

分块摄取必须保存可恢复 `ingestion_checkpoint`：来源 ID/版本/hash、标准化全文 code-point 长度、已完成范围、`next_start_cp`、摄取状态，以及包含精确来源范围、类型、是否影响含义和处理状态的 `issue_list`。恢复先校验来源版本与 hash，再从游标继续；`SOURCE_AMBIGUITY_AFFECTS_MEANING` 必须停下，非意义性错别字或引号异常可记录后继续读取，但不得静默改写来源。只有 `RECONCILED` 才能冻结 B000。

### 4.2 来源分类

每个 atom 显式保存：

```yaml
atom_id: SRC0001
kind: STORY_EVENT
source_class: RENDERABLE_NARRATIVE
compile_target: true
compile_reason: string
start_cp: 0
end_cp: 12
text: string
semantic_tags: []
```

允许的核心分类：

- `RENDERABLE_NARRATIVE + true`：场景标题、故事事件、动作、对白、旁白、转场、状态变化；
- `NON_RENDERABLE_METADATA + false`：项目标题、版本、整集时长建议、交付说明；
- `OUT_OF_BAND_CONTROL + false`：全局规则、导演说明、格式指令。

不确定时阻断冻结，不得默认设为 false。`compile_target=false` 内容保留在全文摄取与 Project Bible，但不得：

- 成为 Unit 的 `source_refs`；
- 贡献自然时长；
- 成为故事 claim 的 trace；
- 被伪装成“授权删减”。

Atom 与 Unit 必须保持两个层级：

- 一个 Unit 绑定一个首尾连续的场景 `source_window`，通常覆盖多个相邻 atom；
- `source_window` 的正文必须逐字等于所列 atom 拼接，并覆盖完整对白轮次、动作/反应落点与理解当前场景所需的相邻语义；
- 禁止默认一 atom 一 Unit，禁止把半句、孤立对白、标题残片或标点切片单独包装成可制作目标；
- 同一连续场景过长时，沿完整动作落点切成相邻 Unit；跨时空或包含多个分离动作落点时，先保持完整来源窗口，再路由成 `EDITED_SEQUENCE`。

最终分别报告：

```text
ingestion_coverage = 全部 atom 对冻结全文的连续覆盖
render_coverage = compile_target=true atom 的 Unit 覆盖
```

二者都必须为 100%。一处未授权遗漏不能被“总体 99%”掩盖。

## 5. 全局真值与哈希

完整通读后建立一次 `global_state`，至少包含：

- `source_classification`；
- `unit_manifest`；
- `project_rules`；
- `continuity_bible`；
- `visual_continuity_domains`；
- 稳定的 `capability_plan`；
- `prompt_soul_version`、导演密度校准与 Style/Asset/Sound 索引。

未来或逐目标对象不得进入 `global_state`：尚未创建的 `prompt_quality_record` ID/正文、每 Unit 负向候选/选择计划、`unit_handoff_out` 正文，以及未来 task/Gate/checkpoint 空壳。它们在真实创建时计算自己的 hash 并回链 `global_state_sha256`，不能仅因编译后续工作而改变全局真值哈希。

使用 UTF-8、Unicode NFC、LF、递归 key 排序和紧凑 JSON 计算：

```text
global_state_sha256 = sha256(canonical_json(global_state))
```

所有 committed checkpoint 必须引用同一 `global_state_sha256`。修改来源分类、Unit Manifest、项目规则、连续性设定集、稳定能力计划或长期 Style/Asset/Sound 索引时：

1. 不静默续写；
2. 计算影响范围；
3. 保留稳定 ID；
4. 标记受影响 Unit 与下游为 `stale`；
5. 建立新的 skeleton revision 或 checkpoint chain。

## 6. Unit、连续性与提示词追踪

### 6.1 Unit 原则

- 先冻结完整 Unit Manifest，再开始 B001；
- Unit 按来源与因果顺序连续；
- 优先在完整对白、动作落点、反应落点、场景/时间转换处切分；
- 不在音节、关键接触、身份揭示中段或不可读的不可逆状态中间切分；
- 已提交 Unit 不重切、不重编号。

每个 Unit 至少保存连续窗口，而不是只保存零散 `source_refs`：

```yaml
source_window:
  atom_range: [SRC0004, SRC0011]
  atom_ids: [SRC0004, SRC0005, SRC0006, SRC0007, SRC0008, SRC0009, SRC0010, SRC0011]
  start_cp: 120
  end_cp: 488
  exact_text_sha256: sha256
```

`atom_ids` 必须连续且与 `atom_range` 一致；Unit 的故事 claim、动作与 Prompt 只能来自该窗口内 `compile_target=true` 的 atom。lookahead 只服务连续性规划，不得把未来动作、结果或揭示提前写进当前 Unit。用户点名位置和机器抽样位置都先编译成完整窗口；点名 anchor 时取能收完当前句、对白轮次、动作结果和直接反应的最短连续窗口，不得截断语义或吞入无关下游段落。

每个 Unit 在 Prompt 编译前必须登记 `director_contract.target_mode = EDITED_SEQUENCE | GENERATABLE_SHOT`：

- `EDITED_SEQUENCE` 含跨地点、跨时间或多个分离动作落点，只能先交付顺序明确的 sequence design 与 `shot_plan`，并标记 `NOT_A_SINGLE_SHOT`；
- `GENERATABLE_SHOT` 是单一连续时空、单一可观察动作链与明确入口/出口，才可直接建立 `SHOT_KEYFRAME / SHOT_MOTION` 合同；
- 至少四轮来源对白且至少三名说话者，或存在多个动作/反应切换时，不得保持 `GENERATABLE_SHOT`；先记录 `SPLIT_REQUIRED` finding，再改为 `EDITED_SEQUENCE`；
- Sequence 若要进入视频 Prompt，先拆成稳定 Shot 子目标，再逐 Shot 建唯一质量记录；不得用更长文字、罗列多种运镜或“一镜到底”把 Sequence 冒充 Shot；
- 路由若非来源明示，保存 `origin_status: PROPOSED_DIRECTOR_INFERENCE` 和来源依据，不能改变原事件、对白、因果或顺序；
- `EDITED_SEQUENCE` 由 prepare 先生成非空、有序、不可改编号和来源范围的锁定镜头骨架；模型逐镜填写具体戏剧任务、可选非剧情导演动作和摄影。每个 shot 只含一个连续时空和一个可观察动作链；`GENERATABLE_SHOT` 的单镜资格也由 helper 复算，不得用空 shot plan 掩盖跨时空；
- Sequence 的镜数按完整动作、反应、时间跃迁、对白轮次和风险动态派生。每个 shot 的 `action_state_chain` 必须表达完整来源句义或完整可观察事件，不能是截断句子前缀；多个年份、成长阶段、地点或动作结果必须逐阶段落镜，泛化“成长蒙太奇／信息分屏”不能独自承担整段导演化；
- 来源语义锚、入口、逐项来源动作、出口、连续性、镜头来源范围与来源主张槽由 helper 锁定，并生成逐项 provenance。语义门同时记录当前窗口首次出现的短语和高置信动作关系；模型不得手填来源证明或改写来源主张。表演、摄影、声音、逐镜 purpose/camera、可选 `action_additions` 与唯一导演控制正文由 finalizer 确定性登记为导演提案；新增项不得改变剧情状态、提前揭示未来信息或混写来源事实。
- helper 从锁定骨架与创作字段确定性生成 `director_contract.execution_beats`：Sequence 每个 shot 恰一 beat，Shot 路由恰一 beat；每项必须明确入口状态、空间位置、可观察动作、摄影、声音顺序和出口状态。来源声音按所在镜头与原始顺序投影，不得缺失、重复、调序或额外添加；画面文字和内心文字不进入音轨。NEP 含唯一一份“逐镜视频提示词（每条可单独复制）”，每镜按人物场景、画面表演、摄影、声音对白、结束画面和限制组织，不向用户泄漏机器字段；结束画面必须逐镜显式出现，不能因为动作正文已写结果而省略。MP 不得含执行技术块。角色主观 POV 不得露观察者；固定机位不得同时运动；“无对白”不得与内心独白并存；每镜不得有含混声源或标点碰撞。
- finalizer 在晋级前运行表演可行性拦截：嘴部占用与同一角色发声、隐藏嘴部式伪修复、现实声源与幻想开口错配、动作/摄影复制、通用声音占位和缺少结束画面任一命中都退回。可见道具转移、发声后重新持有，以及嘴部被占用者与实际说话者不同的镜头不得误伤。标点只作为对白节拍候选，不自动决定镜数；同一句跨镜维持单一声音游标。

### 6.2 Continuity Ledger

永久状态至少覆盖身份、服装、场景拓扑、道具结构、声音基线与风格指纹。动态状态至少覆盖：

- 人物位置、朝向、视线和姿态；
- 伤势、污迹、湿度、服装状态；
- 道具归属、手部占用、开合与损坏；
- 天气、时间、介质和主光方向；
- 未完成动作、速度、受力与摄影轴线；
- 对白游标、持续声音和声学空间；
- 已完成事件、不可逆状态和 Future Prohibition；
- `planned_state` 与 `observed_state` 的权威来源。

完整账本不进入供应商 Prompt。当前 Unit 只提取真正影响生成的 5—8 个 Continuity Capsule 事实。

每对相邻可生成镜头还要按 `ALPHA7_MASTER_PRODUCTION_CONTROL.md` 保存一行接力：上一镜交出的动作、位置、视线、道具、遮挡、构图或声音线索必须被下一镜接收，并同步核对手口占用、开放运动、轴线、光线、声场和对白进度。没有真实素材时只登记计划末态；素材被用户接受后，观察末态覆盖计划。被拒绝素材不进入 Canon，也不作为续接父片。

### 6.3 Prompt Soul、活动资产与对白

每个 `(target_type, target_id, source_spec_version, generation_role)` 只建立一条 `CURRENT` 的 `prompt_quality_record`；同一 Unit/镜头可以分别引用资产参考、静态关键帧、起始帧与视频运动等多个角色记录。完整字段与 Gate 直接使用 `PROMPT_QUALITY_CORE.md`。长篇层只保存这些记录的 ID、版本和必要 hash；不得把 `director_beats / semantic_atoms / dialogue_fit / adapter_integrity[]` 复制到 Unit、四层 Prompt 或 checkpoint。

长篇差异只在加载与交接：当前 Unit 加载连续 `source_window`、仅供连续性规划的少量 lookahead、相关 Bible 切片、入口/出口连续性、当前对白与 Provider 证据；不重载完整 Bible、旧 Prompt 和历史批次。跨 Unit 对白 handoff 保存精确下一文本位置和声音状态，下一 Unit 不从句首重说、不省略或换人。

项目制作记录随每个 Unit 或真实尝试更新进度、完成证据、恢复位置、资产版本、预算估计、实际成本与尝试上限。预计与实际金额分开；单价没有当前来源时不猜数值。外部付费生成前先取得用户对调用次数、费用依据和停止条件的批准。这些记录只服务恢复和审计，不进入视频 Prompt。

纯文字省算力线路先由 prepare helper 从冻结对白库存向每个目标注入只读 `{{VERBATIM_DIALOGUE_SLOT:<dialogue_id>}}`。模型只能在 `prompt_overlay` 引用完整 slot，不能手抄对白正文、拆 slot、改 slot ID、换说话者或新增伪 slot；finalizer 合并真实库存后再确定性计算 `dialogue_diff`。`missing / changed / added / narration_promoted_to_spoken` 任一非空即 FAIL。叙述默认不能成为角色对白；若导演提议把叙述变成旁白，或新增台词、画外音、动作、调度、镜头含义、因果补充，必须单列 `PROPOSED_DIRECTOR_INFERENCE` 并回链来源范围，不能计入“来源对白逐字通过”，也不得冒充 `VERBATIM / FAITHFUL_PARAPHRASE`。

角色或动物发出的“啊、嗯、唉”等无词义表演声必须分类为 `NON_LEXICAL_VOCALIZATION`，逐字进入声音设计并保留表演归属、顺序与情绪语境，不得误作环境 `SFX` 或新增对白；物体飞过、撞击、脚步等才是 `SFX`。来源仅写情绪结论时，皱眉、退开、散开等具体表情与调度必须单列 `PROPOSED_DIRECTOR_INFERENCE`。涉及需要谨慎呈现的年龄、身体边界或冲突场面时，冻结来源仍逐字保留，导演层优先用遮挡、反应镜头、声音与非图解式构图，避免身体凝视或冲突细节特写。

MP、TP 与 NEP 必须完成不同职责：MP 保存来源块、导演意图、provenance 与连续性，且不含执行技术块；TP 只说明转换；NEP 是逐镜可复制工作稿，含 execution beats 所需动作、空间、表演、摄影、声音、入口和出口。MP 与 NEP 同文、TP 冒充执行稿或 NEP 仍是泛化概述都返工。

### 6.4 `prompt_source_trace`

每个非负向语义 claim 必须恰有一条 trace。机器层保存：

```yaml
claim_id: CL001
text: 中文自然语言 claim
trace_id: TR001

trace_id: TR001
relation: VERBATIM | FAITHFUL_PARAPHRASE | VISUALIZATION | CONTINUITY_CARRY | PROJECT_CONTROL | DIRECTORIAL_CONTROL
source_refs: [SRC0001]
state_refs: []
project_rule_refs: []
capability_ids: []
```

规则：

- story claim 只引用当前 Unit 的 `compile_target=true` atom；
- 当前 1.5 的来源 claim 由 helper 按锁定语义锚逐项生成，正文、关系、来源范围、数量与顺序均不可编辑；工作面只开放一个预分配导演控制槽的正文，留空表示不使用；
- `CONTINUITY_CARRY` 只引用合法入口状态；
- `PROJECT_CONTROL` 只引用冻结 Project Rule，不新增剧情事件；
- specialist claim 只能来自当前 PRIMARY/SUPPORT 能力及其来源/状态证据；
- 当前窗口尚未首次出现的专名、引文或状态词不得提前进入表演、摄影、声音、逐镜任务、动作补充、MP、TP、NEP 或导演控制正文；
- 高置信动作关系锁定执行主体、动作对象或工具及肯否关系。主体或工具互换、同句自相矛盾直接返工；无法唯一确认的中文指代进入内容复核，不由系统猜测；零宽等默认不可见控制字符只从语义比较副本移除，不能用于拆散专名或动作词，也不能借此改写原始正文；
- 未来来源、被抑制能力、无锚定模板、非成片 metadata 均不能支持 claim；
- 内部 `SRC/U/SC/SQ/B/checkpoint/hash` 等工程 ID 不进入交给视频模型的自然语言 Prompt。

## 7. Pilot、批次与最小工作集

### B001 Prompt Quality Pilot

- 一般长篇先做 3—5 个 Pilot Unit；`TEXT_ONLY_ECO_TEST` 固定三个。用户点名目标时走 `USER_TARGETED_EXACT_RANGES_V1`，三个连续场景窗口就是本轮唯一 Pilot，但不能声称机器代表性；用户未点名时才走 `MACHINE_REPRESENTATIVE_V1`，由冻结 Manifest 确定性选择三个连续多 atom 场景窗口；
- 每轮只启用一种选择模式并创建一套 `target_windows / compiled_unit_overlays`，不为“同时保留两轨”重复生成第二套 Prompt。无论哪种模式，helper 都计算特征矩阵与缺口；用户点名覆盖不足只写 finding，机器模式才能使用代表性 spread 主张。模型不得自行宣称“代表性”“开中结尾”或“非连续”；
- 选择证据至少保存 Manifest hash、特征矩阵 hash、选中 ID/来源顺序、相邻顺序差、派生的 `derived_noncontiguous`、已覆盖与可覆盖但缺失的维度。是否非连续只由顺序差机器计算，不是通过条件；
- 若来源存在对应候选，样本必须覆盖来源对白、最高风险、至少两个位置桶和实际存在的全部 `EDITED_SEQUENCE / GENERATABLE_SHOT` 路由；算法按新增覆盖最多、风险更高、来源顺序更早确定性破同分；`spread_policy.claim` 必须从真实 Unit order 派生并由验证器重算，不能靠自报通过；
- 每个目标工作区只有 `editable_paths` 精确列出的创作叶可改。模型填写场景名、表演、声音、摄影、引号判断、仍开放的说话者、逐镜戏剧任务/可选导演动作/摄影、MP、TP 三数组、NEP、预分配导演控制槽正文、负向句和具体 findings；来源主张、来源发声主体与来源对白 slot 均由 helper 锁定。模型禁止填写来源结构、镜头范围、provenance、inference、检查布尔值、hash、终点、`PASS`、`CURRENT`、验证结果或运行总结；
- 正式 ECO 创作遵守当前 `GUIDE_ONLY`：只读 `SKILL.md`、ECO 合同、冻结来源及 `OVERLAYS.json.authoring_guide / target_windows / compiled_unit_overlays`，并声明正式输入与禁止读取 `scripts / tests / schemas / fixtures / self-test gold`；宿主执行能力未暴露时只写 `NOT_EXPOSED`。当前 `alpha7-overlay-guide-1.5` 与 `immutable_contract.authoring_workflow` 的精确顺序只在 ECO 定义；三个运行 helper 的联合哈希变化后必须重新 prepare，旧工作面不能继续提交；
- 用户没有明确点名 anchors/ranges 时必须使用 `MACHINE_REPRESENTATIVE_V1`；模型自行挑选的范围仍属机器选择。每轮只生成一套目标与 overlays；
- 低算力运行允许每回合只完成 1 个目标；只有全部目标都具备完整 MP/TP/NEP、逐 Shot 执行 beat、完整来源/对白覆盖、语义门与来源声音投影通过、finalizer 复算通过的对白差异与内容自检，以及唯一当前结构质量记录后，才可申请完成；结构、同作者内容自检、由本轮创作者之外的编辑审阅三轴不得合并表述；
- 剧情概述、工程 `valid=true`、角色立绘或静物图都不能算 Prompt Quality Pilot 通过；
- 有真实供应商执行时，同一批 Pilot 还要服从银幕总控的生成观察与修复关卡；
- 文字 Pilot 通过只证明 Longform 编译合同，不证明真实媒体表现。

代表性 Prompt Pilot 是校准样本，不是连续生产 batch，也不得冒充从 U001 起无缺口的生产覆盖。没有当前 provider/surface 时仍产出 MP、TP 与可复制的供应商中性 NEP，但不得创建 PP 或 Generation Readiness；已有当前手工网页入口但不依赖版本能力主张时，可按总控合同交付 `MANUAL_COPY_TEXT_SPEC_ONLY`。`TEXT_ONLY_ECO_TEST` 只有在 finalizer 合并 overlay、注入来源对白并对预先冻结的最终名称自验证后，才可宣布文字样片完成；验后改名、复制替换或正文编辑会使该验证失效。

### B002 及后续

- Prompt Quality Pilot 通过并具备对应继续授权后，才另起连续生产 batch；目标接近 10 个 Unit，但保持 4—10 个动态范围；
- 在可复算 Prompt 字符预算可用时，参考 18,000—28,000 字符；该预算用于上下文安全，不是内容质量或供应商能力硬指标；
- 自然边界、因果完整性和高复杂度优先于凑满 10 个；
- 上批出现两个以上硬失败、容量接近上限或上游被修订时，下一批缩小 25%—50%；
- 非最后批越界需要 `batch_budget_exception` 和具体理由。

每批只加载：最新 committed checkpoint、相关 Project/Asset Bible 切片、本批 Unit 及前后 lookahead、本批来源、当前连续性域、必要参考、激活能力、当前 Prompt 质量核心和未解决异常。不要重新加载全部旧 Prompt、完整 ONEFILE、无关专业路线或依赖聊天记忆重建状态。

若用户已明确授权两轮 `TEXT_ONLY_ECO_TEST` 或 `TEXT_ONLY_TO_RUN_SUMMARY`，Prompt Pilot 后不得重复询问“是否继续”；在不批准任何创意真值的前提下流转到本轮 `RUN_SUMMARY`。只有来源歧义影响含义、P0 阻断或上下文不足时停在检查点。

## 8. Checkpoint 与恢复

每个 checkpoint 至少保存：

```yaml
checkpoint_id: B001
status: COMMITTED
source_sha256: sha256
skeleton_sha256: sha256
global_state_sha256: sha256
prompt_soul_version: ALPHA7-PQS-2
previous_checkpoint_sha256: sha256
batch_units: []
accepted_units: []
prompt_quality_record_ids: []
next_unit_id: U006
continuity_snapshot: {}
unresolved_exceptions: []
batch_handoff: {}
sha256: sha256
```

`sha256` 对排除自身 `sha256` 字段后的 canonical checkpoint 计算。首个 checkpoint 的 `previous_checkpoint_sha256` 指向 skeleton；后续形成连续 hash chain。只有 `COMMITTED` 批次计入进度，半批或聊天摘要不得自动视为 accepted。

`prompt_quality_record_ids` 只引用本批已接受 Unit 的唯一质量记录，不复制 MP/PD/PP 正文、`director_beats`、semantic atoms 或 adapter 诊断。`continuity_snapshot` 保存恢复所需的 `density_calibration / style_fingerprint_id / active_asset_capsule_hash / dialogue_audio_carry / open_action / camera_vector / sound_state`；详细资产、对白和质量内容仍从当前版本权威记录解析。

项目顶层同时保存 `latest_checkpoint_id` 与 `latest_checkpoint_sha256`，两者必须指向最后一个 committed checkpoint 的 ID 与 canonical hash；只保存聊天里的“上次做到哪里”不构成恢复指针。

恢复顺序：

1. 验证 source hash；
2. 验证 skeleton 与 `global_state_sha256`；
3. 验证 checkpoint hash chain；
4. 验证 accepted Unit 无缺口、重复或倒序；
5. 验证 Unit/Batch handoff；
6. 加载最后 committed `continuity_snapshot`；
7. 从 `next_unit_id` 继续。

## 9. Unit/Batch 双层交接

Unit 只交接给 frozen manifest 中的紧邻下一 Unit：

```yaml
unit_handoff_out:
  scope: UNIT_TO_UNIT
  from_unit_id: U005
  to_unit_id: U006
  state_out_sha256: sha256
  entry_facts_for_next_unit: []
  open_actions: []
  dialogue_audio_carry: []
```

Unit handoff 禁止包含 `batch_id`、`checkpoint_id`、`next_batch_id`、`resume_instruction` 或 portable resume 文本。

`entry_facts_for_next_unit / open_actions / dialogue_audio_carry` 必须足以恢复未完成动作、摄影运动、声音桥和精确对白游标，但不得复制完整 Prompt。跨 Unit 对白续接项至少保留说话者、精确下一文本位置、声线/情绪/音量趋势、声学空间和底噪；摄影与动作向量保存在状态引用中，COPY Prompt 再展开为自然语言入口。

Batch 恢复只存在于 checkpoint：

```yaml
batch_handoff:
  scope: BATCH_TO_BATCH
  from_checkpoint_id: B001
  next_checkpoint_id: B002
  last_accepted_unit_id: U005
  next_unit_id: U006
  boundary_after: U005
```

两层 `next_unit_id` 必须一致。即使批次在 U005 结束，Unit 层仍写 U005→U006；B001→B002 只由 checkpoint 表达。`batch_handoff` 不保存当前 checkpoint 自身 hash，避免递归自引用。

## 10. 负向条款边界

负向控制使用结构化、可哈希、整句库存：

```yaml
negative_clause_plan:
  candidate_clauses:
    - clause_id: NEG001
      text: 不得无因改变角色身份或数量。
      risk_refs: [RISK001]
      origin: CORE
      text_sha256: sha256
  selected_clause_ids: [NEG001]
negative_clauses:
  - 不得无因改变角色身份或数量。
```

必须满足：

- 一项只含一条完整约束，带终止标点；
- 选中顺序与最终序列逐字一致；
- 每条有 `risk_refs` 与匹配 SHA-256；
- 调整时整句删除、增加或完整改写后重算；
- 禁止字符串尾部裁切、半句、未登记尾巴、重复句和为凑比例填充；
- 负向条款只控制当前风险，不能成为第二份剧情 Prompt。

Alpha.7 不继承通用负向比例硬门。若具体供应商存在已核验限制，由 Provider Registry 或当前 Pilot 建立 provider-local 规则；没有证据时，不编造“最佳比例”。

## 11. 与 Alpha.7 状态及真实性合同对接

- 全局骨架与 Prompt 工程文字完成，只创建精确 scope 的 `spec_completion_record`；
- `TEXT_ONLY_ECO_TEST` 的 Pilot 真实终点只可为 finalizer 验证后写入的 `TEXT_PILOT_COMPLETE`，不得同时或在六轴摘要中声称 `TEXT_SPEC_COMPLETE`；只有另行完成全文或精确点名范围的全部连续编译后，才可使用相应范围的 `TEXT_SPEC_COMPLETE`；被排除媒体步骤为 `EXCLUDED_BY_USER`，执行/观察/媒体 QA/生产验证保持 `NOT_EXECUTED / NOT_EXECUTED / QA_NOT_EXECUTED / NOT_TESTED`，不得写 `SIMULATED_ONLY`；
- 纯文字 Pilot 的状态分三轴：确定性结构验证、同轮 `content_self_review`、由本轮创作者之外的编辑审阅。`quality_scope = CONTRACT_STRUCTURAL` 与 `quality_status = PASS` 只证明合同结构；内容自检至少覆盖具体场景名、工作稿存在、事实/提案分离、逐镜戏剧节拍和声音无歧义；它不能冒充交叉编辑审阅。没有相应证据时 `editorial_review_status = NOT_REVIEWED`、`content_readiness = REVIEW_REQUIRED`、`resume_entry = EDITORIAL_REVIEW`，并保留 `INDEPENDENT_EDITORIAL_REVIEW_REQUIRED`；
- `GLOBAL_GATE`、Longform Pilot 验证和 checkpoint commit 是编译关卡，不替代内容编辑复核或 `GENERATION_READINESS_GATE`；机器 `valid=true` 只允许表述为“结构校验通过”，不能单凭它宣布创作质量通过或可直接生产；
- Prompt Quality Pilot 必须检查真实 MP/PD/PP 正文和对应角色的 `prompt_quality_record`；工程状态、hash、coverage 或 checkpoint 全绿不能替代 Prompt Quality 检查；
- Pilot 晋级还必须同时满足：机器计算的代表性证据通过、来源对白 slot/inventory/diff 通过、三个（或非 ECO 路线要求的 3—5 个）样本逐一 `CURRENT / PASS`、最终机器状态文件验证退出码为 0；这些完成值只能由 finalizer 在成功验证后一次写入；
- finalizer 验证失败时终点为 `PILOT_REWORK_REQUIRED`，质量为 FAIL，并保存 `validation_result` 与最小恢复动作；不得先写完成状态或完成语气的用户总结再改口；
- 没有真实媒体时，不实例化 `SHOT_GATE` 或 `SEQUENCE_CONTINUITY_GATE`；
- `production_validation` 保持 `NOT_TESTED`；
- 真实媒体到来后，用 Observation 更新 `OBSERVED_STATE`，再把变化写入下一 checkpoint；
- 来源或真实状态变化引发重编时，保留拒绝、修正、版本和 hash 轨迹；
- 用户可见说明、风险、恢复摘要和下一步默认使用自然简体中文；机器字段、ID、枚举、hash 和供应商 token 保持英文。

Longform 编译完成不等于 `REAL_PRODUCTION_COMPLETE`，更不等于发布、内容规范、素材许可或传播效果已经验证。

## 12. 确定性验证

连续生产或恢复模式必须对本轮实际长内容根合同 JSON 运行长篇验证器；开发期 `--self-test` 只验证 Skill 自身，不能代替产物验证。`TEXT_ONLY_ECO_TEST` 不在本文件维护第二套命令：只调用当前纯文字 ECO 工作流的 prepare 高层入口，再逐字执行 `AUTHORING.json.immutable_contract.authoring_workflow` 的检查、重试、提交或重准备参数数组。

prepare 只从来源与登记选择派生不可变合同、连续窗口、引用库存、对白 slot、短指南和空 overlay，不发明导演内容。作者只编辑指南开放的三块；finalizer 独占 slot 合并、computed `content_self_review`、execution beats、派生 hash、根 `runtime_identity`、状态晋级、原位三载体写入与实际路径自验证。已有输出时不得删除覆盖，改用新空路径并执行 `reprepare_argv`；验后不得移动或改名。

普通创作运行不得读取 helper/finalizer/validator 源码、fixtures、测试说明、Schema 或 `--self-test` 结果，不得自建胶水脚本，也不得使用 `python -S` 或关闭宿主保护。纯文字具体字段、错误码、命名合同和恢复动作一律回到 `TEXT_ONLY_ECO_WORKFLOW.md`，避免本引擎与 ECO 双份漂移。

验证器检查：

- 全文 hash、atom span 与双覆盖；
- `compile_target` 过滤；
- Unit 顺序、完整覆盖与 trace 一对一；
- `global_state` 投影和 `global_state_sha256`；
- `FULL_PROJECT` 模式归一化；
- Pilot、后续批次范围与批次覆盖；
- checkpoint hash chain 与最新指针；
- Unit/Batch handoff 作用域；
- continuity snapshot 必需字段；
- 负向条款的完整句、库存、顺序和 hash；
- 无真实生产证据时的 `NOT_TESTED` 边界。

普通创作运行必须验证本轮实际产物；Skill 自测不能代替这一步。验证成功只证明本文件定义的长内容编译与恢复合同成立，不证明真实视频质量、供应商产能或 Production Validation。
