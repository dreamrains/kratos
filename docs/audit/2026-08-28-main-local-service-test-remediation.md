# `main` 本机服务问题修复与测试体系收口报告

日期：2026-08-28

> 后续状态：当前 digest 的 R01–R06、R07 publication 与 R09 routing_integrity 已在精确授权下全部通过，实际 Provider 调用为 38 / 96；用户随后已将该精确 digest 声明为本地发布候选。见 [L4 执行结果与候选决定边界](2026-08-28-gate-d-ea127-l4-execution-and-candidate-decision.md)及[候选声明](2026-08-28-gate-d-ea127-local-release-candidate-declaration.md)。下文保留 L4 执行前的本机测试与修复快照。

## 结论

本轮发现的可复现阻断问题已修复，测试入口也已收口：当前工作树的零 Provider 全量 pytest、编译检查、前端语法检查和 diff 卫生检查全部通过；当前源码的独立本地 Flask 服务通过了真实浏览器的上传、SSE、工具执行、证据发布、持久化恢复、会话隔离与导出旅程。

客观判定是：**当前工作树达到“本地离线与本机系统完整性通过”，但不是新的 Gate D 发布候选，也不是 Provider、暂存或生产通过。** 当前 release source digest 已由历史候选变化为 `sha256:ea127a942d6a3bbfe2a7459de22782f499b77a5cd9ee2d4ce40f2c1e0fac07e8`；旧 digest 的真实 Provider 收据不能冒充当前源码证据。本轮没有真实 Provider 调用、提交、推送或部署。

## 基线与边界

| 项目 | 结果 |
|---|---|
| 分支 | `main` |
| HEAD / `origin/main` | `0ef87d1629f84bafa0ad42698d3ad6b11dd2510d` |
| 当前 release source digest | `sha256:ea127a942d6a3bbfe2a7459de22782f499b77a5cd9ee2d4ce40f2c1e0fac07e8`（343 项） |
| Provider 边界 | `API_BASE=http://127.0.0.1:9`、假 API key、`GOLDEN_LIVE_SMOKE=0`；本地 acceptance 另设默认 `LLMClient` fail-fast 守卫 |
| 用户资产 | 未跟踪 `artifacts/`、`tmp/` 未暂存、未删除、未提交 |
| Git 操作 | 未暂存、未提交、未推送、未部署 |

## 问题分析与修复

### 1. Windows checkout 下 R07 冻结 hash 假失败

根因是冻结 JSON 按 LF 字节生成 hash，而 `core.autocrlf=true` 的 Windows 工作树使用 CRLF。文件语义和 Git blob 未变，但 raw-byte hash 不同，导致预检在 Provider 前失败。

修复后，受控 UTF-8 JSON 的旅程文件 hash 在计算前统一换行符；新增 LF/CRLF 和真实 tracked replay 的回归测试。该修改只消除 checkout 表示差异，不放宽候选、数据或 source digest 契约。

### 2. 发布文本缺少合计 `71` 笔和 `30` 个自然日

根因有两层：`compare_periods` 只返回各期间计数，没有联合范围；发布事实预算饱和时，联合范围字段也可能被普通字段挤出。

修复后，工具返回 `combined.row_count` 与 `combined.day_count`，并提高这两个跨期间范围事实在发布合成中的保留优先级。真实样例浏览器旅程最终显示 `1818`、`684`、`71`、`30` 四个锚点以及 `-62.38%` 描述性变化。

### 3. Workbench 显示“未绑定会话”

根因是模板只把项目名当作绑定条件，真实会话没有项目时仍被标成未绑定。修复后标签区分 `项目：...`、`会话：...` 和真正的未绑定状态，并增加会话/项目静态契约测试。

### 4. 本地 acceptance 的隐藏 LLM fallback 风险

根因是主轮确定性客户端与辅助 LLM 钩子没有被同一零 Provider 客户端完全隔离，确认或语义辅助路径可能落入默认 `LLMClient`，进而尝试关闭地址并产生误导性的 fallback。

修复后，本地验收的主轮与辅助钩子共用同一确定性客户端；主链固定为 `load_data → compare_periods → record_evidence_record → final`，禁用 stream→sync 补发，并对任何默认 `LLMClient` 调用设置 fail-fast 守卫。浏览器旅程中守卫未触发，客户端计数保持 `provider_calls=0`。

### 5. Pandas 字符串日期与“情景模拟”意图漏判

遗留 V10 runner 揭示两个仍然有效的问题：Pandas `StringDtype` 日期列未被自动识别；中文“情景模拟/模拟分析”未进入分析意图。分别改为使用 `is_string_dtype` 和补充意图关键词，并增加标准 pytest 回归。

## 测试脚本整理

测试目录现在只保留 pytest 可发现的测试；默认套件不再依赖 `collect_ignore` 或手工排除。

- `test_pipeline_comprehensive.py` 经审阅确认是零 Provider 测试，已纳入默认全量集合，并修正 stdout 副作用及真实边界断言。
- `test_comparability.py` 从顶层自定义 runner 改为 13 个标准 pytest 测试。
- 104 项工具面自检移动到 `scripts/acceptance/offline_tool_surface_smoke.py`，由标准 pytest 子进程包装验证退出码和 `PASS: 104 / FAIL: 0`。
- 新增测试套件卫生门禁，禁止静默排除、测试目录内不可发现脚本、仓库专用绝对路径、`sys.exit` 和已清理 runner 回流。
- 新增 `tests/TESTING.md`，冻结零 Provider 全量入口、定向矩阵、静态检查、真实浏览器层及真实 Provider 授权边界。

已删除的遗留脚本包括：`regression_test.py`、`test_sse_reactivity.py`、`test_v10_new.py`、`test_v91.py`、`test_web_gui.py`、`test_web_workbench_replacement.py`，以及仅用于静默排除的 `conftest.py`。它们存在导入即执行、失效绝对路径、隐式 Provider 风险、重复旧 UI 字符串断言或与当前契约冲突等问题；仍可从 Git 历史恢复。原 `test_tools_comprehensive.py` 的有效工具覆盖没有删除，而是迁移为隔离 smoke 并纳入 pytest。

## 最终自动化与静态结果

| 检查 | 结果 |
|---|---|
| 零 Provider 全量 pytest | **2342 passed, 9 skipped, 39 warnings in 455.31s** |
| `python -m compileall -q src scripts tests` | 通过 |
| `node --check src/data_agent/web/static/js/app.js` | 通过 |
| `git diff --check` | 通过 |

39 条 warning 来自常量或近常量样本下的 NumPy 相关系数除零、SciPy 偏度/峰度/正态性检验精度损失，以及 statsmodels 完全共线时 VIF 除零。它们没有造成测试失败，但表示这些退化输入下的统计结果必须继续带限制说明；本报告不把 warning 隐藏为“完全无风险”。

9 个 skip 均由测试自身的条件标记产生，本轮没有增加全局排除文件，也没有为获得绿灯而临时跳过失败测试。

## 当前源码真实浏览器旅程

使用当前工作树启动独立 Flask 服务，项目与会话目录位于系统临时目录，真实运行生产 Web、SSE、`AgentLoop`、工具注册、证据存储与 Workbench 投影；分析规划客户端为本地确定性实现，真实 Provider 被关闭并设 fail-fast。

结果：

1. 通过真实文件选择器上传 `reference/test_doc/省钱卡订单.xlsx`；
2. 实际执行 `load_data`、`compare_periods`、`record_evidence_record`；
3. 页面显示 `1818`、`684`、`71`、`30`、`-62.38%`，并保留非因果边界、工具收据与限制；
4. 后端生成 1 条 evidence、1 条 verification、1 个 publication packet，`trust_status=ready`；
5. 整页刷新后恢复对话、收据、四个锚点及已验证结论；
6. 新建会话为空且不泄漏旧结论，切回旧会话可恢复；
7. Markdown 导出入口可触发，浏览器控制台 warning/error 为空；
8. 服务日志未出现默认 Provider fail-fast 守卫命中；隔离服务完成后已停止，端口 5016 不再监听。

残余现象：`turn_end` 后 Workbench 的验证结论不是每次都即时出现；本次后端状态已 ready，但面板在整页刷新后才显示。持久化与恢复正确，因此它不是数据丢失或发布失败；仍应作为前端投影时序的非阻断残余继续观察，不能声明“即时 Workbench 更新已完全通过”。

后续隔离取证确认：同一确定性旅程的原始 SSE 在约 1 秒内依次发出最终 `text_delta`、durable `turn_end` 并关闭，后端同时已有 evidence、verification 与 publication packet。因此残余范围进一步收窄为浏览器消费/Workbench 投影生命周期，而不是 AgentLoop、工具执行、发布持久化或服务端 SSE 完成边界。局部前端终止实验曾导致输入框保持 loading，已全部撤回；该问题转为独立 Web 生命周期事项，不阻塞 Gate D 的核心分析与路由证据，但在解决前不得声明无刷新多轮 Web 体验完全通过。

## 最终判定

可以声明：

- 当前 digest 的零 Provider 全量自动化通过；
- 当前 digest 的本机真实浏览器系统完整性旅程通过，但有 Workbench 即时投影时序残余；
- 测试入口已统一，原有有效工具覆盖被保留，失效/重复/危险 runner 已清理。

不能声明：

- 当前 digest 的真实 Provider R01–R06、R07、R09 已通过；
- 当前 digest 已成为新的 Gate D 发布候选；
- staging、生产、部署或远程服务已验证。

如果要恢复“本地发布候选”资格，下一步应基于当前 digest 重新冻结 Gate D 授权与报告路径，并取得新的精确 Provider 调用授权；本报告本身不授权 Provider、提交、推送、合并或部署。
