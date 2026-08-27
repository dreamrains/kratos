# Data Agent 测试指南

本目录只有 pytest 可发现的测试。默认套件必须在关闭真实 Provider 的环境中运行，且不得通过 `collect_ignore`、文件名技巧或手工排除制造假绿。

## 1. 本地零 Provider 全量回归（权威默认入口）

在仓库根目录使用 PowerShell：

```powershell
$env:API_BASE='http://127.0.0.1:9'
$env:API_KEY='data-agent-offline-no-provider'
$env:GOLDEN_LIVE_SMOKE='0'
.\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests -q
```

该命令包含单元、契约、集成、真实样例数据、Route A 重放与隔离工具 smoke。`test_pipeline_comprehensive.py` 是默认套件的一部分，不得再单独排除。判断结果以本次命令的实际退出码和输出为准，不复用历史通过数量。

## 2. 变更后的快速定向验证

- Route A 可数性与零调用预检：

  ```powershell
  .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_route_a_journey_countable.py tests\test_route_a_journey_replay.py tests\test_route_a_provider_preflight.py -q
  ```

- 多文件与真实样例数据：

  ```powershell
  .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\real_data tests\test_multifile_regressions.py tests\test_multi_file_scope.py tests\test_slice4_multifile_integrity.py -q
  ```

- Web、会话、确认与发布完整性：

  ```powershell
  .\.venv\Scripts\python.exe -m pytest -p no:cacheprovider tests\test_web_overhaul.py tests\test_confirmation_continuation.py tests\test_sse_publication_order.py tests\test_local_publication_acceptance.py tests\test_slice6_workbench_minimal.py -q
  ```

定向验证只用于快速反馈，不能代替最终的全量回归。

## 3. 静态与编译检查

```powershell
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
node --check src\data_agent\web\static\js\app.js
git diff --check
```

## 4. 本机真实 Web 进程与浏览器验收

浏览器验收必须启动当前源码的独立本地 Flask 进程，使用隔离的项目和会话目录，并保持 `API_BASE=http://127.0.0.1:9`。至少验证：

1. 新建会话并上传真实样例数据；
2. `load_data` 和目标分析工具真实执行；
3. 结论、证据、错误事件和发布锚点在页面可见；
4. 刷新后恢复同一会话；
5. 新会话不泄漏旧会话状态；
6. 导出入口可用，浏览器控制台无新增错误。

本地确定性 LLM 客户端只能证明 Web/AgentLoop/工具/持久化的系统完整性，不能证明真实 Provider 表现。

## 5. 真实 Provider 与发布边界

真实 Provider 旅程不是默认测试。执行前必须冻结当前 source digest、候选与数据 hash、模型参数、唯一报告路径、精确最大调用数和失败纪律，并取得用户逐字授权。源码变化后，旧 Provider 收据不得冒充当前源码证据。

测试结论必须分别陈述：离线 pytest、静态检查、本机真实浏览器、真实 Provider、暂存/生产。只有实际执行过的层级才能声明通过；“本地发布候选”不等于已推送、已部署或生产验证通过。
