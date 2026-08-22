# Data Agent V2 Slice 5C5W：真实旅程语义 preflight gate

## 目标

将“真实统一旅程已经显式确认分析单位”从可选 preflight 元数据升级为 PASS 的硬条件。API 产品流仍允许用户明确暂不确认并接受受控 needs-input；release real-provider journey 则不得为可预防的语义追问消耗一次真实调用。

本切片不调用 Provider，不推断 `unit_id` 的业务含义，不签发 authorization。

## RED 基线

在 5C5V 已能绑定 semantic context 后，未传 `confirmed_analysis_unit_column` 的 real-provider preflight 仍返回 PASS。聚焦 RED 证明 release validator 没有区分“结构合法的未确认上下文”和“已经满足真实旅程调用前提的上下文”。

## 实施范围

1. real-provider preflight 升级为 v6；
2. validator 对空 `confirmed_analysis_unit_column` 返回稳定 reason code `real_provider_analysis_unit_unconfirmed`；
3. validator 接收独立重算的 `expected_semantic_context` 并严格比较，漂移返回 `real_provider_semantic_context_mismatch`；
4. semantic context 仍属于 request fingerprint；直接篡改同时触发 fingerprint mismatch；
5. stop conditions 增加 `analysis_unit_semantics_unconfirmed`，明确必须在 Provider 调用前停止；
6. CLI 未传确认列时退出非零；显式传入合法列时才可能 PASS；
7. 更新所有 validator 消费方与 provider-neutral regression。

## 明确边界

- release preflight 的严格 gate 不删除正常产品流中的“暂不确认”选项；
- `unit_id` 只在确定性测试中作为显式参数，不因此成为真实旅程的用户确认；
- preflight PASS 只证明调用身份、预算、schema 和停止条件闭合，不是 Provider journey PASS；
- 不自动调用、重试、repair 或补跑；
- 不切换根入口、不删除旧系统、不合并或推送。

## 验证

- 未确认和已确认 preflight focused tests；
- CLI fail/pass 双路径；
- V2/config 全量确定性测试；
- compileall、JSON parse、`git diff --check` 与 release source digest。
