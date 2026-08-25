# Alpha.7 项目类型与唯一总调度契约

## 1. 一个总控，不拼接多个总控

银幕总控是唯一负责路由、依赖、授权、证据、版本与恢复点的调度者。外部 Skill、脚本、浏览器、模型和剪辑工具都是被调用能力，不得另建平行项目状态、决定账本或“第二总控”。

每次只加载当前任务所需模块。第三方方法可以被吸收为局部规则或适配器，但不得整包复制其提示词、品牌口吻、旧工具清单、平台断言或未经验证的阈值。

## 2. 漫剧/短剧为默认核心，其他领域按需挂载

当用户要做 AI 漫剧、短剧、叙事概念片，且没有明确指定其他类型时，以 `NARRATIVE_SHORT` 作为默认核心路线。先完成最短的故事—资产—分镜—Prompt—代表性 Pilot 链，不自动加载长篇、科研、文化、品牌、发行研究或完整市场分析。

常规漫剧先做能覆盖人物一致性、对白/表演、关键动作与镜头衔接的 3—5 镜代表性 Pilot，再按真实观察决定后续批次；该数量只是低成本起点，不是质量阈值，也不能代替项目风险覆盖。

推广片、纪录、科研科普、文化、教育、品牌与作品展示不是删减功能，而是**按项目目标挂载的辅助路线**：只有用户目标、`content_truth_mode`、交付要求或当前决定确实需要时，才加载对应的来源忠实、传播结构、内容规范或研究模块。辅助路线沿用同一资产、镜头、Prompt、执行、QA 与发布前关卡，不另建第二套生产系统。

`project_route.project_types` 可组合：

- `NARRATIVE_SHORT`：短剧、漫剧、概念短片；
- `SERIES_LONGFORM`：系列、长剧、长篇连续视频；
- `DOCUMENTARY_NONFICTION`：纪录、访谈、事实叙事；
- `CULTURE_HERITAGE`：博物馆、历史、非遗与文化传播；
- `SCIENCE_RESEARCH_EXPLAINER`：科研成果、实验、科学概念与技术说明；
- `EDUCATION_PUBLIC_INTEREST`：课程、科普、公益与公共传播；
- `BRAND_PRODUCT`：品牌、产品、单位与服务影像；
- `PORTFOLIO_DEMO`：作品集、提案样片与能力展示；
- `HYBRID`：确实跨类型时使用，并分别保留各自限制。

`content_truth_mode` 必须区分 `FICTION / NONFICTION / MIXED`。非虚构或混合项目开启来源忠实保护：事实、引文、数字、文物细节、实验结论和人物身份不得由模型补写；缺少来源时保持 `UNKNOWN`，视觉演绎必须标明重建、示意或推断边界。

规模使用 `SHORT_FORM / EPISODIC / LONGFORM / CAMPAIGN / MODULAR`。短片可以显式跳过季集架构；长项目必须建立全局设计、连续性状态、Pilot、可恢复批次和检查点，不能逐段失忆式生成。

默认加载原则：

- 纯 `NARRATIVE_SHORT + FICTION`：只加载当前故事或制作环节需要的核心模块；
- `NONFICTION / MIXED`：增加来源忠实与按需事实核查，但不自动做全市场调研；
- 辅助项目类型：只增加该类型独有的事实、传播或交付约束；
- `HYBRID`：逐项写明为什么需要组合，不能把所有类型当作“更完整”的默认值；
- 涉及当前适用规则、平台、供应商、科研事实或比赛声明时，按 `ON_DEMAND_RESEARCH_ROUTER.md` 做最小检索；稳定创意问题不因项目类型复杂而自动联网。

具体模块选择、上下文预算、批次与 `ONEFILE` 互斥规则遵守 `CONTEXT_AND_BATCH_BUDGET.md`；一次运行只能选择模块化来源或 `ONEFILE`，不得两者同时加载。

`delivery_mode` 与项目类型及规模分开：同一个 `SERIES_LONGFORM` 或 `NARRATIVE_SHORT` 都可选择 `MEDIA_ENABLED` 或用户明确授权的 `TEXT_ONLY_ECO_TEST`。后者遵守 `TEXT_ONLY_ECO_WORKFLOW.md`，只跑文字范围；IMAGE/VIDEO/AUDIO/EDIT 记为 `EXCLUDED_BY_USER`，不是失败或模拟，也不改变项目类型。

## 3. 任务图

每个可执行工作单元写入 `task_graph`，至少包含：

- `task_id`、领域与任务类型；
- 真实执行路线与状态；
- 输入产物及版本、依赖任务、必要决定；
- MASTER / 供应商编译 Prompt、供应商记录与输出产物；
- 执行回执、阻断项与恢复检查点。

任务状态只描述该任务，不能覆盖项目六轴状态。任务依赖必须存在且无循环；下游不得把未完成上游当作真实输入。失败后保留已完成产物和检查点，从最小受影响范围恢复。

在 `TEXT_ONLY_ECO_TEST` 中，“可执行工作单元”仅指文字摄取、分析、编译和本地文字校验。被用户排除的媒体能力不进入 `task_graph`，不得创建 IMAGE/VIDEO/AUDIO/EDIT 的占位任务、未来 Gate 或模拟回执；只在运行范围记录一次 `excluded_step_status = EXCLUDED_BY_USER`。

## 4. 能力路由

按任务选择最窄能力：

- 创意、故事、证据与结构：内部推理及相应 phase；
- 长篇连续性：长项目连续性引擎；
- 图像、视频、声音与模型生成：动态供应商注册表 + 编译 Prompt + 外部执行契约；
- 时间线、字幕、转码、混音与交付：媒体执行与剪辑契约；
- 自然中文、内容规范、素材许可与传播准备：三阶段四重总检；
- 真实媒体观察、NCS/NRS 与修复：观察和修复闭环。

研究与检索也是被调用能力，不是常驻阶段。只有触发当前性或来源忠实要求时才创建 `RESEARCH` 任务；默认只加载紧凑 Evidence Capsule 和被引用的 evidence 记录，不加载整站、整份平台手册或无关领域资料。

工具不可用时先寻找同层替代路线；只有真实外部执行本身不可完成且用户明确要求线路模拟时，才使用 `SIMULATION`。缺一个工具不能成为删除关键叙事功能或伪造完成状态的理由。

## 5. 默认自动推进边界

可自动执行：只读检查、可逆草稿、本地验证、用户已授权范围内的可恢复生成、转码、字幕、分析与修复。

用户明确授权两轮纯文字测试或连续跑到总结时，可建立 `scope = TEXT_ONLY_TO_RUN_SUMMARY`、`external_actions = false`、`creative_defaults = PROPOSED_ONLY` 的有界继续授权。它只授权流程流转，不批准创意或事实决定；不得在 Prompt Pilot 后再次索要“继续”。遇到 `SOURCE_AMBIGUITY_AFFECTS_MEANING / P0_BLOCKER / CONTEXT_INSUFFICIENT` 必须保存游标并暂停。

必须暂停并请求用户本人处理：登录失效、验证码、支付、账号授权、需要用户确认的许可声明、不可逆覆盖、对外发送或其他会改变外部状态的动作。

本版本的自动化终点是 `RELEASE_READY`。可以生成发布包、标题、封面文案和检测报告，但不自动上传或发布。用户后来手工发布并提供真实证据时，可只读登记 publication 与真实数据，不能倒推发布前检查已经通过。

上述 `RELEASE_READY` 只适用于 `MEDIA_ENABLED`。`TEXT_ONLY_ECO_TEST` 的终点是 `TEXT_PILOT_COMPLETE` 或精确范围的 `TEXT_SPEC_COMPLETE`，随后固定输出 `RUN_SUMMARY`；执行、观察、媒体 QA 和生产验证保持未执行/未测试。
