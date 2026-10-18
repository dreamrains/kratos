# R3.4 / R4 M01 正向判据与比较发布边界

范围：重建树 `codex/trust-rebuild-20260927`，基线 HEAD `d22696d`；供体 `main@b181646` 只读。控制路线在批前选为 `local_http_api`，使用现有 Provider 禁用 rehearsal、正常 `/api/upload`→`/api/chat`→SSE→持久会话→导出。上传 picker、正文视觉和刷新 oracle 为 `unassessed`；本记录不代表自然模型、真实 Provider 或正式默认验收。

## 独立正反判据

- 原 M01 `F-SALES.csv` 不变：2026-09-01—12 共 12 行，每行 amount=10；原值和 120、非空数 12。没有第二可比窗口、成本和效果测量，行动子目标应保持 `evidence_insufficient/checked`；不得把 12 日 120 当成未来 7 日阈值。
- 新增 `F-ACTION.csv` 仅作**正向输入判据**，不取代冻结 M01。2026-09-07—13 与 09-14—20 各 7 行、均为五个工作日和两个周末；每行 `net_contribution=amount-campaign_cost`。独立手算：A 的 amount/cost/net/orders 为 700/140/560/70，B 为 770/175/595/77；B−A 为 +70/+35/+35/+7；成本每单从 2 变为 175/77。`tests/test_r3_m01_positive_oracle.py` 固定逐行关系、窗口和总量，防止只靠模型文案制造“效果”。
- 正向请求明示两个完整日期范围、净贡献列含义和用户自己的未来行动规则：下一等长窗口净贡献不低于基准期且成本每单不高于本期时才考虑小规模受控试验，否则暂停增加预算并复核。两期的净贡献变化是描述性的，不能归因于投放。未来窗口尚无观测，当前资料只可能支持**前瞻监测条件**，不能声称该条件已经触发或投放效果已证。

## 正常 app 基线与发现

首次 `tmp/r3m01positivebase1` 因测试提示把结束日期写为 `09-13/09-20`，被现有 `time_window` 确认正确挂起；该会话没有工具回执，不算产品失败或正向证据。更正为四个完整日期后，新目录 `tmp/r3m01positivebase2` 原六轮及正向一轮均完成。正向会话 `19cb268a0263` 的当前 `compare_periods` 已发布四项正确两期结果，但候选里的下一窗口行动措辞被追加为“补充解释”，`answer_bindings.v1` 只有 `observed_comparison`、`requirement_refs=[]`；正向提示当时也缺少可识别的精确“有条件行动建议”跨度，`answer_requirements=[]`。此段文字没有条件、成本比率或规则身份的宿主绑定，不能凭 `validate_final_narrative` 返回无问题判为可信。它是 R4 内容边界的当前正常 app 反例。

修复将本轮有原话跨度的 `conditional_action` 子目标复用到现有 `answer_requirements`；比较宿主块只绑定一个具体行动缺口并在当前比较位置渲染。若该缺口存在，未绑定的模型候选不进入正文，原稿及 SHA 留在**同一个 publication packet** 的 `candidate_resolution=withheld_pending_semantic_binding`，供后续语义核审；不是第二账本。已核的所有比较行、方法和非因果说明继续发布。该措施只防止本例候选混入，**不把缺口改名为行动建议完成**，也没有宣称覆盖未被语义意图识别的任意开放行动句。

最终 Provider 禁用批次：`tmp/r3m01positivefinal1`，端口 5263、监听 PID 24456、exec session 84022（已停止），launcher SHA-256 `5F99813E93C29FE1A09A36A3307435962A4EBDA07DE511BF48CFC034B83691DA`，HTTP driver SHA-256 `C82E13C396C35BC7D8828E918892F2374D5B188D0563358A10D7C6C806945B87`。启动、两组之间及结束健康均为 `ok=true, provider_enabled=false`。原六轮会话 `4db8d3bbc21e` 全部 `completed`，结果 JSON SHA-256 `3A19D79FFB60EA2D350B6FA1DCF0551503FEBF820045011F7273D2FC2234E7AF`；正向会话 `2aa7f3f98c81` `completed`，结果 JSON SHA-256 `C1DB6A7813A5230CD08E2DDDE76696CE9C0167E5D167F455264DBDA517C033B5`。两上传票据的文件名和 SHA 与本批夹具一致；七轮各唯一 `turn_end`、无 error event、终态等于 durable run state，导出均为 `exported`。原六轮保留 120/12，最后行动缺口 `evidence_insufficient/checked`；正向四行 700→770、140→175、560→595、70→77 均正确，行动缺口同为 `evidence_insufficient/checked`，候选原稿留包但未进入答案。`runtime.jsonl` 中 `forbidden_provider_transport=0`，本批实际 Provider initiated calls=0。视觉 oracle 为 `unassessed`。

## 下一结构实施判定

“有数据列”尚不等于“行动证据闭合”。当前 `compare_periods` 只核各列两期值；产品没有对任意上传数据逐行核实 `net=amount-cost`，没有把成本每单的分母与同版订单事实组合成衍生 claim，也没有把用户原话规则解析为可校验的操作符、触发和停止条件。更没有受控实验或因果效果测量。

下一功能片沿同一 packet / `answer_bindings.v1` 增加**行动主张的结构化候选与宿主验证**：候选须引用本轮原话 requirement、用户规则来源、已发布结果 claim 和当前 `compare_periods` 回执；逐项标明指标/单位、A/B 日期范围及粒度、成本和结果公式、未来同口径窗口、触发/停止操作符及描述性证据上限。宿主重读当前数据身份和原回执，复核两个非重叠等长窗口、逐行净贡献关系、非零订单分母与衍生比率，并拒绝其他版本或未经证实的因果/任意阈值。开放语义审核负责“结构规则是否忠于用户原话”和过度推断；现有 Shadow 校准不足，不能直接授权候选。缺任一条件继续局部发布正确比较与具体缺口，保留候选供审阅。完成后用新目录跑原六轮与正向场景，以及成本缺失、分母零、窗口不等长、版本变化、伪规则、因果越界的反例；再评估 R4 策略和 R5 入口。

本轮没有修改正式默认、调用真实 Provider、推送或部署。R3/R4 仍为 `in_progress`，R5 未开始。

最终代码定向回归 `19 passed`；新目录完整 E2 `tmp/r3m01positivefinalfo1` 为 `2914 passed / 1 skipped / 16 warnings`。这些是确定性和 Provider 禁用证据，不说明自然模型会正确产生结构化行动规则。

## 后续子片：同版行动数值输入闭合（2026-09-27）

按上述下一结构任务，在现有 `publication_synthesis.v3` 与 `answer_bindings.v1` 中接收一个 `conditional_action_inputs` 提案。宿主从当前 `compare_periods` 回执、数据身份及工作空间重读两期源行，核对等长且不重叠的每日窗口、逐行 `gross-cost=net`、非负成本和订单数、正的两期订单分母，并使四项两期总量与当前比较事实一致。持久块记录版本指纹、事实引用、两期总量、成本每单的分子/分母及用户规则原话摘要；状态固定为 `inputs_verified_semantics_unassessed`。模型的行动措辞仍不发表，`conditional_action` 子需求仍为 `evidence_insufficient/checked`。此片没有核准列角色的业务语义、未来窗口触发/停止操作符、规则忠实性或因果效果。

接线诊断按新目录隔离：`tmp/r3m01actioninputs1` 与 `tmp/r3m01actioninputs2` 的原六轮完成，正向因模型未收到预览包而失败。检查持久消息后裁决：比较事实位于 `sources`，不能用 `evidence` 非空门阻断预览。`tmp/r3m01actioninputs3` 两组完成，预览已注入，但其后新增 `record_evidence_record` 使终稿 `binding_digest` 变化，过期提案被正确拒收。故现有 wrap-up 入口在行动预览后仅当本轮回执集变化时刷新同一 packet；不放松摘要验证，也不建第二协议/账本。三诊断批次均 Provider 0，均不作为完整正向交付证据。

最终 Provider 禁用正常 app 批次 `tmp/r3m01actioninputs4`，控制路线 `local_http_api`，端口 5267、监听 PID 23772、exec session 92627（已停止）。启动、两组之间与结束健康为 `ok=true, provider_enabled=false`。launcher SHA-256 `F409A8A3048E4245F3FA87832CF28EB711231DE2EAC7E969924E445C0425E697`；现有 HTTP driver SHA-256 `C82E13C396C35BC7D8828E918892F2374D5B188D0563358A10D7C6C806945B87`。原六轮会话 `eab55981a9a9`、结果 SHA-256 `C1A82CAFD80DCBDFEB052E8F5BD5E3AC3393EC581E3E5B74FDCF7759D0C16C3F`；正向会话 `abf70571f670`、结果 SHA-256 `DA9886281E9A23B22AE4A8FB55884AD6BBC595A18B73ACC2CC9815E4B4EDE09D`。七轮各唯一 `turn_end`、状态 `completed`、SSE 与 durable run state 一致、两份导出 `exported`，上传票据文件名/SHA 经 driver 检查。正向持久包有 `observed_comparison` 与 `inputs_verified_semantics_unassessed` 两块：A=700/140/560/70，B=770/175/595/77；成本每单为 140/70 与 175/77。四项比较仍在正文；行动原稿同包保留且 `withheld_pending_semantic_binding`。`runtime.jsonl` 的 `forbidden_provider_transport=0`，实际 Provider initiated calls=0。上传 picker、答案视觉及刷新仍 `unassessed`。

下一步是 R4 的**用户规则语义闭合及开放解释策略**：把原话中的未来同口径七日、两个同时满足条件、小规模试验与否则暂停复核，连同尚未观测的未来窗口，映射成可定位且可反驳的行动候选；受限语义核审不得新增事实、覆盖上述确定性失败或把描述性变化说成因果。还需反例覆盖错列角色、伪规则、过期版本、零分母、窗口变化与越界解释，并保留正确比较/否定。R3/R4 继续实施，R5 暂不进入；自然模型、正式默认、外部 Git 和真实 Provider 均未获本片授权。

最终代码复核发现需按轮次清零行动预览摘要；并且已核数值输入后，旧缺口正文仍误称成本/效果关系未绑定。宿主比较块现在根据持久的已核输入状态原位说明已核内容，同时明示列业务定义/单位、未来观测及用户规则的双条件和触发/停止语义仍未核。新目录 `tmp/r3m01actioninputstext1` 为最终正常 app 批次：端口 5269、PID 2712、exec session 92849（已停止），health 在启动、组间和结束均 `ok=true, provider_enabled=false`；原六轮会话 `b5c770819e63`、正向会话 `29ebd3ce8640`，七轮均唯一 `turn_end` / `completed`，SSE 与 durable run state 一致，两份导出均 `exported`。原结果 SHA-256 `5D467BE3B7C25AF4E780AD5168DA55804F23028CAE37CD4D49B52A94AE1FBE85`，正向结果 SHA-256 `E95D5D2C37B26E8D820D8E148653ECEB6BABFCDC43409D602A6CF8F4F0ECCF2E`；launcher/driver 摘要同上。正向持久块仍为两块，其中行动输入 `inputs_verified_semantics_unassessed`；正文准确写出两期逐行净贡献与成本/订单列分母已核，未来及规则语义未核，四项比较全保留。候选仍 `withheld_pending_semantic_binding`，行动需求仍 `evidence_insufficient/checked`；`forbidden_provider_transport=0`、实际 Provider initiated calls=0。最终 E2 收据见计划；视觉仍 `unassessed`。

最终代码定向测试 11 passed；完整 E2 `tmp/r3m01actioninputstextfo1` 为 2916 passed / 1 skipped / 16 warnings。验证范围仍为本地确定性、Provider 禁用 app；自然模型、视觉、真实 Provider 与正式发布未评估。
