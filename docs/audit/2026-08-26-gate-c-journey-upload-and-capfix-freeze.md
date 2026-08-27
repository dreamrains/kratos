# Gate C 旅程仪器修正与 R07/R09 重冻结（未执行 Provider）

日期：2026-08-26

## R09 首跑事实（授权消耗 8/24）

收据：[r09 report](2026-08-26-gate-c-journey-r09-report.json)。8 轮 8 次调用：`load_data` → 浏览/profiling → **`curve_fitting` 被真实路由并执行**（R09 靶风险「高级工具存在但实际不可达」的答案：可达且被选用）→ 模型继续探索（`read_file`、`list_files`×3）→ 轮 9 被 cap 拒绝。锚点未产出（无最终回答）。

## 两处仪器缺陷（用户追问 R07 后定位，均已修）

1. **旅程缺上传阶段**（R07 四跑根因的真正层次）：计划 §5 定义 R07 旅程「在现有 Web 上传 D03 → 提问」，回放构架却跳过上传直接提问——「上传的数据」对模型是不存在的上下文，跑 1-3 靠 `list_files` 碰巧自发现，跑 4 走了正确的产品路径（澄清挂起）。修复：manifest 新增 `uploads` 段；执行器在提问前把冻结数据经产品上传路径（校验 hash 后复制进 `inbox_dir`）真实上传——R07 候选已加上传段，问题措辞现为真。
2. **round_cap 与 WRAP_UP_ROUND 撞车**（R09 首跑根因）：cap=8、wrap-up=8 时收尾消息在第 9 轮才可见，而第 9 轮已被 cap 拒绝——收尾机制被结构性废掉。修复：预检新增结构性校验「round_cap 必须大于当前生效的 wrap_up_round，否则零调用拒绝」；R09 候选 cap 8→10。

## 重冻结

- 受控源码摘要：`sha256:60399d57bf01716d0d27c77b2d42a04c43120ef6f247d4c558b4706118068271`（两旅程共享同树摘要）。
- R07（`route_a_gate_c_journey_r07_candidate.json`）：新增 `uploads`（savings_card_orders → inbox/省钱卡订单.xlsx）；round_cap 10、阶梯不变、至多 30 次；问题/数据/契约不变。
- R09（`route_a_gate_c_journey_r09_candidate.json`）：round_cap 8→10（wrap-up 8 后余 2 轮收尾）；其余不变；至多 30 次。
- 离线门禁：`64 passed`（旅程+preflight+守卫套件）；`compileall`、`git diff --check` 通过；本修正 Provider 调用 `0` 次。
- 上传集成为真实链路测试：模型按文件名 `load_data` 从 inbox 加载上传文件成功。

## 所需单独授权（两条可分别或一起授权）

```text
我授权 Gate C R07 旅程五跑：仅在 source digest sha256:60399d57bf01716d0d27c77b2d42a04c43120ef6f247d4c558b4706118068271 上，使用 openai/deepseek-v4-flash，先按清单 uploads 段把 savings_card_orders（hash 9475ab52…）经 inbox 路径上传为 省钱卡订单.xlsx，再以真实 AgentLoop（含默认 WRAP_UP_ROUND=8）执行 R07_end_to_end_publication_journey 恰好 1 次：轮次至多 10、每轮按冻结阶梯 [2000, 8000, 32000] 单次非流式请求、该轮 finish_reason=length 即升档，总计至多 30 次 Provider 调用，使用 2026-08-25-gate-c-journey-r07-preflight.md 冻结的问题、数据 hash、temperature=0、timeout=120 秒与契约（load_data 必需、最终回答含 1818/684/71/30 锚点），并仅写入 docs/audit/2026-08-26-gate-c-journey-r07-fifth-report.json。预检不通过则零调用；失败即停止；不重试、不换模型、不回退、不补跑。
```

```text
我授权 Gate C R09 路由旅程二跑：仅在 source digest sha256:60399d57bf01716d0d27c77b2d42a04c43120ef6f247d4c558b4706118068271 上，使用 openai/deepseek-v4-flash，以真实 AgentLoop（含默认 WRAP_UP_ROUND=8，round_cap=10 大于阈值）执行 R01_retention_curve_routing_journey 恰好 1 次：轮次至多 10、每轮按冻结阶梯 [2000, 8000, 32000] 单次非流式请求、该轮 finish_reason=length 即升档，总计至多 30 次 Provider 调用，使用 2026-08-26-gate-c-journey-r09-freeze.md 冻结的问题（显式数据路径）、数据 hash、temperature=0、timeout=120 秒与契约（load_data 与 curve_fitting 必需、最终回答含 0.188/0.982/62 锚点），并仅写入 docs/audit/2026-08-26-gate-c-journey-r09-second-report.json。预检不通过则零调用；失败即停止；不重试、不换模型、不回退、不补跑。
```
