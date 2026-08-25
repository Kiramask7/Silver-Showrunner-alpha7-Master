# Alpha.7 Master 高密度 Prompt 质量核心

本文件是精细分镜到供应商成品 Prompt 的唯一质量核心，只在 Stage 9/10、Prompt 审阅或修复时加载。AI 漫剧/短剧为默认核心；真人、3D、推广、科普、文化与非虚构项目复用同一合同。不复制其他 Skill；既有决定、来源、未知/因果、年龄保护、素材许可与真实状态边界优先。

剧本、对白、分镜和 Prompt 的跨层全量交接同时遵守 `ALPHA7_CONTINUUM_CREATIVE_FIDELITY_ENGINE.md`。本文件定义导演与 Prompt 质量；CONTINUUM 合同定义上游内容不得在交接中丢失。

## 目录

1. 产品与低算力原则
2. 唯一 `prompt_quality_records[]`
3. 静态图像与 4—30 秒视频密度
4. Prompt Soul 与导演节拍
5. 资产、连续性与对白
6. 四层 Prompt 的不同职责
7. 最终可复制 Prompt 的结构槽位
8. Provider 适配保真与有序压缩
9. Prompt Quality 检查（Generation Readiness requirement）
10. 用户可见交付与真实性边界

## 1. 产品与低算力原则

最终 `PROVIDER_COMPILED` Prompt 是本阶段的用户产品。状态、Trace、Gate、哈希和质量记录用于保护它，不能替代它，也不能把算力耗尽后只留下剧情摘要、标题清单或一句“动。”。

低算力运行遵守：

- 每个当前生成目标、生成角色和 `source_spec_version` 只建立一条 `prompt_quality_record`；四层 Prompt 只引用它，不复制同一质量账本；
- MP 保存详细权威导演合同，TP 保存简洁转换计划，NEP 保存完整可复制的中性执行稿，PP 保存绑定当前供应商的成品；
- 完整资产 Bible、连续性账本和来源 Trace 留在工程层；当前镜头只抽取生成必需胶囊；
- 先完整编译 3—5 个真正高风险或代表性的 Prompt Pilot，质量通过后再批量；
- 普通用户默认只看到最终可复制 Prompt、极短中文意图和必要阻断项，不看到内部表、枚举或分数；
- “可直接复制”必须按字面成立：不得留下对白指针、待填空位、内部执行字段或要求用户再到别处拼接的内容。每个逐镜 Prompt 内联该镜唯一一次逐字对白，并包含单独生成所需的人物、场景、道具、表演、摄影、声音与结束画面。
- Prompt 编译前执行表演可行性检查。嘴部占用与长对白、手部占用与新动作、承重/接触状态与后续位移、对白朗读时间与镜头时长互相冲突时，必须先用不改变剧情的可见道具转移、调度、来源已允许的声画桥或动作先后解决；不得以“保持可信”、隐藏嘴部、避开口型或换到幻想画面掩盖现实身体仍无法发声的矛盾。发声身体必须唯一；幻想形象开口、声音却指定来自嘴部仍被占用的现实身体时直接退回。若改为幻想发声、传音、旁白或内心声音会改变来源含义，必须登记导演提案并先取得用户确认。
- 字符数、时间线占比和段落数量只作诊断，不作为跨供应商通用硬门。质量硬门检查语义完整、逐镜可执行与适配保真。
- 默认 `compression_authority = NONE`，最终 PP 使用 `FULL_FIDELITY`。不能为了省算力、追求短 Prompt 或迎合未知入口而删减；确有已核验上限时分段并保存 handoff，用户要求紧凑版时另建变体，不覆盖完整版本。

## 2. 唯一 `prompt_quality_records[]`

机器层在项目顶层维护：

```yaml
prompt_quality_records:
  - id: PQ-001
    target_type: SHOT
    target_id: SH-001
    generation_role: SHOT_MOTION
    generation_medium: VIDEO
    source_spec_version: v1
    master_prompt_id: MP-001
    transform_plan_id: TP-001
    neutral_execution_prompt_id: NEP-001
    provider_prompt_ids: [PP-001]
    prompt_soul_version: ALPHA7-PQS-2
    quality_evaluation_scope: PROVIDER_COMPILED
    prompt_soul_artifact_ids: [ART-STORY-001, ART-STYLE-001]
    prompt_soul_sha256: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
    longform_source_bindings: []
    reference_delta: null
    lifecycle_status: CURRENT
    prompt_quality_profile: MANGA_CORE
    sequence_mode: EDITED_SEQUENCE
    natural_duration_seconds: 12
    density:
      band: D08_12
      planned_beat_count: 4
      hero_beat_ids: [BT-002]
      short_insert_reason: null
      exception: null
    active_asset_capsule: []
    continuity_capsule: []
    director_beats: []
    semantic_atoms: []
    dialogue_fit:
      status: NOT_APPLICABLE
      dialogue_ids: []
      fragments: []
    adapter_integrity:
      - provider_prompt_id: PP-001
        adapter_mode: SYNTAX_AND_REFERENCE_MAPPING
        compression_authority: NONE
        status: NOT_RUN
        adapter_operations: []
        preserved_dimensions: []
        loss_findings: []
        segment_handoff_ids: []
    two_pass_reviews: []
    quality_status:
      status: NOT_RUN
      fail_codes: []
      findings: []
      diagnostics: {}
```

一条记录只绑定一个 `target_type + target_id + source_spec_version + generation_role`，可为该目标/角色绑定多个 provider 编译出的 `provider_prompt_ids[]`；每条 PP 在 `adapter_integrity[]` 中必须恰有一条同 ID 记录。`ASSET` 目标绑定真实资产 ID，不需要先造分镜；`SHOT` 目标绑定真实叙事镜头。同一镜头可以分别拥有关键帧/首帧/尾帧 IMAGE 与运动 VIDEO 记录，但不能让静态组件重复计入 canonical editorial duration。当前活跃状态只保留唯一 `CURRENT` 完整记录；旧版本压缩为 tombstone 或迁入带版本/哈希的审计 Artifact，不能让完整旧 beats/atoms/adapters 常驻膨胀。MP、TP、NEP 在对应层尚未形成时允许为 `null`，`provider_prompt_ids` 可暂为空；某个 PP 进入 Generation Readiness 前，四层 ID 和该 PP 的 adapter record 必须解析到相同目标、角色、媒介和版本。

当前 PQ 只使用目标四元组，不保存第二个 `shot_id`。MP/TP/NEP/PP 中为旧导入保留的兼容 `shot_id` 也不能替代 target 四元组：`target_type = SHOT` 时必须等于 `target_id`，`target_type = ASSET` 时必须为 `null`。

`prompt_soul_artifact_ids[]` 引用当前故事/信息承诺、角色与视觉/声音方向等已经登记且带版本与内容哈希的 `TEXT_SPEC` Artifact；允许的受控类型包括 `prompt_soul / global_truth / script / screenplay / story_bible / character_bible / creative_bible / world_bible / style_bible / visual_bible / sound_bible / director_bible / production_text_spec`，状态必须为 `SPEC_READY / TEXT_SPEC_COMPLETE / USER_APPROVED / VALIDATED / LOCKED` 之一。字幕草案、修复日志、执行中间物或仅名称含 brief/story 的任意文件不能冒充 Soul。`prompt_soul_sha256` 由这些 artifact 的 ID、版本和 `content_locator.sha256` 确定性计算。上例的 64 位值只展示字段形状，不是可复用证据；实际项目必须重新计算。这里不复制全文，但防止只带一个通用版本号、丢掉本项目真正的情绪核心、主题承诺与审美灵魂。

### 2.1 顶层枚举

- `target_type`：`ASSET | SHOT`
- `generation_role`：`ASSET_REFERENCE | ASSET_MOTION_REFERENCE | SHOT_KEYFRAME | SHOT_START_FRAME | SHOT_END_FRAME | SHOT_MOTION | SHOT_COMPOSITE_LAYER | CUSTOM`
- `prompt_quality_profile`：`MANGA_CORE | CINEMATIC_GENERAL | NONFICTION_VISUAL | BRAND_PROMO | BRAND_NONFICTION`
- `generation_medium`：`IMAGE | VIDEO`
- `sequence_mode`：`STATIC_IMAGE | EDITED_SEQUENCE | CONTINUOUS_TAKE | HYBRID`
- `density.band`：`STATIC_IMAGE | SHORT_INSERT | D04_07 | D08_12 | D13_18 | D19_24 | D25_30 | MERGE_REQUIRED | SPLIT_REQUIRED`
- `lifecycle_status`：`CURRENT | STALE | DEPRECATED`
- `quality_status.status`：`PASS | FAIL | NOT_RUN`

`ASSET_REFERENCE / SHOT_KEYFRAME / SHOT_START_FRAME / SHOT_END_FRAME / SHOT_COMPOSITE_LAYER` 只用于 `IMAGE`，`ASSET_MOTION_REFERENCE / SHOT_MOTION` 只用于 `VIDEO`；`CUSTOM` 必须显式声明媒介，并且同一目标、版本同时需要图像与视频时应拆成明确角色，不得用一个 CUSTOM 键混写两种媒介。角色/场景资产或静态组件不参与成片逐镜时长求和。

引用编辑、参考派生、有输入参考的 `CUSTOM` 或 `SHOT_COMPOSITE_LAYER` 还必须建立 `reference_delta`，并由每个 PP 的 `REFERENCE_DELTA_MAPPING` adapter operation 回链。`source_reference_ids[]` 只能引用已登记参考；可用源元素从这些参考的 `controls` 与对应资产 `locked_features / variable_features` 解析。`preserve_element_ids[]`、`change_element_ids[]`、`add_element_ids[]` 三组互斥，`output_element_ids[]` 必须精确等于三组并集；`preserve/change` 必须已经存在于源输入。若 `allow_new_elements = false`，则 `add_element_ids[]` 必须为空，输出不得要求源图未声明的物件、人物、文字或拓扑。一项内容不能一边“保持不变”一边“改变”，也不能一边禁止新增一边要求新增。普通从零生成且不依赖参考的目标使用 `reference_delta: null`。

任何 `reference_delta != null` 的目标都属于强制两遍审阅范围，不受“普通目标每批只抽一个”的省算力规则例外。每个 PP 的审阅记录必须保存当前 `reference_delta_sha256`，并把 `reference_delta_check` 判为 `PASS`；审阅者要对照实际 PP 逐项核查保持、改变、新增与最终输出，而不是只检查账本集合。delta、MASTER、PP 或 Soul 任一内容变化，旧审阅立即失效。没有 delta 时这两个字段分别为 `null / NOT_APPLICABLE`。

`MANGA_CORE` 优先保证人物身份、轮廓与服装一致，表情和姿势可读，动作因果清楚，画面节拍适合 AI 漫剧/动态漫生成，且对白、字幕和声音责任明确。它不强制 2D、3D、横屏、竖屏或任何固定画风。

`NONFICTION_VISUAL` 用于科研、科普、教育、文化、文博、纪录等事实型可视化：事实主张、示意图边界、原件/照片职责和受保护未知项必须形成可解析来源的 MUST atom。`BRAND_PROMO` 为纯品牌/产品推广建立产品功能、比较、性能和传播主张边界。文化联名、科研单位品牌片等同时含事实型与品牌路线的项目使用 `BRAND_NONFICTION`，同时满足两组边界；不能改用 `CINEMATIC_GENERAL`、只选其中一个 profile 或把组合项目降成 `HYBRID` 文案来回避要求。

### 2.2 `semantic_atoms[]`

`semantic_atoms` 只记录适配前后必须保真的关键语义，不复制整份 Prompt：

```yaml
- atom_id: PSA-001
  dimension: ACTION_ENDPOINT
  priority: MUST
  canonical_claim: 角色拉开抽屉并停在完全打开状态
  source_or_state_refs: [REQ-001]
  master_anchor: 完全打开
  compiled_anchors:
    - provider_prompt_id: PP-001
      output_anchor: fully open
```

- `dimension`：`DURATION | EVENT_ORDER | IDENTITY | COUNT | ASSET_STATE | REFERENCE_RESPONSIBILITY | SPACE | ACTION_ENDPOINT | PERFORMANCE | VERBATIM_DIALOGUE | CONTACT_PHYSICS | MATERIAL_LIGHT_ENVIRONMENT | CAMERA | SOUND | CONTINUITY | PROTECTED_BOUNDARY`
- `priority`：`MUST | SHOULD | MAY`

只为当前目标真正适用的关键语义建 atom。每个适用基础维度至少有一个 MUST atom，不能把全部关键事实降成 MAY 回避保真。`source_or_state_refs` 必须解析到真实资产、镜头状态、决定、来源或受保护边界；裸写 `SRC####` 不算已解析。长篇 source atom 通过 `longform_source_bindings[]` 回链已登记的 `longform_source_atom_registry / longform_prompt_source_trace` 文字产物、版本与哈希，并且 atom 必须真实存在于该 registry。`NONFICTION_VISUAL / BRAND_NONFICTION` 的事实与受保护边界还必须回链 `project_route.primary_source_artifact_ids` 或相应的已核验证据，不能只自引分镜。各层 `prompt_sections[].atom_ids` 把 atom 映射到该层正文 span；`compiled_anchors[]` 与 `provider_prompt_ids[]` 逐项对应，MUST 的 `output_anchor` 必须真实出现在该 atom 对应 PP 的非 `NEGATIVE` 正向 section。翻译、改写或供应商语法转换不能跳过该检查。每个 provider 的缺失或改变写入对应 `adapter_integrity[].loss_findings`。`MUST` 缺失或改变必然阻断；`SHOULD/MAY` 只在有明确供应商限制或用户授权时按有序压缩处理。

## 3. 静态图像与 4—30 秒视频密度

### 3.1 静态图像

角色标准图、场景图、道具图、关键帧和首尾帧使用 `generation_medium = IMAGE`、`sequence_mode = STATIC_IMAGE`、`natural_duration_seconds = null`、`density.band = STATIC_IMAGE`，并恰有一个静态导演节拍。该节拍的 `time_range = null`，描述要被定格的可见状态、构图、主体姿态/表情、空间关系、材质光线、参考职责和禁止项；不伪造入口到出口的时间变化。

静态图仍须覆盖适用的目标、参考职责、主体身份/数量、构图、空间、材质光环境、事实/安全边界和负向约束。只有背景纹理或纯图形任务时，可以把人物表演、对白、动作终态等维度标为不适用，但必须保留理由。

角色定妆、多视图标准图、场景、道具和风格参考图使用 `target_type = ASSET / generation_role = ASSET_REFERENCE`，直接绑定真实资产 ID；不要求先存在 `shot_id`。真正包含旋转、走动或表演的资产参考视频使用 `ASSET_MOTION_REFERENCE / VIDEO`。镜头关键帧、首帧、尾帧或合成图层使用 `target_type = SHOT` 和相应 `SHOT_*` role。它们都是生成组件，但不把静态组件时长重复计入成片 canonical duration。

### 3.2 视频

密度是导演节拍锚点，不是强制硬切数量：

| 当前单次生成自然时长 | 默认正式镜头/连续阶段 |
|---:|---:|
| 4—7 秒 | 2—3 |
| 8—12 秒 | 3—5 |
| 13—18 秒 | 4—6 |
| 19—24 秒 | 6—8 |
| 25—30 秒 | 8—10 |

- `EDITED_SEQUENCE` 按正式切镜计数；`CONTINUOUS_TAKE` 按可见动作、空间、摄影、表演或声音状态发生变化的连续阶段计数；`HYBRID` 同时允许两者。
- 克制微表演、单主体静态展示可取下沿；多人互动、复杂动作、空间揭示、机械变化或 VFX 可取上沿。
- 一镜到底不能成为降低导演信息的理由；每个阶段必须产生新的可见状态或观看任务。
- 少于 4 秒的孤立节拍优先与相邻内容合并；超过 30 秒按完整对白、动作落点、反应落点或场景边界拆分。
- 叙事上必须单独存在的短插入镜可使用 `SHORT_INSERT`：一个可见状态变化清楚的节拍，并保存具体 `short_insert_reason`。它不需要额外用户批准，也不能被用来把本应完整呈现的动作切成碎片。
- `generation_medium = VIDEO` 且 `density.band = MERGE_REQUIRED / SPLIT_REQUIRED` 时，当前质量记录不能 `PASS`；必须先合并、拆段或建立带 handoff 的多个可执行记录。
- 偏离区间必须保存 `density.exception.reason + evidence_ids + user_authorized`；省算力、赶进度或模板不足不是有效理由。
- `hero_beat_ids` 选择真正的身份建立、情绪转折、关键接触、高潮或结尾。4—7 秒通常 1 个，8—12 秒 1—2 个，13—24 秒至少 2 个，25—30 秒 2—3 个；这是可调导演建议，不是跨项目数字硬门。

I2V 的 `SHOT_MOTION` 记录必须绑定上游 IMAGE 输出的当前 artifact/version 与明确参考职责。READY 阶段至少有已登记输入；RUNNING/EXECUTED 必须能访问真实输入媒体并回链产生它的任务/回执。不能只在自由文本里写“参考上一张图”。

### 3.3 Prompt 家族与不可混用项

同一故事镜头可以需要多条 Prompt，但每条只承担一个 generation role：

| 角色 | 媒介 | 必须保留 | 不得混入 |
|---|---|---|---|
| `ASSET_REFERENCE` | IMAGE | 身份/几何/服装/道具或场景锁、标准构图、材质与光 | 视频秒数、连续动作、对白音轨 |
| `ASSET_MOTION_REFERENCE` | VIDEO | 身份锁、可观察步态/转身/表演阶段、入口和出口 | 当前故事镜头的新事件 |
| `SHOT_KEYFRAME / START_FRAME / END_FRAME` | IMAGE | 当前镜头单帧可见状态、构图、姿态/接触、空间与连续性 | 伪时间线、前后动作、声音 |
| `SHOT_MOTION` | VIDEO | 当前事件、完整导演时间线、表演、物理、对白声音和出口 | 下一镜剧情、对白附录、未批准真相 |
| `SHOT_COMPOSITE_LAYER` | IMAGE | 本层主体、位置、边缘/遮罩、光影和与其他层的接口 | 假装同一供应商一次生成完整合成结果 |

角色、服装、场景、道具、生物、车辆、机甲和风格参考各自只抽取本目标必需事实。不能因为 Prompt 类型不同就改变同一资产的身份、数量、拓扑、色块、道具归属或当前状态。

当用户目标明确是手机随拍、家庭录像、DV、监控、网络摄像头或纪录片素材时，Prompt Soul 另保存“素材来源身份”：拍摄者、设备/年代、拍摄目的及适用的可观察成像/操作特征。对焦搜索、曝光波动、压缩伪影、固定高位或手持误差必须与该设备一致。商业广告、动画、神话视效和受控电影摄影不自动加载纪实缺陷包。

## 4. Prompt Soul 与导演节拍

每个 `director_beats[]` 使用合并字段，避免拆出十几个平行小表：

```yaml
- beat_id: BT-001
  target_id: SH-001
  time_range: {start_seconds: 0, end_seconds: 3}
  priority: REGULAR
  entry_state: 可见入口状态与必须继承的连续性
  camera: 景别、机位、观看目的、主要运动家族与结束位置
  space: 主体位置、方向、前中后景、轴线与可用通道
  action_physics: 准备、重心或速度、执行、接触/释放、反作用、制动与终态
  performance: 视线、呼吸、姿态、手势、微表情、反应延迟与情绪变化
  contact_material_environment_vfx: 接触点和力；皮肤/头发/织物/硬表面、光影、天气/介质和效果的因果响应
  dialogue_audio: 逐字对白与口型责任，或无对白时的环境声、拟音、声音桥和后期责任
  exit_state: 已完成状态、未完成运动及下一节拍继承项
  risk_load: MEDIUM
  high_risk_event: NONE
  compiled_anchors:
    - provider_prompt_id: PP-001
      section_id: SEC-PP-001-TIMELINE
      execution_anchor: 本拍在最终 PP 中完整出现的机位、动作与可见终态片段
      camera_anchor: 本拍最终 PP 的机位片段
      action_anchor: 本拍最终 PP 的动作片段
      exit_anchor: 本拍最终 PP 的可见终态片段
```

枚举：

- `priority`：`HERO | REGULAR`
- `risk_load`：`LOW | MEDIUM | HIGH`
- `high_risk_event`：`NONE | IDENTITY_CLOSEUP | VISIBLE_LIP_SYNC | PRECISION_HAND_CONTACT | MULTI_SUBJECT_CONTACT | CLOTHING_CHANGE | MECHANICAL_TRANSFORMATION | LIQUID_OR_DENSE_VFX | OTHER`

视频节拍的 `time_range` 必须连续覆盖自然时长。静态图节拍的 `time_range = null`，且 `entry_state / dialogue_audio / exit_state` 可以为 `null`；静态必须信息写入单帧可见状态、构图、姿态/接触、材质光环境和参考职责，不用“无对白/无入口/静态定格出口”等占位句伪造时序。`action_physics` 在静态图中只描述当前姿态、重心、接触和材料受力，不描述未发生的前后动作。

每个 VIDEO 节拍对每个最终 PP 恰有一条 `compiled_anchors[]`。`execution_anchor` 必须在该 PP 的正向 `DIRECTOR_TIMELINE` section 中只出现一次，并真实包含本拍单独的 `camera_anchor / action_anchor / exit_anchor`；不同节拍不得复用或重叠同一片段。没有 `LANGUAGE_TRANSLATION` adapter 时，这三个锚必须分别逐字等于 canonical `camera / action_physics / exit_state`，不能用“自然发生、八拍全部保留”等概括替代。跨语言 PP 才允许使用目标语言锚点，并必须有 `LANGUAGE_TRANSLATION` operation 与当前哈希绑定的两遍审阅。静态 IMAGE 的 `compiled_anchors[]` 为空，正向成品 section 不得加入秒数、运镜、对白或音轨；`NEGATIVE` 中合理写“不要运镜/无对白”不算伪动态。

每个节拍只保留一个主要叙事动作、一个主要运镜家族和最多一个高风险事件。动作按需要覆盖“准备 → 执行 → 接触/释放 → 力传递 → 反作用 → 制动/回弹 → 余势 → 终态”。表演把情绪翻译成当前景别可读的视线、眼睑、眉、嘴唇、下颌、呼吸、肩颈、手指和重心变化；远景使用轮廓、步态和姿态，不浪费算力写不可见微表情。

接触应说明施力主体、目标、接近方向、接触点、对齐、压力/摩擦/压缩、负载传递、反作用与稳定持有或释放。VFX 必须有来源、路径、遮挡/接触、场景照明、主体/环境响应、衰减和残留；没有来源时不自动添加粒子、火花、烟雾或体积光。

## 5. 资产、连续性与对白

### 5.1 活动资产胶囊

`active_asset_capsule[]` 每项只保存：

```yaml
- asset_id: CHAR-001
  asset_version: v2
  reference_ids: [REF-001]
  generation_essential_facts:
    - 当前镜头必须看见的身份/几何/服装/材质事实
```

完整 Character/Costume/Scene/Prop/Creature/Vehicle/Mecha/Style/Sound Bible 留在资产层。每个活动资产通常只抽取当前生成需要的少量事实；不得用“节省算力”删除身份、数量、关键色块、道具归属或当前状态。

`continuity_capsule[]` 只保存影响当前入口、动作与出口的事实，例如位置、朝向、视线、服装/伤势/湿润、道具归属、未完成动作、主光方向、摄影轴线、持续声音和不可回退状态。它不替代完整连续性账本。

### 5.2 对白调度

`dialogue_fit.status` 使用：`FIT | SPLIT_REQUIRED | NOT_APPLICABLE | NOT_RUN`。

```yaml
fragments:
  - dialogue_id: DLG-001
    fragment_index: 1
    speaker_asset_id: CHAR-001
    verbatim_text: 当前时间段实际说出的逐字片段
    start_seconds: 1.2
    end_seconds: 3.8
    delivery_mode: ONSCREEN_LIP
    bridge_from_previous: false
    acoustic_state_ref: SNDSTATE-001
```

`delivery_mode`：`ONSCREEN_LIP | L_CUT | VOICE_OVER | AUDIO_POST_REQUIRED`。

- 用户/来源对白未经授权逐字保留；估算或实测表明说不完时必须 `SPLIT_REQUIRED`，不得删字、虚构高速语速或把对白附在时间线末尾。
- 同一句可以跨镜：可读脸部为 `ONSCREEN_LIP`；切听者、道具、环境或反应时为 `L_CUT`，声音继续且画面人物闭口；来源本来是旁白/内心/广播时使用 `VOICE_OVER`。
- 逗号、感叹号、问号、破折号只提供可选表演节拍，不自动生成切镜。每个切点必须有独立的可见叙事职责；同一句跨镜只保留一个连续声音游标，不在新镜重新从句首播放。
- 后续片段必须 `bridge_from_previous = true`。按顺序拼接全部片段必须与当前 `dialogue_id` 原文逐字一致。
- 目标模型不生成声音时使用 `AUDIO_POST_REQUIRED`，仍保留台词、声线、节奏、环境和同步点，不伪装成原生音频能力。

### 5.3 对话视频的完整导演责任

含对白或人物非词汇发声的 `SHOT_MOTION` 还必须满足：

- 每段明确说话人、语言、发声内容、起止时间、声线/气息/音量趋势、停顿和交接；
- `ONSCREEN_LIP` 时只让当前说话人口型运动，听者保持符合角色的视线、呼吸、姿态或动作反应；
- 切到听者、道具、环境或反应镜头时使用 `L_CUT`，声音连续但可见听者不同时开口；
- 一句跨镜时保存精确文字游标和声学状态，后一镜不从句首重说；
- 逐字台词只在实际时间段出现一次，不在 `SOUND` 或 Prompt 尾部再复制一份清单；
- 每镜必须单列可见 `exit_state`，即使动作正文已写到结果也不能省略；声音没有来源时明确不添加，不能用“接触声、衣料声和环境底噪”等通用句填满声音栏。
- `SOUND` 汇总声线和责任，不概述或改写台词；模型无原生声音时保留完整时间表并转为 `AUDIO_POST_REQUIRED`；
- 对白自然时长超出镜头时先拆镜、延长经批准的编辑时长或调整调度，不删除台词、不虚构高速语速。

角色表演信息不应只写成括号情绪。当前景别需要能读到说话前的准备、说话中的目的和压力、对方反应以及句后关系/动作状态。多人对话逐轮维护说话对象、视线、位置和话语权，不能只列台词顺序。

### 5.4 对白、动作、参考与镜头交接的共同门

叙事视频还必须加载 `ALPHA7_MASTER_PRODUCTION_CONTROL.md`。对白先形成完整连续声音，再由语义重音、表演、证据和动作变化选择镜头；标点不能单独制造切镜。同一句跨镜时，每段只承担本镜实际发声文字，后段承接同一句声音，全部片段拼回后逐字等于来源。

每个视频节拍的 `action_physics` 必须闭合准备、主要动作或施力、接触或释放、可见后果和可继承终态；`camera` 只承担一个有动机的观看任务，并写清结束构图。每项参考只负责一个主要内容，同时登记禁止带入项；动作或摄影参考不能覆盖身份、服装、环境、标识和已接受状态。

每对相邻镜头必须有交接记录，至少覆盖身份与服装、位置与方向、视线、姿态与动作阶段、道具归属、手口占用、开放运动、轴线与摄影阶段、光线、声音、对白进度、剪法和备用切法。已接受素材的真实末态覆盖计划状态；被拒绝素材不得成为下一镜来源。

## 6. 四层 Prompt 的不同职责

### `PROVIDER_NEUTRAL_MASTER`

MASTER 是详细、权威、供应商中立的导演合同。它覆盖当前镜头的资产、参考职责、入口状态、全部导演节拍、动作/表演/接触/材质/环境、对白声音、出口状态、保护边界和验收条件。MASTER 不能只是摘要、标题或一行意图。

### `TRANSFORM_PLAN`

TP 是简洁的内部转换计划，不复制 MASTER 全文。它说明：需要怎样重排为执行文本、参考如何映射、声音由模型还是后期承担、是否因已核验入口限制分段、哪些 MUST 语义不得移动或删减。TP 不可提交给外部模型，也不得新增故事事实。

### `NEUTRAL_EXECUTION_PROMPT`

NEP 是完整、自包含、可复制的供应商中性执行稿。它把 MP 的导演意图按 TP 落成逐镜执行文字，保留全部适用 MUST 语义、对白和导演密度；它不绑定具体供应商，不得写未经当前证据支持的供应商能力，也不能进入生成 Gate、执行任务或执行回执。

### `PROVIDER_COMPILED`

COMPILED 是完整、自包含、可复制并可直接提交给当前 provider/model/version/surface 的成品。它从 MP 经 TP 与 NEP 编译，保留全部适用 MUST 语义与导演密度，只转换目标入口需要的自然语言、引用标签、输入关系、分段和声音责任。不能把 TP 的简洁误写成最终 Prompt 也应简短，也不能把 NEP 原样改标题冒充供应商适配。

每条 COMPILED 还必须声明唯一 `execution_contract`：

- `MANUAL_COPY_TEXT_SPEC_ONLY`：用户已经自行确认网页入口可用，本轮只需要可复制文字，且成品不依赖当前模型/版本、价格、精确时长、参考语法或专有能力结论。Registry 只保存 `USER_REPORTED + SURFACE_ONLY + AVAILABLE/LIMITED + SURFACE_MANAGED_UNKNOWN + NOT_RUN`，不得登记 capability claim、请求生成时长或裁切承诺。它可以完成文字质量检查，但永远不能进入 Generation Readiness、READY/RUNNING/EXECUTED 生成任务或充当真实执行证据。
- `GENERATION_EXECUTABLE`：需要把该 PP 当作当前生成对象使用；必须绑定当前 provider/snapshot/model/version/region/surface 与适用能力证据，并满足 Pilot、Gate 和执行合同。只有这一类 PP 才是生成资格候选。

从 manual 升级为 executable 不是改一个枚举：必须先补当前证据、重新编译/复核适配，并按新版本重新评估 Generation Readiness。

`execution_contract` 不决定“写短还是写全”。两类 COMPILED 默认都必须是完整可复制的 `FULL_FIDELITY` 成品；区别只是能否进入真实生成资格。紧凑版只能在用户明确要求时另建，入口限制则使用带 handoff 的完整分段。

四层共用同一条 `prompt_quality_record`。禁止把相同 `director_beats`、`semantic_atoms` 或质量诊断分别复制进 MP、TP、NEP、PP。

### 6.1 正文唯一与 `prompt_sections[]`

MP、TP、NEP、PP 的正文分别只保存在 `master_prompt_text / transform_plan_text / neutral_execution_prompt_text / prompt_text`。`prompt_quality_record` 不复制任何一层全文。每层正文旁只保存轻量 `prompt_sections[]` 元数据，用 Unicode code-point span 把该层唯一正文无缝分区。模型只写有序 section 的内容与引用；必须实际运行 `scripts/compile_prompt_sections.py` 自动拼正文并计算区间，不得让模型手算 `start_char/end_char`，也不得用 UTF-8 字节数、UTF-16 code unit 或界面显示宽度代替：

```yaml
prompt_sections:
  - section_id: SEC-001
    kind: DIRECTOR_TIMELINE
    order: 4
    start_char: 186
    end_char: 1220
    atom_ids: [PSA-001]
    beat_ids: [BT-001, BT-002]
```

- `kind`：`TASK | REFERENCE_ASSET | SCENE_STYLE_CONTINUITY | STATIC_FRAME | DIRECTOR_TIMELINE | SOUND | NEGATIVE | TRANSFORM_PLAN`
- span 使用 `[start_char, end_char)`，按当前层正文的 Unicode code point 计数；第一段从 0 开始，相邻段首尾相接，最后一段精确结束于正文长度，不允许空档、重叠或越界；
- 编译器插入的段间分隔符归入前一 section 的 span；按区间切片后顺序拼接，必须与唯一正文逐字一致；
- section 只存位置和引用，不再复制正文片段；`atom_ids/beat_ids` 必须解析到同一质量记录；
- MP/NEP/PP 使用适用的成品结构 section；TP 只能使用 `TRANSFORM_PLAN`，其引用必须覆盖全部 MUST atoms，明确它们将如何保留、映射或分段；
- NEP 不得包含计划专用 section，也不得与 TP 同文。PP 的 section 与文本由编译产生，不能照抄 NEP；该 `provider_prompt_id` 对应的 `adapter_integrity[].adapter_operations[]` 必须记录真实执行过的适配操作。
- 只有编译器实际产物与当前完整状态通过结构/语义验证后，才能声明 section spans 或 Prompt Quality 为 `PASS`。轻量人读记录、Markdown 摘要、未运行 helper 的临时账本只能写“未核验”，不得因看起来连续或保存了哈希就冒充已验证。

## 7. 最终可复制 Prompt 的结构槽位

视频 `PROVIDER_COMPILED.prompt_text` 默认形成一个自包含复制块：

```text
【生成任务与可见结局】
时长/画幅或继承方式、媒介、核心事件、完整可见终态和时间稳定要求。

【参考职责与活动资产锁】
每个输入控制什么、不控制什么；人物/主体身份、数量、服装、道具和关键几何/材质。

【场景、风格与入口连续性】
空间地标、环境介质、固定光源、媒介/风格指纹和当前必须继承的可见状态。

【导演时间线】
按时间连续写全部镜头/阶段；每段覆盖入口、摄影、空间、动作物理、表演、接触/材质/环境/VFX、对白声音和出口。

【声音设计】
汇总只写跨全片的声线、声学空间、底噪、音乐/混音和后期责任；逐字对白只在实际时间段出现一次。

【精简负向约束】
只针对当前镜头已识别风险，使用完整句，不生成第二份反向剧情。
```

时间线必须承载主要导演信息，但不以固定字符比例放行。过渡节拍可以紧凑，HERO 节拍必须比过渡节拍拥有更多可执行细节。不得附加重复英文静态关键词串，除非用户明确要求第二语言版本；翻译仍须保留完整时间导演合同。

静态图像使用同一复制块的任务、参考资产、场景风格和负向约束，但把“导演时间线/声音设计”替换为一个“单帧构图与可见状态”段；不为了套视频模板编造秒数、运镜、对白或前后动作。

## 8. Provider 适配保真与有序压缩

每个 `provider_prompt_id` 有单独的 `adapter_integrity[]` 项；不得用一个 provider 的 PASS 给其他 PP 放行。其 `adapter_mode`：

- `SYNTAX_ONLY`：只转换语言或目标入口语法；
- `SYNTAX_AND_REFERENCE_MAPPING`：同时转换参考标签、输入槽位和多模态关系；
- `SEGMENT_WITH_HANDOFF`：入口容量不足时拆成连接片段，并显式传递身份、空间、动作、声音与出口状态。

每项 `compression_authority`：`NONE | VERIFIED_SURFACE_LIMIT | USER_REQUESTED`。没有已核验入口限制或用户明确要求时，不主动压缩成短 Prompt。

`adapter_operations[]` 使用轻量操作记录，不复制输入/输出正文：

```yaml
- kind: REFERENCE_TAG_MAPPING
  source_section_ids: [SEC-M-002]
  output_section_ids: [SEC-P-002]
  evidence_ids: [E-CAP-001]
```

`kind`：`LANGUAGE_TRANSLATION | REFERENCE_TAG_MAPPING | INPUT_RELATION_MAPPING | SURFACE_SYNTAX | AUDIO_RESPONSIBILITY | DURATION_SEGMENTATION | MODEL_NEUTRAL_REALIZATION`。每个 PP 至少有一项与实际编译相符的操作；不得用空数组或虚构操作证明“已经适配”。

允许改变：目标语言、合法引用标签、输入关系表达、供应商参数位置、已核验的声音责任和分段包装。

禁止改变或删除：目标时长与节拍数量、事件顺序、身份/数量、资产状态、参考职责、动作方向和终态、人物表演、逐字对白、关键接触物理、材质/光/环境、摄影目的、声音、连续性、未知项和因果边界。

确有入口上限时按顺序处理：

1. 删除重复质量词、同义句和工程说明；
2. 压缩参考已清楚提供的静态复述与不可见装饰；
3. 合并重复摄影、光影和声音常量；
4. 压缩 MAY，再压缩不影响结果的 SHOULD；
5. 仍无法承载时使用 `SEGMENT_WITH_HANDOFF`，不得删除 MUST 语义假装适配成功。

适配后用 PP 的 `prompt_sections[].atom_ids` 与 `semantic_atoms` 逐项比较，并把缺失/改变写入该 PP 的 adapter record。每项 `status` 使用 `PASS | FAIL | NOT_RUN`；任一 MUST atom 缺失/改变，或 `loss_findings[]` 非空时为 `FAIL`，该 PP 不得进入真实执行。

## 9. Prompt Quality 检查（Generation Readiness requirement）

每个目标执行对象在进入 Generation Readiness 前必须通过：

1. 当前 `target_type + target_id + source_spec_version + generation_role` 恰有一条 `lifecycle_status = CURRENT` 的质量记录，并能解析当前 Prompt Soul artifacts、MP、TP、NEP、目标 PP 及其唯一 adapter record；
2. MP 是详细权威导演合同，TP 是简洁转换计划，NEP 是完整可复制的中性执行稿，PP 是绑定当前供应商的完整成品；
3. 四层各自只有一份正文；`prompt_sections[]` 无缝覆盖对应正文且不复制文本，TP section 覆盖全部 MUST atoms，NEP 与 TP 不同，PP 与 NEP 不同并记录真实 adapter operations；
4. 图像使用一个 `STATIC_IMAGE` 节拍且不伪造时间；视频动态密度落入对应 band，或有证据化例外，全部时间段从 0 连续到自然时长，无重叠、空档或提前结束；`MERGE_REQUIRED / SPLIT_REQUIRED` 不得直接通过；
5. 每个 `director_beat` 的合并字段都有实质内容；VIDEO 的每拍还须对每个 PP 提供单独、正向、不可复用的编译锚，不能只写标题、空泛形容词或重复模板；
6. 视频至少一个真正重要的 HERO 节拍获得比过渡节拍更具体的动作、表演、接触/材质、摄影和声音控制；静态图唯一节拍则把细节集中在主体身份、姿态/接触、构图、空间和材质光环境，不强制声音；
7. 所有活动资产、参考职责、入口连续性、受保护未知项、数量和因果边界可解析且没有静默漂移；
8. 对白为 `FIT/NOT_APPLICABLE`，逐字重构、说话者、口型/镜外责任和声音桥正确；
8A. 当前制作记录中的动作因果、参考职责和相邻镜头交接闭合；已接受真实末态优先，进度、资产、实际成本和尝试上限有证据且不进入最终 Prompt；
9. COMPILED 保留全部适用 MUST semantic atoms；当前目标 `provider_prompt_id` 对应的 adapter integrity 为 `PASS`；同语言逐拍锚与 canonical 一致，跨语言适配存在真实翻译 operation；
10. 每个 Prompt 与计划生成目标/角色 1:1；不存在“同上、其余类推、参考前镜”；
11. 只有 `GENERATION_EXECUTABLE` PP 可进入 Generation Readiness；`MANUAL_COPY_TEXT_SPEC_ONLY` 即使文字质量通过也只能交付复制；
12. 内容规范或素材许可阻断项为零；传播准备度不能抵消阻断。

### 9.1 代表性 Prompt 的两遍审阅

机器合同能阻止空壳、漏项和断链，但不能单靠字符串证明导演判断优良。为避免“花很久把账本做对，最后成品仍平庸”，首批 3—5 个 Prompt Pilot 采用两遍审阅：第一遍负责创作和编译；第二遍只读当前目标真值、MASTER 与最终 PP，不参考作者的自评分，逐项回答以下问题，并写入该质量记录的 `two_pass_reviews[]`：

1. 不看内部表，普通导演能否从 PP 还原本镜的观看任务、事件顺序和可见终态；
2. 身份、数量、入口/出口、动作方向、接触物理、表演和摄影是否具体到可执行，而不是“自然、电影感、保持一致”等空词；
3. PP 是否遗漏 MASTER 的关键事实，或偷偷新增真相、因果、年龄、素材许可/事实主张；
4. 静态图是否真的只有单帧可见状态，视频是否真的有足够阶段、反应与可剪切点；
5. 供应商适配是否产生了实际价值，而不是把 NEP 换个标题或原样复制。

每条审阅绑定 `provider_prompt_id`、MASTER/PP/Soul 当前 SHA-256、审阅范围、事件/终态或静态状态还原、遗漏/偷加/具体性/适配价值检查、结论与时间；正文或 Soul hash 变化即失效。VIDEO 还原当前事件与可见终态，IMAGE 只还原单帧可见状态。若质量记录含 `reference_delta`，还必须绑定当前 `reference_delta_sha256` 并让 `reference_delta_check = PASS`；缺失、旧 hash、`FAIL/NOT_RUN` 都不得通过。

任一核心问题答“否”时，该目标保持 `FAIL`，回到最小受影响 section 修订。批量阶段不为每个普通镜头重复完整二次长审：所有 Prompt Pilot 样本和所有高风险目标必审，每批再抽查至少一个普通目标；普通但含 HERO 节拍并不因此自动触发全量二审。其余目标运行确定性检查和与已通过 Pilot 的局部一致性检查。5 个代表 Pilot 可以覆盖 20 个同族批量 Prompt，但必须作为批次的非空子集，覆盖本批 provider/snapshot、format、task、medium/role、quality/adapter 与高风险类别；抽查失败才扩大到本批受同一模板、资产或 adapter 影响的目标，而不是重跑全项目。

明确失败代码：

- `PQ_TRIVIAL_OR_SUMMARY_ONLY`：空白、一字/一句笼统动作、剧情摘要或只有标题；“动。”必须命中此项；
- `PQ_DENSITY_MISSING`：没有足够导演节拍且无合法例外；
- `PQ_BEAT_CONTRACT_THIN`：视频节拍缺入口、动作、摄影、表演、声音或出口；静态节拍缺单帧主体、姿态/接触、构图、空间或材质光环境；
- `PQ_ASSET_OR_REFERENCE_DRIFT`：身份、数量、资产或参考职责漂移；
- `PQ_DIALOGUE_LOSS`：对白缺字、重复、乱序、换人或声音桥断裂；
- `PQ_ADAPTER_LOSS`：Provider 适配删减、概述化或改变 MUST 语义；
- `PQ_REFERENCE_DELTA_INVALID`：引用编辑/派生未闭合源元素、保持/改变/新增集合冲突、输出集合不等于合法并集，或禁止新增却要求源输入中不存在的元素；
- `PQ_BOUNDARY_VIOLATION`：未知项、因果、数量、年龄、安全、内容规范或素材许可边界被改写；
- `PQ_INTERNAL_LEAKAGE`：工程 ID、哈希、Gate、恢复卡或模板说明进入模型执行文本。

`quality_status.diagnostics` 可以记录字符数、导演时间线占比、重复率、段落长度和供应商限制，但这些指标不得单独把语义稀薄 Prompt 判为 PASS，也不得因低于某个跨模型字符阈值自动失败。质量记录 `PASS` 只证明文字执行合同成立，不证明模型会服从或真实视频已经通过 QA。

### 9.2 Master 创作预检

机器状态的 Prompt Quality Gate 负责完整四层账本；包根目录的 `运行银幕总控.cmd 创作预检 <创作预检.json> --output <机器报告.json>` 负责对一个可复制创作切片进行第二种、较小而直接的保真核对：

- 第一个完整剧本样场使用 `SCRIPT`；
- 每个 Prompt Pilot 的视频 PP、所有对白/人物非词汇发声/压缩高风险 PP 使用 `VIDEO_PROMPT`；
- 第一个静态图 PP 使用 `IMAGE_PROMPT`；
- 批量阶段每批至少抽查一个普通视频 PP；任何抽查失败扩大到同模板、资产或 adapter 影响的目标。

它必须检查来源覆盖、逐字发声、说话人和顺序、视频时间线、每拍完整锚、最终 section 合同、静态/动态分离和压缩授权。报告只进入机器附件；普通用户看到自然中文问题和修复。该工具 `PASS` 与 Prompt Quality `PASS` 均成立后，仍只能证明文字规格，不证明真实生成效果。

## 10. 用户可见交付与真实性边界

普通创作者默认看到：

1. 一句自然中文导演判断或阻断说明；
2. 一个完整、可复制的 `PROVIDER_COMPILED` Prompt；
3. 只有在需要手动操作时才给最短必要的参考上传/入口步骤。

`prompt_sections[]`、质量记录和质量诊断全部在后台生成并落盘。只有用户要求审计、调试或专业交接时，才展示 MP、TP、NEP、sections、质量记录、semantic atoms、adapter loss 或机器诊断。

Prompt Quality 检查通过仅表示当前文本规格具备执行资格候选，并作为 `Generation Readiness Gate` 的 mandatory requirement；它不创建新的 Gate 类型。没有真实生成媒体时，Observation、媒体 QA、连续性验证、发布和学习仍保持未执行；Production Validation 必须保持 `NOT_TESTED`。
