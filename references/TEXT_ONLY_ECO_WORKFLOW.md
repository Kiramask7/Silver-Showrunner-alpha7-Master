# Alpha.7 Master 纯文字省算力工作流

本工作流只处理用户明确要求的纯文字导演测试：忠实编译剧本、文学原作或专业资料，不生成图片、视频、声音，不剪辑，不接 API。当前写入合同是 1.5；更早合同只作为迁移输入读取。

## 1. 普通用户首屏

首次说明最多五行，使用自然简体中文，不显示内部版本、ID、状态码、哈希、JSON 或脚本路径：

```text
不只会生成画面：我们让 AI 先学会当总导演。
这轮只做视听导演文字工作，不生成图片、视频或声音，也不剪辑。
我会忠实处理你的来源，不擅自改变事实、剧情、人物或对白。
你点名就测试指定片段；没有点名时，我会选择能够覆盖不同位置和类型的重点内容。
完成后交付创作包、机器记录和简短总结；遇到影响含义的歧义会保留进度并说明。
```

用户文件先呈现场景名、来源片段、导演处理、逐镜表和供应商中性提示词工作稿（可复制）。MP、TP、NEP、`runtime_identity` 等机器术语只进入机器文件或用户明确要求的技术审计。

## 2. 固定范围与三文件

- `delivery_mode = TEXT_ONLY_ECO_TEST`，文字 Pilot 终点为 `TEXT_PILOT_COMPLETE`；它不代表全文完成、外部编辑通过或媒体生产通过。
- 最终目录只允许三个冻结名称：`长篇文字测试包.md`、`MACHINE_STATE.json`、`RUN_SUMMARY.md`。用户自定义时必须在 prepare 前同时提供安全的 `.md / .json / .md` basename；缺一项即全部使用默认名。
- 提交模式固定为 `IN_PLACE_THREE_CARRIER_V1`。最终名与目录须在验证前冻结；验证后不得改名、移动、复制替换、转码或编辑。需要改变时重新 prepare 到新的空目录。
- 成功后最终目录只能有上述三文件，临时三载体必须清理。不得另写 memory、日志、缓存、胶水脚本、checksum 或第四份交付；不得删除既有结果强行覆盖。目标非空或恢复不安全时按 `E_NO_DELETE_COMMIT_REQUIRES_NEW_PATH` 换新目录。
- 禁止 `python -S`、猴子补丁、跳过 Gate、用自测冒充实际产物验证，或用自定义外壳包住真正机器合同。

## 3. 唯一轻量运行面

正式创作开始时只读取：

```text
SKILL.md
references/TEXT_ONLY_ECO_WORKFLOW.md
```

随后只执行包根目录的统一启动器，让高层 prepare 摄取来源、选窗并生成工作面；不要先读 `scripts/`、`tests/`、`schemas/`、fixtures、gold 或实现源码，也不要直接调用 `python`：

```powershell
运行银幕总控.cmd 准备 "SOURCE.txt" --output-dir "FINAL_OUTPUT_DIR" --run-id RUN001 --selection-mode MACHINE_REPRESENTATIVE_V1 --sample-count 3
```

启动器依次检查用户明确指定的 `SILVER_PYTHON`、Codex 自带环境、WorkBuddy 自带环境、`py / python3 / python`，每项都必须通过真实 Python 3.10+ 版本探针；Windows 应用商店空入口不算可用环境。普通用户无需安装、选择或理解 Python。路径含中文或空格时使用完整引号，不使用 ExecutionPolicy Bypass。

用户明确点名 3—5 个不重叠范围时改用 `USER_TARGETED_EXACT_RANGES_V1`；未点名时只能用 `MACHINE_REPRESENTATIVE_V1`。范围、最终名或目录变化必须重新 prepare，不能由模型手写选择证据或窗口。

prepare 后，正式创作只读取 `OVERLAYS.json.authoring_guide`、`target_windows`、`compiled_unit_overlays`；`source_read_scope_attestation` 必须声明 GUIDE_ONLY 边界和禁止读取项。`authoring_guide.guide_version = alpha7-overlay-guide-1.5`，它是字段形状、枚举、可编辑路径、分类提示、命令与修复动作的单一精确真值；本合同不重复这些对象 shape。若指南缺定义，安全中断并报告，禁止转读源码或测试答案补猜。

## 4. 创作叶与 helper 所有权

- prepare 冻结来源窗口、逐字来源锚、单镜资格、`locked_director_scaffold`、镜头编号与范围、固定转换角色、对白候选、来源主张槽、语义门和 `editable_paths`。模型不得改这些字段、hash、provenance、状态、检查布尔值或验证结果。
- 模型只填写指南列出的 creative leaves：具体场景名、表演、总摄影、声音、引号分类；仅为仍开放的口播候选填写说话者；Sequence 每镜的 purpose、`action_additions`、camera；MP、TP 三个创作数组、供应商中性的 NEP、完整负向句，以及 `quality_overlay.scene_title / findings`。来源主张不可编辑，只能填写预分配 `DIRECTORIAL_CONTROL` 槽的正文。`action_additions` 可为空，不得为填字段发明剧情动作。
- 来源对白只通过指南给出的逐字 slot 引用。标为 `SOURCE_LOCKED_NONLEXICAL` 的人物发声由来源锁定主体，不出现在可编辑说话者映射中；无法唯一确认主体时在准备阶段退回，不能猜测或改成环境声。模型不得改 slot、复制对白正文或自行宣布差异通过；只有分类为真实口播的项目进入对白轨。
- helper/finalizer 从锁定来源与创作叶确定性生成入口、来源动作、出口、连续性、shot plan、逐项来源/提案证明、语义检查、对白与引号的逐镜归位、`execution_beats`、inference、内容自检、Prompt Quality 和派生 hash。未来信息不得提前进入当前窗口，动作主体、工具与肯否关系必须服从来源；无法可靠判定的中文指代交给内容复核。零宽等默认不可见控制字符不参与语义比较，但来源与创作正文保持原样，不借清理改写用户文本。逐镜声音只能来自当前镜头的来源与引号，并保持来源顺序；画面文字和内心文字不进入音轨，整体声音原则只出现一次。普通用户最终只得到一份“逐镜视频提示词（每条可单独复制）”，同时能直接看到剧情拆解与分镜总览。模型不得手填这些归位记录、PASS、证明或机器质量卡。
- 来源事实与导演提案必须分开；不得改写、删减、提前或补造来源事件、人物、对白、因果。Sequence 必须逐镜填写真实、场景特异的 purpose/camera；不得用模板、机械 atom→shot、同文摄影或空 shot plan 假通过。

## 5. 唯一执行顺序

精确命令只取自 `AUTHORING.json.immutable_contract.authoring_workflow`，统一启动器只替换已经失效的宿主解释器位置，不改变其余参数；不得手拼：

1. prepare 后只编辑 creative leaves。
2. 执行 `运行银幕总控.cmd 检查 "<AUTHORING.json>"`；启动器读取 `check_argv`，只检查而不写最终文件。
3. 失败时只按错误路径修改 creative leaves，再执行 `运行银幕总控.cmd 重试 "<AUTHORING.json>"`；不得改锁、目录、窗口或机器字段。
4. 检查通过后才执行 `运行银幕总控.cmd 提交 "<AUTHORING.json>"`。需要重建工作面，或系统提示当前工作面来自旧 helper 时，执行 `运行银幕总控.cmd 重新准备 "<AUTHORING.json>"`。finalizer 同次生成机器证明、自检、质量记录、总结并验证最终名称下的实际三文件。

`validation_result.valid=true` 只能说明结构合同通过；空 findings 不等于内容通过。失败写 `PILOT_REWORK_REQUIRED` 并保留最小恢复动作，不得先提交后修文件。

## 6. 诚实状态与恢复

媒体八项始终为用户排除：`IMAGE / VIDEO / VOICE / MUSIC / SUBTITLE_ALIGNMENT / EDIT / MEDIA_QA / PUBLISH = EXCLUDED_BY_USER`。四个生产真实性轴必须分开：执行未发生、观察不适用、媒体 QA 不适用、Production Validation 为 `NOT_TESTED`；NCS/NRS 无真实媒体时为 `NOT_SCORED`。禁止写“模拟生成”“媒体已验证”或 Generation Readiness。

文字审阅三轴也必须分开：机器结构校验、同作者 `content_self_review`、本轮创作者之外的编辑审阅。前两项通过仍不能冒充第三项；成功 Pilot 的 `resume_entry` 是 `EDITORIAL_REVIEW`，并保留 `INDEPENDENT_EDITORIAL_REVIEW_REQUIRED`。

遇到来源歧义影响含义、P0、上下文不足、helper 锁不一致、目录不安全或连续授权越界时立即安全中断：保留规范临时三载体和检查结果，不登录、不付费、不上传、不调用外部工具、不生成媒体。恢复时先核来源版本/hash、锁和目录，再执行 guide/`authoring_workflow` 给出的 retry、reprepare 或 resume；不得重做已确认范围，也不得继承失效的 PASS。

连续授权只覆盖当前纯文字流程到 `RUN_SUMMARY.md`，不授权新的剧情真值、外部动作或媒体生产。普通总结只写本轮完成项、保留问题、媒体未执行事实和下一步，不泄露内部 ID、错误码、hash 或命令。
