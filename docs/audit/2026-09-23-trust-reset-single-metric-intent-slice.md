# 单项指标请求与工具身份：插入切片（2026-09-23）

## 边界与历史背景

基线为 `main@88da00bbfedb5f2cbb8749c37cca8940af875d00`；本切片没有调用真实 Provider、启动浏览器或引入新模型请求。原始三计划仍要求：保留有据分析价值、不能因词语缩窄用户综合目标、每个明确子问题要有回答或诚实缺口；硬门只承担可封闭的证据判定。R7—R21 的散文误拒/误放、R4 M02/M03 的候选与 `answer_bindings.v1` 种子，以及 Phase 2 后的观测/派生宿主渲染，均是设计背景；被中途叫停的 R4 不是唯一依据。

额外只读核对了本地实际会话：`sessions/9810fe7bacf6` 是省钱卡长篇多指标与因果/补充分析混合请求；`sessions/9959216b6a4a` 是留存公式拟合；`sessions/8ddfa3029b15` 有后续“做 LTV”及真实业务参数确认。这些是旧产品行为的样本，不作为正确答案 oracle。尤其前两会话的 `analysis_spec.metrics` 分别出现泛化的 `retention` 与占位 `target_metric`，不能授权具体指标。现有 `TurnIntent` 仅含路由类型、清晰度、行动及歧义，LLM 分类结果也不返回可核验的指标/分母/窗口；意图识别可帮助区分开放任务，却不是发布事实身份。

## RED → 结构化替代物 → 旧门退役

- RED：`请回答复购率` 的生命周期返回零个 requirement；即使回执中有精确 `复购率.value`，用户单项也可被遗漏。若仅靠“直接请求”句式强制缺口，`请给出结论` 会被错误改写为“结论无同名指标回执”。聚焦 RED 首轮 3 failed/1 passed；此误伤追加反例单测也确实失败。另有同名多来源与真实零值的边界。
- 结构化替代物：沿现有 requirement 生命周期记录 `single_direct_candidate`，不创建第二意图、claim 或账本通道。仅当**当前发布包**中有唯一、有限数值、工具所有的同名路径段或同回执 `metric/value` 对时，标记 `metric_identity_status=verified`；这时该用户项才接受现有 `answer_bindings.v1` typed observed/derived claim 的宿主校验与原位渲染，或需具体缺口。两个同名数值不能任挑其一；真实零是有效数值。无匹配或多义时仅 `unassessed`，不自动生成指标缺口，也不将模型/`analysis_spec` 标签升级为 `answered`。候选抽取只是现有请求前缀的更窄直接结果句式，不能用于解释开放分析语义。
- 退役旧门：单项未被抽出便默认完整的放行，以及把直接请求句式、意图分类或旧 plan 的指标标签当成硬性指标身份的做法。无新增发布词表、第二 planner、隐藏模型审核或额外 Provider 调用。

用户在发现“请给出结论”误伤后明确裁决：**仅同名工具身份设硬门；无匹配保持 `unassessed`，不自动生成指标缺口。** 因而初版宿主自动缺口渲染已撤销，误伤反例保留为回归。

## 验证与未关闭风险

定向五文件（覆盖、发布、数值、M02 情景、Shadow 协议）最终为 **199 passed**。`tmp/tprb10` 的 2879 passed/1 skipped/16 warnings/0 failed 只对应软候选局部发布边界再次收窄前的源码快照，不可冒充最终收据。最终 fresh `tmp/tprb11` 全量离线为 **2880 passed、1 skipped、16 warnings、0 failures**；JUnit `tests=2881/errors=0/failures=0/skipped=1`，SHA256 `0F35FBBAC0E71C1F9003846D5C46C742B15E8E7660B54F5F68198042C69A86BB`，runner `provider_calls=forbidden`。这些验证只属本地 E2，不代表内置浏览器或真实模型。

本切片**不**证明所有无绑定散文安全。尤其无同名回执的 `single_direct_candidate` 不构成发布硬门；如果模型仍在自由散文声称一个无据数值，本切片不会据此宣称已经解决全局数字溯源。其正确后续是扩展同一 `answer_bindings.v1` 的 claim 族与宿主渲染，并以多历史正反例校准，而不是恢复基于邻近词语/数字的猜测门，或把 Shadow 当总审批门。开放分析任务、复合请求、语义同义词、窗口/分母差异也不会因这一小切片被误报为完整支持。
