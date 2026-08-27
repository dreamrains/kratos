# Gate D `ea127a94` L4 执行结果与候选决定边界

日期：2026-08-28

## 结论

获授权的 R01–R06、R07 publication、R09 routing_integrity 三项 L4 均已在同一 release source digest 上通过。实际 Provider 调用合计 **38 / 96**；没有换模型、Provider 回退、countable stream→sync 补发、越权重试或补跑。

结合当前 digest 已通过的完整零 Provider 集合、定向契约矩阵、静态门禁和独立真实本地浏览器 L3，当前源码已具备完整的本地 L0–L4 技术证据。用户随后已审阅剩余风险，并将该精确 digest 声明为“本地发布候选”；见 [候选声明](2026-08-28-gate-d-ea127-local-release-candidate-declaration.md)。该决定本身不等于部署或外部环境验收。

## 绑定与授权边界

| 项目 | 结果 |
|---|---|
| 分支 / HEAD / `origin/main` | `main` / `0ef87d1629f84bafa0ad42698d3ad6b11dd2510d` / `0ef87d1629f84bafa0ad42698d3ad6b11dd2510d` |
| release source digest | `sha256:ea127a942d6a3bbfe2a7459de22782f499b77a5cd9ee2d4ce40f2c1e0fac07e8`（343 项） |
| 模型 | `openai/deepseek-v4-flash` |
| 冻结 | [Gate D `ea127a94` L4 授权冻结](2026-08-28-gate-d-ea127-l4-authorization-freeze.md) |
| 授权状态 | 三段均已消费；不得再次执行、重试或补跑 |
| 候选状态 | 用户已将该精确 digest 声明为本地发布候选 |
| 工作区边界 | 未暂存、未提交、未推送、未部署、未切根；`artifacts/`、`tmp/` 未触碰 |

三项执行前均重新通过零调用 preflight；source digest、candidate / 数据 / 问题 / prompt / oracle replay hash、模型、预算与唯一报告路径全部匹配。执行完成后复算 release source digest 仍为 `ea127a94…07e8`。

## L4 执行收据

| 范围 | 结果 | Provider 调用 | 关键合同 | 报告 SHA-256 |
|---|---|---:|---|---|
| R01–R06 判断纪律 | 6 / 6 passed | 7 / 18 | 五场景首档停止；R01 仅按 `2000 length → 8000 stop` 升档 | `560a249fa7248b507bda4ccb0ec273897197bb52e195aff772fb124baebf09fe` |
| R07 publication | passed | 16 / 36（主 14、辅助 2） | 10 / 10 轮；真实 `load_data + compare_periods`；无 error；1818 / 684 / 71 / 30 均满足 | `4cee23960f3cca08f3edfef0d05abe7f03128625205d3e156419a697554d0b52` |
| R09 routing_integrity | passed | 15 / 42（主 11、辅助 4） | 10 / 12 轮；真实 `load_data + curve_fitting`；无 error；数值锚点 `not_required` | `77dc16f6db32e153459403193e82b01d566e02f354d5a772973e190231011daa` |
| **合计** | **全部 passed** | **38 / 96** | 三份收据绑定同一 digest | — |

报告：

- [R01–R06 当前 digest 批次报告](2026-08-28-gate-d-ea127-r01-r06-countable-batch-report.json)
- [R07 当前 digest publication 报告](2026-08-28-gate-d-ea127-r07-countable-publication-report.json)
- [R09 当前 digest routing_integrity 报告](2026-08-28-gate-d-ea127-r09-countable-routing-report.json)

### 可数性与失败纪律复核

- R01–R06 只有 R01 在 2000 tokens 以 `length` 结束后升至 8000；六场景均在第一个非截断响应停止。
- R07 第 6、7、9、10 主轮发生冻结阶梯允许的 `2000 length → 8000`；两个辅助钩子各调用一次，均以 `length` 结束后没有重试或升档。
- R09 只有第 9 主轮发生冻结阶梯允许的 `2000 length → 8000 stop`；四个辅助钩子各调用一次，其中第 2、4 个以 `length` 结束后没有重试或升档。
- 三项报告均无请求异常和 error event，也没有额外模型、Provider fallback、countable sync fallback 或报告路径之外的补充执行。

## 同 digest 的 L0–L4 证据

| 层级 | 当前结果 |
|---|---|
| 完整零 Provider 集合 | `2342 passed, 9 skipped, 39 warnings in 455.31s` |
| Gate D 定向契约矩阵 | `66 passed in 11.96s` |
| 静态门禁 | compileall、前端 `node --check`、`git diff --check` 通过 |
| 真实本地浏览器 L3 | 上传 → SSE → 真实工具执行 → 证据发布 → 刷新恢复 → 会话隔离 → 导出通过；Provider 关闭 |
| 当前 L4 | R01–R06、R07、R09 全部通过；38 / 96 |
| source binding | 上述本地与 Provider 收据均绑定 `sha256:ea127a94…07e8` |

## 候选决定与剩余风险

当前源码已满足本地 Gate D 候选审阅所需的核心分析、路由、发布、离线测试和本机浏览器证据。仍需向用户披露并由用户决定是否接受以下边界：

1. 当前 release source 是 `main` 上的未提交工作树，不是新的 release commit；HEAD 与 `origin/main` 仍为旧提交 `0ef87d1…`。
2. Workbench 在 `turn_end` 后的即时投影存在非阻断时序残余；服务端 SSE、持久化与刷新恢复已通过，但不能声明“无刷新多轮 Web 体验完全通过”。
3. 全量测试的 39 条 warning 来自退化统计输入下的 NumPy / SciPy / statsmodels 警告；没有测试失败，但相关统计结论仍需保留限制说明。
4. 尚未做新的暂存、提交、推送、部署、staging 或 production 验证。
5. `artifacts/`、`tmp/` 是用户未跟踪资产，本轮保持未触碰、未暂存。

因此，当前准确状态是：**`sha256:ea127a94…07e8` 的本地 L0–L4 技术证据已经闭合，并已由用户声明为“本地发布候选”；用户另行授权提交与普通推送，但没有授权部署。**
