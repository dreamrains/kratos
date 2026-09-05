# M01-A03 上传绑定与留存闭环真实 Provider 浏览器授权冻结

日期：2026-08-30

## 当前停止点

本冻结准备矩阵场景 `M01` 的第 3 次独立授权尝试 `A03`，只允许 **1 次真实 Provider、1 次真实浏览器 Web 用户旅程**。本文与零调用预检本身不构成执行授权。

旧尝试均已消费且不得复用：`M01-A01`（旧名 B01）在启动变量预检阶段零调用退出；`M01-A02`（旧名 B02）完成上传绑定和数据加载，但因服务运行在网络受限环境而产生 2 次连接失败。A03 使用全新的 candidate、启动器、workspace、sessions、收据和报告路径。

本冻结不授权 Git 写操作、提交、推送、部署、staging、production、删除原会话 `bc52915a96a4` / `365ef1d3ea3e`，或处理既有 `artifacts/` 与无关 `tmp/` 内容。

## 根修复基线

- 新增可复用 `StrictProviderCallGuard`，主请求、辅助请求和流式请求共享同一个首错熔断状态。
- 任一真实 Provider 请求失败后，后续逻辑调用只增加 `blocked_attempts`，不得增加 `calls` 或触达底层 Provider。
- 并发 Provider 调用、模型变化、token 越界和调用上限均在底层请求前 fail-closed。
- 收据 schema v2 记录 started/finished 时间、首个失败 ordinal、终止原因、真实调用数和本地拦截数。
- Web 启动器改为调用 tracked 通用引导层，不再复制独立计数实现；无头 Gate C 的主/辅助请求也共享粘滞失败语义。
- 真实服务启动必须通过网络可用的已批准执行路径，并设置 `DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED=1`；该标记只作冻结执行确认，不替代执行工具的网络权限审批。

## 冻结事实

| 项目 | 冻结值 |
|---|---|
| matrix case / attempt | `M01-A03` |
| release source digest | `sha256:e0e71952b4e5ba8ef8c6cb0f9944eaa20f20c471fff5dfcaf1a433b7702882c1`（349 项） |
| 模型 | `openai/deepseek-v4-flash` |
| candidate | `docs/audit/2026-08-30-real-provider-browser-m01-a03-candidate.json` |
| candidate SHA-256 | `sha256:4623060fbae28ad05fe427c9fac36c5b1f2f08595ede25e202021d0c7ae9028e`（CRLF 规范化为 LF 后） |
| 数据 | `reference/test_doc/游戏B留存.xlsx` |
| 数据 SHA-256 | `sha256:63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0` |
| prompt SHA-256 | `sha256:554a731ac44430a9bfa3515d568e2fcd26c8d03338c8316e90645c0922b46a3c` |
| oracle SHA-256 | `sha256:edaaf68547c0cd71d053803465c8d1a145ff6de3ccc2ceb93a7104d4037ae046`（canonical UTF-8 JSON） |
| 计数启动器 | `tmp/real-provider-browser-m01-a03-counted-server.py` |
| 计数启动器 SHA-256 | `sha256:49049da5cd936b6c23b0494f62caa207034f5240418b01339ee77a5b4e8aea94`（CRLF 规范化为 LF 后） |
| 本地端口 | `127.0.0.1:5190` |

精确用户提示词：

```text
请先检查这份留存数据的质量与字段结构，然后比较幂律、指数和对数留存曲线，给出最佳公式、参数、拟合优度和限制；同时生成一张包含实际留存均值与最佳拟合值两条曲线的对比图，并把关键结论记录为可核查证据。
```

## 冻结的唯一 Web 用户旅程

1. 在 1440×1000 桌面视口打开当前源码新会话，确认页面静态资源带当前内容哈希。
2. 上传冻结的 `游戏B留存.xlsx`，核验 opaque upload ticket、大小与 SHA-256；在首个模型请求前核验文件已归属新会话，并确定性加载为 `游戏B留存__raw` / `游戏B留存`（62×13）。
3. 发送一次冻结提示词。若且仅若出现与当前留存拟合匹配的 `method_confirmation`，选择“按此方法继续”；确认恢复期间核验 composer 不可发送。
4. 等待真实模型、工具调用、最终回答、证据、图表和任务完成。目标工具为 `detect_data_quality`、`curve_fitting`、`record_evidence_record`、`create_chart`。
5. 在浏览器直接核验对比图 `actual_retention` 与 `power_fit` trace、标题与图例。
6. 核验 Workbench 顶部会话 ID、页面根滚动及主页面/图表页 error/warn 日志。
7. 刷新同一会话，核验最终回答、证据、图表、任务和会话归属恢复；检查友好 `confirm_method` 气泡、协议文本和空气泡。
8. 通过页面导出一次 HTML 会话，并核验导出物归属当前会话。

不得增加提示词、第二分析回合、补充旅程或临时 oracle。

## 调用、熔断与网络纪律

- 全部主请求与辅助 LLM 请求共用硬计数器，总上限 **32 次**；上限是停止护栏，不是调用目标。
- 主生成初始 `max_tokens=8000`；辅助请求仅允许 `max_tokens=300` 或 `800`。
- `temperature=0.0`、`timeout=120s`、`num_retries=0`。
- 仅主生成出现“无可见正文且 `finish_reason=length`”时，允许产品现有的 `8000 → 32000 → 128000` 有界升档，每档每个逻辑调用至多一次；辅助请求不升档。
- 禁止 stream→sync 补发、模型切换、Provider fallback、传输失败重试和补充旅程。
- 首个 Provider 失败后立即全局熔断；所有后续产品调用必须本地拒绝，不得新增真实调用计数。
- 计数服务只能通过明确批准的网络可用执行路径启动，并同时设置 `DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED=1`；不得在默认网络受限执行环境中启动。

## 继续收集与严重阻断

同一冻结旅程中，以下非阻断 oracle 偏差只记录、不停止，继续完成剩余已冻结步骤：单序列或图例错误、Workbench 标题错误、根区域空白滚动、刷新确认气泡/协议文本/空气泡错误、console warning/error、刷新恢复或导出归属失败。继续收集不得增加提示词、模型回合或旅程。

以下属于严重阻断并立即停止：任一预检不匹配、Provider 传输/超时/策略/并发失败、达到调用上限、上传摘要或会话归属失败、需要新用户选择的非预期确认、文件恢复提问、阻止后续冻结页面状态产生的工具或流程错误。停止时记录真实 `calls` 与本地 `blocked_attempts`。

## 验收 oracle

1. 上传票据不泄露服务器路径；文件在首个模型请求前完成会话归属与确定性加载，不生成共享 inbox 副本。
2. 不得出现“文件不存在、重新上传、提供完整路径”类提问或 `ask_user_question`。
3. 最终回答包含 `62`、`0.18800129`、`-0.71667274`、`0.98240474`、排除 `6` 个零值点，并明确“描述性拟合，不作因果解释，不向未观测周期外推”。
4. 至少 1 条可核查证据、1 个图表产物；对比图目标 trace 为 `actual_retention` 与 `power_fit`。
5. Workbench 精确显示会话 ID；确认恢复期间 composer 禁用；页面无根区域空白滚动。
6. 刷新后结果、证据、图表、任务、友好确认气泡和导出物均恢复；协议文本与空气泡不可见。
7. 浏览器主页面和图表页 error/warn 日志目标为 0；Provider 收据完整记录所有已启动和本地拦截请求。

## 唯一写入路径

- 隔离 workspace：`tmp/real-provider-browser-m01-a03/workspace`
- 隔离 sessions：`tmp/real-provider-browser-m01-a03/sessions`
- Provider 精确计数收据：`tmp/real-provider-browser-m01-a03/provider-calls.json`
- 最终报告：`docs/audit/2026-08-30-real-provider-browser-m01-a03-report.json`

## 授权前证据

- 严格计数、通用引导层和无头计数客户端定向回归：`32 passed`。
- 当前源码全量零 Provider 回归：`2372 passed, 9 skipped, 40 warnings in 440.41s`。
- M01-A02 现场确认上传绑定、会话归属、`游戏B留存__raw` / `游戏B留存` 及 62×13 数据加载均先于 Provider 尝试完成。
- M01-A03 零调用预检返回 `ready=true`；source / candidate / launcher / prompt / oracle / data hash、模型配置、API 配置存在性和 `call_cap=32` 均匹配；预检后 workspace、sessions、收据和报告均不存在。

## 精确授权文案

```text
我授权 M01-A03 上传绑定与留存闭环的真实 Provider 完整浏览器验收：仅在 release source digest sha256:e0e71952b4e5ba8ef8c6cb0f9944eaa20f20c471fff5dfcaf1a433b7702882c1 上，通过已批准的网络可用执行路径并设置 DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED=1，使用 openai/deepseek-v4-flash、candidate sha256:4623060fbae28ad05fe427c9fac36c5b1f2f08595ede25e202021d0c7ae9028e、数据 sha256:63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0、prompt sha256:554a731ac44430a9bfa3515d568e2fcd26c8d03338c8316e90645c0922b46a3c、oracle sha256:edaaf68547c0cd71d053803465c8d1a145ff6de3ccc2ceb93a7104d4037ae046 和计数启动器 sha256:49049da5cd936b6c23b0494f62caa207034f5240418b01339ee77a5b4e8aea94，执行 2026-08-30-real-provider-browser-m01-a03-authorization-freeze.md 冻结的 Web 用户旅程恰好 1 次；全部主请求与辅助请求共用硬上限 32 次，temperature=0、timeout=120 秒、num_retries=0，主生成初始 max_tokens=8000，辅助请求仅允许 max_tokens=300 或 800，仅主生成无可见正文且 finish_reason=length 时允许按 8000→32000→128000 每档每个逻辑调用至多一次升档；禁止 stream→sync 补发、模型切换、Provider fallback、失败重试、额外提示词和补充旅程。首个 Provider 失败后必须全局熔断，后续逻辑调用只允许本地拒绝且不得增加真实调用数。单序列/图例、Workbench 标题、根滚动、确认投影、console、刷新恢复或导出归属等非阻断 oracle 失败只记录并继续完成同一冻结旅程的剩余步骤；预检不匹配、Provider 传输/超时/策略/并发失败、调用上限、上传完整性或会话归属失败、需要新用户选择的非预期确认、文件恢复提问或阻止后续页面状态产生的工具/流程错误属于严重阻断，立即停止并记录真实 calls 与 blocked_attempts。只允许写入冻结的隔离 workspace、sessions、Provider 计数收据和 docs/audit/2026-08-30-real-provider-browser-m01-a03-report.json；不授权 Git 写操作、部署、staging、production 或删除原会话。
```
