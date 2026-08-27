# Gate D `5583e095` 浏览器与收据汇总（历史快照）

初始日期：2026-08-26

本次更新：2026-08-27

## 当前绑定

- 分支 / HEAD：`rebuild` / `787534486052af805ab487b41b96f73bc4b1d996`。
- release source digest：`sha256:5583e0956e84131885014256b74b44b008806882481fa47f5c82aa4a0eff4de7`（346 个受控条目）。
- 后续 `e7ec4011…b14f1dc` 的当前 L0–L3 与 L4 过期判定见 [测试契约收口后当前源码准入审阅](2026-08-27-gate-d-current-source-after-test-contract-remediation-audit.md)；本文件以下内容只描述 `5583e095…eff4de7` 快照。
- 当前源码修复了 acceptance replay / journey 的隐藏辅助 LLM 调用与流式失败后的同步二次请求，并移除了本地浏览器 helper 的预置 inbox 文件。
- 本轮修复后没有调用真实 Provider；`artifacts/`、`tmp/` 保持未跟踪且未触碰。

## 用户下午测试日志的证据等级

用户提供的 `test.txt` 是外部诊断旁证，不是仓库指令、受控 candidate 或 Gate D 收据。其下午日志中可见辅助请求从 300 token 升到 1200 token，以及流式 10/20/40 秒重试后再进入同步 fallback；这与静态审阅发现的两个计数盲区一致：

1. replay / AgentLoop 的 intent、playbook 等辅助路径能绕过 journey 主 client，自建未计数 `LLMClient`；
2. 主流式请求失败后，AgentLoop 的通用同步 fallback 能再次消费 Provider 请求。

该附件只用于形成 RED 假设；最终判定来自当前源码的失败测试、修复后测试、零调用 preflight 和本地浏览器证据。最终复核时原桌面路径已不存在，因此不把附件内容或文件 hash 写成可复现受控证据。

## 可数性修复与 RED

修复前 RED 明确复现：

- R07 replay 构造了 2 个未注入的 `LLMClient(max_tokens=300)`；
- 第一次主请求异常后，真实 AgentLoop 进入同步 fallback 并消费第二个响应。

当前实现：

- `AgentLoop` 可显式注入 `auxiliary_llm_client`，并将 intent、method playbook、要求提取、上下文压缩统一走该边界；默认产品路径仍保持原有 client / retry 语义。
- replay 注入 `ProviderNeutralAuxiliaryClient`，只做本地确定性回放，报告 `provider_calls=0`；不会构造 Provider client。
- 获授权 journey 的主轮和辅助调用共用同一个 exact counter；辅助调用单次 `max_tokens=300`、`response_format={"type":"json_object"}`、总 cap 6，净化收据单列 main / auxiliary。
- `CountableJourneyClient.allow_stream_sync_fallback=false`；失败请求占用一次槽位后即停止，不再由 AgentLoop 同步补发。
- 辅助 Provider 请求失败会在首个主轮前 fail closed；无效辅助语义只允许本地确定性规则继续，不产生第二次 Provider 请求。

最终断网式门禁：

- `tests/test_route_a_journey_countable.py tests/test_route_a_journey_replay.py tests/test_route_a_provider_preflight.py`：`64 passed in 12.46s`；
- `tests/test_llm_intent.py tests/test_method_playbooks.py`：`34 passed in 36.34s`；
- `python -m compileall -q src scripts/acceptance`：通过；
- `git diff --check`：通过，只有 LF→CRLF 工作副本提示；
- 环境：`API_BASE=http://127.0.0.1:9`、假 key、`GOLDEN_LIVE_SMOKE=0`，真实 Provider 0。

## 当前 digest 的零调用预检

| 范围 | ready / errors | Provider 调用 | 主轮上限 | 辅助上限 | 总上限 |
|---|---|---:|---:|---:|---:|
| R01–R06 判断纪律 | `true / []` | 0 | 18 | 0 | 18 |
| R07 publication journey | `true / []` | 0 | 30 | 6 | 36 |
| R09 routing_integrity journey | `true / []` | 0 | 36 | 6 | 42 |

三项 preflight 均返回当前 `5583e095…eff4de7`；命令没有产生 LiteLLM / Provider 输出，也没有创建执行报告。精确 candidate、数据、问题与 prompt hash 见 [2026-08-27 授权冻结](2026-08-27-gate-d-countable-l4-authorization-freeze.md)。

## 当前 digest 的真实本地浏览器验证

### 隔离与 Provider 保护

- Codex in-app Browser 打开真实页面 `http://127.0.0.1:5011/`；真实 Flask、SSE、AgentLoop、工具 registry、session 持久化和页面渲染。
- 服务使用全新系统临时 workspace / sessions，启动前 inbox 不存在且文件数为 0。
- `API_BASE=http://127.0.0.1:9`、假 key、`GOLDEN_LIVE_SMOKE=0`、`MCP_ENABLED=0`；固定本地控制 client，Provider 0。
- `scripts/acceptance/local_publication_synthesis_web.py` 不再复制或预置任何工作簿；第一次工具调用只能引用页面实际上传的 `省钱卡订单.xlsx`。

### 页面与落盘证据

1. 通过页面可见上传控件的 file chooser 上传 `reference/test_doc/省钱卡订单.xlsx`；页面显示“省钱卡订单.xlsx / 1 个文件已附加”。
2. 隔离 inbox 最终且仅有 `省钱卡订单.xlsx`，13,406 bytes；上传副本与仓库 reference 均为 `sha256:9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3`，不存在旧 helper 名称 `publication_synthesis_orders.xlsx`。
3. `conversation.json` 的首个 assistant 工具调用是 `load_data({"source":"省钱卡订单.xlsx","name":"publication_orders"})`，随后为 `compare_periods`；没有跳过上传边界。
4. `workspace_meta.json` 的 raw / analysis 数据集 `source_path` 均指向该隔离 inbox 上传文件；两者均为 71 行 × 7 列。
5. 持久化收据顺序为 `load_data`（`tr_1eb02a6f3ac9`）→ `compare_periods`（`tr_c0fb95486c25`）。最终页面可见 1818、684、15/15 以及比较边界；session meta 另确认 71 行。
6. 输入框恢复可用；浏览器 console warning / error 为 `[]`。

本地服务取证后已停止；系统临时证据目录保留未删除。该结果是当前 digest 的 L3 浏览器 / 上传 / 工具 / 持久化证据，不是任何真实 Provider L4 收据，也不单独满足 R07 publication 合同中的全部 1818/684/71/30 最终文本锚点。

## 当前 digest 的获授权 Provider 收据

用户于 2026-08-27 逐段粘贴三个互相独立的精确授权。执行前再次确认三个 preflight 均 `ready=true`、`errors=[]`、Provider 0，candidate hash 和唯一报告路径均匹配；随后严格按 R01–R06 → R07 → R09 顺序执行。

| 范围 | 净化报告 / SHA-256 | 结果 | 实际 / 上限 |
|---|---|---|---:|
| R01–R06 判断纪律 | [报告](2026-08-27-gate-d-r01-r06-countable-source-batch-report.json) / `sha256:6abf7b32b81209844b58b839da06db0685231dbff7471dc6b954b1943ebc8a6e` | 6/6 passed；六场景均在 2000-token 第一档 `stop` | 6 / 18 |
| R07 publication | [报告](2026-08-27-gate-d-r07-countable-publication-report.json) / `sha256:f8f94548875664d74b914e20f92e157addb667f624178c53b882fe24da685f75` | passed；10/10 轮；`load_data`、`compare_periods` 与 1818/684/71/30 全部满足；无错误 | 13 / 36 |
| R09 routing_integrity | [报告](2026-08-27-gate-d-r09-countable-routing-report.json) / `sha256:17e897eba626ee0b060a7ecf1bb03d9a795e91a7417be75ba20e0e380789b161` | passed；10/12 轮；`load_data`、`curve_fitting`；锚点 `not_required`；无错误 | 16 / 42 |

本轮合计 **35 / 96 次**真实 Provider 调用：

- R07 为主请求 11、辅助 2；第 10 主轮唯一一次按 `length` 从 2000 升到 8000。两次辅助均为 `length`，按冻结纪律不升档、不重试，转本地确定性规则。
- R09 为主请求 12、辅助 4；第 5、10 主轮按 `length` 从 2000 升到 8000。第 4 次辅助为 `length`，同样没有升档或重试。
- 全部请求使用 `openai/deepseek-v4-flash`、temperature 0、timeout 120 秒；没有 stream→sync 补发、换模型、Provider fallback 或补跑。

三个报告均通过净化结构复核，不含 Provider 原文；报告与执行后复算的源码摘要均为当前 `5583e095…eff4de7`。旧 `98e600…` R01–R06/R09 和 `86ad…` R07 报告继续只保留为历史证据。

## 当前结论

**当前 digest 的 R01–R07 与 R09 L4 及九文件矩阵已通过，但 Gate D 仍非发布候选。** countable / fail-closed acceptance、当前 L3 浏览器、同 digest L4 和独立九文件 / 多文件 32 项已闭环；[完整离线集合](2026-08-27-gate-d-current-digest-full-offline-matrix-audit.md) 为 2192 passed、9 skipped、26 failed、4 errors，隔离后仍有六组陈旧测试 / manifest 合同未收口。用户也尚未决定是否接受修复导致三份 L4 过期的成本。不会自动提交、推送、合并、部署或切根。
