# Alpha.7 Master 中文优先语言与呈现合同

本文件仍是 Alpha.7 的语言用途规范；用户复杂度档位、scoped completion、Prompt 分层与状态真实性统一遵守 `ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`。

## 目的

让不同模型在不破坏机器结构的前提下，稳定向中文创作者输出自然、清楚、可执行的中文。

## 五个语言维度

```yaml
language_profile:
  interaction_language: zh-CN
  creative_artifact_language: zh-CN
  dialogue_language: PROJECT_DEPENDENT
  provider_prompt_language: PROVIDER_OPTIMAL_WITH_ZH_EXPLANATION
  release_copy_language: TARGET_DEPENDENT
```

- `interaction_language`：对话、问题、建议、风险、阶段结果与下一步。
- `creative_artifact_language`：项目简报、故事、剧本、分镜、资产表、QA 与修复报告。
- `dialogue_language`：角色台词语言，由作品世界与发行目标决定。
- `provider_prompt_language`：生成模型执行提示词采用的语言。
- `release_copy_language`：标题、简介、字幕、营销文案的目标语言。

这五项只能按明确范围分别改变。用户要求英文字幕，不会改变交互语言；海外发行也不会自动改变剧本工作语言。

## 默认与覆盖

- 用户使用中文或语言无法判断：`interaction_language = zh-CN`。
- 导入旧项目但没有语言记录：迁移层可暂按 `DEFAULT / zh-CN` 读取，必须补写语言字段后再进入严格 Schema 校验；`--allow-legacy-import` 仅供迁移前审计。
- 用户明确要求另一种语言：记录 `source = USER_EXPLICIT`，保存用户原话，只修改被点名的语言字段。
- 不对明显使用中文的用户追问“你希望用什么语言”。只有跨语种目标会改变制作或发行时才询问。

## 机器字段保持稳定

以下内容保留英文或原样：

- ID：`Q-001`、`D-001`、`E-001`；
- 状态与枚举：`PROPOSED`、`VALIDATED`、`SIMULATED_ONLY`；
- JSON/YAML key、Schema、文件名、路径；
- 代码、参数、命令、控制 token、引用 ID；
- 模型、平台、产品的正式名称。

不要创建中文枚举副本。中文只是显示层。

## 状态显示表

| 机器码 | 中文显示 |
|---|---|
| `DRAFT` | 草案 |
| `PROPOSED` | 待确认提案 |
| `USER_APPROVED` | 用户已批准 |
| `VALIDATED` | 已验证 |
| `LOCKED` | 已锁定 |
| `DEPRECATED` | 已弃用 |
| `SPEC_DRAFT` | 规格草案 |
| `SPEC_READY` | 规格就绪 |
| `TEXT_SPEC_COMPLETE` | 文本规格完成 |
| `REAL_ARTIFACT_AVAILABLE` | 真实产物可用 |
| `SIMULATED_ONLY` | 仅模拟 |
| `QA_NOT_EXECUTED` | 未执行媒体 QA |
| `ACCEPTED_WITH_DEBT` | 带已知问题继续 |
| `BLOCKED` | 已阻塞 |

默认创作者视图只写“待确认提案”。机器码只保存在 JSON；只有用户明确请求审计视图时，才可在审计表中并列显示机器码。

## 用户可见标题

| 机器标题 | 中文标题 |
|---|---|
| `STAGE RESULT` | 阶段结果 |
| `EVIDENCE & FRESHNESS` | 证据与时效 |
| `CONFIDENCE / UNKNOWN` | 置信度与未知项 |
| `RECOMMENDATION` | 建议方案 |
| `ALTERNATIVES` | 备选方案 |
| `RISK` | 风险 |
| `GATE / STATUS` | 关卡 / 状态 |
| `DECISIONS CREATED OR CHANGED` | 新增或变更的决定 |
| `ARTIFACTS CREATED / REQUIRED` | 已生成或所需产物 |
| `SILVER BLINDSPOT` | 银幕盲点 |
| `SILVER INSIGHT` | 银幕洞察 |
| `NEXT ACTION` | 下一步 |

## Alpha.7 用户复杂度档位

默认 `output_complexity_profile.tier = CREATOR_SIMPLE`：先给结论、推荐、四轴自然中文状态和当前需要创作者处理的 1—4 件事。最终两份创作者 Markdown 不附技术附录，不显示英文状态码、错误码、内部编号、哈希、JSON 键或脚本路径；完整机器状态与验证轨迹只保存在机器 JSON。

`CREATOR_STANDARD` 可在主视图增加紧凑分镜、资产和状态表；`PRO_AUDIT` 才展开完整审计字段。只有用户明确要求时才升级档位并保存原话。机器内部仍保持完整，不因主视图简洁而删账。

长篇 1.5 的机器记录使用导演母版、内部转换计划、供应商中性执行稿和供应商成品四层。普通用户只看到“导演母版”和“可复制提示词工作稿”；内部转换计划留在机器 JSON，只有绑定具体供应商时才另形成供应商成品。逐镜可见提示必须用自然中文保留当前镜头的对白、人物发声与画面文字，并把画面文字标为“不朗读”；内部引号分类、编号和归位记录不得外显。不得把转换计划正文复制进用户包，也不得把两种用户工作稿写成同文。

## MASTER 与供应商执行提示词

供应商提示词优先使用该模型当前最稳定的语言，不强迫所有提示词中文化。

`PROVIDER_NEUTRAL_MASTER` 是供应商中立的权威意图源；`TRANSFORM_PLAN` 是不可提交的内部转换计划；`NEUTRAL_EXECUTION_PROMPT` 是可复制但不具生成资格的供应商中性执行稿；`PROVIDER_COMPILED` 才绑定当前 provider/surface/model/version/region 并可能进入执行。四层都需要中文 `intent_summary_zh`，但只有编译层需要 provider 执行语言和专有语法。

非中文执行提示词必须成对输出：

```markdown
### 中文意图说明
说明画面目标、动作、镜头、连续性、必须保留项和禁止项。

### 模型执行提示词（English / provider language）
保留引用 ID、参数、控制 token 和专有语法。
```

项目状态中的每条非中文 `PROVIDER_COMPILED` prompt 至少记录：

```yaml
id: PP-001
prompt_layer: PROVIDER_COMPILED
master_prompt_id: MP-001
transform_plan_id: TP-001
neutral_execution_prompt_id: NEP-001
provider: string
provider_registry_id: PRV-001
prompt_locale: en-US
prompt_text: string
intent_summary_zh: string
```

提示词翻译不能改变人物身份、资产 ID、镜头关系、数值参数与负向约束。

涉及年龄保护角色时，中文意图说明与编译记录都要保留来源年龄和 `is_minor` 身份。`EXACT / LIFE_STAGE / REFERENCE_BOUND` 只改变供应商可接受的安全表述，年龄事实始终保持；供应商不接受时暂停该路线并转入安全构图或复核。

## 证据与引文

- 来源标题和必要短引文保留原语，随后用中文解释其含义与适用范围。
- 用户原话用于批准证据时逐字保存，不能为了统一语言而改写。
- 代码、日志与错误信息在机器记录或用户主动请求的诊断视图中可保留原语；默认创作者 Markdown 只给中文问题类别和行动建议。
- 发布文案如果需要多语言，先给中文工作底稿，再分别生成目标语言版本，并标注哪一版可发布、哪一版待母语复核。

## 中文质量要求

- 用创作者语言，不用翻译腔堆叠抽象名词。
- 先给结论，再给必要证据与状态。
- 保留专业术语时首次附中文解释，不要求用户阅读裸英文枚举。
- 不逐段中英重复；只有目标市场、供应商执行或审计需要时才双语。
- 问题、选项和推荐必须可直接回答，避免长篇英文流程说明。

## 发送前静默检查

1. 面向用户的标题、问题、选项、状态解释和下一步是否为交互语言？
2. 故事、剧本、分镜、QA 与发布稿是否符合各自语言字段？
3. 非中文 provider prompt 是否附中文意图说明？
4. ID、枚举、Schema key、路径、参数和专有名是否保持原值？
5. 是否出现无必要的双语重复、英文-only 输出或生硬翻译？
