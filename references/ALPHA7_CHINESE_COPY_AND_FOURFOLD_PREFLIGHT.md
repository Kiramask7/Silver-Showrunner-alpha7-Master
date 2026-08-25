# Alpha.7 中文传播与四重预检合同

## 目录

1. 目标与边界
2. 中文优先合同
3. 三层检查顺序
4. 四个模块
5. 阻断与状态
6. 输入合同
7. 输出合同
8. 运行方法
9. 与现有发布关卡衔接
10. 审计取舍

## 1. 目标与边界

本模块把中文文案、自然表达、内容规范、素材许可来源和传播设计接到同一条可复算的预检链。它服务于剧情、科普、教育、文化传播、纪录片、品牌内容和比赛展示，不把所有项目强制套进短剧模板。

它只回答四类问题：

- 文案是否像具体创作者在当前场景里表达，同时有没有改坏事实；
- 当前材料是否存在需要阻断或专业复核的内容规范问题；
- 实际使用资产是否有可追溯、覆盖本次用途的素材许可链；
- 本阶段的受众、承诺、钩子、兑现和包装是否已经形成。

它不做以下事情：

- 不判断文本是否“由 AI 写成”，不输出 AI 生成概率；
- 不预测播放量、点击率、完播率或爆款概率；
- 不发明黄金时长、最佳发布时间或万能成功门槛；
- 不把关键词命中直接等同于违法、违规或平台必然拒绝；
- 不验证授权文件真伪，不替代专业人员、平台或许可方判断；
- 不把预检结果直接写成 `RELEASE_READY`；
- 不用自然表达分或传播准备度抵消内容规范、素材许可阻断。

## 2. 中文优先合同

面向目标用户和目标赛事时，默认按以下规则输出：

- 对话、提问、策划、剧本、分镜说明、风险、修复建议、封面文案、标题、简介和报告使用自然简体中文；
- 不为显得专业而逐行中英双写；
- 机器字段、状态码、JSON/YAML 键、文件名和代码在机器记录中保持原值；默认创作者 Markdown 不展示这些内容，模型正式名称可按原名展示；
- 供应商需要英文提示词时，同时给中文创作意图，不把整个工作流切成英文；
- 原始英文证据可保留原文，判断和适用性说明使用中文；
- 对外文案先说受众能得到什么，再说明能力和方法；不使用虚假数字、虚假背书或空洞“行业领先”。

中文自然化遵循“先保护、再改写”：

1. 先标记数字、日期、范围、单位、版本号、引用、专名、主体归属、命令、路径、字段、指标和错误信息；
2. 再删除开场套话、空总结、姿态层、商业黑话和表演性技术腔；
3. 不机械轮换同义词，不为“更像人”新增原文没有的事实；
4. 最后分别做保真回读和残留模板腔回读。

## 3. 三层检查顺序

四个模块都参与三层检查，但强度不同。

| 阶段 | 运行目的 | 自然表达 | 内容规范 | 素材许可来源 | 传播准备度 |
|---|---|---|---|---|---|
| `EARLY` 前置轻检 | 防止方向性返工 | 只定语域与保护项，不重写全文 | 识别题材、主张和目标地区硬风险 | 建立资产来源字段和授权计划 | 明确受众、承诺、钩子、兑现和证据计划 |
| `IN_PROCESS` 过程复检 | 在剧本、资产和包装形成时纠偏 | 检查旁白、对白、字幕和推广草稿 | 检查具体场景、台词、主张和标识计划 | 每个新资产即时入账，检查范围、期限与凭证 | 检查注意力结构、证据支持、平台适配和标题草案 |
| `FINAL` 成品总检 | 对准确版本给发布前结论 | 润色最终标题、简介、字幕、旁白并复核保真 | 复核真实成片、最终文案、AI 标识和当前规则证据 | 复核最终资产清单的完整素材许可链 | 结合成片、标题、封面和格式给结构覆盖分 |

不得只在最后运行内容规范和素材许可检查。最后发现许可范围不覆盖、人物未授权或主张无来源，可能导致整段内容或资产重做。

## 4. 四个模块

### 4.1 自然表达

输出：

- `expression_score: 0..100`；
- 命中的模板腔问题族；
- 每份文本的受保护片段清单；
- 原文与润色稿之间的受保护片段漂移。

`expression_score` 是透明的风格检查信号，不是 AI 检测概率。低分只能触发修订建议，不单独阻断发布。

当输入文本同时提供 `original_text` 时，脚本比较数字、日期、URL、引号内容和代码片段。若该文本声明 `must_preserve: true`，最终阶段的保护项漂移会升级为事实保真阻断，并同时进入内容规范模块。

### 4.2 内容规范

脚本能做的确定性检查包括：

- 绝对化、保证性、零风险表达；
- “研究表明”“数据显示”等无来源权威引述；
- 爆款概率、黄金时长、最佳发布时间等伪精确传播结论；
- 需要进一步语义复核的内容信号；
- 最终阶段的 AI 标识计划、真实媒体、媒体观察、当前平台规则证据；
- 标题、封面、字幕和格式是否绑定同一最终版本；
- 事实/已验证主张是否有来源回链。

关键词只负责定位，不负责裁决。涉及医疗、金融、年龄保护、个人信息、危险行为或适用范围要求时，必须重新核对当前官方来源，并在需要时交由专业人员复核。

### 4.3 素材许可与来源

资产应在进入项目时登记，而不是最后补账。最少字段包括：

- `asset_id`、`kind`、`source`、`license_status`；
- 授权/许可证/订单/下载/生成任务的 `evidence_ids`；
- 商业用途、平台、地区和期限范围；
- 署名要求与执行位置；
- 人物肖像、声音、表演、数字人或克隆使用同意；
- AI 生成平台在生成时适用的账号套餐、条款版本和任务凭证；
- 翻唱、改编、采样音乐的词曲权与录音制作者权。

`CLEAR`、`LICENSED` 或 `PUBLIC_DOMAIN_VERIFIED` 如果没有凭证回链，最终阶段仍然阻断。脚本只能检查登记完整性和范围一致性，不能鉴定凭证真伪。

### 4.4 传播准备度

传播准备度使用本阶段必需字段的覆盖率，公开公式为：

```text
readiness_score = 已形成的必需维度数 / 本阶段必需维度总数 × 100
```

维度包括：受众、核心承诺、开场钩子、兑现、继续观看理由、证据支持、平台适配、标题一致性、封面一致性和格式适配。早期只要求方向字段，中期增加包装与平台字段，最终要求十项齐备。

该分数只表达结构覆盖，不表达内容质量，更不表达实际传播结果。真实效果只能在实际发布后用真实数据学习；本版本不自动发布。

## 写回项目状态

脚本首先生成单独的人读报告。只有输入同时提供 `state_binding`，并绑定项目内的 `preflight_id`、精确 `artifact_id + version`、FINAL SHA-256、证据、阻断 issue 和 checker，结果才会包含 `state_record_status = READY` 与可写入 `fourfold_preflight_records` 的 `state_record`。缺少任何硬关联时仍保留报告，但 `state_record = null`；不得手工把报告标题或分数改写成状态通过。

FINAL PASS 额外要求内容规范与素材许可分别有项目 evidence IDs。阻断结论必须回链项目 `blocking_issue_ids`；脚本不会用内部 finding ID 伪造 issue。写回后仍须运行 `scripts/validate_state.py`，由项目账本验证产物、哈希、证据和发布准备关卡是否属于同一对象与版本。

## 5. 阻断与状态

四个模块必须分别出结论：

- 自然表达：`PASS | REVIEW`；
- 内容规范：`PASS | REVIEW | BLOCK`；
- 素材许可来源：`CLEAR | REVIEW | BLOCK`；
- 传播准备度：`READY | REVIEW`。

总状态按固定优先级生成：

```text
内容规范 BLOCK + 素材许可 BLOCK -> BLOCKED_BY_COMPLIANCE_AND_RIGHTS
内容规范 BLOCK                  -> BLOCKED_BY_COMPLIANCE
素材许可 BLOCK                  -> BLOCKED_BY_RIGHTS
FINAL 有待复核项         -> REVIEW_REQUIRED
FINAL 全部满足           -> READY_FOR_RELEASE_READINESS_GATE
EARLY / IN_PROCESS       -> CONTINUE_WITH_NOTES
```

`READY_FOR_RELEASE_READINESS_GATE` 只表示可以进入现有 `RELEASE_READINESS_GATE`。它不是 `RELEASE_READY`，也不是发布证据。现有 Gate 仍须精确绑定真实最终媒体、版本、发布包、规则证据和必要批准。

## 6. 输入合同

最小示例：

```json
{
  "project": {
    "project_id": "P-001",
    "stage": "FINAL",
    "target_platforms": ["比赛提交页"],
    "target_regions": ["目标地区"],
    "aigc_used": true,
    "aigc_label_plan": "READY",
    "real_final_media": true,
    "media_observed": true,
    "current_rule_evidence_ids": ["EV-RULE-001"],
    "checked_at": "2026-08-14",
    "commercial_use": false
  },
  "texts": [
    {
      "text_id": "TXT-001",
      "kind": "description",
      "original_text": "岩芯形成于约 2 亿年前。",
      "text": "这段岩芯形成于约 2 亿年前。",
      "must_preserve": true,
      "source_ids": ["EV-SCI-001"]
    }
  ],
  "claims": [
    {
      "claim_id": "CL-001",
      "text": "岩芯形成于约 2 亿年前。",
      "classification": "VERIFIED",
      "source_ids": ["EV-SCI-001"]
    }
  ],
  "assets": [
    {
      "asset_id": "A-001",
      "kind": "IMAGE",
      "source": "用户原创",
      "license_status": "USER_CREATED",
      "used_in_final": true
    }
  ],
  "distribution": {
    "title_matches_content": true,
    "cover_matches_content": true,
    "subtitle_matches_final": true,
    "format_checked": true
  },
  "attention": {
    "audience_defined": true,
    "core_promise": "看懂岩芯里的时间证据",
    "opening_hook": "一块石头为什么记录了两种海洋？",
    "payoff": "展示证据链",
    "continuation_reason": "逐层揭示年代",
    "proof_points": ["EV-SCI-001"],
    "platform_fit": true,
    "title_content_alignment": true,
    "cover_content_alignment": true,
    "format_fit": true
  }
}
```

机器字段保留英文，字段内的解释、问题和修复建议使用中文。

最终三文件交付时，机器 JSON 继续保存完整字段与四个模块记录；两份创作者 Markdown 只显示自然中文结果，不附技术附录，不显示英文状态码、错误码、内部编号、哈希、JSON 键或脚本路径。用户原文与模型正式名称不因这一呈现规则而改写。

## 7. 输出合同

JSON 结果包含：

- `engine`、`engine_version`、`input_sha256`；
- `stage`、`overall_status`、`evaluation_date` 与日期来源；
- 四个分离模块的状态、发现项与处理建议；
- 自然表达信号分、传播结构覆盖分；
- 内容规范/素材许可阻断数量；
- 固定的真实性与状态边界说明。

每条发现项包含：

```yaml
finding_id:
module:
severity: P0 | P1 | P2
blocker: true | false
location:
message_zh:
matched:
required_action_zh:
evidence_ids: []
```

## 8. 运行方法

```powershell
python scripts/fourfold_preflight.py --input project_preflight.json `
  --out fourfold_preflight.json `
  --report fourfold_preflight.md
```

从标准输入运行：

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Get-Content -Raw project_preflight.json | python scripts/fourfold_preflight.py
```

Windows PowerShell 5 的原生程序管道可能默认损坏中文；因此优先使用 `--input`。必须走管道时先设置上面的 UTF-8 输出编码。

运行内置回归：

```powershell
python scripts/fourfold_preflight.py --self-test
```

脚本只使用 Python 标准库，不联网、不上传项目材料。

素材许可期限检查优先使用 `project.release_date`，其次使用 `project.checked_at`；两者都没有时才使用运行当天，并在结果中标为 `evaluation_date_source = RUNTIME_DATE`。需要可复算的归档结果时必须显式提供日期。

## 9. 与现有发布关卡衔接

推荐顺序：

```text
EARLY 四重轻检
-> 策划、研究、故事/非虚构结构
-> IN_PROCESS 四重复检
-> 生成、观察、QA、修复、剪辑
-> 最终成片 + 标题 + 封面 + 字幕 + 简介
-> FINAL 四重总检
-> 现有 RELEASE_READINESS_GATE
-> 停止；本版本不自动发布
```

不得用以下材料通过最终检查：

- `SIMULATED_EXTERNAL_STEP`；
- 文字 QA；
- 计划生成的资产；
- 未观察的媒体；
- 旧成片版本的素材许可或内容规范记录；
- 传播准备度高分。

## 10. 审计取舍

本模块在实现前审阅了本地 Aladin 内容规范、封面、音乐许可模块和 Tomato Novelist，以及两个 MIT 第三方仓库。具体来源、版本、许可和未吸收内容见 `THIRD_PARTY_ATTRIBUTIONS.md`。

保留的做法：

- 多来源材料归一、命中位置和整改回灌；
- 素材许可台账、用途/平台/地区/期限范围；
- 标题—封面—内容一致性；
- 受众、利益、疑虑、承诺和兑现；
- 中文自然化前保护数字、引用、专名、主体和技术片段。

拒绝吸收的做法：

- 未给来源的“点击决策 0.5 秒”“封面承担 80% 点击”“点击率差 2–5 倍”；
- 固定平台复核权重冒充当前官方规则；
- 英文 power-word、固定词长和数字奖励组成的通用标题分；
- “黄金开篇”“最佳字数”“爆款基因”等未经当前证据验证的普遍门槛；
- 用 seed 或固定提示词承诺角色/封面一致性；
- 把本地词表零命中写成平台必过。
