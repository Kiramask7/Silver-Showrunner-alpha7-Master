# Alpha.7 外部执行与回执契约

## 1. 能做就真实执行，不能做就诚实停在边界

外部动作可走四条真实路线：`LOCAL_TOOL / BROWSER / API / MANUAL`。开始前先做能力探测：工具是否存在、当前页面或接口是否可访问、账号与地区权限是否匹配、输入是否齐全、动作是否可恢复、是否涉及费用或对外状态变化。

模型“知道某网站”不等于具备浏览器控制权；能打开页面不等于已登录；能生成 Prompt 不等于已执行；文件名、截图描述或用户口述不等于系统已观察媒体。

## 2. 外部生成标准路径

1. 绑定当前 `provider_registry_id`、模型、版本、地区、入口与任务能力；
2. 从 `PROVIDER_NEUTRAL_MASTER` 建立 `TRANSFORM_PLAN` 与 `NEUTRAL_EXECUTION_PROMPT`，再编译当前 `PROVIDER_COMPILED` Prompt；TP 不可提交，NEP 可复制但不能进入生成 Gate 或执行；
3. 通过 `GENERATION_READINESS_GATE` 的精确 scope；生成任务进入 `READY` 前写入非空 `generation_targets[]`，逐项绑定目标类型、目标 ID、生成角色、媒介和当前 `provider_prompt_ids[]`；任务级 Prompt 集合必须是这些目标 Prompt 的精确展平集合；
4. 执行最小 Pilot，保存输入、设置、输出位置和时间；
5. 创建真实 Artifact 与 `execution_receipt`；
6. 系统可访问媒体后才建立 Observation、NCS/NRS 和媒体 Gate；
7. 通过后按可恢复批次继续，失败则进入最小范围修复。

用户可以指定“用某浏览器、某网站、某模型，先给角色和场景各生成两张参考图；确认后再生成分镜视频”。系统应把它解析成 `ASSET_REFERENCE → SHOT_KEYFRAME/SHOT_START_FRAME → SHOT_MOTION` 的任务图和可恢复批次，逐项执行并保留回执；数量只是用户批准的执行参数，不代表质量或成功概率。图生视频任务必须显式消费已经登记版本/hash 的上游图像 Artifact。`task_scope` 是说明文字，不是执行授权来源；即使它提到原始聚合镜头，真实执行对象也只能来自一致的 `generation_targets + provider_prompt_ids`，不能越过已拆出的安全组件目标。

## 3. 执行回执

每次真实外部动作都写 `execution_receipts`：

- 任务、执行路线、真实/模拟模式、执行器，以及 `execution_domain = PRODUCTION_MEDIA | LOCAL_VALIDATION | LOCAL_TEXT_TOOL`；
- 开始/完成时间、请求范围和供应商记录；
- 输入与输出的精确产物版本；
- 可观察证据与外部定位；
- 结果、阻断原因、授权类别与是否可恢复。

新回执必须显式写 `execution_domain`；缺少该字段的旧 Alpha.7 回执只按 task type 做窄范围兼容推断。`PRODUCTION_MEDIA` 表示生图/视频/音频、渲染或导出等生产动作；`LOCAL_VALIDATION` 表示预检、研究、分析或 QA 工具；`LOCAL_TEXT_TOOL` 表示文字、转写、字幕稿或时间线工具。真实本地验证/文字工具可以诚实写 `REAL + SUCCEEDED`，但不得输出 `MEDIA / PACKAGE`，也不得把项目媒体 `execution_mode`、执行轴、Observation、媒体 QA 或 release 升级为真实生产。

生成任务的状态与回执严格对应：`PLANNED / BLOCKED / READY` 可以尚无回执；`RUNNING / EXECUTED_FAILED / EXECUTED_SUCCEEDED` 只能引用 `PROVIDER_COMPILED`，并分别需要真实 `RUNNING / FAILED / SUCCEEDED` 的 `PRODUCTION_MEDIA` 回执。该回执与任务双向引用，且 route、provider snapshot、compiled Prompt IDs 与 source spec versions 必须一致；失败回执也必须包含结束时间、失败证据和原因，不能用一个失败标签冒充执行。

`SUCCEEDED` 必须有可核对的真实输出或执行证据。生产媒体成功必须产生真实 `MEDIA / PACKAGE` Artifact；研究或只读检查可以只产生 Evidence 或真实 `TEXT_SPEC`。任务与回执必须双向引用。

## 4. 人工边界

遇到 `LOGIN / CAPTCHA / PAYMENT / ACCOUNT_PERMISSION / IRREVERSIBLE_ACTION`：

- 不跳过既定边界，不伪造，不替用户同意；
- 保留页面、步骤、已完成产物和恢复点；
- 把任务标为 `BLOCKED`，说明用户只需完成哪一个动作；
- 获得明确授权后，从检查点恢复，而不是重跑全项目。

当前版本没有自动发布任务类型。对外上传、发布、发消息和购买额度不能被普通“继续”授权。

## 5. 模拟与人工回传

只有用户明确要求工作流模拟时，才创建 `SIMULATED_ONLY` 回执。模拟回执不得引用真实输出 Artifact、不得触发 Observation 或 QA、不得解锁批量生产或发布资格。

用户在外部手工生成后：先登记为 `USER_REPORTED`。只有文件、页面或数据实际可访问，并完成版本、来源和内容核对后，才能升级为系统直接观察。

供应商拒绝时，任务与真实失败回执必须保存所用 provider/surface/model/version/region/snapshot、当前 `PROVIDER_COMPILED` ID、source spec version、拒绝范围、时间、外部定位与失败证据。拒绝不会自动授权修改人物年龄或故事事实；先使用内容规范重编译、局部/远景/背面/剪影、分层合成或另一已核验供应商，确需改变创意决定时再向用户请求授权。

## 6. 恢复与重试

重试必须诊断驱动：参数微调、替换参考、局部重生、换执行路线或换供应商都要说明影响范围。不要机械重复同一请求，也不要把“换更强模型”当唯一方案。长任务按检查点恢复；已经通过的无关任务不重做。
