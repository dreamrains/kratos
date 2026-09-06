# Data Agent 测试指南

默认测试体系只验证确定性的离线行为。任何未显式替换的 Provider 请求都会立即失败，避免网络等待、隐式重试和误耗调用额度。

## 日常快速验证

在仓库根目录使用 PowerShell：

```powershell
.\.venv\Scripts\python.exe scripts\testing\run_regression.py quick
```

该套件覆盖执行控制、回复合成、工具恢复和 Web/SSE 生命周期，用于开发过程中的快速反馈。

## 全量离线回归

```powershell
.\.venv\Scripts\python.exe scripts\testing\run_regression.py full-offline
```

这是提交和推送前的权威默认入口，收集整个 `tests/`。运行器为每次执行创建独立的 `tmp/test-runs/` 目录，并保存 JUnit 结果。

数据量较大或耗时较长的用例也可以单独运行：

```powershell
.\.venv\Scripts\python.exe scripts\testing\run_regression.py slow-offline
```

定向路径可追加到套件名称后，但只能位于 `tests/` 下。定向验证不能代替最终全量回归。

## 静态与编译检查

```powershell
.\.venv\Scripts\python.exe -m compileall -q src scripts tests
node --check src\data_agent\web\static\js\app.js
git diff --check
```

## 已停用的验收体系

旧矩阵、真实浏览器和真实 Provider 验收已从可执行测试树移除，在重新设计前不得运行。历史结果不属于当前源码的回归证据，也不能用离线通过替代浏览器或 Provider 结论。

保留的设计边界和未来重建要求见 [退役的浏览器与 Provider 矩阵](../docs/testing/retired-browser-provider-matrix.md)。
