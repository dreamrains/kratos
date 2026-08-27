# Gate D `e7ec4011` 本地发布候选声明

日期：2026-08-27

## 声明

用户已审阅 Gate D 当前源码证据与剩余风险，并明确将下列 release source digest 声明为**本地发布候选**：

```text
sha256:e7ec4011ecced91664cbb492e7ccf0d1cfe6d13c16ab2facf0a20f165b14f1dc
```

| 项目 | 候选绑定 |
|---|---|
| 分支 / HEAD | `rebuild` / `787534486052af805ab487b41b96f73bc4b1d996` |
| release source inventory | 346 项 |
| Gate D | 通过；本地发布候选已由用户声明 |
| 完整离线集合 | `2222 passed, 9 skipped, 29 warnings` |
| 九文件 / 多文件矩阵 | `32 passed` |
| 真实本地浏览器 L3 | 通过 |
| 当前 digest L4 | R01–R06、R07 publication、R09 routing_integrity 全部通过；35 / 96 次 |

证据见 [当前源码准入审阅](2026-08-27-gate-d-current-source-after-test-contract-remediation-audit.md) 与 [L4 执行结果及候选决定边界](2026-08-27-gate-d-e7ec-l4-execution-and-candidate-decision.md)。

## 声明边界

本声明只确认上述精确 digest 是**本地发布候选**，不表示：

- 已创建 release commit；
- 已合并或推送；
- 已完成 staging / production 验证；
- 已部署、切根或迁移历史数据；
- 已授权再次调用 Provider；
- 已授权处理 `artifacts/`、`tmp/` 或删除历史实现。

上述动作仍须单独、精确授权。任何 release-source 内容变化都会产生新 digest，并使本候选声明不再适用于变更后的源码；届时须重新评估受影响的证据层级。

## 已接受但未消失的风险

用户是在已披露下列边界后作出候选声明：

1. 当前工作树中的受控源码与审计变更尚未提交。
2. `test_pipeline_comprehensive.py` 与 `test_sse_reactivity.py` 仍是明确审计并排除的遗留边界。
3. L3 关闭 API 时，辅助语义钩子存在 10 / 20 / 40 秒本地退避延迟。
4. 本地发布候选不等于 staging 或 production 已验证。
5. 未跟踪用户资产 `artifacts/`、`tmp/` 继续保持未触碰、未暂存。

因此，Gate D 的准确结案状态为：**上述精确 digest 已成为本地发布候选；所有 Git 写入后的提交、合并、推送及任何部署动作仍停在独立授权边界。**
