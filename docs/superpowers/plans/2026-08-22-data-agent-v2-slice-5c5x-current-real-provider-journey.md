# Data Agent V2 Slice 5C5X：当前源码真实 Provider 旅程

## 已冻结身份

- source digest：`sha256:2dbb829eefb47652556222dfc055faa64a97b8fb0950e50d7d6518e675181fba`
- scenario：`unified_analysis_entry`
- fixture：`tests/fixtures/v2_slice4d_combined.csv`
- model：`openai/deepseek-v4-flash`
- purpose：`analysis_planning`
- analysis unit：用户已确认 `unit_id`
- Provider host：`api.deepseek.com`

正式 preflight 为 `docs/superpowers/evidence/2026-08-22-v2-5c5x-real-provider-preflight.json`。validator 必须在 authorization 签发前重新计算 source、dataset、semantic context、Planner schema 和 token budget，并与该文件严格相等。

## 调用边界

本计划本身不授权调用。新的用户授权必须明确包含上述 source digest、模型、场景、目的、允许发送到 `api.deepseek.com` 的规划元数据和恰好 1 次调用。

授权后只允许：

1. 上传冻结 fixture；
2. 重新估算完整 planning context；
3. 签发一份单次 runtime authorization；
4. 执行恰好 1 次 `analysis_planning` Provider 调用；
5. ready 时执行确定性续跑、浏览器恢复和人工语义评审准备。

任一 Provider、Planner contract、unsupported 或 needs-input 结果立即停止，不重试、不 repair、不补跑。needs-input 的 follow-up 必须重新生成估算和 preflight，并获得新的精确授权。

## 真实数据目录边界

`reference/test_doc` 已获准用于后续测试，但不属于本次 frozen unified preflight。当前只做本地文件清点和结构画像；任何真实文件的外部 Provider 元数据传输必须作为新的场景，单独冻结文件、问题、行粒度语义、source digest 和调用次数并再次获得用户授权。

## 执行结果

用户随后对冻结的 source digest、模型、场景、目的、Provider host、规划元数据出境范围和恰好 1 次调用完成授权。执行结果：

- upload、planning estimate：HTTP 200；
- authorization、analysis planning：HTTP 201；
- Provider calls observed：1；automatic retries：0；
- authorization：`provider_auth_5d41558e9c5e4fe78dd3941da9076f52`，状态 `consumed`；
- plan：`plan_3f2cc581acb91892eb3fcc2e`，规划后 `ready`，确定性续跑后 `consumed`；
- route：`multi_finding_synthesis`；
- 参数完整绑定 `date`、`sales`、`channel` 与用户确认的 `unit_id`。

本次授权已经完全耗尽，不可复用。没有 retry、repair、fallback 或 follow-up Provider 调用。

确定性续跑与刷新均为 HTTP 200，终态为 `turn_completed` / `finalized`，生成 5 个答案块、2 张图和 2 个 Finding。续跑 Provider calls 为 0。HAC 趋势与 Welch/Hedges g 组间差异均经独立复算，与发布值一致；发布内容保留观察性、非因果和非干预效果边界。

因此签发当前 source digest 上 `unified_analysis_entry` 的 `real_provider_analysis_journey` PASS receipt。没有签发 `human_semantic_review` PASS，不宣称完整 release readiness、产品完成或根入口切换。

随后通过实际 Codex In-app Browser 从 `/v2-workbench?session_id=session_real_5c5x&turn_id=turn_real_5c5x_deterministic` 恢复持久化结果。首次加载和完整页面刷新后均观察到 5 个唯一答案块、2 个唯一 figure、2 个 iframe，两个 chart shell 均为 loaded；页面可见错误和 console error 均为空。服务器请求审计只出现 GET，没有 planning 或 analyze POST，Provider calls 为 0。因此另行签发当前 digest 的 `refresh_persistence_journey` PASS receipt。

本步骤没有重跑 provider-neutral 完整浏览器交互 fixture，因此旧 digest 的 `browser_interaction_journey` receipt 仍然 stale；也没有独立人工评审，因此不签发 `human_semantic_review` PASS。

最后在当前 digest 上重新执行统一入口确定性 journey，owner、incident 与 SSE 三层均 PASS，Provider calls 为 0。至此 `unified_analysis_entry` 的 current-source 缺口收敛为：`browser_interaction_journey` 与 `human_semantic_review`。完整产品矩阵的其他场景仍保留各自的真实 Provider、浏览器、刷新与人工语义缺口，不能由 unified 场景代替。
