# Gate D `5583e095` digest 完整离线矩阵审计（历史失败快照）

日期：2026-08-27

> 后续状态：用户已接受证据过期成本并完成测试契约 / manifest 收口；新 digest `e7ec4011…b14f1dc` 的完整集合与 L3 状态见 [当前源码准入审阅](2026-08-27-gate-d-current-source-after-test-contract-remediation-audit.md)。本文件保留 `5583e095…eff4de7` 的失败诊断，不冒充当前源码状态。

## 当前绑定与边界

- 分支 / HEAD：`rebuild` / `787534486052af805ab487b41b96f73bc4b1d996`。
- release source digest：`sha256:5583e0956e84131885014256b74b44b008806882481fa47f5c82aa4a0eff4de7`（346 项）。
- 本轮只运行离线收集、测试和只读诊断；没有修改 release source，没有调用 Provider，没有触碰 `artifacts/`、`tmp/`。
- 环境：`API_BASE=http://127.0.0.1:9`、`API_KEY=gate-d-offline-no-provider`、`GOLDEN_LIVE_SMOKE=0`、`-p no:cacheprovider`。
- 继续排除 `tests/test_pipeline_comprehensive.py`（不能用于零 Provider 声明）与 `tests/test_sse_reactivity.py`（依赖失效样例、导入即执行遗留脚本）。

## 完整集合

收集命令：

```powershell
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider --collect-only -q --ignore=tests\test_pipeline_comprehensive.py --ignore=tests\test_sse_reactivity.py
```

结果：`2231 tests collected`。历史“223 passed, 1 skipped”没有保存完整文件清单，因此本轮没有根据旧数字伪造选择性命令，而是运行当前测试树的完整可执行集合。

执行结果：

```text
26 failed, 2192 passed, 9 skipped, 27 warnings, 4 errors in 432.61s
```

期间两次 LiteLLM 路径被关闭的 `127.0.0.1:9` 捕获；没有到达真实 Provider。这也意味着该完整集合不能笼统称为“全部纯逻辑单测”，但可以作为 fail-closed 的零 Provider 运行。

## 九文件与多文件矩阵

独立新进程运行：

- `tests/test_reference_data_manifest.py`
- `tests/test_real_data_integration.py`
- `tests/real_data/test_multifile_analysis_quality.py`
- `tests/real_data/test_multifile_real_data_scenarios.py`
- `tests/test_slice4_multifile_integrity.py`
- `tests/test_multifile_regressions.py`
- `tests/test_multifile_workbench_view.py`

结果：`32 passed in 4.09s`。这覆盖九文件 manifest / hash、真实数据集成、多文件质量与 fault injection、Slice 4 完整性、回归和 Workbench 投影。九文件条件通过，但不能抵消完整集合未通过。

## 隔离重验

将完整集合失败涉及的十个文件 / 节点分别放入全新 pytest 进程：

| 隔离组 | 结果 | 定性 |
|---|---|---|
| streaming without guard | 1 failed | 稳定复现；旧测试仍要求逐 delta 立即输出，当前实现有意缓存最终文本并在持久化后一次发布 |
| synthesis policy final answer | 1 failed | 稳定复现；测试要求精确等于 `final answer`，当前 publication boundary 有意附加 receipt-backed appendix |
| phase comprehensive parallel | 1 failed | 稳定复现；测试把结果解包为二元组，当前正式返回 `(tool_call, content, structured_data)` |
| scoped workspace parallel | 1 failed | 稳定复现；同一二元组 / 三元组契约落差 |
| streaming context cleanup 文件 | 9 failed, 5 passed | 首个事件的 `turn_id=None` 字段与旧断言不一致；断言中止后 generator 未关闭，随后同文件出现 context 泄漏级联 |
| tool surface exact manifest | 1 failed | 实际 registry 75 项，manifest 73 项；缺 `curve_fitting`、`synthesize_time_series` |
| task plan versioning | 1 passed | 完整集合失败为顺序依赖 |
| tool recovery | 6 passed | 完整集合的 4 个 context-binding 失败为顺序依赖 |
| trustworthy load integration | 3 passed | 完整集合的 2 个 context-binding 失败为顺序依赖 |
| system data analysis quality audit | 4 passed | 完整集合的 4 个 setup error 为顺序依赖 |

隔离重验说明完整集合的 30 个 fail/error 不是 30 个独立产品缺陷；稳定根因集中在六组陈旧测试 / 清单合同，另有由早期 generator 断言中止引起的 AgentContext 顺序污染。

## 当前实现对照

1. `AgentLoop` 的 streaming 路径明确写有“persist final message before client can render final delta”，因此恢复旧的未持久化逐 delta 行为会破坏当前浏览器刷新一致性，不应为了旧断言回滚产品代码。
2. `AgentLoop._render_terminal_publication()` 与 `tests/test_publication_synthesis.py` 已把 receipt-backed appendix 定义为产品发布边界，旧测试的精确字符串断言应改为验证正文和 appendix。
3. `_execute_tools_parallel()` 与正式 caller 都使用三元组并记录 `structured_data`；两个二元组解包测试落后。
4. Slice 3 / Slice 4 冻结分别明确新增 `curve_fitting`、`synthesize_time_series`；Gate C / 当前 R09 又真实验证 `curve_fitting` 可达。实际 registry 为 75、manifest 为 73，差异是受审阅工具未回填静态清单，不是未知工具突然进入运行时。

## Gate D 判定与停止点

**当前 digest 的九文件矩阵通过，但完整测试未通过，因此 Gate D 仍非发布候选。**

最小修复预计只触达测试与 `tests/acceptance/tool_surface_manifest.json`，不需要回滚当前产品行为；但这些路径进入 release-source digest。任何修复都会使当前 digest 的 R01–R06、R07、R09 三份 L4 收据立即过期，并需要在新 digest 上重新完成离线 / 浏览器 / Provider 证据。

在用户明确接受这一证据失效成本前，不修改上述测试或 manifest，不调用 Provider，不提交、推送、合并或部署。
