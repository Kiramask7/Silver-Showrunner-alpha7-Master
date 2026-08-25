# Alpha.7 媒体执行、剪辑与字幕对轴合同

审计日期：2026-08-14（Pacific/Auckland）  
适用范围：剧情、漫剧、概念片、纪录/科普、文化传播、教育、品牌、比赛展示及长篇连续视频的媒体后半链。

## 1. 交付目标与真实性边界

银幕总控不把“写出剪辑方案”冒充“完成剪辑”。本合同建立一条可由本地工具真实执行、可替换剪辑前端、可恢复并可审计的后半链：

```text
真实素材与许可记录
-> 标准 media-source
-> 标准 media-timeline
-> PREPARE 预检
-> FFmpeg 或 Remotion 适配器真实导出
-> execution receipt + 成片 SHA-256
-> ffprobe 技术检查
-> 供应商时间戳或 Whisper 对轴
-> 人工语义复核
-> 字幕合成/重新导出
-> 绑定最终成片哈希的视觉、声音、连续性与节奏 QA
-> FINAL 四重总检
-> RELEASE_READINESS_GATE
```

本版本的自动化终点仍是 `RELEASE_READY`，不自动上传或发布。任何一环缺少真实文件或精确版本证据，都保留为 `NOT_EXECUTED / EXECUTION_PENDING / OBSERVATION_PENDING / QA_NOT_EXECUTED`，不得用规划、命令文本、假文件名或模拟回执补齐。

以下等式永久成立：

| 已有材料 | 不能冒充 |
|---|---|
| 时间线 JSON 已生成 | 视频已导出 |
| FFmpeg/Remotion 命令已编译 | 命令已成功执行 |
| MP4 文件存在 | 本管线执行来源已证明 |
| 导入回执的字段、哈希与成片一致 | 回执声称的进程确实运行过 |
| ffprobe 读到视频流 | 画面、声音、节奏与连续性已通过 |
| Whisper 生成字幕 | 人名、术语、数字和语义已正确 |
| 字幕时间码合法 | 字幕与最终声音逐句准确 |
| 本地 JSON 自称人审 `PASS / QA_PASSED` | 人工确实看过/听过成片，或机器已证明主观 QA |
| 素材许可字段填写为 `CLEAR` | 已取得专业意见或平台许可 |
| 剪映/VideoCut 工程草稿 | 最终成片或 FFmpeg/Remotion 回执 |

## 2. 架构：一个标准时间线，多个可替换适配器

唯一事实源是 `silver-showrunner/media-timeline@1`。FFmpeg、Remotion、剪映、VideoCut 或其他编辑器只能读取或映射它，不能各自创建平行的剧情版本、时间线真相或项目状态。

### 2.1 必需输入

`media-source@1` 至少登记：

- 项目、时间线和版本 ID；
- 帧率与输出分辨率；
- 每个视频、图片、音频和字幕资产的本地路径、版本与素材许可状态；
- 轨道、片段、绝对开始时间、持续时长、素材入点、层级、音量和转场；
- 是否存在对白、是否必须有音频、字幕来源；
- 首选渲染引擎、输出路径和编码目标；
- 可选编辑器适配器，但它们不进入核心依赖。

示例：

```json
{
  "schema": "silver-showrunner/media-source@1",
  "project_id": "P-001",
  "timeline_id": "TL-001",
  "version": "v0.1",
  "fps": 25,
  "resolution": {"width": 1080, "height": 1920},
  "speech_expected": true,
  "audio_required": true,
  "assets": [
    {
      "id": "VID-001",
      "kind": "video",
      "path": "media/S001.mp4",
      "version": "v1",
      "rights_status": "CLEAR",
      "rights_evidence_ids": ["EV-RIGHTS-001"]
    },
    {
      "id": "VO-001",
      "kind": "audio",
      "path": "media/voice.wav",
      "version": "v1",
      "rights_status": "CLEAR",
      "rights_evidence_ids": ["EV-CONSENT-001"]
    }
  ],
  "tracks": [
    {
      "id": "V1",
      "kind": "video",
      "items": [
        {"id": "C-001", "asset_id": "VID-001", "start": 0, "duration": 5}
      ]
    },
    {
      "id": "A1",
      "kind": "audio",
      "allow_overlap": true,
      "items": [
        {"id": "A-001", "asset_id": "VO-001", "start": 0.4, "duration": 4.2, "gain_db": -2}
      ]
    }
  ],
  "subtitle_policy": {
    "source": "WHISPER",
    "language": "zh-CN",
    "burn_in": true,
    "semantic_review_required": true
  },
  "render": {
    "preferred_engine": "AUTO",
    "output_path": "renders/P-001_v0.1.mp4",
    "video_codec": "h264",
    "audio_codec": "aac"
  },
  "optional_editor_adapters": ["JIANYING"]
}
```

`scripts/build_media_timeline.py` 会拒绝远程 URL、网络共享路径、重复 ID、不兼容轨道、禁止轨道上的重叠及无效转场；它只生成规格，不执行渲染。`--hash-files` 会为当前存在的本地素材计算 SHA-256，`--strict-assets` 会在素材缺失时返回非零。执行版时间线必须使用 `--hash-files`；PREPARE 会重新计算当前素材哈希，缺失或不匹配都会阻断，避免同一路径下素材被替换后沿用旧 QA。

### 2.2 时间线精度原则

- 时间统一使用秒，帧率单独登记；适配器负责做确定性的帧换算。
- 视频、画外音、对白、音乐和音效都必须使用各自的绝对 `start/end`；不能把所有音频从 0 秒开始混合。
- 总时长取启用轨道中项目的最大结束时间，不用“原素材时长求和”代替实际时间线。
- 转场会改变有效重叠与持续时间，适配器必须显式计算，不能套固定偏移公式。
- 文本、LOGO、图表、字幕和特效属于 `overlay/subtitle` 轨；不能静默烧进源素材后丢失来源。
- 长篇项目继续遵守全局状态、Pilot、约 10 单元可恢复批次和检查点，不把整个长片一次性塞进单条命令。

## 3. PREPARE：执行前先证明环境和输入可用

运行 `media_preflight.py --mode prepare`，至少检查：

- 时间线 schema 与引用的本地素材是否存在；
- 选定引擎的本地可执行依赖是否就绪；
- FFmpeg 路线同时具备 `ffmpeg` 和 `ffprobe`；
- Remotion 路线具备本地项目、已声明依赖、本地 CLI、Node、pnpm 和许可复核记录；
- 字幕来源为 `WHISPER` 时，本机 Whisper CLI 与 FFmpeg 是否可用；
- 素材许可状态是否存在 `BLOCK/REVIEW/UNKNOWN`。

预检脚本不会安装软件、不会使用 `npx` 临时联网下载、不会打开浏览器、不会渲染、不会转写、不会发布。`READY` 只代表可以交给渲染适配器执行。

## 4. 引擎路由

### 4.1 FFmpeg：默认的线性媒体基线

适用：

- 常规剪切、拼接、裁切、缩放与画幅适配；
- 明确的淡入淡出或交叉转场；
- 画外音、对白、音乐、音效的时间偏移、混音与响度处理；
- SRT/ASS 字幕合成、转码、抽取音轨和交付封装；
- 无需复杂程序化排版的短片与批量镜头。

FFmpeg 适配器必须：

1. 先用 `ffprobe` 读取每个真实输入的流、时长、分辨率、帧率和音频情况；
2. 对无音轨视频显式生成静音或采用无音频图，而不是假设每个输入都有音轨；
3. 按标准时间线的绝对位置对视频和音频做 `trim/setpts/atrim/asetpts/adelay`；
4. 按真实相邻片段持续时长计算转场，不复制固定间隔的 `xfade offset`；
5. 音乐、旁白、对白和音效分别处理电平，再混合；不可把外部 voice manifest 写在文本中却不作为真实输入；
6. 字幕路径、字体和特殊字符使用平台安全转义，并验证中文字体实际存在；
7. 使用参数数组调用，`shell=false`，不生成包含未转义用户路径的命令字符串；
8. 非零退出码、超时、输出为空或 ffprobe 失败均视为失败；
9. 对最终输出重新计算 SHA-256 并写真实执行回执。

当前随包提供的 `scripts/render_media_ffmpeg.py` 是“严格线性基线”，不是上述全部 FFmpeg 能力的通用实现。它只真实执行以下最小安全子集：

- 恰好一个启用且从 0 秒连续到总时长的视频轨；
- 画面项目为本地视频或 PNG/JPG/JPEG 静态图；
- 视频按源入点/时长裁切，统一缩放、补边、帧率和像素格式后顺序拼接；
- 自动保留有音轨视频的源声音，并允许零个或多个本地音频项目按绝对开始时间叠加；
- 对各音频项目应用增益、48 kHz 重采样和混音；先对实际选中区间执行只读 `volumedetect`，有有效信号时使用单遍响度目标，全静音/近静音时显式保留静音而不把非有限测量值送入 `loudnorm`；
- MP4 + H.264/libx264，存在音频时使用 AAC；
- FFmpeg 成功后由 ffprobe 核对视频流、音频流、分辨率和时长，再生成绑定哈希的回执。

当前近静音判定使用各选中音频项目叠加增益后的保守峰值上界 `<= -70 dBFS`。计划与回执必须记录每个探测 argv、测得峰值和所选 `PRESERVE_NEAR_SILENCE / LOUDNORM_SINGLE_PASS` 策略；这只是技术信号检测，不是听感、对白可懂度或混音 QA。

遇到以下内容返回 `UNSUPPORTED`，不静默删除或换成相似效果：

- `overlay`、烧录字幕、转场或任意 `effects`；
- 多视频轨、layer 非 0、画面重叠、画面空隙或画面结束时间不等于总时长；
- Remotion job、非 MP4、非 H.264/AAC 或非 PNG/JPG/JPEG 静态图；
- 音频项目越过画面结尾、源入点越过真实媒体时长；
- 时间线声明必须有声音，但源视频和音频轨均无可用音频流。

需要转场、字幕、复杂图形或多层合成时，应路由到后续专用 FFmpeg 适配器、Remotion 或可选人工编辑器；严格线性基线不会为了“跑完”而降级创作意图。

### 4.2 Remotion：程序化图形与复杂排版的可选引擎

适用：

- 动态图表、科研/科普可视化、数据驱动版式；
- 复杂标题动画、可复用品牌/栏目模板；
- React 组件化字幕、注释、卡片、示意图和屏幕合成；
- 同一数据生成多个画幅或多个版本。

Remotion 不是 FFmpeg 的“更强替代”，也不是必装依赖。路由到 Remotion 时必须使用已存在的本地项目和锁定依赖；禁止用一次性 `npx` 下载制造不可复现环境。实际导出使用官方 CLI `remotion render`，输出仍须由 ffprobe、哈希回执和媒体 QA 验证。

Remotion 使用特殊许可。个人、小团队、公司、自动化产品和批量渲染的适用条件可能不同；每次正式使用前按当时官方许可核对使用方、团队规模和用途，并保存复核证据。本合同不作适用规则结论，也不把存在依赖等同于许可已满足。

### 4.3 剪映、VideoCut 与其他编辑器：仅可选适配器

这些工具可以用于人工精修、工程交换或团队偏好，但不得成为核心流水线的唯一真相源。适配器至少应输出：

- 源时间线版本与 SHA-256；
- 映射成功、降级或不支持的轨道/效果清单；
- 工程文件或导出文件的真实路径、版本与 SHA-256；
- 由谁、何时、用哪个软件版本执行；
- 尚需人工检查的字体、转场、关键帧、混音和字幕项。

只有工程草稿而没有真实导出，状态仍是 `EXECUTION_PENDING`。电脑上没有剪映或 VideoCut 不会阻断 FFmpeg/Remotion 基线。

## 5. 真实渲染适配器与执行回执

本包现已提供 FFmpeg 严格线性基线的真实执行器；Remotion 与复杂 FFmpeg 能力仍需各自专用适配器。所有真实适配器都必须以参数数组运行本地可执行文件，并记录：

- `engine`、可执行文件绝对路径和版本；
- 完整 `argv[]`，以及明确的 `shell: false`；
- 开始与结束时间、退出码、标准输出/错误摘要；
- 当前 `timeline_sha256`；
- 输出文件路径、大小和 `output_sha256`；
- 超时、重试、失败原因和恢复检查点。

最小回执：

```json
{
  "schema": "silver-showrunner/media-execution-receipt@1",
  "status": "EXECUTED_SUCCEEDED",
  "engine": "FFMPEG",
  "timeline_sha256": "<64位SHA-256>",
  "output_sha256": "<64位SHA-256>",
  "exit_code": 0,
  "technical_probe_status": "PASS",
  "shell": false,
  "argv": ["C:/Tools/ffmpeg/bin/ffmpeg.exe", "-i", "...", "final.mp4"],
  "executable": "C:/Tools/ffmpeg/bin/ffmpeg.exe",
  "tool_version": "ffmpeg version ...",
  "started_at": "2026-08-14T08:00:00Z",
  "finished_at": "2026-08-14T08:00:42Z"
}
```

`render_media_ffmpeg.py` 在当前进程直接启动 FFmpeg、得到退出码 0、重新 ffprobe 并核对输出后，可以在它自己的返回值和新回执中写 `EXECUTED_SUCCEEDED`。但 `media_preflight.py --mode final` 读取的是导入 JSON；即使回执状态、哈希、大小、时间顺序、`argv[]`、输出路径和当前 ffprobe 都一致，也只能写 `consistency_status=PASS / evidence_class=IMPORTED_SELF_ASSERTED / attestation_status=NOT_VERIFIED`。在没有调用方配置的受信公钥验签或同一受信进程事件时，FINAL 保持 `execution_status=EXECUTION_PENDING`、`pipeline_execution_proven=false`，并给出 `EXECUTION_RECEIPT_ASSERTED_ONLY`。本包当前未实现该包外信任锚。

这一区分不否认真实执行器已经产生文件；它只防止任意人复制或手写一个自洽 JSON 后，让另一个进程把“声明一致”误写成“来源已证明”。ffprobe 仍单独报告 `technical_media_probe_executed=true`。

执行器同时具备以下防护：

- 必须读取匹配当前时间线 ID、版本和 SHA-256 的 `READY` PREPARE 报告；
- 必须显式提供本地 `ffmpeg` 与 `ffprobe` 路径，并与 PREPARE 记录的路径和版本完全一致；
- Windows 下只接受 `.exe`，拒绝 `.bat/.cmd` 或脚本包装器绕开 argv 边界；
- 在执行前重新计算时间线内部哈希和所有输入资产哈希；
- 输出、计划和回执必须是互不相同的新路径，且不能覆盖素材、时间线、PREPARE 报告或工具；
- FFmpeg 固定使用 `-n`，不用 `-y`；参数以 `argv[]` 传递，`shell=false`，并受显式超时限制；
- dry-run 只做只读探测并写 `execution_status=NOT_EXECUTED` 的计划，不生成成片或回执；
- FFmpeg 失败、超时、未产生非空文件或输出 ffprobe 不匹配时写失败回执，不能被 FINAL 预检当作成功。

## 6. 配音、字幕与 Whisper 对轴

### 6.1 字幕来源优先级

1. 配音/视频供应商提供且已验证的词级或句级时间戳；
2. 对最终锁画面音轨运行 Whisper；
3. 人工对轴与复核；
4. 剧本时长估算只可生成 `SCRIPT_DRAFT`，不能用于最终验收。

Whisper 官方实现需要 FFmpeg 解码媒体，可输出 JSON、SRT、VTT 等格式，也支持词级时间戳选项。使用它时应保存：模型名、语言、任务、命令参数、源音频/成片 SHA-256、输出文件 SHA-256 和运行时间。

### 6.2 正确顺序

```text
锁定画面和主声音版本
-> 对该版本运行供应商时间戳或 Whisper
-> 校验时间码范围、顺序与越界
-> 人工逐句核对人名、术语、数字、标点、同音词和说话人
-> 生成最终 SRT/ASS
-> 合成或重新导出
-> 新成片产生新 SHA-256
-> 对新哈希重新做 ffprobe 与最终媒体 QA
```

字幕复核记录使用 `silver-showrunner/caption-review-record@1`，至少包含内容寻址的 `review_record_sha256`、`review_record_id`、字幕与成片 SHA-256、成片 artifact ID、字幕/时间线版本、复核者 actor/type/provenance、带时区的 `reviewed_at` 和明确 `scope[]`。记录哈希能发现记录修改，不能认证是谁创建了记录。导入记录因此固定标为 `IMPORTED_SELF_ASSERTED / NOT_VERIFIED`，即使自称 `PASS` 也只能进入 `REVIEW_REQUIRED`，不能自动证明人工语义复核发生过。

可选 `--caption-source-text` 会把 SRT/VTT/JSON cue 文本与本地 canonical dialogue/transcript 做 NFKC、casefold、去空白/标点后的确定性比较；不一致直接阻断。该比较机器可重算，但只证明两个文本产物一致，不证明源文本与实际声音一致。`timecode_status = PASS` 永远不能自动升级为 `semantic_accuracy = PASS`。

### 6.3 字幕与中文可读性

- 中文字体必须在实际渲染环境存在，不默认假设 Arial 能覆盖中文；
- 检查安全区、字号、行数、断句、说话人标签、颜色与背景对比；
- 不把脚本字符数/固定语速直接当作真实对轴；
- 非虚构项目额外核对专名、引文、实验条件、数据和单位；
- 每次字幕修改后都视为新版本，旧 QA 不自动继承。

## 7. 音乐、配音与声音许可

声音资产进入项目时即登记，不能等成片后补：

- 音乐需要区分词曲、录音、改编、采样、翻唱和表演相关许可；
- `royalty-free` 不是默认值，也不等于无需遵守平台、地区、期限、署名或商业范围；
- AI 配乐/配音保存生成平台、账号套餐、当时条款版本、任务记录和输出回执；
- 声音克隆、数字人或可识别个人声音保存明确同意及用途范围；
- 许可证、订单、授权书和来源页面要有本地证据 ID；只写一个网址或口头说明不足以最终 `CLEAR`；
- 素材许可脚本的分数或词表结果只能作为排查线索，不构成专业意见。

素材许可状态为 `BLOCK` 时禁止正式导出用途；`UNKNOWN/REVIEW` 或 `CLEAR` 但无证据回链时，只允许内部预览并进入复核。

## 8. FINAL 媒体预检与 QA

最终预检接受真实成片、执行回执、字幕产物、字幕语义复核证据和视觉 QA 证据：

```powershell
python scripts/media_preflight.py `
  --timeline build/media-timeline.json `
  --mode final `
  --rendered renders/final.mp4 `
  --execution-receipt receipts/render.json `
  --caption-artifact captions/final.srt `
  --caption-source-text dialogue/final-transcript.txt `
  --caption-review-evidence evidence/caption-review.json `
  --visual-qa-evidence evidence/media-qa.json `
  --out build/media-final-preflight.json
```

技术预检能检查：文件存在与大小、哈希、视频/音频流、编解码器、分辨率、总时长和字幕时间码。它不能观察画面内容。

视觉 QA 记录使用 `silver-showrunner/media-qa-review-record@1`，必须绑定当前成片 SHA-256、artifact ID 和时间线版本，记录 reviewer actor/type/provenance、带时区时间与 `scope[]`，并内嵌可解析的 `observations[]` 和 `qa_gate`；Gate 必须引用同一记录内的 Observation，且 artifact、版本和结果一致。`review_record_sha256` 覆盖整条记录，但仍不是身份签名。

`media_preflight.py` 只能验证这些结构、引用和内容绑定。没有包外信任锚时，它会输出 `VISUAL_QA_ASSERTED_ONLY`，保持 `OBSERVATION_PENDING / QA_NOT_EXECUTED`，绝不把自填记录提升成 machine-observed。人工或具备真实媒体访问能力的系统实际执行复核时还要检查：

- 黑帧、重复帧、冻结、闪烁、抖动、形变、文字乱码；
- 角色、服装、道具、场景、光线和动作连续性；
- 对白口型、配音、音效、音乐、响度、削波与静音段；
- 字幕同步、安全区、遮挡、断句和语义；
- 叙事信息释放、节奏、NCS/NRS 和首尾状态；
- 标题、封面、最终成片、AI 标识与素材许可版本是否一致。

受信系统确认的 `QA_PASSED` 只对其证据绑定的成片哈希有效。任何重新编码、换字幕、换音乐、修改画面或重新导出都会产生新哈希，必须重新建立至少受影响范围的 Observation 和 QA。当前本地预检不会把未验签的外部 `QA_PASSED` 当作该受信确认。

## 9. 与四重总检及发布门衔接

媒体 QA 后再对最终版本运行 `FINAL` 四重总检：自然表达、内容规范、素材许可来源和传播准备度。内容规范和素材许可同时也必须在 `EARLY/IN_PROCESS` 做轻检与复检，不能拖到最后才发现整段内容不可用。

媒体预检输出中的：

```text
overall_release_status = NOT_DETERMINED_BY_MEDIA_PREFLIGHT
legal_clearance_provided = false
publication_executed = false
```

是硬边界。只有后续四重总检与 `RELEASE_READINESS_GATE` 对同一最终成片、字幕、封面、标题和素材许可包通过后，项目才可标为 `RELEASE_READY`。

## 10. 本地运行

构建时间线：

```powershell
python scripts/build_media_timeline.py `
  --input media-source.json `
  --output build/media-timeline.json `
  --hash-files `
  --strict-assets
```

执行前预检：

```powershell
python scripts/media_preflight.py `
  --timeline build/media-timeline.json `
  --mode prepare `
  --out build/media-prepare.json
```

如果可执行文件未加入 PATH，可显式提供：

```powershell
python scripts/media_preflight.py `
  --timeline build/media-timeline.json `
  --mode prepare `
  --ffmpeg C:/Tools/ffmpeg/bin/ffmpeg.exe `
  --ffprobe C:/Tools/ffmpeg/bin/ffprobe.exe `
  --whisper C:/Python/Scripts/whisper.exe `
  --out build/media-prepare.json
```

Remotion 项目另加 `--remotion-project` 和 `--remotion-license-evidence`。脚本不会替用户下载依赖或同意许可。

先对严格线性基线做 dry-run：

```powershell
python scripts/render_media_ffmpeg.py `
  --timeline build/media-timeline.json `
  --prepare-report build/media-prepare.json `
  --ffmpeg C:/Tools/ffmpeg/bin/ffmpeg.exe `
  --ffprobe C:/Tools/ffmpeg/bin/ffprobe.exe `
  --dry-run `
  --plan build/ffmpeg-plan.json
```

成功输出必须写 `NOT_EXECUTED`；它只表示时间线属于支持子集、素材与工具仍匹配 PREPARE，并且参数计划已编译。

确认计划后真实执行：

```powershell
python scripts/render_media_ffmpeg.py `
  --timeline build/media-timeline.json `
  --prepare-report build/media-prepare.json `
  --ffmpeg C:/Tools/ffmpeg/bin/ffmpeg.exe `
  --ffprobe C:/Tools/ffmpeg/bin/ffprobe.exe `
  --plan build/ffmpeg-executed-plan.json `
  --receipt receipts/ffmpeg-render.json `
  --timeout 3600
```

输出位置不能用命令行临时改写，只能使用时间线中已经审批和预检的 `render_job.output_resolved_path`。已有输出不会覆盖；需要重新导出时先产生新的时间线版本和新输出路径。

运行内置回归：

```powershell
python scripts/build_media_timeline.py --self-test
python scripts/media_preflight.py --self-test
python scripts/render_media_ffmpeg.py --self-test
```

Windows PowerShell 5 的原生程序管道可能损坏中文；优先用 UTF-8 文件参数，不通过管道传入项目 JSON。

## 11. 当前主机能力快照

2026-08-15 本次修复复验时：

- 使用显式本地 FFmpeg/ffprobe 9.0 路径，对 2 秒 320×240 H.264 + AAC 测试媒体真实执行严格线性基线；正常音调输入以 `LOUDNORM_SINGLE_PASS` 成功，静音 AAC 以 `PRESERVE_NEAR_SILENCE` 成功，两者退出码均为 0、输出均含视频/音频流并通过 ffprobe；
- 修复前同一静音 AAC 在 `loudnorm` 报 `Input contains (near) NaN/+-Inf` 并返回原生 `-22`；旧代码把 Windows 返回值误记为 `4294967274`。修复后既避免把近静音送入 loudnorm，也统一把 32 位无符号原生错误码还原为有符号值；
- 使用真实成片、真实 ffprobe 与真实渲染器回执复现了伪造字幕/视觉 QA 攻击：修复前错误文本 SRT 加自填 `PASS / QA_PASSED` 得到 FINAL `PASS / OBSERVED / QA_PASSED`；修复后同一输入固定为 `REVIEW / EXECUTION_PENDING / OBSERVATION_PENDING / QA_NOT_EXECUTED`，所有主观 truth flag 为 false；
- 未执行 Whisper、Remotion、真实项目人工视觉/声音/连续性 QA、受信签名验签或平台发布。因此这只是最小技术执行 Pilot，不是完整 Production Validation；主观 QA 仍为 `QA_NOT_EXECUTED`。

能力快照会随环境改变。每次真实项目都要重新运行 PREPARE，不能把本次缺失或存在情况永久写进供应商能力结论。

## 12. 本地模块审计结论

### `aladin-drama-edit`

可吸收：结构化轨道、字幕/配音/音乐进入同一时间线、从时间线编译 FFmpeg 执行计划。  
未原样吸收：它主要生成脚本而非实际导出回执；原实现的总时长、变长转场偏移、音频起点、外部配音输入、无音轨素材、Windows 参数转义和输出复核存在不足。Alpha.7 以绝对时间、参数数组、ffprobe 和哈希回执替代。

### `aladin-drama-subtitle`

可吸收：SRT/ASS 双产物、分镜到字幕草稿的结构。  
未原样吸收：依据剧本时长和固定语速估算不是实际对轴；不具备 ASR；默认字体和 ASS 转义不够稳；最后一句结束时间也不能代表成片总时长。Alpha.7 将其定位为 `SCRIPT_DRAFT`，最终改用供应商时间戳/Whisper加语义复核。

### `aladin-drama-music-rights`

可吸收：音乐许可分类、平台/地区/期限/署名字段和风险台账。  
未原样吸收：未知来源不得默认 `royalty_free`；缺失发布日期不得静默用当天改变结论；平台名称不能只做脆弱的精确字符串匹配；固定风险分不能代替许可证、证据文件或专业复核。Alpha.7 对缺证据 `CLEAR` 自动降为复核。

以上审计只吸收方法，不复制品牌、旧工具清单、旧平台断言、固定阈值或未经验证的能力承诺。

## 13. 官方能力与许可来源

- FFmpeg 官方命令文档：https://ffmpeg.org/ffmpeg.html
- ffprobe 官方文档：https://ffmpeg.org/ffprobe.html
- OpenAI Whisper 官方仓库与 README：https://github.com/openai/whisper
- Whisper 官方 CLI 实现：https://github.com/openai/whisper/blob/main/whisper/transcribe.py
- Remotion 官方渲染 CLI：https://www.remotion.dev/docs/cli/render
- Remotion 官方 AI Skills：https://www.remotion.dev/docs/ai/skills
- Remotion 官方许可：https://github.com/remotion-dev/remotion/blob/main/LICENSE.md
- Remotion 官方定价/用途说明：https://www.remotion.dev/

这些链接证明工具公开能力或许可入口，不证明本机已安装、当前项目已满足许可、输出已执行或平台已接受。
