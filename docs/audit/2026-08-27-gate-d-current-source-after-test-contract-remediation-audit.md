# Gate D 测试契约收口后当前源码准入审阅（L0–L4 通过，本地发布候选已声明）

日期：2026-08-27

## 当前绑定与边界

- 分支 / HEAD：`rebuild` / `787534486052af805ab487b41b96f73bc4b1d996`。
- release source digest：`sha256:e7ec4011ecced91664cbb492e7ccf0d1cfe6d13c16ab2facf0a20f165b14f1dc`（346 项）。
- 用户明确接受修复陈旧测试 / manifest 会使 `5583e095…eff4de7` 三份 L4 收据过期的成本，并授权开始实施。
- 获授权的当前 digest L4 已完成：R01–R06、R07、R09 全部通过，实际 Provider 调用 35 / 96。
- 没有提交、推送、合并、部署或切根；没有触碰 `artifacts/`、`tmp/`。

## 测试契约与工具面收口

本轮没有回滚产品运行时，只更新七个 release-source 测试 / manifest 文件：

1. streaming 最终文本测试改为验证“完成并持久化后一次发布”，不再要求未持久化逐 delta 立即外露；
2. synthesis 测试同时验证模型正文与 receipt-backed appendix，不再精确等于裸 `final answer`；
3. phase / scoped workspace 并行测试按正式 `(tool_call, content, structured_data)` 三元组解包；
4. streaming context cleanup 只验证该测试关心的事件类型 / 文本，并用 `finally` 关闭 generator，避免失败断言污染后续 `AgentContext`；
5. `tool_surface_manifest.json` 补入已在 Slice 3 / 4 审计的 `curve_fitting`、`synthesize_time_series`，精确工具数由 73 更新为 75。

第二次聚焦回归为 `19 passed in 4.87s`。随后把 streaming cleanup 放在此前受污染的 task-plan、tool-recovery、可信加载和系统质量审计之前运行，结果为 `31 passed, 2 warnings in 4.69s`，原顺序污染不再复现。

## 当前完整离线证据

环境固定为：

```text
API_BASE=http://127.0.0.1:9
API_KEY=gate-d-offline-no-provider
GOLDEN_LIVE_SMOKE=0
pytest -p no:cacheprovider
```

继续排除：

- `tests/test_pipeline_comprehensive.py`：不能用于零 Provider 声明；
- `tests/test_sse_reactivity.py`：依赖失效样例、导入即执行的遗留脚本，不为制造假绿而修改。

当前测试树完整可执行集合结果：

```text
2222 passed, 9 skipped, 29 warnings in 412.66s (0:06:52)
```

运行末尾有一次 LiteLLM 提示，但地址仍是关闭的 `127.0.0.1:9`，没有到达真实 Provider。当前 digest 的完整集合没有 fail / error。

独立九文件 / 多文件矩阵结果：

```text
32 passed in 4.11s
```

`python -m compileall -q src scripts tests main.py` 与 `git diff --check` 均通过；后者只有 LF→CRLF 工作副本提示。

## 当前 digest 的真实本地浏览器 L3

- Codex in-app Browser 打开 `http://127.0.0.1:5011/`，使用真实 Flask、SSE、AgentLoop、工具 registry、session 持久化和页面渲染。
- 服务绑定全新系统临时目录 `C:\Users\duguy\AppData\Local\Temp\data-agent-gate-d-e7ec4011-bfac7d00758e44d5a0e1efe546272f25`；未删除该证据目录。
- 页面通过可见上传按钮与 file chooser 上传 `reference/test_doc/省钱卡订单.xlsx`；页面显示“省钱卡订单.xlsx / 1 个文件已附加”。
- 隔离 inbox 仅有该文件，13,406 bytes；上传副本与 reference 均为 `sha256:9475ab522503a735a49cd82346d655d9a38040e951a52c08b6b621f98323d4d3`。
- `conversation.json` 的 assistant 工具顺序为 `load_data({"source":"省钱卡订单.xlsx","name":"publication_orders"})` → `compare_periods`；收据顺序为 `tr_6ba6e4d16db0` → `tr_2dfc90836c09`。
- raw / analysis 两个数据集均为 71×7，`source_path` 都指向隔离 inbox 上传文件。
- 页面最终显示 1818、684、两个 15 天期间及“不能单独证明因果关系”的边界；输入框恢复可用。
- 刷新后最终回答和锚点仍在；刷新前后 browser warning / error 都为 `[]`。
- 固定主 client 不请求 Provider；辅助语义钩子访问关闭的 `127.0.0.1:9` 时出现本地 10/20/40 秒退避并最终使用确定性规则，没有外部 Provider 流量。该行为作为 L3 fail-closed 事实记录，不冒充 countable L4。
- 取证后本地服务已停止。

## 当前 L4 状态与执行收据

`5583e095…eff4de7` 上的三份净化报告继续只作历史能力证据。用户随后逐字授权 [当前 L4 授权冻结](2026-08-27-gate-d-e7ec-l4-authorization-freeze.md) 的三段执行；预检均为 `ready=true`、`errors=[]`、Provider 0，且全部冻结 hash 与唯一报告路径匹配。

| 当前报告 | 结果 | Provider 调用 | 报告 SHA-256 |
|---|---|---:|---|
| [R01–R06](2026-08-27-gate-d-e7ec-r01-r06-countable-batch-report.json) | 6 / 6 passed；六场景均在 2000 tokens 非截断停止 | 6 / 18 | `c416db4d58701abc1215c555b866b7e4baf8847db115589fe715f17e31956ee2` |
| [R07 publication](2026-08-27-gate-d-e7ec-r07-countable-publication-report.json) | passed；10 / 10 轮；`load_data + compare_periods`；1818 / 684 / 71 / 30 | 13 / 36（主 11、辅助 2） | `eae33462960920697825c10e09e1d6d0af253bee7b9cc6c22ee2f58ebc01de69` |
| [R09 routing_integrity](2026-08-27-gate-d-e7ec-r09-countable-routing-report.json) | passed；9 / 12 轮；`load_data + curve_fitting`；数值锚点 `not_required` | 16 / 42（主 12、辅助 4） | `a4576203aa1097cebe6a72c9aef3fd52e9f9cb2bc3965244acedf6e7a1716feb` |
| **合计** | **全部 passed** | **35 / 96** | 三份均绑定 `e7ec4011…f1dc` |

R07 只有第 10 主轮、R09 只有第 5 / 6 / 9 主轮按冻结纪律由 2000 tokens 的 `length` 升至 8000；辅助钩子没有升档或重试。没有换模型、Provider fallback、countable stream→sync 补发或补跑。执行完成后复算 release source digest 仍为 `e7ec4011…f1dc`。完整逐次审阅见 [L4 执行结果与候选决定边界](2026-08-27-gate-d-e7ec-l4-execution-and-candidate-decision.md)。三段授权均已消费，不得再次执行。

## Gate D 判定与候选边界

| 条件 | 当前判定 |
|---|---|
| acceptance Provider 可数、失败即停 | 满足 |
| 当前完整离线集合 | 满足：2222 passed、9 skipped |
| 当前独立九文件 / 多文件矩阵 | 满足：32 passed |
| 当前 compileall / diff check | 满足 |
| 当前真实浏览器上传 / 双工具 / 持久化 | 满足 L3 |
| 当前 R01–R07 / R09 L4 | 满足：三份当前报告全部 passed；35 / 96 |
| 当前全部收据同一 digest | 满足：离线、浏览器与 L4 均绑定 `e7ec4011…f1dc` |
| 用户候选决定 | 满足：用户于 2026-08-27 将精确 digest 声明为本地发布候选 |

**Gate D 已通过；用户已将 `sha256:e7ec4011…f1dc` 声明为本地发布候选。** 正式边界见 [本地发布候选声明](2026-08-27-gate-d-e7ec-local-release-candidate-declaration.md)。当前 Provider 授权已全部消费，不再调用或补跑；本地候选不等于 staging / production 已验证，也不授权自动提交、推送、合并、部署或切根。
