# Stage 9 — 导演图与精细分镜

本阶段把已批准故事/信息结构编成可进入 Prompt 的镜头真值，不写供应商成品。运行边界见 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`；剧本、对白与 Prompt 的全量交接见 `../references/ALPHA7_CONTINUUM_CREATIVE_FIDELITY_ENGINE.md`；对白先排声音、动作因果、参考职责、相邻镜头交接和制作登记见 `../references/ALPHA7_MASTER_PRODUCTION_CONTROL.md`；年龄受保护角色、复杂同镜、供应商能力与对白 coverage 见 `../references/AGE_SAFETY_PROVIDER_AND_COVERAGE_CONTRACT.md`；导演密度、节拍、资产胶囊、对白调度和 Prompt Pilot 统一调用 `../references/PROMPT_QUALITY_CORE.md`，本文件不复述其字段和表格。

导演意图、动作、声音和连续性使用 `creative_artifact_language`；机器 ID、时间码、枚举和 Schema key 保持规范形式。

## 输入

- 当前批准的脚本/信息结构、`canonical_duration` 与版本；
- 当前范围按顺序冻结的事件、对白、旁白、人物非词汇发声与必保视觉事实；
- 当前资产、Reference Registry、Style Bible、声音和格式变体；
- 决定、受保护未知项、数量与因果边界；
- `dialogue_inventory`、年龄受保护角色安全 profile、适用供应商能力证据；
- 当前制作记录中的逐字对白排程、参考职责、已接受素材末态、资产版本、进度与尝试上限；
- 上游 Artifact 版本/hash 与开放 blocker。

缺少会改变镜头语义的输入时只列缺口和安全可做范围，不补写真相。

## 执行步骤

### 1. 建立 1:1 镜头契约

每镜只保存当前需要的信息：`shot_id`、序列、叙事目的/来源、承担的来源单元、`state_in`、必做事件、`planned_state_out`、时长、资产/参考/格式、对白与声音、摄影和转场、连续性、风险、禁止变化及 Production Alternative。对白回链稳定 `dialogue_id + shot_plan_id`；资产与镜头双向解析。当前分镜范围的来源单元并集必须覆盖全部必保事件、发声和视觉事实；拆到多镜时保持顺序，不能重复对白、提前结果或用反应镜头替代事件本身。

只有批准内容能成为必做事件。`PROPOSED/UNKNOWN` 不得借分镜坐实；受影响镜头登记 `protected_unknown_ids / quantity_ids / causal_boundary_ids`。相关性逐镜检查时间相邻、声音/振动、空间指向、视觉相似和台词字幕，文字写“非因果”不能抵消画面因果暗示。

### 2. 生成策略

正常镜头使用 `generation_required = true`。同镜含复杂未成年/成年人、多主体遮挡、精确接触、长动作链或复杂口型，且缺少当前入口能力证据时：

- `DECOMPOSITION`：拆成动作、反应、插入、前态/结果态；
- `COMPOSITE`：建立分离图层/镜头与遮罩、边缘、位置、素材许可、版本和 hash。

原聚合镜头改为 `generation_required = false` 并说明 `no_generation_reason`，其四层 Prompt ID 为空；可执行 Prompt 只属于派生的真实 SHOT 目标。年龄未知保持 `UNKNOWN`，已核实年龄不得改写；安全表达模式不改变人物事实。

### 3. Prompt-ready 导演源

按质量核心把生成对象声明为 `target_type + target_id + generation_role + generation_medium`。Stage 8 已建立的角色/场景静态参考图使用 `ASSET_REFERENCE / IMAGE`；需要转身、步态或表演的资产参考视频使用 `ASSET_MOTION_REFERENCE / VIDEO`。本阶段可为同一叙事镜头分别建立 `SHOT_KEYFRAME / SHOT_START_FRAME / SHOT_END_FRAME / SHOT_MOTION / SHOT_COMPOSITE_LAYER`。静态 IMAGE 使用一个 `STATIC_IMAGE` 单帧构图合同，不编造时间线；VIDEO 才准备自然时长、连续阶段、活动资产/连续性胶囊、对白 fragments、风险和 HERO 节拍。静态组件不重复计入 canonical editorial duration。漫剧默认 `MANGA_CORE`，但媒介、风格和画幅仍服从批准决定。单个视频节拍只保留一个主要动作、一个主要运镜家族和最多一个高风险事件；一镜到底使用连续阶段，不能降低信息密度。

有对白时先检查可用时长。说不完则 `SPLIT_REQUIRED`；不得删字、硬加速或末尾附对白清单。同一句跨镜按质量核心使用 `ONSCREEN_LIP / L_CUT / VOICE_OVER / AUDIO_POST_REQUIRED`，拼接后逐字等于库存原文。说话镜同时明确听者反应、口型责任、停顿、句后状态和跨镜声桥；模型不支持声音时只改变声音生产责任，不改变台词和时间点。

拆镜不能只跟着标点走。逗号、感叹号、问号和破折号只是候选表演节拍；每次切镜都要承担新的听者反应、道具状态、空间信息、权力变化或笑点落点。每镜按“准备 → 主动作 → 可见后果 → 结束状态”收束，一个主要动作配一个主要摄影任务，摄影栏不得改写一遍动作栏。

分镜定稿前检查发声身体与道具占用：同一角色嘴部被道具占用时，清楚对白之前必须拍到松口和道具承接，不能靠避开口型、隐藏嘴部或切到幻想画面假装冲突不存在。画面里另一个角色说话不构成冲突；修改发声方式会改变来源含义时先交用户确认。

对每个可生成镜头先建立动作因果链：准备状态、主要动作或施力、接触或释放、可见反作用、动作制动与确定终态；摄影只写如何让这一链条可读以及停在哪里。对每对相邻镜头再建立交接行，逐项核对人物与服装、位置和方向、视线、姿态与动作阶段、道具归属、嘴部和双手占用、开放运动、摄影轴线、主光、声场、对白进度、主剪法与备用切法。上一镜交出的动作、位置、道具、遮挡、构图或声音线索必须被下一镜明确接收。

没有真实成片时使用 `planned_state`；回传素材经用户接受后，`observed_state` 覆盖计划并触发后续局部重编译。被拒绝素材不进入连续性真值。制作记录随本阶段更新进度、完成证据、恢复位置和当前资产版本，但这些机器信息不进入创作者的逐镜提示词。

从身份/表演、最高动作/声音风险和必要连续性中选 3—5 个代表性 Prompt Pilot；可包含一个身份关键 `ASSET_REFERENCE` 或一条确有动作验证价值的 `ASSET_MOTION_REFERENCE`，但不能只用最容易的角色立绘、转身样片或静物替代困难镜头。先做局部 Pilot 不要求同一 SHOT_PLAN 的全部生成目标一次完成。

### 4. 时长、转场与格式

项目只保留一个当前 `canonical_duration`；新增、删除、拆分或改时长后重算逐镜总和。容差必须有来源、批准和范围。若声称 provider 可直接执行，当前 model/version/surface/region/task、输入方式和时长必须有适用 `capability_evidence_ids`；否则保持 `TARGET/UNKNOWN`，先核验、拆镜或试制。

转场使用 `CONTINUOUS_ACTION | NARRATIVE_CUT | MONTAGE_ELLIPSIS`，逐项写明继承状态。横竖版默认分别建立规格；只有真实安全区证据支持时才用 `TESTED_COMMON_SAFE_ZONE`。不同机位/调度/节奏建立单独的 `shot_variant_id` 和 Prompt。

### 5. 校验与落盘

检查唯一 ID、版本、双向引用、时长算术、派生镜头功能覆盖、ASSET/SHOT 目标与 generation role、对白库存、未知/数量/因果边界、年龄事实、供应商能力证据、节拍实质内容和 Pilot 代表性。对白、镜头或时长变化使受影响字幕、TTS coverage 和四层 Prompt 失效；资产、首帧或参考职责变化只使依赖它们的目标失效，不重编无关镜头。

新建或实质改写的分镜/对白库存登记当前 `TEXT_SPEC` Artifact、版本与 `content_locator.sha256`，再对精确版本/hash 运行 `IN_PROCESS` 四重检查：自然中文、内容规范、素材许可来源、传播理解链。内容规范/素材许可阻断不可被传播分抵消；无真实媒体时只检查规格，不能声称媒体通过。

首个完整分镜样场、所有对话高风险目标，以及发生删减、顺序或时长变化的范围，准备 CONTINUUM `VIDEO_PROMPT` 或 `SCRIPT` 预检输入并运行本地工具。此处先验证来源覆盖、对白与镜头时间是否能闭合；最终 PP 形成后还要在 Stage 10 对同一范围再跑最终 Prompt 预检。

## 最小实例

```yaml
shot_id: SH-001
state_in: 当前可见入口
required_event: 已批准的单一核心事件
planned_state_out: 下一镜必须继承的出口
generation_required: true
duration_semantics: TARGET
asset_ids: [CHAR-001]
dialogue_ids: []
protected_unknown_ids: []
quantity_ids: []
causal_boundary_ids: []
prompt_ready_director_source: PREPARED
```

示例只展示路由；真实导演字段由质量核心完整实例化，不能把这些短句当成正式 MASTER。

## 输出、停止条件与完成边界

输出当前 `SHOT_PLAN`、对白库存、派生/合成规格、Prompt-ready 导演源、Pilot 选择及 Artifact/四重检查记录。以下任一项阻止进入 Stage 10：

- 必做事件仍依赖未批准真相或开放 blocker；
- 时长不一致、资产/参考/对白无法解析；
- 复杂同镜没有安全可执行策略；
- 指定入口缺少适用能力证据；
- 因果、年龄、内容规范或素材许可存在阻断；
- 导演节拍只是摘要、模板或空字段。

分镜 scope 完整时只创建 `scope_type = SHOT_PLAN` 的 completion record。没有真实镜头时不实例化 `SHOT_GATE/SEQUENCE_CONTINUITY_GATE`，也不声称 Prompt、媒体或连续性已经完成。
