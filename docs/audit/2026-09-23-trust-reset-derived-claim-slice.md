# 可信发布重置：派生量 claim 垂直切片（Shadow 前）

日期：2026-09-23。基线 `main@32640302a064063b382f1267e0abf41faf3c3e08`。本文件记录该基线后的插入修复，不是完整 Shadow、浏览器或真实 Provider 验收。

## 1. 历史目标与精确 RED

对照三份原始计划：VP P4 要求用户子问题到相关结果的可恢复映射；IC 不允许方法模板取代真实业务缺口；CP CR03/CR04/CR07 要求明确子问题的覆盖、数字/单位/派生一致，且正确独立结论不被一条错误清空。总计划 §4.2—4.5 规定沿用 `answer_bindings.v1`、宿主验证与原位渲染，模型散文不承担事实数据库职责。不能只按最近被叫停的 R4：历史 AC22—AC27、R8/R11/R14/R16/R21 同时提示算术错误、来源/版本混淆与正确内容误删的双侧风险。

基线现场：AC22 的 `22400 × 0.051 = 1142.4` 在既有 `EvidenceRecord.derived_measurements` 中通过宿主复算，旧 `answer_bindings.v1` 散文“留存人数约1142人。”也通过旧显示值检查；但新的明确子问题结构门正确地不把该散文当 `answered`，只读复核得到 `binding_issues=[]`、`publication_issues=[unbound_requirement_numeric, missing_answer_requirement]`、`answer_coverage=unresolved`。这是一处需迁移的**正确候选误拒**，不能放松数值门来解决。相反，只要模型把 EvidenceRecord 的 `metric/claim_key` 改写成别的指标，数值复算仍可能成立，故它不是指标身份权威。

用户在本阶段明确裁决：**仅工具回执中的可核验指标身份授权 `answered`**。EvidenceRecord 标签只作线索；算术正确但工具身份未证实的结果保持 `unassessed`/具体缺口，不能交给 Shadow 充当随机总审批门。

## 2. 结构化替代与旧门退役

仍使用一个 `answer_bindings.v1`：`claim_type=derived_metric`、`status=computed`、`unit_status=not_confirmed`、唯一 `claim_id/exact_text=[[claim:...]]`、一个 `requirement_ref`、一个工具 `fact_ref`、一个 `derived_ref`。宿主按当前 packet 确认工具事实路径中的精确指标名，或同一回执的精确 `metric/value` 对；该事实为有限数值。EvidenceRecord 的派生项必须唯一且引用同一工具回执，操作数须经既有封闭运算 validator 重算，内部数据身份一致；如当前工具回执携带版本/指纹，操作数版本还必须与之匹配。派生结果与工具事实数值必须相等。任何一步失败都不给 `answered`。

通过后由宿主在占位符位置渲染**工具回执的原始数值尺度**，并紧邻说明单位未确认及派生算术已复算。不从字段名、模型自由句或 EvidenceRecord 标签换算百分比。真正的零值保留为结果，不能改写成缺失。版本核对仅限该派生的 `operand_refs`：同一 EvidenceRecord 中无关的另一版本测量不能阻断独立可信结论，而被引用的跨版本操作数仍拒绝。旧 `_binding_numeric_issues` 对自由句末数字的检查继续约束 legacy 块，但不再解析 typed 派生占位符；typed 路径由同回执事实和宿主重算取代。没有新通道、规划器、账本、浏览器框架或审核模型调用。

## 3. 回归及未完成范围

先加三条并实测 RED：正确 typed 派生占位符未被接纳；模型标签不能让无关工具事实授权；派生值/回执链接不一致未被专属绑定错误识别。随后加入真实 packet 构建正例、跨版本操作数与当前回执版本、伪造已确认单位、观测与派生真零值，以及无关测量版本不误阻断的正例。定向五文件 189 passed。`tmp/tprb7` 在最后这条作用域收窄之前完整通过 2869 passed、1 skipped、16 warnings、0 failed，JUnit SHA256 `52B5AE03893D2ABD388A7C250DA44A77B7FCF1139495BAF66F958D38501B85E2`；它是前一代码快照的有效收据，不是最终实现收据。最终代码的新短目录 `tmp/tprb8` 全量 `full-offline`：**2870 passed、1 skipped、16 warnings、0 failed**；JUnit `tests=2871/errors=0/failures=0/skipped=1`，SHA256 `C573A466350818F1AFF8722DCDDB2C45ADDE9D13015B5C4F82251060D13A15DF`，runner `provider_calls=forbidden`。此阶段最高只到 E2，不是 E3/E4。

这个切片仅覆盖工具已有**同指标、同数值** fact 的简单派生量，不承诺证明任意自由文本语义。没有工具指标身份的 EvidenceRecord 仍不得自我授权；比较/拟合/复杂范围、单一问题未抽成 requirement、无数值但过强的自由结论仍待逐族 RED 和结构化映射。当前一条无效 binding 会拒绝整个候选并触发既有一次修订；若修订失败，并未证明其它独立可信 claim 能单独发布，CR07 的异常路径仍未完全关闭。下一阶段必须同时保留 R7—R21/R4 正确与错误候选，检查独立可信 claim 保留率和未绑定事实检出率；不能回到词表补丁，也不能让 Shadow `overall` 覆盖确定性失败。E3 浏览器和 E4 真实 Provider 均未在此执行，后者仍需新精确冻结及用户显式授权。
