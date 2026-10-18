# R3.4 M06 确认后局部交付：根因与结构裁决

日期：2026-09-27。目标树 `codex/trust-rebuild-20260927@825376b`；供体 `main@b181646` 未改。控制路由为 `local_http_api`；以下均为 Provider 禁用正常 app 路径，不是视觉或自然模型验收。

## 原始判据

IC 的真实业务选择只决定净收益成本范围；选择“代金券及渠道成本”后，仍须执行数据分析并在同一回答里区分已算订单总额、未算净收益和缺少的成本/促销增量证据。CP 的明确 `result`/`gap` 子目标须各自有结果或具体原因；VP 的已核订单值不能因净收益缺口被吞掉。缺失数据情景继续只给一个可执行下一步，不能编数或宣称完成。

## 两批正向控制与定位

现有演练脚本的 IC-B03 分支过去在真实确认后直接返回散文，`tmp/r4m06audit1` 因无本轮计算回执 fail-closed。为隔离执行与发布责任，仅在既有 Provider-disabled `scripts/testing/run_p7_browser_rehearsal.py` 的 IC-B03 分支中让确认后依次 `load_data`、`transform_data(group_aggregate)`、`record_evidence_record`，保留原问题、真实选择和同会话恢复；没有让脚本提供成本数值，也没有新增测试框架或生产规划器。

批前均确认 worktree/HEAD、`.venv`、launcher、新目录和空闲端口；既有 HTTP driver `tmp/r3_m06_http_probe.py` SHA-256 `9819C630E84F1C562439E1D53E61CB2EBD0819D9F1FC8E9477B0881CA1768826`，修改后的 launcher SHA-256 `63DB58B4CABF302D7DC0B5930E499D8086ED611064679A8984AC630D56566CE6`。`tmp/r3m06receipt1` 端口 5251、PID 14796、exec 52335 已停，结果 SHA-256 `7633C3760327FDEBFB70FF1FDB59292062A9B66A8BD75628869D615C12831FF5`；`tmp/r3m06receipt2` 端口 5252、PID 24168、exec 37059 已停，结果 SHA-256 `07E715534D7E940CA83E809D0C6469C21A6E2E5E0DB21F39761E527C1F0D201C`。每批两个独立会话：不存在数据的会话 completed；成本会话先 suspended，选择“代金券及渠道成本”后同一会话仅恢复一次，SSE 各轮唯一终态且与 run state 一致，持久会话/导出完成。两批均产生 3 个成功工具回执（加载、聚合、证据记录），派生表存在；最终成本轮仍 failed，0 个已发布 packet。第一批成本会话 `f36fdb99318e`，第二批 `4ce5dc58abbb`。后批前后健康为 `ok=true/provider_enabled=false`，runtime 无 `forbidden_provider_transport`，实际 Provider 发起 0；picker、可视答案、浏览器刷新未评估。

两批同根因不收敛。候选正文虽笼统说“净收益未计算”，却没有将语义需求 `促销净收益` 与 `已算、未算和缺少证据分开` 分别绑定到已核聚合及具体缺口；`_answer_coverage_issues` 因此给两项 `missing_answer_requirement`。已有聚合宿主块只承接表达/行动需求，不承接 `result/gap`；本轮加载回执本来就不属于可发布聚合来源，尝试把 `load_data` 加入声明入口与此根因无关，代码和对应测试已撤回。不能通过向演练散文补齐标签、放宽词面窗口、附尾注或把缺失成本写成零来过关。

## 设计裁决与下一实现边界

在既有 `answer_requirements`、当前聚合回执和 `answer_bindings.v1` 中实现**局部交付绑定**：一个同版本已核聚合块发布订单原值及方法；当前活跃 `result` 需求若无对应计算回执，明确标 `not_computed`，不得标 `answered`；当前 `gap` 需求在同一正文逐项说明已算聚合、未算目标及缺少的计算输入/回执，并标 `checked`。确认范围只能从同会话 resolved 的真实业务确认记录引用，须验证 confirmation ID、response ID、所选选项与原任务/计划身份；选择本身不提供成本金额。预览与终态复用同一构包边界，原需求及本轮恢复需求保持来源引用，不能从模型正文猜覆盖。

正反例须覆盖：真实确认后有聚合、缺失成本时保留已核 120/12 和准确净收益缺口；无确认、skip、伪造/旧确认、换版本、无聚合、净收益有真实计算回执时不得误标；额外独立正确结果不丢失。先做有意义的 packet/renderer 测试，再以新 run dir 重跑完整 M06 正常 app 批次和 E2。若结构方案仍不收敛，停止第三个同型补丁，保留 fail-closed 并将原 DoD 明确列为未完成。M01 真条件建议、R4 开放语义审核、视觉和自然模型能力仍独立待验，R5 不能因本控制批次启动。

## 结构实现与最终批次

在现有 `AgentLoop` 中把真实确认 ID、原计划 ID 和原结果需求 ID 带到恢复轮；加载数据引发的再规划在同一活跃 result/gap 任务上保持原计划身份。`build_publication_packet` 从同会话确认事件重放中核对 resolved、single-select、真实选项、response ID 和计划/原需求，预览与终态在同一边界纳入原需求及本轮需求。当前聚合块只在没有已确认聚合指标映射时承接局部交付：保留源/派生版本核对后的已算值与方法，`result` 标 `not_computed/checked`，`gap` 标 `answered/checked`；绑定所选范围并明确它不等于成本金额，绝不把缺失值作零。已确认指标映射、跳过、伪造响应、换会话/计划、撤回原需求和篡改绑定均不从此路径取得局部交付。该实现只复用现有 `answer_bindings.v1`，未新增 planner、账本或发布通道。

最终代码的完整控制批次 `tmp/r3m06partialfinal2`：端口 5257、PID 17652、exec session 69434 已停，driver/launcher SHA 与上文相同，结果 SHA-256 `EAA4658875C9EC6FDAFFED6A71574EE6929B77E0290C3D297610ADB7C3122DC9`。缺失数据会话 `ea853886d4ad` completed；成本会话 `9585625c20f8` 从 suspended 到同会话一次真实选择后 completed，唯一 SSE `turn_end` 与持久状态一致，上传票据 SHA、导出均闭合。成本轮 3 个工具回执、1 个 ready/final packet；计划 ID 保持 `spec_88c5be4f47e5`。正文保留源 12 行、派生 1 行、amount_sum=120、amount_count=12 和原值求和/非空计数方法，明确选择「代金券及渠道成本」只是口径，净收益未形成可核结果，缺少其他输入或结果测量，不把缺失值作零。原始与恢复轮两个 `result` 均 `not_computed/checked`、两个 `gap` 均 `answered/checked`。绑定块的 packet digest 与最终快照一致，引用当前 transform 回执；前后健康 `ok=true/provider_enabled=false`，runtime 无 `forbidden_provider_transport`，实际 Provider 发起 0。HTTP 路线的 picker、可视正文和浏览器刷新仍为 `unassessed`。这证明的是 Provider-disabled 脚本执行下的产品链局部交付；自然模型是否自行选工具、解释成本/促销效果的语义质量仍未证明。

定向发布/聚合边界为 159 passed。第一轮全 E2 `tmp/r3m06partialfo1` 有 2910 passed、2 failed、1 skipped；失败仅因旧单元测试用不含 confirmation ID 属性的最小对象，跟踪函数曾直接访问该属性。改为可选取值后，无回执 fail-closed 测试仍通过；随后增加已确认聚合映射优先保护。最终代码的新全 E2 `tmp/r3m06partialfo2` 为 **2912 passed、1 skipped、16 warnings**；第一轮失败批次没有充当通过证据。
