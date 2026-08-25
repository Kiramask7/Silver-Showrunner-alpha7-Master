# 第三方来源、许可与吸收边界

本文件只记录本轮中文传播与四重预检模块实际审阅过的来源。未列入的仓库或 Skill 不表示已经复核、安装或授权。

## 1. MrGeDiao / shuorenhua

- 项目：https://github.com/MrGeDiao/shuorenhua
- 审计提交：`a9145e38875f116d65235a728cd0048b7c3d9003`
- 审计日期：2026-08-14
- 仓库声明版本：v2.3.0
- 许可：MIT
- 版权所有：Copyright (c) 2026 MrGeDiao
- 使用方式：仅吸收“先保护事实与关系，再做自然化”“分场景控制改写强度”“保真回读与残留味回读分开”的方法；本项目脚本为另行编写的实现，没有复制其短语表、评测集或自动化代码。
- 安全结论：主 Skill 和参考文档是提示词/文档资源；`automation/check_repo.py` 会执行本地子进程并动态编译执行仓库内 `hard_metrics.py`，`automation/gen_star_history.py` 会调用 `gh api graphql`。这些自动化脚本未打包、未执行、未成为运行依赖。
- 保留要求：如果后续复制或分发该仓库的实质代码/文本，必须同时保留 MIT 版权声明与许可文本。

## 2. Alireza Rezvani / claude-skills / copywriting

- 项目：https://github.com/alirezarezvani/claude-skills
- 审计子路径：`marketing-skill/skills/copywriting/`
- 审计提交：`aa8d778811a557a2c28ccadda4cf3d0bd028a4cc`
- 审计日期：2026-08-14
- 子技能声明版本：1.0.0
- 许可：MIT
- 版权所有：Copyright (c) 2025 Alireza Rezvani
- 使用方式：仅吸收“先确认受众、行动、问题、收益、疑虑与证据”“清晰优先于花巧”“功能必须连接用户结果”“标题、正文和行动一致”的一般写作原则；没有复制页面模板或评分脚本。
- 安全结论：审计子路径只有 Markdown 与一个 Python 标准库标题评分器，没有网络、子进程或动态执行。该评分器以英文 power words、固定 6–12 词、数字和任意权重评分，不适用于中文比赛文案，未接入。
- 保留要求：如果后续复制或分发该仓库的实质代码/文本，必须同时保留 MIT 版权声明与许可文本。

## 3. 本地 Aladin 模块

审计路径：

- `C:/Users/kiram/.codex/skills/aladin-drama-comply`
- `C:/Users/kiram/.codex/skills/aladin-drama-cover`
- `C:/Users/kiram/.codex/skills/aladin-drama-edit`
- `C:/Users/kiram/.codex/skills/aladin-drama-music-rights`
- `C:/Users/kiram/.codex/skills/aladin-drama-subtitle`

共同情况：

- 各 `SKILL.md` 声明 MIT；模块目录未包含单独的 `LICENSE` 文件，本轮无法从包内证明完整再分发许可文本；
- Python 脚本使用标准库，静态扫描未发现网络、子进程、动态执行或注册表操作；
- 内容规范、封面、音乐样例流水线已在临时目录实际运行，能够产生 JSON、Markdown、HTML/CSV；
- 只作为审计参考，没有复制脚本、规则表或可执行工具，也没有把这些本地 Skill 打入发布包。

吸收：

- 多来源归一和命中位置；
- 素材许可凭证、期限、平台、用途、署名与回灌字段；
- 封面、标题与正片资产一致性；
- 标准时间线先登记镜头、字幕、配音、音乐和依赖，再交给具体渲染适配器；
- 从已锁定台词生成字幕草稿，但最终对轴仍以真实锁定媒体和人工语义复核为准；
- 明确“预检不能替代平台复核或专业意见”。

拒绝吸收：

- 没有当前官方证据的固定平台权重和 100 分门槛；
- “封面承担 80% 点击”“0.5 秒”“CTR 差 2–5 倍”等无来源精确推广陈述；
- 用 power words、身份词、反转词和固定加分预测点击；
- 用 MD5 seed 承诺身份一致性；
- 把未核验登记编号写成已经通过；
- 只扫描文本就声称视频画面符合内容规范。

## 4. 媒体工具官方资料

以下资料只用于确认接口职责和设计可替换的媒体执行层：

- FFmpeg 项目与命令行文档：https://ffmpeg.org/ 与 https://ffmpeg.org/ffmpeg.html
- ffprobe 文档：https://ffmpeg.org/ffprobe.html
- OpenAI Whisper 官方仓库：https://github.com/openai/whisper
- Remotion 官方文档与渲染命令：https://www.remotion.dev/docs/ 与 https://www.remotion.dev/docs/cli/render

吸收边界：FFmpeg/ffprobe 只作为转码、探测、合成和验收的可选本地执行器；Whisper 只作为锁定媒体后的转写/对轴候选；Remotion 只作为程序化图形与渲染适配器。当前发布包没有复制或分发 FFmpeg/ffprobe 二进制、Whisper 代码或模型权重、Remotion 包或任何第三方可执行工具；用户环境是否安装、版本是否适用及真实输出质量都必须另行预检和取证。官方链接不是运行成功证据，也不替代各项目的许可与授权范围核对。

## 5. 本地 Tomato Novelist

- 路径：`C:/Users/kiram/.codex/skills/tomato-novelist`
- 许可：目录中未发现 `LICENSE`，`SKILL.md` 也未声明许可；不得复制或分发其实质文本和模板。
- 安全结论：唯一 Python 文件没有网络或子进程调用，但文件头混入 YAML frontmatter，Python 3.12 AST 解析失败，不能作为可执行依赖。
- 使用方式：只把“尽早建立冲突/问题”“情绪有变化”“结尾给继续观看理由”视为一般叙事启发，不复制平台模板。
- 拒绝吸收：固定 2200–2800 字、黄金三行、书架页 50% 点击、爆款基因、评论诱导和无来源质量阈值。

## 6. mosonlab / open-novel-fanqie

- 项目：https://github.com/mosonlab/open-novel-fanqie
- 核对日期：2026-08-22
- 许可：MIT
- 版权声明：Copyright (c) 2026 novelcatch
- 使用方式：只吸收“正文前先有可演的场景节拍”和“人工拍板后再继续”的一般工艺思路；本项目相关文字为独立重写，没有复制其 Skill、代码、模板、演示文稿或固定平台参数。
- 拒绝吸收：对标仿写参数、固定字数、爆款判断、平台收益或任何与银幕总控通用导演任务无关的规则。
- 保留要求：如后续复制或分发该项目的实质文本、代码或模板，须同时保留 MIT 版权与许可声明。

## 7. Narcooo / InkOS

- 项目：https://github.com/Narcooo/inkos
- 核对日期：2026-08-22
- 核对版本：官方仓库当日公开版，`package.json` 声明 1.7.2
- 许可：AGPL-3.0-only
- 使用方式：只参考“风格样本应绑定项目”、“长任务保留可恢复状态”、“研究资料不直接污染故事事实”等一般设计思路。本项目没有复制其词表、禁用句式、Skill 文本、代码、测试或提示词。
- 安全与许可边界：InkOS 不进入银幕总控运行包，不成为依赖，不运行其安装、联网、模型调用或发布流程。如未来需要复制、改作、嵌入或网络部署其 AGPL 内容，必须先独立复核开源义务。

## 8. zhouwei713 / realistic-video-prompting

- 项目：https://github.com/zhouwei713/seedance-prompt
- 本地审阅路径：`C:/Users/kiram/.codex/skills/seedance-prompt`
- 核对日期：2026-08-22
- Skill 声明版本：1.1.2
- 许可：MIT；本地包包含 `LICENSE`
- 使用方式：吸收“先确定素材来源身份”“把抽象氛围翻译为可观察现象”“设备特征应来自真实成像/操作机制”“音画元素互相对应”的一般视频提示词原则。CONTINUUM 将其改写为条件路线：只有用户明确需要手机随拍、DV、监控、纪录片等素材身份时才加载对应物理特征，不把纪实缺陷套到全部题材。
- 独立扩展：CONTINUUM 的剧本来源覆盖、逐字对白、说话人/顺序、四层 Prompt、全量交付、分段 handoff、本地创作预检和 Production Validation 边界均为银幕总控自己的合同与实现。
- 未复制：没有复制该 Skill 的七段模板、设备参数包、现成句库、清单正文或代码；没有把第三方文件打入发布包。

## 9. Silver Longform v5.1.0

- 本地来源：`Silver-Longform-Continuity-Video-Director-Skill-v5.1.0-PURE.zip`
- 核对日期：2026-08-23
- 许可：压缩包中未发现独立许可文件，不把它当作可自由再分发的第三方代码包。
- 使用方式：同属 Silver 工作流的设计参考，只吸收逐字对白、发声时长、跨镜连续声音、对白节拍先于镜头和计划/观察分离的方法；Master v1.1.3 的制作合同、Schema、检查器和测试为独立实现。
- 未复制：没有把 Longform 的脚本、模板、合同文件或成品单文件打入 Master 发布包。

## 10. Emily2040 / Seedance 2.0 Skill OS v6.7.0

- 项目：https://github.com/Emily2040/seedance-2.0
- 本地审阅包：`C:/Users/kiram/Downloads/seedance-2.0-main.zip`
- 核对日期：2026-08-23
- 核对版本：v6.7.0
- 许可：MIT
- 版权所有：Copyright (c) 2026 Iamemily2050 (@iamemily2050)
- 使用方式：吸收一个主要动作和可见终点、参考素材单一职责与禁止串线、已接受真实末态优先、当前片段局部编译及单变量重试的一般方法；Master 使用自己的术语、数据合同和检查器。
- 未复制：没有把该仓库的 Skill、参考文件、脚本、图片或测试直接打入 Master 包。
- 保留要求：如未来复制或分发其实质文本或代码，须保留 MIT 版权与许可声明。

## 11. TateZhouSiu / create-storyboard-skill

- 项目：https://github.com/TateZhouSiu/create-storyboard-skill
- 核对日期：2026-08-23
- 许可：MIT
- 版权所有：Copyright (c) 2026 Tate Zhou
- 使用方式：吸收相邻镜头接力、可剪辑连续、主剪法与备用切法、动作/视线/道具/遮挡/声音桥接的一般方法；Master 的交接字段和验证逻辑为独立实现。
- 未复制：没有复制其脚手架、模板、最终板式、脚本或固定时长建议，也没有把仓库文件打入发布包。
- 保留要求：如未来复制或分发其实质文本或代码，须保留 MIT 版权与许可声明。

## 12. chenhuiIMBA / kiro-ai-manju

- 项目：https://github.com/chenhuiIMBA/kiro-ai-manju
- 核对日期：2026-08-23
- 许可：仓库根目录未发现明确的 `LICENSE`，Skill frontmatter 也未声明许可。
- 使用方式：只把“每步更新进度、资产与成本，项目可以跨会话恢复”视为一般管理思想，并在 Master 中独立设计字段、Schema、检查器和自然中文说明。
- 未复制：没有复制其代码、阶段模板、目录模板、提示词、命令、固定平台依赖或原文表达。
- 拒绝吸收：固定供应商、未经本轮核验的模型能力/价格、自动付费调用、与 Master 现有阶段和用户确认边界冲突的规则。

## 13. 许可与安全规则

1. 第三方“声明 MIT”不等于可以丢掉版权和许可声明。
2. 许可证不明时，只学习一般思想，不复制表达、表格、代码、模板或素材。
3. 不运行未审计的一键安装、远程脚本、动态执行和外部发布动作。
4. 第三方固定分数只能作为其作者的启发式设计，不能升级为 Silver 官方事实。
5. 平台、适用规则、供应商和价格信息在每个真实项目中按当前日期重新核查。
