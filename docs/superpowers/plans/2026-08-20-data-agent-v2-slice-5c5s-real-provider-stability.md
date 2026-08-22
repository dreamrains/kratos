# Data Agent V2 Slice 5C5S：真实 Planner 最小重复性协议

- **日期**：2026-08-20
- **状态**：两份条件式单次调用已完成；稳定性 FAIL，已停止
- **基线提交**：`d465b405ded787774f4dfff904ef3881ec5e0726`
- **source digest**：`sha256:4d0895b17d6f5a62b0a8fd470ecb8d8b0efd3067495b538f86d0e15581906c93`
- **本切片 Provider calls**：2

## 1. 实施时发现并纠正的边界

最初考虑新增 Python 稳定性合同和 RED 测试。但 `compute_release_source_digest()` 明确纳入 `src/`、`scripts/`、`tests/` 和 `pyproject.toml`；该草案会把 digest 从 `4d0895...` 改为新值，并立即使 5C5Q 的成功样本 stale。如此一来，原计划的“1 个现有样本 + 2 个追加样本”会退化成至少 3 个全新样本，增加调用成本且失去当前闭环价值。

因此撤回未提交源码草案，不放宽现有单次 preflight，也不增加兼容层。5C5S 只增加 docs-only 的执行与证据协议，继续复用已经由当前源码 validator 验证通过的 5C5Q 单次 preflight。文档不参与 release source digest，现有成功样本保持 current。

## 2. 当前冻结身份

- 场景：`unified_analysis_entry`；
- Provider 目的：`analysis_planning`；
- 模型：`openai/deepseek-v4-flash`；
- Provider host：`api.deepseek.com`；
- dataset fingerprint：`sha256:90457a00971443e408347fa586fa933e9f924d13e611a879f57165836c9db20a`；
- release preflight identity fingerprint：`sha256:f2908f90327a0e43ce6fc9c74eb574a7e3d5311abe564be2ec3b0000d806385d`；
- Planner schema fingerprint：`sha256:6d0eaf57ac63110ee5cc6ca5a6290bc7fe206c69cb6a7b4d943cf60a9ac363e8`；
- baseline plan identity fingerprint：`sha256:e3c1a3bfbc8ac82b99bdb15832b88b1114b932570e92a2ac772379dc860228e9`。

当前单次 preflight 已重新执行 validator：PASS，reason codes 为空，Provider calls 0，authorization issued false。estimated input 为 3,510，available input 为 992,000，`fits=true`。

## 3. 三样本最小重复性设计

5C5Q 是当前 digest 上的 baseline：恰好 1 次 Provider call、0 retry、ready plan、确定性续跑 PASS、独立复算一致、真实 Provider receipt PASS。

追加两个 trial，但不创建可消费两次的 pooled authorization：

1. `5c5s_additional_1`：只签发一份恰好 1 次的 runtime authorization；
2. 仅当第一轮全部 PASS，才签发 `5c5s_additional_2` 的另一份恰好 1 次 runtime authorization；
3. 每轮重新估算并严格比较实际 model 与完整 planning context；authorization ID、client action ID 和 consumer request ID 必须唯一；
4. 任一轮失败，立即停止，不签发下一份 authorization，不自动 retry、repair、fallback 或补跑；
5. 每个 ready plan 都继续执行零 Provider 调用的确定性分析、独立复算和安全证据记录。

因此用户可一次确认整个条件式协议，但运行时仍是两份隔离的一次性授权。第一轮失败时总新增调用数为 1，第二份 runtime authorization 不会签发或消耗；两轮都通过时总新增调用数恰好为 2。

## 4. PASS 与失败定义

稳定性 PASS 需要 baseline 加两轮追加样本共 3 个 PASS，并且：

- release preflight identity、模型、数据、问题、完整 planning context 和 Planner schema 完全一致；
- normalized `analysis_kind + parameters` 与 baseline plan identity 完全一致；
- 每轮 Provider calls=1、automatic retries=0、authorization consumed once；
- 每轮 planning 为 ready，确定性续跑通过，统计值与独立复算一致；
- 不保存 API key、原始 Provider response、reasoning 或不受控模型文本。

Provider/Planner 错误、`needs_input`、unsupported、plan identity 漂移、确定性续跑失败或独立复算不一致都使该轮失败并触发停止。失败不是自动修改 Planner 合同或模型适配的依据；必须先分析受控证据。

## 5. 授权边界与后续

当前只完成零调用协议，尚未签发 runtime authorization，也没有调用 Provider。用户此前表示“可以再授权 5 次”是预算意愿，不等同于当前精确协议授权。

建议的精确授权为：允许在本文件冻结身份上顺序执行两份单次调用；第一份恰好 1 次，仅当 PASS 时第二份再恰好 1 次；允许向 `api.deepseek.com` 发送同一规划元数据；任一失败立即停止，不重试。

即使稳定性 PASS，也只会解除人工语义评审中的 stability blocker，不会自动签发 human-semantic receipt。仍需独立人工逐维审查；完整产品矩阵的其他场景也不会因此自动 PASS，不授权根入口切换、旧系统删除、push 或 merge。

证据：

- `docs/superpowers/evidence/2026-08-20-v2-5c5s-real-provider-stability-preflight.json`；
- `docs/superpowers/evidence/2026-08-20-v2-5c5s-deterministic-evidence.json`。

## 6. 条件式调用结果

用户按本协议授权两份顺序执行的单次调用。第一轮使用全新的 session、authorization、client action 和 consumer request identity，恰好调用 1 次、0 retry，返回与 baseline 完全一致的 `ready/multi_finding_synthesis` 计划；确定性续跑为 HTTP 200/200、5 个 blocks、2 张图，语义指纹与 baseline 相同，独立统计复算一致。因此满足第二轮签发条件。

第二轮再次使用全新的运行时身份，恰好调用 1 次、0 retry；upload/estimate 为 HTTP 200，authorization/planning 为 HTTP 201，authorization 已 consumed。Provider 返回合同合法的 `needs_input` 计划，包含 2 个问题，没有 route 或 parameters。它不是 transport、Planner contract 或 context-window 失败，但与 baseline/第一轮的 normalized plan identity 不一致。

协议因此判定 FAIL：3 个同 digest 样本中 2 个 PASS、1 个 FAIL，没有达到 3 个匹配 PASS。第二轮没有执行确定性分析，没有保存或回答问题文本，没有 follow-up、repair、retry 或补跑；两份授权均已耗尽，用户此前保留的 3 次预算并未自动获得授权。

当前安全证据只能确认同一冻结请求产生了两次相同 ready plan 和一次合法 needs-input 分歧。该现象与 Provider/模型规划变异或 prompt 中仍存在可被不同解释的歧义一致，但现有脱敏证据不能确定 Provider 内部原因。不得据此直接放宽 `needs_input` 合同或自动填答。

新增证据：

- `docs/superpowers/evidence/2026-08-20-v2-5c5s-trial-1-attempt.json`；
- `docs/superpowers/evidence/2026-08-20-v2-5c5s-trial-2-attempt.json`；
- `docs/superpowers/evidence/2026-08-20-v2-5c5s-stability-result.json`。

## 7. 共享合同诊断与下一切片

代码核查确认，当前 planning metadata 只包含 filename、source fingerprint、row count 与列的 name/dtype/role；它没有显式说明行粒度或观察单位的业务语义。`needs_input` schema 在每个 DatasetPlanningContext 中都可选，只约束空 route 和 1–3 个问题；system prompt 没有定义何时才允许选择该分支，compiler 也不验证受控 prerequisite 是否确实缺失。现有测试证明 status/payload 形状一致，却没有覆盖 `needs_input` 的语义资格。

这构成共享合同缺口，但不能据此简单强制 ready：identifier role 或字段名并不能证明独立观察单位。下一切片应先写 RED 回归，为缺失 prerequisite 增加受控身份，并使 tool schema、system contract、compiler、Plan Ledger 与 HTTP 投影共同约束 `needs_input`；完整上下文上的无依据 needs-input 必须 fail closed，真正缺失语义的上下文仍保留澄清路径。该修复会改变 source digest，开始前必须明确接受现有 source-bound receipts 将 stale；本切片不直接实施。

诊断证据：`docs/superpowers/evidence/2026-08-20-v2-5c5s-needs-input-diagnosis.json`。
