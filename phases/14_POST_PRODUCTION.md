# Stage 13 — 后期制作与成片资格

本阶段的规格完成范围、真实媒体 basis 与 Gate 时机遵守 `../references/ALPHA7_RUNTIME_INTEGRITY_CONTRACT.md`；字幕/TTS coverage、复杂同镜合成、文字产物哈希与文字模拟末端遵守 `../references/AGE_SAFETY_PROVIDER_AND_COVERAGE_CONTRACT.md`。

后期建议与工作沟通遵守 `interaction_language`；角色台词与配音遵守 `dialogue_language`；字幕和发布稿遵守 `release_copy_language`。后期规格、真实后期执行、成片通过和发布资格必须分别记录。

## 后期输入 Gate

开始真实后期前，确认所用资产和镜头版本可访问，剪辑决定、`EDITED_STATE`、声音视点、字幕语言和开放 blocker 已明确。当前 `dialogue_inventory`、`shot_plan_id`、镜头时间范围、`subtitle_cues` 与 `tts_coverage_records` 必须属于同一版本；复杂同镜采用 `COMPOSITE` 时，各图层资产、位置、遮罩/边缘、素材许可、版本和哈希也必须齐全。未锁定的 `PROPOSED` 或 `UNKNOWN` 选择不能静默成为必做后期要求。只有真的执行该资格评估时才实例化 Gate，并在 `scope_bindings` 绑定当前输入版本；计划中的后期 Gate 不建占位对象。

## 标准媒体时间线与执行适配器

后期执行遵守 `../references/ALPHA7_MEDIA_EXECUTION_AND_EDITING.md`。唯一时间线事实源是 `silver-showrunner/media-timeline@1`：真实素材与素材许可记录先进入 `media-source@1`，再由 `../scripts/build_media_timeline.py` 编译为标准时间线，并用 `../scripts/media_preflight.py` 做文件、时长、轨道、输出路径和工具预检。满足严格线性子集时，可由 `../scripts/render_media_ffmpeg.py` 真实执行；复杂图层、字幕、转场、画面空隙或程序化图形不得静默降级，改走明确适配器或回到规格修订。

- **FFmpeg**：默认的可审计本地转码、拼接、混音、字幕合成与导出基线；
- **Remotion**：用于程序化图形、复杂排版或组件化视频，但仍读取同一标准时间线；
- **剪映 / VideoCut**：仅作为可选编辑器适配器或人工交接，不建立平行剧情、时间线或完成状态；
- 其他工具只有在适配器明确、输入输出可核对时才能加入。

命令编译、工程文件或时间线 JSON 不等于真实导出。真实后期任务须进入 `task_graph` 并产生 `execution_receipt`、新 Artifact 与文件哈希；渲染后再以 ffprobe/等价证据做技术检查，并对真实成片执行媒体 QA。

`minor_adult_same_shot_strategy = COMPOSITE` 的结果必须在同一标准时间线中明确列出各层来源和合成操作，不得以文件名或备注把它伪装成供应商一次生成。任何拆镜或合成修改都触发时长、镜头依赖、字幕和 TTS coverage 重算。

## 声音

- 对白、VO 与角色 Voice ID/参考；
- SFX、环境声、音乐和 cue sheet；
- 声音视点、响度、清晰度和可访问性；
- 授权、来源、使用范围与版本。

声音获得批准后，锁定稳定 Voice ID 或参考。不得把角色名随机哈希为声音并包装成艺术选角。

从当前 `dialogue_inventory` 建立 `tts_coverage_records`，每条记录保存 `scope_shot_plan_ids / scope_dialogue_ids / covered_dialogue_ids / tts_coverage_status / dialogue_audio_bindings / measurement_coverage_status / measured_dialogue_ids / measured_duration_seconds / output_artifact_refs / evidence_ids`：

- 没有 `tts_required=true` 的对白：`NOT_APPLICABLE`；
- 需要 TTS、但只完成文字规格或尚无 MEDIA Artifact 绑定：`NONE`，此时 covered、bindings 与 output refs 均为空；
- 每条 covered dialogue 都有且只有一个同版本 `MEDIA` Artifact 绑定，且只覆盖所需对白真子集：`PARTIAL`；
- 每条 scope dialogue 都有且只有一个同版本 `MEDIA` Artifact 绑定，covered 与 scope 完全相等：`FULL`。

`tts_coverage_status` 只证明逐条 `MEDIA` Artifact 映射已经登记，不证明这些音频真实存在或时长已测。真实音频覆盖另算：只有 binding 指向真实、带哈希和匹配证据的 Artifact/version 且有实测时长时，对白才进入 `measured_dialogue_ids`；measured 集合为空时为 `measurement_coverage_status = NONE`，真子集必须为 `PARTIAL`，不能借总时长或一段样音写成全片。`measurement_coverage_status = FULL` 要求 measured 集合与 scope 完全相等，`measured_duration_seconds` 由各 binding 确定性求和。即使两种 coverage 都为 `FULL`，仍不证明素材许可清楚、口型同步、混音或 QA 通过；真实 TTS 还需同意/来源、execution receipt、版本、SHA-256 与观察证据。

## 字幕与图形

- 时间轴和必要的说话人识别；
- 安全区、平台格式和多语言变体；
- 可读 UI、标识和图形插入；
- 只有明确编辑理由时才使用强调样式。

Whisper 或供应商时间戳只能在**画面与最终音轨锁定后**用于字幕对轴；媒体、音轨或剪辑版本一变，旧时间码立即失效。自动转写后必须进行人工语义复核，逐项核对人名、术语、数字、否定词、说话人、断句和屏幕文字；“转写成功”与“时间码合法”都不等于字幕语义正确。字幕版本必须回链最终音轨/成片哈希，复核完成前保持 `QA_NOT_EXECUTED` 或相应待复核状态。

每条 `subtitle_cues` 必须回链当前 `dialogue_id / shot_plan_id / shot_id / timing_spec_version`，并保存 `start_seconds / end_seconds`。对当前版本计算：

```text
expected subtitle dialogue IDs = dialogue_inventory 中 subtitle_required=true 的 dialogue_id
covered subtitle dialogue IDs = subtitle_cues 中的 dialogue_id
missing dialogue IDs = expected - covered
orphan dialogue IDs = covered - dialogue_inventory
```

存在任何漏句、孤立句、重复 cue、旧 `timing_spec_version`、错 `shot_id` 或 cue 越出对应镜头时间范围时，字幕 coverage 不完整，不能进入最终字幕验收。shot plan 拆分、合并、改时长或改对白后，旧 cues 立即失效并按当前 `dialogue_inventory` 重建。时间码集合通过后仍要做人工语义复核。

## 剪辑、时长与格式

以真实 `EDITED_STATE`、节奏证据、对白结构和音乐结构编排信息、情绪和因果。每次剪辑后从实际时间线重新计算最终时长，与当前 `canonical_duration` 比较；没有合法容差时不得自动套用默认百分比或用估算范围掩盖差异。

双画幅不能默认由同一母版裁切。若安全区、人物位置、文字、动作或节奏不成立，应建立单独剪辑/镜头变体并分别 QA。

本阶段新建或实质改写、并被下游引用的时间线规格、字幕稿、cue map、TTS coverage、合成说明和后期报告都登记为当前 `TEXT_SPEC` Artifact，保存 `status + version + content_locator.sha256`。文字改变后旧哈希、completion 与预检不自动继承。

## 成片关卡顺序

1. 对真实剪接序列执行 `SEQUENCE_CONTINUITY_GATE`；
2. 对包含声音、字幕、图形和交付件的真实成片执行 `FINAL_ARTIFACT_GATE`；
3. 只有成片通过后，才进入单独的 `RELEASE_READINESS_GATE`。

`SHOT_GATE` 通过不自动通过序列；序列通过不自动证明最终成片或发布资格。最终成片存在也不等于已经发布。

## 无真实媒体时

没有可访问真实媒体时，只能完成后期规格。以下对象只描述本阶段的 `stage_result.workflow_status`，不能覆盖项目全局或上游阶段已经发生的真实执行：

```yaml
workflow_status:
  spec_status: SPEC_READY
  execution_status: NOT_EXECUTED
  observation_status: OBSERVATION_PENDING
  qa_status: QA_NOT_EXECUTED
  publication_status: RELEASE_NOT_READY
  learning_status: NO_REAL_DATA
  status_basis:
    execution_artifact_ids: []
    observation_ids: []
    qa_gate_ids: []
    release_gate_ids: []
    publication_ids: []
    learning_ids: []
```

上例是本阶段没有任何真实执行 basis 的纯规格状态；若项目已有上游真实事实，必须保留相应 basis，不能清空。后期文字规格本身通过上游完整性检查时，只为精确 `RELEASE_SPEC_ARTIFACT` 或相应文字产物创建 scoped completion，并明确排除媒体执行、观察、QA、发布与学习。如果规格仍有缺口，保持 `SPEC_DRAFT`。无媒体时不实例化 `SEQUENCE_CONTINUITY_GATE` 或 `FINAL_ARTIFACT_GATE`；不得声称后期已执行、成片已完成、QA 已通过或具备发布资格。

若用户明确要求文字线路模拟，且本轮真实登记了 `SIMULATED_EXTERNAL_STEP`，只把上例的 `execution_status` 改为 `SIMULATED_ONLY`，并设置 `execution_mode = SIMULATION`；`observation_status / qa_status / publication_status / learning_status` 仍分别为 `OBSERVATION_PENDING / QA_NOT_EXECUTED / RELEASE_NOT_READY / NO_REAL_DATA`，`terminal_markers` 仍为空。若没有实际模拟外部步骤，必须继续使用 `NOT_EXECUTED`，不能为了让线路看似走完而改成 `SIMULATED_ONLY`。
