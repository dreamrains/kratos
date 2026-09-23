# 可信发布重置：观测区间描述拟合 claim 垂直切片

日期：2026-09-24。实施基线：`main@a96fd18eeda02cf5441371fe1cdb6f2a96c8cfbf`。只扩展既有 `answer_bindings.v1`、`curve_fitting` 回执及当前发布包；没有新 planner、账本、浏览器框架、语义词表、审核模型调用或真实 Provider 调用。

## 原始目标与跨历史背景

三份原始计划要求：保留已观察范围内有证据的拟合结果和必要口径；严格分开描述拟合、未验证情景、可信预测及因果；明确子问题不得由关键词或模型自报覆盖。R4 M02 的正确候选被散文配对门误删，但 R4 被中途停止，不单独作为完整 oracle。R11 的正确 D7/无 D30 边界、R14 的 CV 算术问题、R16 的“同比例”与无依据样例推断、R21 的任务权威冲突，以及 R7—R21 曾经多轮离线绿而真实失败，共同要求同时检验误拒与误放。本轮没有把旧真实会话中的自然答案自动视为正确样板。

上一切片的 `scenario_extrapolation` 已可在用户请求 D30 时渲染参数、R² 和情景值；但仅请求解释观测曲线时，不能靠虚构一个未来时间点才能使用宿主表格。真实 `curve_fitting` 工具返回 `points/fits/effective_n/claim_ceiling`，`publication_contract` 把全部族参数、R²、观测 x 范围和验证状态投影到同回执 `publication_scope.scenario_extrapolation`。本阶段测试不仅使用 R4 形状，也调用实际工具函数构建 packet。

## RED → 结构化替代物 → 旧门退役

- RED：在基线添加四条聚焦测试，正确的观测拟合 `claim_type=descriptive_fit` 因占位符未获 typed 校验而失败；缺族、模型自报 R²、外来回执及伪造预测/验证状态也没有专属拒绝。初跑为 **4 failed**。
- 结构化替代物：在同一 `answer_bindings.v1` 使用唯一 `[[claim:...]]`、`status=descriptive`、`unit_status=not_confirmed`、`validation_status=none`、当前 `curve_fitting` receipt_ref 与回执中**全部**族名；三个 refs 数组为空，不擅自把未匹配子问题标为 `answered`。宿主确认同一当前 source/scope、描述等级、至少 5 个有效点、有限观测范围、全部有限参数和 R²、无模型提供的显示值，并在占位符原位按**回执排序**渲染三族参数和 R²。结果注明仅限观测范围，未做留出/回测/外部验证，单位与零值含义未确认；不渲染外推、预测、显著性或因果。渲染前再次验证以防 packet 变化。
- 旧门退役范围：这类观测拟合事实不从自由散文中的族名、R² 和措辞反向凑证据；模型若不产出有效 typed 绑定，仍不能靠散文占位符放行。其它自由散文门并未整体拆除，也未添加关键词。修订后局部发布只保留独立且重新校验的宿主结果。

## 本阶段证据与仍未关闭的边界

新增测试覆盖历史 R4 形状、真实工具输出、缺族/伪造值/外来回执、伪造预测或验证状态、非有限值/布尔参数、点数与单位状态、渲染前变更、局部发布保留，以及正常/伪造候选的终局发布路径。七个相邻测试文件最终定向离线为 **216 passed**。`tmp/tprb13` 在最后一条终局路径用例加入前全量离线为 **2896 passed、1 skipped、16 warnings、0 failures**，JUnit SHA256 `915904D8989AEDB33BF50395581CF61E8CC71BF3684F95C42BA12A5ABD5E23C5`；它是前一测试快照的有效收据，不冒充最终集合。`tmp/tprb14` 在最终测试集合中为 **2896 passed、1 skipped、1 failed**；唯一失败 `test_offline_tool_surface_smoke` 的子进程超过原有 180 秒上限，JUnit SHA256 `6A529921EFA02B3318B86A0957F929B925B2A18B1008A64E6B0FC76FAF75956E`，保留为失败收据，未调阈值或改产品代码。随后全新 `tmp/tprb15` 完整离线 **2897 passed、1 skipped、16 warnings、0 failures**，JUnit `tests=2898/errors=0/failures=0/skipped=1`，SHA256 `63BB3C4378B329AC315922353FE637C084EC1B9F2830E20B249F9142EC2F349F`，runner `provider_calls=forbidden`。最高证据等级为 E2，不能称 E3 浏览器或 E4 真实 Provider。

这不是自由散文风险的总修复：有效拟合表旁仍可能有另一句无绑定的错误数字或过强结论；没有工具指标身份时仍不得凭模型标签升级 `answered`。描述拟合也不自动支持 D30、经过验证的预测、显著性、因果或条件建议。带维度比较、通用未绑定数字、用户问题到指标的语义映射仍未封闭；不以新词表、整篇尾注或 Shadow `overall=pass` 代替结构化证明。真实 Provider 前仍须新的精确冻结和显式用户授权。
