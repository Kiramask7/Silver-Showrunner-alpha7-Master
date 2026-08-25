# Alpha.7 Master 上下文与批次预算

## 1. 目的

用最小工作集保留银幕总控的完整能力。这里的“预算”指模型需要读取和生成的上下文，不是本地验证器运行时间，也不是质量上限。

漫剧、短剧和叙事概念片使用 `MANGA_CORE` 默认路线。文化、科研科普、教育、品牌、长篇、真实媒体执行与发布审计仍然可用，但只在项目类型或当前任务命中时加载。

## 2. 唯一入口与互斥读取

运行时先读 `SKILL.md`，然后只加载当前任务所需模块。

- 模块运行：读取 `SKILL.md` 与选择器返回的文件；
- 便携运行：只读取一个外置的 `*-ONEFILE.md` profile，建立来源索引后只使用相关 `SOURCE` 片段；
- 两种方式互斥。禁止同时把 ONEFILE 和其源模块放入上下文；
- Schema 与确定性工具只能通过当前路线公开的命令执行，不得作为创作背景全文加载。`TEXT_ONLY_ECO_TEST` 使用 `GUIDE_ONLY` 正式只读面，禁止打开 `scripts/`、`tests/`、schemas、fixtures、版本史或 self-test gold；Skill 源码开发与发布构建仍在隔离上下文中运行回归测试。

可用 `scripts/select_runtime_modules.py` 生成当前工作集。`schemas/runtime_route_registry.json` 是文件选择的唯一事实源；选择器只执行登记规则，不保留第二套模块清单，也不替代用户批准或 Gate。

### 2.1 三档预算执行

选择器提供三档硬预算。这里的“规则”是 `SKILL.md + 已选模块`；“来源与状态”是本轮实际可见的来源正文、项目状态和检查点。三档上限如下，任何一列都不能单独越线：

| 档位 | 总可控输入上限 | 规则上限 | 来源与状态合计上限 | 输出预留上限 |
|---|---:|---:|---:|---:|
| `RESTRICTED` | 8,000 | 3,500 | 4,500 | 2,500 |
| `STANDARD` | 16,000 | 6,000 | 10,000 | 5,000 |
| `ENHANCED` | 32,000 | 10,000 | 22,000 | 10,000 |

选择器同时保证在计入本档输出预留后，宿主上下文窗口仍至少保留 25%。这 25% 是宿主余量，不是允许继续塞入来源或规则的隐藏额度。档位名无法识别时必须按 `RESTRICTED` 执行，不能猜成更宽松档位。

总可控输入必须同时计算：`SKILL.md`、已选模块、当前可见来源、当前可见状态。来源与状态既可提交已知 token 数，也可用 `--source-visible-file / --state-visible-file` 让选择器按实际文件估算。来源不是预算外附件，不能另计、后补或用“外部加载”绕开上限；不得只计算模块而漏掉小说、剧本、项目账本或检查点。

任一硬上限或宿主余量不满足时输出 `SPLIT_REQUIRED`，保留完整的已选能力与依赖，`selected_capabilities_removed` 必须为 0。选择器同时给出 `minimum_split_batches` 与 `checkpoint_plan`：按最少批次数顺序执行，在批间保存 Global Truth 哈希、来源游标、状态切片哈希、已选能力标识和开放问题。禁止为了压入窗口而静默删除质量合同、连续性合同或当前任务必需能力。若规则本身超限，也必须分阶段携带检查点，不能伪称删掉规则后可直接运行。默认档位为 `STANDARD`，示例：

```powershell
python -B scripts/select_runtime_modules.py --project-type SERIES_LONGFORM --task PROMPT --budget-profile STANDARD --source-visible-file 小说.txt --state-visible-file PROJECT_STATE.json
```

返回的 `budget.total_visible_tokens` 与 `budget.total_controllable_input_tokens` 都是入口、模块、来源与状态的合计；`rule_tokens` 和 `source_state_tokens` 分别接受对应硬门。`minimum_host_reserve_tokens` 至少等于宿主窗口的 25%，`output_reserve_tokens` 不超过本档上限，`selected_capabilities_removed` 必须始终为 0。规则量以选择器对当前冻结文件的当次回报为准；任一档位超限时必须如实返回 `SPLIT_REQUIRED`，不能引用过期固定数，也不能伪称可以一批直跑。

## 3. 当前工作集

普通任务建议只包含：

1. `SKILL.md`；
2. 一个项目类型或当前阶段入口；
3. 一个当前 phase；
4. 只有确实触发时才加入的一至两个专业合同；Prompt 已有可编译导演源时不重复加载导演阶段，只有缺失时才补载；
5. 当前项目的 Global Truth 胶囊、活跃资产、当前镜头/Unit 和少量前瞻。

如果需要一次读取多阶段全文、全部历史 Prompt、完整状态、ONEFILE 与测试材料，应先判断是否误路由。不能用“为了保险”作为无限扩张上下文的理由。

## 4. Global Truth 胶囊

每个项目只维护一份当前 Global Truth，至少包含：

- 核心创意与不可妥协项；
- 事实模式、来源与受保护未知项；
- 角色/主体、世界、视觉和声音的稳定锚点；
- 当前画幅、用途、时长与供应商决定；
- 当前版本、全局哈希、开放阻断项和最近检查点。

已关闭历史通过 ID、版本和哈希引用。除非当前修改触及其来源，不回灌旧 Prompt、旧观察或完整审计正文。

## 5. Pilot 与批次

### 漫剧、短剧和叙事短片

- 先选 3—5 个代表镜头：角色近景、复杂动作/接触、关键情绪或对白、核心风格、最高风险连续性；
- Prompt Pilot 通过后，再生成真实媒体 Pilot；
- 批量阶段默认每批 5—10 个镜头；
- 批内只读当前镜头、相邻状态、活跃资产胶囊和当前供应商能力；
- 风格、角色、故事结构或供应商版本改变时，回到受影响的最小 Pilot，不重跑无关镜头。

### 长篇与系列

- 先用 `ingestion_checkpoint` 分块摄取并记录已完成 code-point 范围、下一游标与异常清单；全量 reconcile 后再冻结全文来源、全局设计和稳定 ID；
- `atom` 只负责逐字覆盖来源，不能默认等同于 Unit。先把同一连续时空、同一场景语义中的相邻 atom 合成 `source_window`，再建立可制作 Unit；一个 Unit 可以且通常应覆盖多个连续 atom，不能把孤立对白、半句叙述或标点切片单独当作 Unit；
- 每轮只启用一种选择模式：用户点名 3—5 个目标时，`USER_TARGETED_EXACT_RANGES_V1` 把它们扩成连续场景窗口并作为该轮唯一 Pilot；用户未点名时，`MACHINE_REPRESENTATIVE_V1` 才从冻结 Manifest 选择 3—5 个代表窗口。两种来源分别登记，用户点名不能冒充机器代表性，但也不额外生成第二套 overlays；helper 对两种模式都计算位置、对白、路由和风险覆盖，缺口如实写 finding；
- Sequence 与 Shot 先分流：`EDITED_SEQUENCE` 只做 sequence design 与有序 shot plan，不能伪装成单镜 Prompt；`GENERATABLE_SHOT` 才直接进入镜头合同。是否非连续由本轮已登记样本的 Unit 来源顺序差派生；只有机器模式可以把该结果用于代表性主张；
- 通过后按 4—10 个 Unit 的可恢复批次推进；
- 每批只加载最新 checkpoint、当前 Unit、仅供连续性规划的必要 lookahead、相关 Bible 切片和开放动作/对白/声音状态；lookahead 不得推进当前窗口外剧情；
- `FULL_EXPORT` 只是一键交付入口，内部仍保留 Pilot、批次、QC 与 checkpoint。

上述数量是默认工作粒度，不是硬质量阈值。项目复杂度或真实 Pilot 证据要求改变时，记录调整理由。

### 纯文字省算力测试

`delivery_mode = TEXT_ONLY_ECO_TEST` 的全部运行细节只以 `TEXT_ONLY_ECO_WORKFLOW.md` 为准。本文件不复制命令、overlay 形状、错误码或总结模板；它只冻结预算边界：模块模式读取 `SKILL.md + ECO 合同 + 冻结来源 + OVERLAYS.json.authoring_guide / target_windows / compiled_unit_overlays`，并声明正式输入与禁止读面；ONEFILE 模式只读外置 `TEXT_ONLY_ECO`，其余模块按需后载。

创作模型只允许调用 ECO 公开入口，再逐字执行 `AUTHORING.json.immutable_contract.authoring_workflow` 的 `check_argv / retry_argv / commit_argv / reprepare_argv`；不得从实现或测试猜字段、自建胶水脚本或跳过安全边界。指南不足时保存工作面并报告缺口。

用户没有明确点名场景时，选择权属于 `MACHINE_REPRESENTATIVE_V1`；模型自己挑选后再写成精确范围仍然是机器选择。`USER_TARGETED_EXACT_RANGES_V1` 只用于用户明确给出的 anchors/ranges。没有 provider 时仍要产出真正可复制、供应商中性的提示词工作稿，但不得冒充 `PROVIDER_COMPILED` 或 Generation Readiness。

prepare 直接使用已存在空任务目录，以 `IN_PLACE_THREE_CARRIER_V1` 原位提交三份冻结名称；默认无 RUN 前缀。finalizer 只验证实际路径，验后禁止改名、移动或复制替换。根 `runtime_identity` 为只读机器身份，archive 证据未暴露时如实为 `NOT_EXPOSED`。结构验证、finalizer 复算的同作者内容自检、由本轮创作者之外的编辑审阅三轴及逐镜 execution beat 规则由 ECO 唯一维护。

## 6. 增量验证

批内只验证本次变化影响的：

- 资产与镜头引用；
- Prompt 质量记录与供应商编译；
- 时长、对白、字幕和连续性；
- 新任务、回执、观察、修复和局部四重检查。

以下边界才运行全量状态和包验证：

- Global Truth 首次冻结或发生结构性变更；
- Pilot 关卡；
- 批次 checkpoint；
- 成片、发布准备或正式发布包构建；
- 迁移、Schema 或 Skill 本体变更。

## 7. 降载信号

出现任一项时立即缩小工作集：

- ONEFILE、源模块、全文、全状态和旧 Prompt 同轮出现；
- 一处局部修改触发大量无关镜头重编；
- 尚未得到代表性最终 Prompt，就先创建全片三层空壳；
- 每回合都运行完整四重总检或输出专业账本；
- 当前回答主要是状态表，而不是故事、导演方案或最终可执行 Prompt；
- 用户等待很久，却还没有可审阅的核心创作产物。

默认修复：保留 Global Truth 和最近 checkpoint，批次缩小 25%—50%，冷存储历史正文，从当前最高风险对象重新开始。

## 8. 用户可见层

普通用户只需看到：当前创作结论、可审阅成品、真实状态和下一步。纯文字测试首次说明和最终总结的普通用户部分都不超过五行自然中文；模块清单、上下文估算、Schema、coverage 与增量验证记录留在开发或审计附件，不得成为普通创作的阅读负担。

默认每回合只新建 1 个主产物和至多 2 个立即会被使用的支持文件；状态、验证与纠错尽量合并到一个机器记录。只有依赖关系、版本锁定或用户交接确实需要时才拆文件，禁止用文件数量冒充完成度。

纯文字 Pilot 的用户可见终点只显示验证后的 `TEXT_PILOT_COMPLETE`，不能同轮显示 `TEXT_SPEC_COMPLETE`；只有另行完成精确点名范围的全部编译时才显示该范围的 `TEXT_SPEC_COMPLETE`。同时说明 `EXCLUDED_BY_USER` 和未执行真实性轴；不得重复粘贴全量 Prompt、历史检查正文或未来阶段空壳来放大输出。
