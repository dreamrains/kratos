# Gate D `ea127a94` 本地发布候选声明

日期：2026-08-28

## 声明

用户已审阅当前源码的 Gate D L0–L4 证据与剩余风险，并明确将下列 release source digest 声明为**本地发布候选**：

```text
sha256:ea127a942d6a3bbfe2a7459de22782f499b77a5cd9ee2d4ce40f2c1e0fac07e8
```

| 项目 | 候选绑定 |
|---|---|
| 分支 / 声明前 HEAD | `main` / `0ef87d1629f84bafa0ad42698d3ad6b11dd2510d` |
| release source inventory | 343 项 |
| Gate D | L0–L4 技术证据通过；本地发布候选已由用户声明 |
| 完整零 Provider 集合 | `2342 passed, 9 skipped, 39 warnings in 455.31s` |
| Gate D 定向契约矩阵 | `66 passed in 11.96s` |
| 真实本地浏览器 L3 | 上传、SSE、工具、证据发布、刷新恢复、会话隔离与导出通过；Workbench 即时投影有已披露残余 |
| 当前 digest L4 | R01–R06、R07 publication、R09 routing_integrity 全部通过；38 / 96 次 |
| 静态门禁 | compileall、前端 `node --check`、`git diff --check` 通过 |

证据见 [本机服务问题修复与测试体系收口](2026-08-28-main-local-service-test-remediation.md) 与 [L4 执行结果及候选决定边界](2026-08-28-gate-d-ea127-l4-execution-and-candidate-decision.md)。

## 声明边界与 Git 授权

本声明确认上述精确 digest 是**本地发布候选**。用户在同一指令中另行授权提交当前受控源码与审计变更，并普通推送当前 `main` 到 `origin/main`。

该授权不包含部署、staging / production 验证、切根、删除历史实现、数据迁移或处理 `artifacts/` / `tmp/`。本轮三段 Provider 授权已经消费，不提供任何重试或新增调用额度。

候选提交与推送的实际 Git 哈希由本轮 Git 命令收据确认；不得在命令成功前预写。任何后续 release-source 内容变化都会产生新 digest，并使本候选声明不再适用于变更后的源码。

## 已接受但未消失的风险

用户是在已披露下列边界后作出候选声明：

1. Workbench 在 `turn_end` 后的验证结论不是每次都即时出现；服务端 SSE、持久化和刷新恢复已通过，但不能声明“无刷新多轮 Web 体验完全通过”。
2. 全量测试的 39 条 warning 来自退化统计输入下的 NumPy / SciPy / statsmodels 警告；没有测试失败，但相关统计结论仍须保留限制说明。
3. 本地发布候选不等于 staging 或 production 已验证；本轮没有部署授权。
4. 未跟踪用户资产 `artifacts/`、`tmp/` 必须保持未触碰、未暂存、未提交。

因此，Gate D 的准确状态是：**`sha256:ea127a94…07e8` 已成为本地发布候选；允许提交并普通推送，但不允许自动部署。**
