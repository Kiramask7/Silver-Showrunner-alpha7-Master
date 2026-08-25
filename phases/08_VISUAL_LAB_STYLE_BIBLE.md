# Stage 7 — 视觉实验室与风格设定集

视觉决定、真实媒体、观察与 Gate 分层遵守 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`。

视觉方向、材质、光线、镜头和参考边界的解释遵守 `creative_artifact_language`。风格名、模型名和必要专业词保留正式名称，并用中文说明其实际作用。

确有选择价值时，最多提出五个彼此真正不同、同时符合故事的视觉方向。

每个方向至少包含：

- 视觉假设及其适配理由；
- 人物和环境的造型语言；
- 材质、光线、镜头和色彩逻辑；
- 优势与缺点；
- AI 稳定性和长线一致性风险；
- 生产成本与人工复核负担；
- 基于 Provider Registry 的当前 provider 适配性；
- 测试 Prompt 或明确的测试方法；
- 禁止项和 IP 边界。

## 硬关卡

只要项目的生产结果依赖视觉执行，纯文字风格提案不能让风格决定或风格设定集产物进入 `LOCKED`。

状态必须按对象拆开：

- 风格方向由系统提出：风格 `decision.status = PROPOSED`，文字风格设定集 `artifact.status = SPEC_DRAFT` 或 `SPEC_READY`；
- 用户明确选择被点名的方向：风格 `decision.status = USER_APPROVED`，并保存 `approval_event`，不另造 `USER_SELECTED`；
- 真实测试媒体存在：媒体产物 `artifact.status = REAL_ARTIFACT_AVAILABLE`；它不等于已观察；
- 实际检查该媒体后：创建 `observation`，相应 `workflow_status.observation_status = OBSERVED`；
- 真实测试证据满足明确要求：相应 Gate 才能 `evaluation_status = EXECUTED`、`outcome = PASSED`，风格决定或产物才可使用 `VALIDATED`；
- 用户明确要求锁定、范围清楚且无开放阻断项：相关决定与产物才可使用 `LOCKED`。

不要创建 `STYLE_LOCKED`、`USER_SELECTED` 或 `TEST_MEDIA_AVAILABLE` 持久枚举。用户选择一个方向只建立批准，不等于真实媒体已经证明该方向稳定可用。
