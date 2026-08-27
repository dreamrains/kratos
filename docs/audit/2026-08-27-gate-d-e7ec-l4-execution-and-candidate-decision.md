# Gate D `e7ec4011` L4 执行结果与候选决定边界

日期：2026-08-27

## 结论

获授权的 R01–R06、R07 publication、R09 routing_integrity 三项 L4 均已在同一 release source digest 上通过。实际 Provider 调用合计 **35 / 96**；没有换模型、Provider 回退、countable stream→sync 补发、越权重试或补跑。

结合已经通过的完整离线集合、独立九文件 / 多文件矩阵、compileall / diff check 和真实本地浏览器 L3，当前源码的 L0–L4 技术证据链已经闭合。用户随后已审阅剩余风险，并将当前 digest 声明为本地发布候选；正式边界见 [本地发布候选声明](2026-08-27-gate-d-e7ec-local-release-candidate-declaration.md)。该决定不授权提交、合并、推送、部署或外部环境验收。

## 绑定与授权边界

| 项目 | 结果 |
|---|---|
| 分支 / HEAD | `rebuild` / `787534486052af805ab487b41b96f73bc4b1d996` |
| release source digest | `sha256:e7ec4011ecced91664cbb492e7ccf0d1cfe6d13c16ab2facf0a20f165b14f1dc`（346 项） |
| 模型 | `openai/deepseek-v4-flash` |
| 冻结 | [Gate D `e7ec4011` L4 授权冻结](2026-08-27-gate-d-e7ec-l4-authorization-freeze.md) |
| 授权状态 | 三段均已消费；不得再次执行、重试或补跑 |
| 候选状态 | 用户已将精确 digest 声明为本地发布候选 |
| 工作区边界 | 未提交、未推送、未合并、未部署、未切根；`artifacts/`、`tmp/` 未触碰 |

三项执行前的 source digest、candidate / 数据 / 问题 / prompt / oracle replay hash 与唯一报告路径均通过预检；执行完成后复算 release source digest 仍为 `e7ec4011…f1dc`。

## L4 执行收据

| 范围 | 结果 | Provider 调用 | 关键合同 | 报告 SHA-256 |
|---|---|---:|---|---|
| R01–R06 判断纪律 | 6 / 6 passed | 6 / 18 | 六场景均在 2000 tokens 得到非截断响应并停止 | `c416db4d58701abc1215c555b866b7e4baf8847db115589fe715f17e31956ee2` |
| R07 publication | passed | 13 / 36（主 11、辅助 2） | 10 / 10 轮；真实 `load_data + compare_periods`；无 error；1818 / 684 / 71 / 30 均满足 | `eae33462960920697825c10e09e1d6d0af253bee7b9cc6c22ee2f58ebc01de69` |
| R09 routing_integrity | passed | 16 / 42（主 12、辅助 4） | 9 / 12 轮；真实 `load_data + curve_fitting`；无 error；数值锚点 `not_required` | `a4576203aa1097cebe6a72c9aef3fd52e9f9cb2bc3965244acedf6e7a1716feb` |
| **合计** | **全部 passed** | **35 / 96** | 三份收据绑定同一 digest | — |

报告：

- [R01–R06 当前 digest 批次报告](2026-08-27-gate-d-e7ec-r01-r06-countable-batch-report.json)
- [R07 当前 digest publication 报告](2026-08-27-gate-d-e7ec-r07-countable-publication-report.json)
- [R09 当前 digest routing_integrity 报告](2026-08-27-gate-d-e7ec-r09-countable-routing-report.json)

### 可数性与失败纪律复核

- R07 只有第 10 主轮发生冻结阶梯允许的 `2000 length → 8000 stop`；两个辅助钩子均只调用一次，其中一个以 `length` 结束后没有重试或升档。
- R09 只有第 5、6、9 主轮发生冻结阶梯允许的 `2000 length → 8000`；四个辅助钩子均只调用一次，其中两个以 `length` 结束后没有重试或升档。
- 三项执行均未出现额外模型、Provider fallback、countable sync fallback 或报告路径之外的补充执行。

## 同 digest 的 L0–L4 证据

| 层级 | 当前结果 |
|---|---|
| 完整离线集合 | `2222 passed, 9 skipped, 29 warnings` |
| 独立九文件 / 多文件矩阵 | `32 passed` |
| 静态门禁 | compileall、`git diff --check` 通过 |
| 真实本地浏览器 L3 | 可见上传 → `load_data + compare_periods` → 页面最终结果 → 刷新持久化通过；browser warning / error 为 `[]` |
| 当前 L4 | R01–R06、R07、R09 全部通过；35 / 96 |
| source binding | 上述当前收据均绑定 `sha256:e7ec4011…f1dc` |

当前源码准入细节见 [测试契约收口后当前源码准入审阅](2026-08-27-gate-d-current-source-after-test-contract-remediation-audit.md)。历史 `test_pipeline_comprehensive.py` 与 `test_sse_reactivity.py` 继续按已审阅边界排除，未为制造假绿而修改。

## Gate D 判定与剩余风险

Gate D 计划的技术条件 1–5 已有当前源码证据：既有三份台账与 Route A 切片已闭环；完整测试、九文件矩阵、真实浏览器和获授权 Provider 批次通过；收据同 digest；工作树 / 依赖 / 配置 / 模型 / 数据 manifest 已明确；本轮没有新增未审阅兼容层、平行运行时、死入口或迁移缺口。

用户已在下列剩余风险被明确披露后，将精确 digest 声明为本地发布候选，因此 Gate D 的候选决定条件已经满足。用户没有授权后续 Git / 发布动作：

1. 当前工作树仍是未提交的受控源码与审计变更；尚无 release commit。
2. `test_pipeline_comprehensive.py` 与 `test_sse_reactivity.py` 是明确排除并审计的遗留边界，不属于本次绿色集合。
3. L3 关闭 API 时，辅助语义钩子会产生 10 / 20 / 40 秒本地退避延迟；这是已记录的 fail-closed 运行风险，不是本次 L4 可数性违约。
4. 尚未做 staging 或 production 验证；本地发布候选也不等于已部署。
5. `artifacts/`、`tmp/` 仍是用户未跟踪资产，本轮保持未触碰、未暂存。

因此，当前准确状态是：**`sha256:e7ec4011…f1dc` 已由用户声明为本地发布候选；尚未授权任何提交、合并、推送、部署或外部环境验收动作。**
