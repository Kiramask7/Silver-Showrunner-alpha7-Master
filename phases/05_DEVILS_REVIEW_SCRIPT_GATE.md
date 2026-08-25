# Stage 4 — 魔鬼审稿与剧本关卡

剧本版本、scoped completion、批准与验证关系遵守 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`。

面向中文用户时，用自然简体中文呈现问题、证据、严重度、修改建议和关卡结论。审稿建议、产物状态、决定状态与关卡结果必须分别记账。

主动攻击以下问题：

- 伪悬念；
- 为反转而反转；
- 被动主角；
- 依赖解释而非戏剧行动；
- 单集结构机械重复；
- 临时作弊的世界规则；
- 只有铺垫没有回收；
- 调性或受众错位；
- 与现有 IP 的具体表达过度相似；
- 内容、适用规则或平台风险；
- AI 生产陷阱；
- Viral Genome 作出的承诺没有兑现。
- 来源事件被摘要代替、完整过程被静默删减；
- 对白缺字、换人、调序、被旁白化或被改成“意思相同”的短句；
- 场景有台词但没有听者反应、动作承接和可见出口；
- 为了适配短时长而让角色不自然高速说话，或把未说完的对白丢到段尾清单；
- 剧本、分镜和 Prompt 使用了不同版本的事件或对白。

## 剧本关卡

剧本本身登记为 `artifact_class = TEXT_SPEC`。常见推进关系是：

- 初稿或修订稿尚未完整：`artifact.status = SPEC_DRAFT`；
- 同一精确版本的文字规格完整：产物保持可引用的当前版本，并创建 `scope_type = STORY_ARTIFACT` 的 `spec_completion_record`；
- 用户明确批准被点名的剧本决定：相应 `decision.status = USER_APPROVED`，并保存 `approval_event`；
- 同一精确版本有适用复核证据：产物或决定才可使用 `VALIDATED`；
- 用户明确要求锁定、范围清楚且无开放阻断项：相关决定与产物才可使用 `LOCKED`。

不要写入 `SCRIPT_DRAFT`、`USER_REVIEWED`、`REVISED` 或 `SCRIPT_LOCKED` 之类专用持久状态；版本与审阅事件由产物版本、scoped completion、复核证据和批准事件表达。剧本文字完整不声称角色资产、Provider 编译 Prompt、真实媒体或生成资格存在。

若当前剧本将进入分镜或 Prompt，至少对首个完整样场和所有发生对白/删减/顺序修改的范围运行 CONTINUUM `SCRIPT` 本地预检。来源覆盖、逐字对白、说话人、发声种类或顺序任一失败，都属于阻断性返工；不能用文风分、人工“看起来差不多”或用户说“继续”覆盖。预检只证明保真结构，不证明剧情精彩或编辑审阅通过。

审稿阶段可以另存用户可见的 `recommendation_code = REWORK` 或 `TEST_FIRST`。它们只是下一步建议，不是 Gate `outcome`，也不是 artifact、decision 或 workflow 状态。`VALIDATED` 必须有针对同一精确版本的复核证据。锁定必须有明确范围，且不存在尚未解决的阻断性必修问题。只要仍有阻断问题，就提出返工建议，或在满足规则时由用户明确接受为 `ACCEPTED_WITH_DEBT`；不得因为用户说“下一步”就锁定剧本。

如果用户决定带着未解决问题继续，记录 `ACCEPTED_WITH_DEBT`，明确债务、风险、下游影响和重新检查的触发条件。继续推进不等于问题已经修复或验证。
