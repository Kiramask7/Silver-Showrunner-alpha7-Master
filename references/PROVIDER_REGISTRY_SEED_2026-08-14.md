# 动态供应商注册表种子 — 2026-08-14

这是一份带日期的官方资料种子，不是永久推荐或静态默认。真实项目必须重新核验用户所在地区、产品入口、账号权限、当前版本和任务 Pilot。

| 供应商 | 显示名 / 别名 | 可核验模型标识 | 重要边界 |
|---|---|---|---|
| OpenAI | GPT Image 2；ChatGPT 端称 ChatGPT Images 2.0 | `gpt-image-2`；快照 `gpt-image-2-2026-04-21` | 产品名与 API ID 分开；图像生成/编辑，不把它登记为视频模型。 |
| Google | Nano Banana Pro / Gemini 3 Pro Image | `gemini-3-pro-image` | Nano Banana Pro 是别名；地区与企业入口权限单独记录。 |
| BytePlus | Dola Seedream 5.0 Pro | `dola-seedream-5-0-pro-260628` | 不与 Seedream 5.0 Lite 混用；地区入口按当前 ModelArk 资料核验。 |
| BytePlus / ByteDance | Dreamina Seedance 2.0 及 Fast / Mini | 各变体使用各自 ID | 不能只写“Seedance”；不同产品入口、地区和服务条款分别登记。 |
| MiniMax | MiniMax H3 | API ID 未经当前 catalog 核验时保持 `null` | 官方博文只证明产品显示名与模型名；不得把 `MiniMax-H3` 据此写成 API model ID。H3 不是 Hailuo 2.3 的别名，也不替代单独的 TTS 供应商记录。 |
| Kuaishou | Kling AI 3.0 系列 | API ID 未经当前 catalog 核验时保持 `null` | Video / Video Omni / Image / Image Omni 分开；网页可用不等于 API ID 已公开。 |

官方来源：

- OpenAI ChatGPT Images 2.0 发布页：<https://openai.com/index/introducing-chatgpt-images-2-0/>
- OpenAI API 模型页：<https://developers.openai.com/api/docs/models/gpt-image-2>
- Google：<https://ai.google.dev/gemini-api/docs/models/gemini-3-pro-image>
- BytePlus Seedream：<https://docs.byteplus.com/en/docs/ModelArk/1824121>
- ByteDance Seedance：<https://seed.bytedance.com/en/seedance2_0>
- BytePlus Seedance：<https://docs.byteplus.com/en/docs/ModelArk/2291680>
- MiniMax H3：<https://www.minimax.io/blog/minimax-h3>
- Kling 3.0：<https://ir.kuaishou.com/news-releases/news-release-details/kling-ai-launches-30-model-ushering-era-where-everyone-can-be>

Registry 仍须记录 `checked_at`、`surface`、`marketing_aliases`、`api_model_id`、`snapshot_id`、`availability_kind`、`region`、`access`、来源证据和本项目 Pilot。价格、稳定性、重试次数和“最好”结论不能从本表推出。
