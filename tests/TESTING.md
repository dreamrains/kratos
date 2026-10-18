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

## 当前验收入口与历史退役范围

本树唯一进度计划是 [可信发布重建总计划](../docs/superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)。旧浏览器框架的退役记录保留在 [历史退役说明](../docs/testing/retired-browser-provider-matrix.md)，不表示当前全部演练/Provider脚本被删除或禁止准备。

| 入口 | 当前职责与边界 |
| --- | --- |
| run_regression.py | Provider禁止的quick/full-offline/slow-offline；完整离线不能代替app/视觉/自然验收 |
| run_p7_browser_rehearsal.py | 唯一隔离Provider禁用正常app入口；新目录、空闲端口、先health，按AGENTS选控制路线 |
| run_p08_real_matrix.py、run_p08_http_matrix.py | 独立真实Provider launcher/HTTP driver及同一账本；只能用于重新精确冻结并明确授权的批次，不能驱动禁用演练 |
| p08_scenario_audit.py、p08_real_matrix_contract.json | 原离线审计与场景模板；模板不是授权freeze，原散文/统计摘要不能替代v2回执claim或自然oracle |
| offline_tool_surface_smoke.py、dependency_preflight.py | 原隔离工具边界与依赖核对；相应测试保留 |
| run_golden_answer_quality.py、run_multifile_quality_scenarios.py | 原质量与多源输入准备能力；真实模型生成另授权 |

完整Provider禁用app批次必须预先冻结精确输入/顺序/选项/oracle，记录service exec/PID/port、上传票据SHA、SSE每轮唯一终态、durable状态/导出和runtime transport=0。HTTP-only picker/可见图表/浏览器刷新/console均unassessed；视觉使用官方IAB能力另签收。不新建浏览器框架或调用账本。

publication_synthesis.py/publication_audit.py旧源码已经精确退役；同名测试文件已迁入新行为，仍有实际回归职责。不能按“旧名字”整删测试，也不能删除原失败目录或字节备份。2026-10-02准备清理仅移除两处无调用helper，共16行，其他AST/原函数名保持，证据见唯一计划和 `tmp/p4-preparation-20261002-r2/test-helper-retirement.json`。
