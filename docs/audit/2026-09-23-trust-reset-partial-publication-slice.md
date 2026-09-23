# 可信发布重置：修订失败后的独立 claim 保留

日期：2026-09-23。基线 `main@dcaee2cd7b08d2c8fc9f974596d9be38d14893b2`。这是 CR07 的 Shadow 前确定性垂直切片；非浏览器或真实 Provider 验收。

## 历史目标与 RED

三份原始计划共同要求：不以规划任务状态或一次错误清空已核验业务价值（VP/IC），CP CR07 明确“未支持主张受限，独立可信部分保留”，总计划 §4.3—4.5 要求宿主确定性验证、原位渲染和逐 claim 降级。历史 R8/R11/R14/R16/R21 同时存在误删正确内容与未支持主张漏过，不能只针对被中途叫停的 R4 单例修补。上一切片已在 `answer_bindings.v1` 建立观测事实、派生量及 M02 情景的宿主可渲染路径，但一次修订失败后的末端仍是全局报错。

本阶段先写 RED：同一候选里“收入”有当前回执、唯一占位符及合法 `observed_fact`；“复购率”错误地引用收入 fact，且自由正文另写“复购率为20%”。第一次调用保持 `(None, error)` 并进入既有一次修订；修订额度用尽的第二次现行结果仍是 `(None, error)`，正确收入 claim 被一起吞掉。反向控制是没有任何合法 typed claim 时必须继续 fail-closed。另检查情景 claim 不得为无关收入 requirement 冒领 `answered`。

## 结构化替代与退役旧门

只在**已有一次修订且再次失败**时，对当前 packet 的解析结果筛出 `observed_fact`、`derived_metric`、`scenario_extrapolation` 中已通过各自宿主校验的 block。每个 block 单独重新走宿主 renderer；相同明确 requirement 至多保留一个已核验结果。其它自由散文、无效 block、原候选中的错误数字、内部 binding fence 均不复制到结果。若一个合法 block 都没有，继续原有非成功错误。

宿主生成正文“已核验的独立结果”和“尚未核验的子问题”；后者在 packet 中保持 `answer_coverage=unassessed`，不能伪装成 `answered` 或计算值。只有观测/派生的相关 requirement_ref 可计入覆盖，M02 情景的任意 requirement_ref 不得替不相关问题授权。持久化的 `answer_bindings` 缩为实际保留的 block；不新增 planner、台账、额外模型调用、末尾免责声明或全篇模型改写。退役的旧门是“修订额度耗尽就整篇丢弃”，不是确定性数值/范围/确认阻断。

## 验证与限制

定向六文件 205 passed，包括首次仍请求修订、耗尽后只保留收入、错误 20% 不可见、无可信 claim 继续拒绝、无关情景不能抢占覆盖，以及既有 M02/数值/持久化回归。新短目录 `tmp/tprb9` 的现有 `run_regression.py full-offline`：**2873 passed、1 skipped、16 warnings、0 failed**；JUnit `tests=2874/errors=0/failures=0/skipped=1`，SHA256 `4054E729530292EBF93DCA89172363813E2DEE5A7E6AE59CC34F8611293B1F90`，runner `provider_calls=forbidden`。这是 E2，不是 E3/E4。

该切片是失败后的安全降级，不代表自然模型会主动生成足量 typed binding，也不解决单一问题未抽出 requirement、比较/拟合等未类型化结论、正确解释性散文保留率。当前宿主降级会丢弃未类型化解释，仍需跨 R7—R21/R4 的正反样本评估价值损失；不能因此放宽错误自由事实，亦不能把 Shadow 变成随机总审批门。E3 Provider-disabled 浏览器及 E4 真实 Provider 均未运行；E4 仍需新冻结和显式授权。
