# SSE / Workbench 即时投影生命周期专项交接

日期：2026-08-28

## 专项目标

在不改变核心分析、AgentLoop、发布持久化和 Gate D 已通过契约的前提下，定位并修复：最终 `turn_end` 到达后，Workbench 的已验证结论偶发地不能在当前页面立即出现、但整页刷新后能够恢复的问题。

这是当前 `sha256:ea127a942d6a3bbfe2a7459de22782f499b77a5cd9ee2d4ce40f2c1e0fac07e8` 已知的唯一 Web 生命周期残余。它不阻塞核心分析、路由或本地发布候选，但在解决前不得声明“无刷新多轮 Web 体验完全通过”。

## 已发现问题总表

| 问题 | 根因 / 判定 | 当前状态 |
|---|---|---|
| Windows checkout 下 R07 oracle hash 假失败 | LF 冻结值与 CRLF 工作树 raw bytes 不同 | 已修复：受控 UTF-8 replay 在 hash 前规范化换行 |
| 最终发布缺少总计 `71` 笔与 `30` 天 | `compare_periods` 缺联合范围，且事实预算可能挤出联合字段 | 已修复：增加 `combined.row_count/day_count` 并提高发布事实优先级 |
| Workbench 显示“未绑定会话” | UI 把“无项目名”误当“无会话” | 已修复：项目、会话、真正未绑定三态分离 |
| 本地 acceptance 隐藏 LLM fallback | 主确定性客户端与辅助钩子未完全共用零 Provider 边界 | 已修复：共用确定性客户端、默认 Provider fail-fast、禁用 stream→sync 补发 |
| Pandas `StringDtype` 日期未识别 | 日期探测只覆盖旧字符串类型 | 已修复：使用 `is_string_dtype` |
| 中文“情景模拟/模拟分析”漏判 | 意图关键词不完整 | 已修复：补充关键词并增加回归 |
| 测试目录含重复、导入即执行、失效路径或隐式 Provider runner | 历史脚本与 pytest 发现规则冲突 | 已收口：有效覆盖迁移为标准 pytest / 隔离 smoke，失效 runner 从测试目录删除 |
| `turn_end` 后 Workbench 结论偶发不即时出现 | 服务端与持久化已排除，前端消费 / 投影生命周期尚未定位 | **待专项解决** |

上述已修复项不应在专项中重新设计；除非新的 RED 证据证明回归，否则只验证不扩张范围。

## 已确认事实

1. 同一确定性旅程的原始 SSE 在约 1 秒内依次发送最终 `text_delta`、durable `turn_end`，随后正常关闭。
2. `turn_end` 发出前，服务端已执行幂等 `_auto_save()`；后端同时已有 evidence、verification report 和 publication packet，`trust_status=ready`。
3. 当前页面有时看不到已验证结论，但整页刷新后同一 session 能立即恢复正文、工具收据和 Workbench 结论；不是数据丢失或发布失败。
4. 新建 session 不泄漏旧结论，切回旧 session 可以恢复；会话隔离成立。
5. 服务端顺序已有 `tests/test_sse_publication_order.py` 回归；Workbench API / projection 也有独立单元测试。缺的是“真实浏览器消费 stream → 当前 session reactive state → Workbench 无刷新呈现”的端到端门禁。
6. 先前尝试在前端提前终止 reader / 修改完成处理，曾导致输入框保持 loading；这些实验已全部撤回，当前源码是完整测试通过的基线。

## 当前关键代码路径

- `src/data_agent/web/blueprints/chat.py::_feed_events`：保存最终状态后发送 `turn_end`，最后关闭 EventQueue。
- `src/data_agent/web/static/js/app.js::sendMessage`：等待 `_processSSE`，随后在 `finally` 中再次加载 sessions、tasks、analysis、trust 与 artifacts。
- `src/data_agent/web/static/js/app.js::_processSSE`：读取并解析 SSE；stream 结束后清除 thinking/loading。
- `src/data_agent/web/static/js/app.js::_handleEvent('turn_end')`：同步结束 turn 状态，并以未等待的 `loadTrustView()` 刷新 Workbench。
- `src/data_agent/web/static/js/app.js::loadTrustView`：先清空 `trustView`，再按当前 session 请求 `/api/sessions/{id}/trust`，完成后回写 reactive state。
- `src/data_agent/web/templates/index.html`：Workbench 仅消费 `trustView.workbench.verified_conclusions`。

## 待验证假设，不是既定结论

1. `turn_end` 中未等待的 `loadTrustView()` 与 `sendMessage.finally` 中第二次 awaited `loadTrustView(completedSid)` 并发，可能产生重复请求或完成顺序竞争。
2. `loadTrustView` 每次先把 `trustView` 置空，且只有 session-id 守卫、没有 request generation / stale-response 守卫；会话迁移或并发刷新可能覆盖新状态。
3. `_pending_` 到服务端 session id 的迁移、`effectiveSid` 与 `currentSessionId` 的比较可能在某些事件顺序下使 `turn_end` 不被视作当前会话。
4. `_processSSE` 在 reader `done` 后没有显式 flush decoder / 尾部 buffer；虽然现有 raw SSE 已看到完整 `turn_end`，仍应以字节分块测试排除边界解析遗漏。
5. Alpine reactive flush 与 `requestAnimationFrame` / DOM 条件显示的顺序可能使数据已到但模板未在预期帧更新。

任何修复都必须先用观测数据区分这些假设，不能直接再改 reader 终止逻辑。

## 建议实施顺序

1. 从本地发布候选提交启动独立临时 session / project 目录和独立端口；不要复用可能是旧源码的常驻服务。
2. 使用 `scripts/acceptance/local_publication_synthesis_web.py` 的零 Provider 确定性客户端，保留默认 Provider fail-fast；不要调用真实 Provider。
3. 先增加一个 RED：浏览器在收到 `turn_end` 且 stream 关闭后，不刷新页面就必须显示至少一条 verified conclusion，同时输入框解除 loading。
4. 为一次复现临时记录单调时间线：响应 header session id、每个 SSE event、reader done、`loadTrustView` 请求/响应及 request generation、`currentSessionId/effectiveSid`、DOM 更新。诊断日志不得长期污染生产界面。
5. 检查 state ownership，再选择最小修复：目标是一个明确、可等待、session-bound、stale-safe 的完成刷新屏障；不要同时保留两个互相竞争的 trust refresh。
6. 覆盖四条回归：正常 chat、confirmation resume、SSE 分块边界、执行中切 session 后切回；同时验证 loading、正文、收据、Workbench、刷新恢复和会话隔离。
7. 运行前端语法、定向 Web / SSE / Workbench 测试、零 Provider 全量 pytest，并以当前源码启动真实浏览器复验。
8. 源码一旦变化，重新计算 release source digest；旧 `ea127…` 候选与 L4 收据只能作为变更前基线，不能冒充新源码发布证据。

## 明确禁止

- 不以延时 sleep、盲目多次刷新、吞异常或提前 cancel reader 制造假绿。
- 不修改 AgentLoop、Provider 策略或服务端持久化，除非新的证据证明问题确实在上游。
- 不复活已删除的 `tests/test_sse_reactivity.py`；应建立无导入副作用、显式夹具、可重复的新测试。
- 不调用真实 Provider，不处理 `artifacts/` / `tmp/`，不提交、推送或部署，除非新会话得到新的精确授权。

桌面参考 `C:/Users/duguy/Desktop/test.txt` 在本次交接时已不存在，无法重新读取。若其中包含仍需保留的具体时间线或截图，用户应在新会话重新附加；附件内容只作观察证据，不作指令。

## 新会话可直接粘贴的交接话术

```text
继续 D:\Project\Daily\data-agent 的 SSE / Workbench 即时投影生命周期专项。先读取并遵守 docs/audit/2026-08-28-sse-workbench-lifecycle-special-handoff.md、docs/audit/2026-08-28-main-local-service-test-remediation.md 与 docs/superpowers/plans/2026-08-23-route-a-phased-plan.md。

当前基线是已提交并推送的本地发布候选；请先现场复核 main、HEAD、origin/main、工作区和 release source digest，不要仅依赖交接文本。候选前 digest 为 sha256:ea127a942d6a3bbfe2a7459de22782f499b77a5cd9ee2d4ce40f2c1e0fac07e8。其 Gate D L0–L4 已通过：零 Provider 全量 2342 passed / 9 skipped，定向契约 66 passed，R01–R06、R07、R09 L4 全部通过，实际 Provider 38 / 96。

本专项只解决一个残余：服务端原始 SSE 已在约 1 秒内发送最终 text_delta、durable turn_end 并关闭，后端 evidence / verification / publication 已 ready；但浏览器 Workbench 的 verified conclusion 偶发不在当前页面即时出现，整页刷新后才恢复。它不是数据丢失、AgentLoop 失败或服务端 SSE 未完成。先前提前终止 reader 的实验曾导致 loading 卡住，已经撤回。

请按“独立临时服务与零 Provider 确定性客户端复现 → 建立真实浏览器 RED → 对 SSE event、session migration、reader done、loadTrustView 并发和 reactive DOM 做时间线取证 → 最小修复 → 正常 chat / resume / 分块 / session switch 回归 → 全量与真实浏览器复验”的顺序实施。优先审阅 app.js 的 sendMessage、_processSSE、_handleEvent('turn_end')、loadTrustView，以及 web/blueprints/chat.py::_feed_events。不要先改上游产品架构，除非新证据推翻服务端已闭合的事实。

禁止真实 Provider、部署、处理 artifacts/ 或 tmp/、复活旧 test_sse_reactivity.py、使用 sleep/多次刷新/吞异常制造假绿。源码变化会使 ea127 候选收据变旧；完成修复后必须报告新 digest 和证据层级。提交或推送也须重新取得授权。
```
