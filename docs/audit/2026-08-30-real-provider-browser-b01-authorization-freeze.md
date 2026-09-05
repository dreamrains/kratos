# B01 上传绑定与留存闭环真实 Provider 浏览器授权冻结

日期：2026-08-30

## 当前停止点

本冻结只准备 **1 次真实 Provider、1 次真实浏览器 Web 用户旅程**，本身不构成授权。旧的上传绑定授权已经消费且不得复用；本批次新增真实 Provider 调用当前为 **0**。

零调用预检已经返回 `ready=true`，并确认冻结 workspace、sessions、Provider 收据和最终报告均不存在。只有用户明确发送本文末尾的完整精确授权文案后，才可启动本批次。

本冻结不授权 Git 写操作、提交、推送、部署、staging、production、删除原会话 `bc52915a96a4` / `365ef1d3ea3e`，或处理既有 `artifacts/` 与无关 `tmp/` 内容。

## 冻结事实

| 项目 | 冻结值 |
|---|---|
| release source digest | `sha256:ad7e16fc46ecd38297e5e3dad12dc94d390fb5ec0cfb5cf90dad3f190bc4b00a`（345 项） |
| 模型 | `openai/deepseek-v4-flash` |
| candidate | `docs/audit/2026-08-29-real-provider-browser-b01-candidate.json` |
| candidate SHA-256 | `sha256:3b1fde1b008e129efb34197cb01dd3fb2939be4df98f48ef6703f366fda00556`（CRLF 规范化为 LF 后） |
| 数据 | `reference/test_doc/游戏B留存.xlsx` |
| 数据 SHA-256 | `sha256:63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0` |
| prompt SHA-256 | `sha256:554a731ac44430a9bfa3515d568e2fcd26c8d03338c8316e90645c0922b46a3c` |
| oracle SHA-256 | `sha256:edaaf68547c0cd71d053803465c8d1a145ff6de3ccc2ceb93a7104d4037ae046`（canonical UTF-8 JSON） |
| 计数启动器 | `tmp/real-provider-browser-b01-counted-server.py` |
| 计数启动器 SHA-256 | `sha256:91f2b7bb6c32e759f8fc4f6adf89d22e01afbc5dffe3cce5d601427ff17c98dc`（CRLF 规范化为 LF 后） |

精确用户提示词：

```text
请先检查这份留存数据的质量与字段结构，然后比较幂律、指数和对数留存曲线，给出最佳公式、参数、拟合优度和限制；同时生成一张包含实际留存均值与最佳拟合值两条曲线的对比图，并把关键结论记录为可核查证据。
```

## 冻结的唯一 Web 用户旅程

1. 在 1440×1000 桌面视口打开当前源码新会话，确认页面静态资源带当前内容哈希。
2. 上传冻结的 `游戏B留存.xlsx`，核验 opaque upload ticket、大小与 SHA-256；在首个模型请求前核验文件已归属新会话，并确定性加载为 `游戏B留存__raw` / `游戏B留存`（62×13）。
3. 发送一次冻结提示词。若且仅若出现与当前留存拟合匹配的 `method_confirmation`，选择“按此方法继续”；确认恢复期间核验 composer 不可发送。
4. 等待真实模型、工具调用、最终回答、证据、图表和任务完成。必须成功执行 `detect_data_quality`、`curve_fitting`、`record_evidence_record`、`create_chart`，工具 error event 为 0。
5. 在浏览器直接核验对比图恰有 `actual_retention` 与 `power_fit` 两条 trace，标题与图例一致。
6. 核验 Workbench 顶部显示精确会话 ID，页面根区域不可下拉出空白，主页面和图表页 error/warn 日志均为 0。
7. 刷新同一会话，核验最终回答、证据、双曲线图、任务和会话归属恢复；用户气泡显示友好 `confirm_method`，不得显示 `<confirmation_response …>` 协议文本或“（无回复内容）”空气泡。
8. 通过页面导出一次 HTML 会话，并核验导出物归属当前会话。

不得增加追问、第二分析回合、补充旅程、失败重跑或临时 oracle。

## 调用与失败纪律

- 全部主请求与辅助 LLM 请求共用硬计数器，总上限 **32 次**；上限是停止护栏，不是调用目标。
- 主生成初始 `max_tokens=8000`；辅助意图/方法/质量请求只允许冻结的 `max_tokens=300` 或 `800`。
- `temperature=0.0`、`timeout=120s`、`num_retries=0`。
- 仅主生成出现“无可见正文且 `finish_reason=length`”时，允许产品现有的 `8000 → 32000 → 128000` 有界升档，每档每个逻辑调用至多一次；辅助请求不升档。
- 禁止 stream→sync 补发、模型切换、Provider fallback、传输失败重试、失败后重跑和补充旅程。
- 任一预检项不匹配则 Provider 0；调用异常、达到计数上限、非预期确认、文件恢复提问、工具错误、单序列伪对比图或任何 oracle 失败均立即停止，并记录实际已消费次数。
- 本次旅程无论通过或失败，授权都立即消费，不得复用。

## 验收 oracle

1. 上传票据不泄露服务器路径；文件在首个模型请求前完成会话归属与确定性加载，不生成共享 inbox 副本。
2. 不得出现“文件不存在、重新上传、提供完整路径”类提问或 `ask_user_question`。
3. 最终回答包含 `62`、`0.18800129`、`-0.71667274`、`0.98240474`、排除 `6` 个零值点，并明确“描述性拟合，不作因果解释，不向未观测周期外推”。
4. 至少 1 条可核查证据；至少 1 个图表产物；对比图浏览器 trace 必须为 `actual_retention` 与 `power_fit` 两条。
5. Workbench 精确显示会话 ID；确认恢复期间 composer 禁用；页面无根区域空白滚动。
6. 刷新后结果、证据、图表、任务、友好确认气泡和导出物均恢复；协议文本与空气泡不可见。
7. 浏览器主页面和图表页 error/warn 日志均为 0；Provider 收据完整记录所有已启动请求。

## 唯一写入路径

- 隔离 workspace：`tmp/real-provider-browser-matrix-b01/workspace`
- 隔离 sessions：`tmp/real-provider-browser-matrix-b01/sessions`
- Provider 精确计数收据：`tmp/real-provider-browser-matrix-b01/provider-calls.json`
- 最终报告：`docs/audit/2026-08-29-real-provider-browser-b01-report.json`

## 授权前证据

- 定向回归：`68 passed in 43.53s`；补充 Workbench/SSE 合同：`11 passed in 0.78s`。
- 当前源码全量零 Provider 回归：`2363 passed, 9 skipped, 39 warnings in 415.92s`。
- 当前源码零 Provider 真实浏览器完整 B01：上传成功；确认恢复期间 composer 禁用；最终公式、证据、任务和 HTML 导出完成；刷新后协议文本与空气泡不可见；双曲线 trace 为 `power_fit` / `actual_retention`；主页面与图表页 error/warn 均为 0。
- 零调用预检：source / candidate / launcher / prompt / oracle / data hash 全匹配，`call_cap=32`；预检后冻结 workspace、sessions、收据、报告均不存在。

## 精确授权文案

```text
我授权 B01 上传绑定与留存闭环的真实 Provider 完整浏览器验收：仅在 release source digest sha256:ad7e16fc46ecd38297e5e3dad12dc94d390fb5ec0cfb5cf90dad3f190bc4b00a 上，使用 openai/deepseek-v4-flash、candidate sha256:3b1fde1b008e129efb34197cb01dd3fb2939be4df98f48ef6703f366fda00556、数据 sha256:63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0、prompt sha256:554a731ac44430a9bfa3515d568e2fcd26c8d03338c8316e90645c0922b46a3c、oracle sha256:edaaf68547c0cd71d053803465c8d1a145ff6de3ccc2ceb93a7104d4037ae046 和计数启动器 sha256:91f2b7bb6c32e759f8fc4f6adf89d22e01afbc5dffe3cce5d601427ff17c98dc，执行 2026-08-30-real-provider-browser-b01-authorization-freeze.md 冻结的 Web 用户旅程恰好 1 次；全部主请求与辅助请求共用硬上限 32 次，temperature=0、timeout=120 秒、num_retries=0，主生成初始 max_tokens=8000，辅助请求仅允许 max_tokens=300 或 800，仅主生成无可见正文且 finish_reason=length 时允许按 8000→32000→128000 每档每个逻辑调用至多一次升档；禁止 stream→sync 补发、模型切换、Provider fallback、失败重试和补充旅程。预检任一不匹配则零调用；执行异常、达到上限、非预期确认、文件恢复提问、工具错误、单序列伪对比图或任一 oracle 失败时立即停止并记录实际已消费次数。只允许写入冻结的隔离 workspace、sessions、Provider 计数收据和 docs/audit/2026-08-29-real-provider-browser-b01-report.json；不授权 Git 写操作、部署、staging、production 或删除原会话。
```
