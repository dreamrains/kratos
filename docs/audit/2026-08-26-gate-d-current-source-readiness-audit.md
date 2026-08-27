# Gate D `5583e095` 源码准入审阅（历史快照）

初始日期：2026-08-26

本次更新：2026-08-27

审阅对象：`rebuild @ 787534486052af805ab487b41b96f73bc4b1d996`

release source digest：`sha256:5583e0956e84131885014256b74b44b008806882481fa47f5c82aa4a0eff4de7`（346 项）

> 后续状态：用户已接受证据过期成本并完成测试契约 / manifest 收口；新 digest `e7ec4011…b14f1dc` 的当前状态见 [测试契约收口后当前源码准入审阅](2026-08-27-gate-d-current-source-after-test-contract-remediation-audit.md)。本文件以下内容只描述 `5583e095…eff4de7` 快照。

## 结论

**下午日志暴露的隐藏调用问题已修复；当前 digest 的 R01–R07 与 R09 Provider 重验也全部通过，但 Gate D 仍不是发布候选。**

acceptance replay 已严格零 Provider；真实 journey 的主轮与辅助 LLM 调用统一计数，流式失败不再触发未计数同步补发；真实本地浏览器在空 inbox 中通过页面上传完成 `load_data → compare_periods`。随后三个精确授权执行共使用 35 / 96 次 Provider 调用，R01–R06、R07 publication 与 R09 routing_integrity 全部通过并绑定当前 digest。尚未满足的是当前 digest 的完整测试 / 九文件离线矩阵以及最终风险审阅与用户发布决定。

## 工作树与边界

| 项目 | 当前事实 |
|---|---|
| 分支 / HEAD | `rebuild` / `787534486052af805ab487b41b96f73bc4b1d996` |
| 受控源码 | 346 个 release-source 条目；digest 如上 |
| 当前改动 | acceptance harness、AgentLoop 辅助注入、intent / playbook、候选、RED 测试、本地浏览器 helper 与审计文档 |
| 用户资产 | 仅既存未跟踪 `artifacts/`、`tmp/`；未读取、暂存、删除或清理 |
| 外部动作 | 本轮获授权 Provider 35 次；无 commit、push、merge、deployment、root cutover、legacy deletion |

## 诊断、修复和门禁

用户附件 `test.txt` 只按外部诊断旁证处理。其 300→1200 辅助 token、10/20/40 秒流式重试和同步 fallback 现象，与代码审阅发现的隐藏辅助 client 和同步二次请求一致；没有把附件中的任何文本当作实施指令或验收真相。

修复后的受控事实：

- replay 显式注入 Provider-neutral auxiliary client；RED 保证不会构造默认 Provider client；
- journey 显式冻结 auxiliary `counted_once`：每次 300 token、JSON object、cap 6，主 / 辅助共享总计数并分别出具净化收据；
- countable journey 禁用 AgentLoop 的 stream→sync fallback；Provider 异常只消费当前槽位并 fail closed；
- 默认 Web / 产品 AgentLoop 未注入该 acceptance client 时，既有 retry / fallback 行为不被本修复暗改；
- 本地浏览器 helper 不再预置 inbox，真实页面上传成为唯一输入来源。

| 门禁 | 当前 digest 结果 |
|---|---|
| countable / replay / preflight | `64 passed in 12.46s` |
| intent / method playbook | `34 passed in 36.34s` |
| compileall | 通过 |
| `git diff --check` | 通过；只有 LF→CRLF 提示 |
| Provider 保护 | `API_BASE=127.0.0.1:9`、假 key、`GOLDEN_LIVE_SMOKE=0`；0 调用 |

修复过程中曾运行较宽影响矩阵；其中发现并修复 9 个旧签名 monkeypatch 兼容失败。余下 `test_execution_control.py::test_loop_injects_synthesis_policy_before_final_answer` 和已在 HEAD 记录的 streaming-without-guard 失败不被本轮改成假绿，也不宣称完整矩阵通过。历史 `test_pipeline_comprehensive.py` 继续不得用于零 Provider 声明；`test_sse_reactivity.py` 继续作为导入即执行遗留脚本排除。

## 当前 L3 浏览器证据

[浏览器与收据汇总](2026-08-26-gate-d-current-digest-browser-and-receipt-summary.md) 记录了空 inbox 起步的真实页面上传：上传文件 hash `9475ab…23d4d3`，落盘 source_path 指向隔离 inbox，收据顺序 `load_data → compare_periods`，数据 71×7，页面显示 1818/684、15/15，console 无 warning / error。服务为本地固定 client，Provider 0；因此它只证明 L3 系统完整性，不替代 R07 L4。

## 当前 L4 预检与获授权执行

三项执行前 preflight 均绑定当前 digest、`ready=true`、`errors=[]`、Provider 0：

| 范围 | 模型 / 请求 | 主轮上限 | 辅助上限 | 总上限 |
|---|---|---:|---:|---:|
| R01–R06 | `openai/deepseek-v4-flash`；temperature 0；timeout 120；JSON；`[2000,8000,32000]` | 18 | 0 | 18 |
| R07 publication | 同模型；10 轮；主轮 ladder；辅助 300-token JSON counted-once | 30 | 6 | 36 |
| R09 routing_integrity | 同模型；12 轮；主轮 ladder；辅助 300-token JSON counted-once | 36 | 6 | 42 |

精确 candidate / question / data / prompt hash、失败纪律和唯一报告路径冻结在 [2026-08-27 授权冻结](2026-08-27-gate-d-countable-l4-authorization-freeze.md)。用户逐段粘贴三段授权后，按 R01–R06 → R07 → R09 顺序执行；三份净化报告均通过结构复核且不含 Provider 原文：

| 当前报告 | 状态 | 调用明细 | 关键 verdict |
|---|---|---|---|
| [R01–R06](2026-08-27-gate-d-r01-r06-countable-source-batch-report.json) | passed | 6 / 18；六场景全部第一档 2000 `stop` | 6/6 判断纪律通过 |
| [R07 publication](2026-08-27-gate-d-r07-countable-publication-report.json) | passed | 13 / 36；主 11、辅助 2；10/10 轮 | 双工具、1818/684/71/30、无错误均满足 |
| [R09 routing_integrity](2026-08-27-gate-d-r09-countable-routing-report.json) | passed | 16 / 42；主 12、辅助 4；10/12 轮 | 双工具、`not_required`、无错误均满足 |

实际合计 35 / 96 次。R07 仅第 10 主轮、R09 仅第 5/10 主轮按 `length` 升到 8000；辅助 `length` 响应均不升档、不重试。没有同步补发、换模型、Provider fallback 或补跑。执行后 source digest 复算仍为当前值。

## 当前与历史 L4 证据

| 证据 | digest | 状态 | 当前 Gate D 用途 |
|---|---|---|---|
| R01–R06 当前批次 | `5583e095…eff4de7` | 6/6 passed；6/18 | 当前判断纪律 L4 |
| R07 当前 publication | `5583e095…eff4de7` | passed；13/36 | 当前双工具与最终锚点 L4 |
| R09 当前 routing_integrity | `5583e095…eff4de7` | passed；16/42 | 当前系统完整性与高级工具路由 L4 |
| 旧 R01–R06 / R09 | `98e600…dbc2e4` | 历史通过 | 过期，只作历史能力证据 |
| 旧 R07 日历 oracle | `86ad00…866a3e` | 历史通过 | 过期，只作历史能力证据 |

## Gate D 条件判定

| 条件 | 判定 | 依据 / 缺口 |
|---|---|---|
| acceptance Provider 可数、失败即停 | 满足 | RED、统一 counter、辅助 cap、禁用 countable sync fallback |
| 当前离线增量门禁 | 满足 | 64 + 34、compileall、diff check |
| 当前真实浏览器上传 / 工具 / 持久化 | 满足 L3 | 空 inbox 后页面真实上传与双工具收据 |
| 当前 R01–R07 / R09 L4 | 满足 | 三份当前净化报告全部 passed，合计 35 次 |
| 全部当前收据同一 digest | 满足 | 三份报告与复算源码均为 `5583e095…eff4de7` |
| 当前完整测试 | 未满足 | [完整离线矩阵审计](2026-08-27-gate-d-current-digest-full-offline-matrix-audit.md)：2231 项中 2192 passed、9 skipped、26 failed、4 errors；稳定根因集中在六组陈旧测试 / manifest 合同 |
| 当前九文件 / 多文件矩阵 | 满足 | 独立新进程 32 passed；覆盖 manifest/hash、真实数据、多文件质量、fault injection、Slice 4 与 Workbench |
| 用户发布决定 | 未发生 | 三段授权只覆盖 Provider 执行，不授权提交或发布 |

## 停止点

当前 Provider 授权已消费完毕，不再调用或补跑。九文件矩阵已通过，但完整集合未通过；隔离诊断表明最小修复应更新陈旧测试合同与 73→75 工具 manifest，而不回滚当前产品行为。由于这些文件进入 release digest，修复会使本轮三份 L4 收据过期；在用户明确接受该成本前停在此处。不会自动提交、推送、合并、部署或切根。
