# `main` 本机服务全面测试报告

日期：2026-08-27

> 历史基线：本报告记录修复前的失败状态。其阻断项已在
> `2026-08-28-main-local-service-test-remediation.md` 中修复并按新 source digest
> 重新验证；不得用本报告的旧 digest 或旧结论代表当前工作树。

## 结论

**本轮全面测试未通过。** 当前本机服务仍可访问，描述性核心链路能够完成真实上传、`load_data`、`compare_periods`、持久化与 Markdown 导出；但当前 Windows checkout 无法复现完整离线绿灯，并且真实浏览器旅程暴露了确认恢复、答案完整性和 Workbench 会话绑定问题。

因此，`e7ec4011…b14f1dc` 的既有“本地发布候选”历史声明没有被本轮改写为新的全面通过收据。当前主分支可以继续作为本机诊断环境，但在修复并重验下述阻断项前，不应继续升级发布范围。

## 基线与边界

| 项目 | 结果 |
|---|---|
| 分支 | `main` |
| HEAD / `origin/main` | `0ef87d1629f84bafa0ad42698d3ad6b11dd2510d` |
| release source digest | `sha256:e7ec4011ecced91664cbb492e7ccf0d1cfe6d13c16ab2facf0a20f165b14f1dc`（346 项） |
| 本机服务 | `http://127.0.0.1:5001/`，PID `13716` |
| Provider 边界 | `API_BASE=http://127.0.0.1:9`、假 API key、`GOLDEN_LIVE_SMOKE=0`；没有真实 Provider 调用 |
| 用户资产 | `artifacts/`、`tmp/` 保持未跟踪且未触碰 |
| 代码变更 | 无；本文件仅记录测试结果，未暂存、未提交 |

完整 pytest 集合继续排除 `tests/test_pipeline_comprehensive.py`（不能用于零 Provider 声明）和 `tests/test_sse_reactivity.py`（依赖失效样例且导入即执行）。

## 自动化与静态门禁

| 检查 | 结果 |
|---|---|
| 完整可执行 pytest 集合 | **6 failed, 2216 passed, 9 skipped, 29 warnings in 410.58s** |
| 九文件 manifest / 多文件场景矩阵 | **32 passed in 4.17s** |
| 正式 Flask / Web 契约集合 | **172 passed in 10.39s** |
| `compileall` | 通过 |
| `git diff --check` | 通过 |

### 完整集合的六个失败

六个失败均位于 `tests/test_route_a_journey_countable.py`，共享同一个预检根因：R07 candidate 冻结的 oracle replay SHA-256 是 `ebcbef8687a26a791b9348300ae3fd42eb55a777866e800f8e058fd9199519ec`，而当前 Windows 工作树原始字节 SHA-256 是 `305fefd3647f1724bbc576c47fe07fc85a7a7625d4e0ae710fd6a6f7eaf4f751`。

Git blob 的 SHA-256 与冻结值相同，但 `core.autocrlf=true` 将工作树文件从 LF 转为 CRLF：blob 含 0 个 CR 字节，工作树含 44 个 CR 字节，长度分别为 2191 与 2235。Git 状态仍显示干净，因此当前 raw-byte oracle hash 契约对正常 Windows checkout 不可移植。预检在 Provider 前失败，没有产生 Provider 调用。

### 遗留 Web 测试边界

`tests/test_web_gui.py` 单独运行时在收集阶段缺少 `reference/workspace/test_sales.csv`，且该文件存在导入即执行行为。它在完整集合中的表现受执行顺序或外部夹具状态影响，不能作为稳定的本机服务绿灯证据。本轮没有为制造假绿而修改它。

## 真实浏览器与隔离服务旅程

浏览器旅程在两个独立临时目录和端口中运行真实 Flask、SSE、`AgentLoop` 与工具注册表，使用确定性本地客户端，未连接真实 Provider。两个隔离测试服务完成取证后已停止；正式的 `5001` 服务保持运行。

### 1. 确认与恢复旅程：失败

- 上传 `省钱卡订单.xlsx` 成功：13,406 bytes，SHA-256 `9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3`。
- `method_confirmation` 正常显示并持久化；浏览器选择“仅做描述性探索”，记录状态为 resolved。
- `/api/chat/resume` 返回 200，恢复后真实执行 `load_data`，生成 `publication_orders` 与 raw 快照，均为 71 行 × 7 列。
- 随后服务日志出现 `Streaming LLM call failed, falling back to sync`，页面最终显示 `Error: LLM 返回为空`；未执行 `compare_periods`。

这证明确认 UI 与记录持久化可用，但当前本地确定性客户端 / 恢复路径的组合无法闭合完整分析。仅凭现有证据不能把原因进一步归咎于某一个单独模块。

### 2. 纯描述性核心旅程：部分通过

- 上传成功并真实执行 `load_data`（收据 `tr_72e17dafda04`）和 `compare_periods`（收据 `tr_69ef74d6b919`）。
- raw / analysis 数据集均为 71 行 × 7 列；两个期间分别覆盖 15 个自然日，记录行数为 47 与 24。
- 最终文本正确包含售价总额 `1818`、`684`、变化率 `-62.38%` 与每段 15 天，并保留“不能单独证明因果关系”的边界。
- 页面刷新后结果和收据保持；新建会话后旧结果不进入新会话正文，返回原 `session_id` 后结果恢复。
- 浏览器 warning / error 均为空。
- Markdown 导出 API 与文件下载请求均返回 200；落盘文件 847 bytes，SHA-256 `1a8f0d8936ffbd77b8287a4834d758ff9736f21ac9f3216dc35efe0d39c7950d`，内容包含问题、收据与计算结果。

仍有三个缺口：

1. 用户明确要求“订单数与覆盖的自然日数”，最终文本没有给出总订单数 `71`，也没有汇总两个 15 天期间为总覆盖 `30` 个自然日；它只展示了每段 15 天。
2. 分析工作台在执行后和刷新后均显示“未绑定会话”。
3. `analysis_state.json` 仍停留在 `stage=plan`，`evidence_records`、`insight_records`、`verification_reports` 均为空；`/api/tasks?session_id=...` 也没有产生可投影任务。

## 服务清理与存活检查

- 隔离测试服务 PID `24424`（5011）和 PID `37352`（5012）已停止。
- 两个临时证据目录保留，未删除：
  - `C:\Users\duguy\AppData\Local\Temp\data-agent-main-0ef87d1-comprehensive-89da625c0799409480af08d714cc3892`
  - `C:\Users\duguy\AppData\Local\Temp\data-agent-main-0ef87d1-descriptive-7075af315e7c466f858443d15f65f782`
- 正式本机服务 PID `13716` 最终复查仍返回 HTTP 200，页面包含 `Data Agent`。

## 判定与建议顺序

本轮判定为：**服务存活，核心描述性链路部分通过，全面验收失败。**

建议下一轮按以下顺序处理，并在每次源码变化后重新绑定 digest：

1. 先修复 R07 oracle replay hash 的跨 checkout / CRLF 可移植性，恢复完整离线集合可复现。
2. 为 confirmation → resume → 后续工具调用增加确定性回归，区分产品恢复逻辑与本地 acceptance client 兼容性。
3. 补齐最终发布文本对“总订单数”和“总自然日覆盖”的请求满足度。
4. 修复会话到 Workbench / task / evidence 投影的绑定，再重跑上传 → 工具 → 有用结论 → 刷新 → 会话隔离 → 导出全旅程。
5. 将 `test_web_gui.py` 改为显式夹具、无导入副作用的可重复测试；不要依赖外部残留文件。

上述修复会改变 release source 或测试契约；若 source digest 改变，既有 Provider 与浏览器收据不得冒充新 digest 证据。本报告不授权新的 Provider 调用、提交、推送或部署。
