# 执行总调度引擎

## 目标

把用户目标编译成一个可恢复、可审计的任务图，并在不制造第二总控的前提下调用故事、证据、长项目、供应商、浏览器、本地工具、剪辑和质检能力。

## 每轮调度

1. 读取真实入口状态与本轮目标；
2. 选择项目类型、事实模式、`delivery_mode` 和最短有效阶段；
3. 涉及年龄受保护角色时读取年龄、来源、同意与用途，选择 `minor_compilation_mode = EXACT | LIFE_STAGE | REFERENCE_BOUND`，并保持年龄事实不变；
4. 只创建当前可执行或紧邻的任务，不预铺几十个空任务；
5. 检查依赖、决定、输入版本、权限、风险和停止条件；
6. 按 `PROVIDER_NEUTRAL_MASTER → TRANSFORM_PLAN → NEUTRAL_EXECUTION_PROMPT → PROVIDER_COMPILED` 分层；只有编译层可进入外部执行；
7. 选择 `INTERNAL_REASONING / LOCAL_TOOL / BROWSER / API / MANUAL / SIMULATION`；
8. 执行后写回真实 Artifact、Evidence、Receipt、Observation 或 Blocker；Receipt 明确生产媒体、本地验证或本地文字工具域，新文字产物也写入状态、版本与 SHA-256；
9. 从检查点推进、修复、回滚或带债继续；
10. 对用户只显示结论、当前进度和必要动作，完整账本放项目文件。

`delivery_mode = TEXT_ONLY_ECO_TEST` 时读取 `../references/TEXT_ONLY_ECO_WORKFLOW.md`。只调度来源摄取、Global Truth、文字规格、Prompt Quality Pilot 与本轮 `RUN_SUMMARY`；用户排除的 IMAGE/VIDEO/AUDIO/EDIT 统一记为 `EXCLUDED_BY_USER`，不创建/执行相关任务、Gate 或模拟回执。

## 路由优先级

- 有真实文件就审阅文件，不重问内容；
- 有成熟产物就从相应阶段继续，不重启发现；
- 有本地确定性工具就优先用于计时、哈希、字幕、时间线、转码和校验；
- 需要现有登录状态时使用浏览器；有稳定接口且已授权时可用 API；
- 外部模型与网站只执行当前 `capability_evidence_ids` 覆盖的 provider/model/version/surface/region/task 能力；不硬编码“15 秒”或迁移另一入口的能力；
- 复杂年龄受保护角色/成年角色同镜或当前能力不足时，选择 `DECOMPOSITION` 拆镜或 `COMPOSITE` 后期合成；原始聚合镜头不得继续编译或执行，再重算组件镜头、时长、Prompt、字幕与 TTS coverage；
- 后期从当前 `dialogue_inventory` 检测字幕漏句；仅完成 TTS 文字规格时写 `tts_coverage_status = NONE`，`PARTIAL / FULL` 的每条 covered dialogue 必须绑定同版本 `MEDIA` Artifact；用 `measurement_coverage_status` 另记真实音频实测覆盖，部分集合绝不冒充全片；
- 不可执行时寻找同层替代，不能将计划改名为完成。

跨阶段运行细则统一读取 `../references/AGE_SAFETY_PROVIDER_AND_COVERAGE_CONTRACT.md`，不在子任务中另造 Prompt、年龄受保护角色或 coverage 同义码。

## 长任务

先用摄取游标与异常清单完成来源 reconcile 和全局设计，再做 3—5 个可非连续的代表性 Pilot；省算力时每轮可只做 1 个并累计。代表性 Pilot 与连续生产 batch 分开；通过后才按 4—10 个连续单元的可恢复批次推进。具体数量是默认工作粒度，不是质量阈值，可由项目规模和证据调整。每批保存全局状态摘要、已完成范围、下一批入口、连续性变更和回滚点。

用户明确授权两轮纯文字测试或 `TEXT_ONLY_TO_RUN_SUMMARY` 时，该授权只允许文字流转，`external_actions = false`，未决创意保持 `PROPOSED_ONLY`。不得在 Prompt Pilot 后重复询问继续；只在来源歧义影响含义、P0 阻断或上下文不足时停在恢复点。每轮末固定输出一份紧凑 `RUN_SUMMARY`，默认仍只交付 1 个主产物和至多 2 个必要支持产物。

## 禁止

- 不创建平行状态机或让子 Skill 覆盖项目账本；
- 不让传播分抵消内容规范或素材许可阻断；
- 不用一个旧 Pilot 解锁新供应商、新版本或新任务；
- 不自动发布，不处理验证码，不替用户付款或接受条款；
- 不把模拟、用户口述、文字 Prompt 或时间线计划记成真实媒体执行。
- 纯文字模拟只有在真实记录 `SIMULATED_EXTERNAL_STEP` 后才使用 `SIMULATED_ONLY`；用户主动排除媒体步骤时使用 `EXCLUDED_BY_USER`，不是模拟，并保持 `NOT_EXECUTED / QA_NOT_EXECUTED / NOT_TESTED`；两者都不产生媒体 QA、发布或学习事实。
- 没有当前 provider/surface 时只产出 MP、TP 与 NEP，不创建空 PP 或 Generation Readiness；普通用户只看到导演母版与可复制提示词工作稿。
- 不吸收外部 Skill 的固定 15/30 秒、固定字符数或负向比例；只有当前 provider 证据与项目风险可以建立局部约束。
