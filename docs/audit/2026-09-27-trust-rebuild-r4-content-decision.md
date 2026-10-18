# R4.1 同包解释与局部交付设计裁决

本记录从 `codex/trust-rebuild-20260927@c9447cc` 的正常 app 路径复核原始 M01/M06 需求。批前选定 `local_http_api`；Provider 禁用，视觉 oracle 为 `unassessed`。`tmp/r3contentbase1` 使用仓库指定 rehearsal 入口，端口 5234、监听 PID 25484、长时 exec session 51842，批后通过该 session 停止；健康 `ok=true/provider_enabled=false`。M01 控制脚本 SHA-256 `CD607059FCFD3C10415E273188B928FD74F45FBCF6FD953EFC747FB7C8EF9BED`；M06 控制脚本 SHA-256 `18482118288227F8EC18C82A4BD12668100284A89F7D827557CC2224ABCBFA50`。

M01 会话 `9cb594353646` 六轮各有唯一 `turn_end` 且 durable completed。六份最终正文完全相同，均有源表 12 行、派生表 1 行、amount_sum 120、amount_count 12、方法和未知单位；有条件建议 0，表达变化 0。发布包的 `candidate_resolution=superseded_by_current_receipt_claims`，即聚合宿主分支整体代替模型候选。结果 JSON SHA-256 `C22512D5454752602B72DA3DA07770B31D020CA22CB1EAA293FB57EA31FA6C9D`。

M06 缺失会话 `1141d70034d7` 未造值，只给加载数据的下一步。成本会话 `f9079cac11df` 先 `suspended`，选择“代金券及渠道成本”后同会话 `completed`；但模型恢复正文只说复用了业务口径，未执行金额聚合，不能把 120、净收益或成本数值标为已算。结果 JSON SHA-256 `BB5E5DECDA5A4CCB62DB35966A14CD57F00F7F9EEB4DDD609E99AB52066E11F3C`。两个控制批的 `runtime.jsonl` 均无 `forbidden_provider_transport`，实际 Provider initiated calls 0。HTTP app 不能证明 picker、视觉呈现或浏览器刷新。

## 正反输出判据

| 输入/情况 | 应保留或交付 | 必须限制 |
| --- | --- | --- |
| M01 当前 F-SALES 12 条，每条 amount=10 | 120、12、当前 12 天、非空原值求和、业务单位未知、描述性范围；业务/分析/管理/大白话/技术表达应可区分 | 不能称真实交易、总体收入、投放效果或因果；12 天总额不能直接与下一周比较 |
| M01 有条件行动 | 仅在同口径、同长度、同粒度的新窗口可比时，以可观测指标变化触发核查；若成本或效果证据缺失，不决定扩投或停止投放 | 任意阈值、不同时间窗比较、把观察变成因果或确定经营结论 |
| M06 确认“代金券及渠道成本” | 记录有效选择及适用范围；若随后真实计算订单总额，保留该独立正确结果；净收益未算与成本/增量证据不足分别说明 | 选择不等于成本数据，未算不等于 0；不能从没有回执的恢复轮次发布 120 |
| M06 缺失源表或工具失败 | 明确未执行/未完成和一个可行动的补数步骤；保留先前独立正确结果 | 不能把失败轮次记为已计算，也不能让失败抹掉无关已核结果 |

## 生产结构决定

1. 同一 `publication_synthesis` packet 和 `answer_bindings.v1` 承载三种责任：宿主验证并渲染封闭数值/方法/版本；受限解释候选在原位置保留与当前事实的引用；需求交付状态明确 `answered / not_computed / evidence_insufficient / unassessed`。来源词检索、自由文尾注或 journal 均不能产生该状态。
2. 聚合宿主分支不能再把有效表达与解释整段丢弃，也不能把当前不可信的“下周低于 120”直接附回。候选建议必须有可核的指标、范围、比较窗口和条件，宿主负责核对这些封闭关系；开放的因果、行动意义与语气留给现有 `publication_audit` 证据绑定审核。审核发现只能定位片段、要求一次定向修订，不能加事实或覆盖数值/版本失败。当前 Shadow 历史关键风险只命中 1/4，故未经新校准不能改正式默认或自动批准开放建议。
3. 若本轮没有所需计算回执，结果状态是 `not_computed`；若口径已定但缺成本金额或促销增量证据，相关净收益判断是 `evidence_insufficient`。二者可同时出现，必须与已算订单总额分开。恢复确认后由正常 AgentLoop/工具轨迹产生回执，宿主不得从 F-SALES 文件或旧候选偷偷代算。
4. 先用现有 packet/renderer/确认内核完成最小纵向实现，保留正确结果并针对不安全解释局部降级；用正反 app 批验证正文、SSE、持久/导出同一答案。若不能在同包保留正确解释又阻断无据建议，则记录原 DoD 未满足，转受限发布决策，不把模板文案或 `unassessed` 改名为通过。

供体最终 `publication_audit.py` 有 747 行，依赖供体 `publication_synthesis.py` 的 `_observed_binding_issue`、`_derived_binding_issue`、`_comparison_binding_issue`、`_descriptive_fit_binding_issue` 等验证接口；较小重建树的当前 3507 行 publication 模块没有这些接口（供体为 4856 行），所以不能整文件回迁并声称审核可用。下一实施片须先按目标树现有 `observed_aggregate`/`observed_comparison`/M02 block 验证器建立最小可核 claim view，再取供体定位 pending prose、结果契约和 Shadow 诊断函数的必要片段；自动处置仍需正反价值校准，不随模块存在而启用。

此裁决针对同一根因重复出现的“宿主整体替换正确结果旁的解释”和“确认恢复无回执仍想交付数字”。下一轮应改变组合/执行接口，不做第三轮关键词、同义词、尾注或离线字段补丁。
