# Data Agent V2 Slice 5C5V：首次调用前语义冻结

## 目标

把 5C5U 的分析单位语义确认前移到第一次 Provider 调用之前，并同时绑定 planning estimate、runtime authorization、Planner request 和 release preflight identity。避免系统已经能够安全收集的业务语义仍需先消耗一次 Provider 调用才能进入 needs-input。

本切片不调用真实 Provider，不自动推断或选择分析单位，不改变单次精确授权和失败即停边界。

## RED 基线

实现前四项聚焦回归稳定失败：

1. `ProviderAuthorizationStore.issue()` 不接受 semantic context；
2. authorization 按 `unit_id` 签发后，plan request 改为 `sales` 仍会调用 Planner；
3. 匹配的首次调用语义不会进入 `DatasetPlanningContext`；
4. real-provider preflight 无法接收或绑定用户确认的分析单位。

这些失败证明 5C5U 只闭合了 needs-input 派生链路，尚未闭合首次调用链路。

## 实施范围

1. runtime authorization fingerprint 增加规范化 `semantic_context`，Ledger 持久化并在 consume 前严格比较；
2. estimate、authorization issue 和 plan create 接受同一受控 semantic context；未知列、非法字段、planning-input 冲突和消费时漂移均在 Provider 调用前 fail closed；
3. planning estimate 返回 eligible analysis-unit columns 和当前确认值，不签发授权；
4. Workbench 第一次估算只加载候选列；用户必须显式选择列或明确选择“暂不确认”，语义变化使旧 estimate 和 pending authorization identity 失效；
5. 第二次无模型估算冻结选择后，才显示“一次调用”确认；
6. provider-neutral fixture 在预确认 `unit_id` 时首次即返回 ready，证明无需先走 needs-input；未确认路径继续保留原 failure/retry 夹具；
7. real-provider preflight v5 接受显式确认列，并将 semantic context 纳入 release request fingerprint。CLI 未传参数时保持未确认状态，不从列名推断。

## 明确边界

- Workbench fixture 中选择 `unit_id` 只验证产品链路，不是用户对真实 Provider 调用的业务语义确认；
- API 仍允许明确“暂不确认”，此时 Provider 可以按受控合同返回 needs-input；
- 不生成可复用的 pooled authorization，不自动 repair、重试或补跑；
- 不签发 real-provider、stability 或 human-semantic PASS receipt；
- 不切换根入口、不删除旧系统、不合并或推送。

## 验证

- authorization、planning HTTP、preflight 和 Workbench focused tests；
- provider-neutral 浏览器旅程：首次估算、显式选择、重新估算、一次授权、ready plan、确定性执行；
- V2/config 全量确定性测试；
- compileall、JSON parse、`git diff --check` 与 release source digest。
