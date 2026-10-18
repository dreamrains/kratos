# R3.4 M06 有输入时的账面净收益与确认边界

重建树 `codex/trust-rebuild-20260927@0f71168`，供体 `main@b181646` 只读。控制路线批前均选 `local_http_api`，使用既有 Provider 禁用演练服务、`/api/upload`、`/api/chat`、SSE、会话/导出接口；视觉 picker、正文渲染和浏览器刷新均 `unassessed`。未启动真实 Provider，未改变正式默认。

## 独立判据

`F-PROMO.csv` 四行，`order_amount` 原值之和 120、非空数 4，文件给定 `incremental_revenue` 原值之和 110、`coupon_cost` 14、`channel_cost` 10。选择“仅代金券成本”时账面差额应为 96；选择“代金券及渠道成本”时为 86。真实业务确认必须显示所选数据集、列与完整算式；数值由宿主从当前聚合回执重算，保留源/派生身份和原 120。仅能称按用户确认列关系计算的账面净收益，不能把文件列名当因果证据或确认货币单位。缺成本值时不能作零；原 F-SALES 缺成本/增量数据的 M06 仍须 `not_computed` 并保留 120/12。

## 诊断与两轮同根因裁决

新可用输入的首两批 `tmp/r3m06data1`（端口 5261、PID 16612、exec 68374、会话 `10f2f482fca7`）和 `tmp/r3m06data2`（端口 5262、PID 14528、exec 50172、会话 `4df91f90a906`）均确认、上传、聚合、SSE 单终态、持久化和导出成功，Provider 0；但两批 `answer_requirements=[]`、`confirmed_business_scope=null`。第二轮改提示仍不收敛。根因是演练客户端辅助意图分类只对旧 `IC-B03` 标记返回 `result/gap`，不是产品确认或上传失败。停止第三次同型文案补丁，裁决为复用旧场景的结构化意图输出，之后才诊断产品发布。

按裁决的新目录 `tmp/r3m06data3`（端口 5263、PID 5076、exec 8418、会话 `aea2a2a32a31`）恢复了同一正常 app 的四个原/续 `result/gap`，真实成本确认 ID 和当前聚合回执；原值 120/110/14/10 已发布，但净收益仍 `not_computed/checked`，86 未发布。这定位了真正产品缺口：已有 `observed_aggregate` 可核源→派生值，未把所选成本算式绑定到同版输入。

## 同一产品链实现与首轮通过

沿用 `answer_bindings.v1` 的 `observed_aggregate` block、现有确认记录和同一 packet：`ask_user_question` 的可选 `value` 提供 `metric_scope_formula.v1`（数据集、增量列、1—2 个成本列），但宿主只在**用户已选择且选项的可见 description 等于宿主生成的完整算式**时认可；旧普通文本成本选择仍走缺证局部交付。宿主从当前 transform 聚合回执核对源/派生版本、原行和各列 sum，然后重算账面差额，block 保留输入、结果、确认与来源身份。渲染再次重算比较，不接受篡改的结果/成本范围/版本。候选列表、用户选择和工具执行仍由原 AgentLoop 完成；无新 planner、发布通道或账本。

`tmp/r3m06data4`：端口 5264、PID 16900、exec 54775 已停；launcher SHA-256 `344641CA5E4A05E15A497C589D6D8185FC0E704EB86A7AA138438EAFA729CD12`，HTTP 控制器 `tmp/r3_m06_data_http_probe.py` SHA-256 `6ACF9865179082BCC78FC14753F1E0000F384C5507EBD0E2A637B84CED9499CB`，结果 JSON SHA-256 `979CA0DB6422B91B9AEA12DB76232BED2B9C74A090BE048F0F804555C93EC062`。会话 `c80dafae6640` 上传票据 filename/SHA 与 `F-PROMO.csv` 一致（SHA-256 `5fcc5baa350131fc427fb0e6957b0b0976e3c7491505714efa91ef883503ca1d`）；首次 `suspended`，选择可见“代金券及渠道成本”及其完整列算式，原会话一次恢复 `completed`，SSE 各轮唯一终态与 durable run state 一致。最终同版 block 引用真实 confirmation，输入 110/14/10，输出 **86**，表格保留 120/4，并声明未测促销因果与单位；原/续两个 result、两个 gap 均 `answered/checked`。持久 assistant 正文与终态逐字相同，3720 字节 Markdown 导出含同一正文；runtime 无 `forbidden_provider_transport`，实际 Provider initiated 0。定向聚合/确认组 65 passed。

## 尚未覆盖

首轮可用输入批只选双成本方案；还需新目录复核仅券方案、原缺数据 M06 和失效/skip 路径。当前提交的完整 E2 `tmp/r3m06datafo1` 为 **2919 passed / 1 skipped / 16 warnings**。同配置全 M01—M06 与历史双向保护矩阵尚未闭合；自然模型能否提出正确结构化选项、列的业务定义及增量测量来源、视觉显示都未验证。`answered` 在本片只指**确认后账面算术**，不授权因果效果或正式 Provider 验收。R3/R4 仍实施中，R5 未开始。

## 固定 HEAD 的 M06 四路径批次

在 `0f71168`、同一 Provider 禁用配置下预先固定顺序：`B06-TOOL` 不存在数据、`IC-B03` 旧文本成本确认且数据缺失、`IC-B03-DATA` 仅券成本、`IC-B03-DATA` 双成本。控制路线 `local_http_api`，服务 `tmp/r3m06matrix1`、端口 5265、PID 17916、exec 61994 已停；批前/分组前/批后健康均 `ok=true/provider_enabled=false`。launcher SHA-256 `344641CA5E4A05E15A497C589D6D8185FC0E704EB86A7AA138438EAFA729CD12`；旧 HTTP 控制器 `tmp/r3_m06_http_probe.py` SHA-256 `9819C630E84F1C562439E1D53E61CB2EBD0819D9F1FC8E9477B0881CA1768826`；新数据控制器 `tmp/r3_m06_data_http_probe.py` SHA-256 `78167A1CCFB6ED1E927495B38F8EA53CC6A1169C776C72344B5D3165975C1EA8`。三个结果 JSON SHA-256 依次为 `15F61858A41BADC775776BFE6190E2523A9557BCE74E0D6A36376FC4FC5405B3`、`E54AA56A76CB1BD6FF1FCAC5C6322567F0FC2809B37732D3D7EB4BE459ADF768`、`9E88CE750AE02A3BDCE4C0834EB7A88A4E49EE89190A816A5378AD5739965BC7`。

| 路径 | 会话与终态 | 当前结果与需求 |
| --- | --- | --- |
| 不存在数据 | `930436533629`，`completed` | 无数值 block，无 120 或伪完成；只保留数据缺口与下一步 |
| 旧文本成本确认 | `9d9d422e47cd`，先 `suspended` 后同会话 `completed` | 源 12 行/订单金额 120 保留；两个原/续 result 均 `not_computed/checked`，两个 gap `answered/checked`，没有净收益 block，不把缺值作零 |
| 仅券 | `e323fcffb863`，先 `suspended` 后同会话 `completed` | 当前同版原值 120/4，增量列 110、券成本 14；账面差额 **96**；原/续 result/gap 均 `answered/checked`，不宣称因果或单位 |
| 双成本 | `c77eb5fe0ee0`，先 `suspended` 后同会话 `completed` | 当前同版原值 120/4，110/14/10；账面差额 **86**；原/续 result/gap 均 `answered/checked`，不宣称因果或单位 |

四个 session ID 唯一；每轮 SSE 单一 `turn_end` 与持久 run state 一致，三个有上传的会话 ticket filename/SHA 均与文件一致。四个终稿均逐字进入 canonical assistant 消息，Markdown 导出保留各非空正文行；旧文本成本导出有 Markdown 空白规范化，不能按整段原始字节相等判断缺失。runtime 中 `forbidden_provider_transport=0`，实际 Provider initiated calls=0。仅券/双成本的值由独立原始四行手算，确认选择同时改变宿主同版算式和最终数值。失效/skip/换版本由定向与完整 E2 保护，尚未在本批 app 路线逐项复跑；视觉和自然模型仍未评估。
## 2026-09-27 M06 skip / 旧版本负向补批（批前冻结）

固定产品 HEAD `0f71168`、供体 `b181646` 只读；控制路线 `local_http_api`，Provider 禁用；现有演练服务入口，新目录 `tmp/r3m06negative1`，端口 5267。现有控制脚本 `tmp/r3_m06_negative_http_probe.py` SHA-256 `17B55A741679CC753F97D75887345C244927AB3607E12601F0A0C2C45AC93853`；沿用原 `IC-B03-DATA` prompt 和 F-PROMO 四行夹具 SHA-256 `5fcc5baa350131fc427fb0e6957b0b0976e3c7491505714efa91ef883503ca1d`。脚本为本批有界 HTTP 控制，不新增浏览器框架或产品入口。

两独立会话按顺序：skip 使用悬挂 confirmation 的当前 ID/version 传 `skipped`，应保留已算订单原值和已核成本列聚合但不能把未确认公式发布为 96/86 或 `answered`；stale 使用另一会话的真实 ID、旧 expected_version 与可用双成本选项，预期一次失败终态、无确认授权/正式净收益。两者检查 ticket 文件名/SHA、每轮唯一 terminal、SSE/durable、持久会话/导出、Provider initiated 0；视觉未评估。此前四路径正向批不与此补批拼接成新完整 M01—M06 矩阵。

首轮 `tmp/r3m06negative1`、端口 5267、PID 13164、exec 97129：skip 会话 `b7e3249ec490` 完成一次 suspended→resume，第二会话的 `/api/chat` 返回 HTTP 422。控制脚本错误地复用了一次性 upload ticket；此批未写完整结果文件，**不计通过**，不归因于产品上传/确认缺陷。健康与 Provider 禁用保持正常，服务已停止。控制脚本改为每会话各自上传相同 SHA 的 F-PROMO，不改产品代码。新批冻结为固定 HEAD `0f71168`、同一 prompt/oracle、`local_http_api`、新目录 `tmp/r3m06negative2`、端口 5268、修正后脚本 SHA-256 `032831A3723DA4FE3661128EB044750A69C0F6A3D111DF079CEA1464C7599A7C`；两路径须整体重新执行。

`tmp/r3m06negative2`、端口 5268、PID 25124、exec 62829 完成两路径：skip `43e196df4e34` 的原值聚合工具已执行，但终稿因原/续两组 `result/gap` 缺少可核交付而 `failed`；旧版本 `1b71fc131304` 以 `expected version 1, current version is 2` 失败且无授权结果。两个终态各唯一、durable 一致，Provider 0。skip 是**产品缺口**：已算原值不应因用户未授权净收益口径而整轮丢失，且不得把 skip 当作已确认公式。设计裁决为复用同一 `answer_bindings.v1` 的 `observed_aggregate`：从持久确认记录验证 SKIPPED/当前会话/响应/原任务 ID，纳入原/续 result/gap；宿主渲染已算聚合及未算净收益的具体原因，coverage 分别 `not_computed/answered`。`confirmed_business_scope` 仍只容纳真实选择，跳过单独作为 packet 中决议来源，绝无净收益算式或计算授权。定向 12 passed；需新目录完整重测正反路径及 E2。服务已停。

产品代码与定向测试已仅按命名文件提交 `c1b42cb`。下一补批**批前冻结**：`control_route=local_http_api`，Provider 禁用、同一 F-PROMO/prompt/两路径独立 oracle，控制脚本 SHA-256 `032831A3723DA4FE3661128EB044750A69C0F6A3D111DF079CEA1464C7599A7C`；新目录 `tmp/r3m06negative3`，端口 5269。skip 应在同版聚合后 completed，原/续 result `not_computed/checked`、gap `answered/checked`，正文保留 120/4 及未算原因，不能出现净收益 96/86；旧版本仍须失败且无正式净收益。每会话单独上传 ticket，逐项核 SSE、持久化、导出和 Provider 0。E2 `tmp/r3m06skipfo1` 在批前启动，待结果记录。

补批 `tmp/r3m06negative3`、端口 5269、监听 PID 21528、exec 6549，批末健康 `ok=true/provider_enabled=false`，运行日志 21 条、`forbidden_provider_transport=0`、Provider initiated calls 0，服务已停止。控制结果 SHA-256 `26043246CA1EEAD027A000197E8A82B74DB613A1E1090BEA897CB23920733A4C`。两个独立上传 ticket 均匹配 F-PROMO 文件及同一 SHA。

- skip 会话 `c42cccf0429d`：初轮 `suspended`，当前 ID/version 的 `skipped` 恢复为 `completed`；每轮唯一 `turn_end`，SSE/durable/canonical/export 对应且导出无缺行。当前同版聚合表保留订单原值 120/4，以及文件原值列 110/14/10，明确「促销净收益」尚未计算、跳过成本范围不授权把列组合为 96/86、不把未选成本当零。packet `skipped_business_scope` 引用持久确认 ID/response/原任务，四个原/续 result/gap 依次为 `not_computed/answered/not_computed/answered`，均 `checked`；无 `verified_net_benefit`。
- 旧版本会话 `cf53276fa562`：初轮 `suspended`，旧 expected_version 恢复为单一 `failed` 终态，错误 `expected version 1, current version is 2`；没有正式净收益 publication，失败状态和导出一致。

此补批闭合 M06 当前配置的 skip/旧版本负向产品路径，视觉和自然模型仍未评估；不取代新 HEAD 的完整 M01—M06 联合批。固定 `c1b42cb` 的完整 E2 `tmp/r3m06skipfo1` 退出 0：**2919 passed / 1 skipped / 16 warnings**，Provider 调用由 runner 禁止。

## 当前 HEAD M06 六路径统一批（批前冻结）

固定 `c1b42cb`、`control_route=local_http_api`，Provider 禁用；现有 `run_p7_browser_rehearsal.py`，新目录 `tmp/r3m06all1`、端口 5270。按缺数据、旧普通成本、仅券、双成本、skip、旧版本顺序执行，六个独立会话；确认和恢复保持各自同会话。控制器 SHA-256：旧 `r3_m06_http_probe.py` `9819C630E84F1C562439E1D53E61CB2EBD0819D9F1FC8E9477B0881CA1768826`、数据 `r3_m06_data_http_probe.py` `78167A1CCFB6ED1E927495B38F8EA53CC6A1169C776C72344B5D3165975C1EA8`、负向 `r3_m06_negative_http_probe.py` `032831A3723DA4FE3661128EB044750A69C0F6A3D111DF079CEA1464C7599A7C`。使用原 F-SALES 与 F-PROMO 各自文件 SHA，独立 oracle 与上文相同：缺失不给数值；旧成本 120/12、净收益未算；仅券 96；双成本 86；skip 保留 120/4 与列原值、净收益未算且原/续需求正确覆盖；旧版本不授权。各路径查 ticket、SSE 唯一终态、持久会话、导出、runtime Provider 0；视觉未评估。本批仍不替代全 M01—M06。

六路径统一批已执行：服务端口 5270、监听 PID 21800、exec 22639，组前/批末健康 `ok=true/provider_enabled=false`，批后停止。`runtime.jsonl` 69 条、禁用 Provider 传输 0、实际 Provider initiated 0。各独立会话及结果：缺失 `60d261f39277` completed/不给数值；旧成本 `0092b48401c4` suspended→completed/120/12、净收益未算；仅券 `7d4e9032b0ef` suspended→completed/110−14=96；双成本 `e516f7b1d272` suspended→completed/110−14−10=86；skip `8aa94f45121e` suspended→completed/120/4 和原值列保留、净收益未算、原/续四项 `not_computed/answered/not_computed/answered` 均 checked；旧版本 `8d9a6612bdfa` suspended→failed、`expected version 1, current version is 2`，无授权净收益。所有终轮各一个 `turn_end`、durable 状态一致、导出与 canonical 最终答案无缺行。四份结果文件 SHA-256 依次为 `9135A496F39616844A1AE3BCDC4911D94151D7EFB96C1B42D81837BB43F77FE3`、`F172CB4566193C2522D07323531C3308512B1A7D46BF440C0052C23067C331BF`、`AB5C6017ECFA5AFED25A1E992A7AA6855FE1D50789947E0A7E73DE1BF76C2988`、`B0DDAB7F04B2E81A6BF0DD6411AA54EB71D7A374DF2CB63C29E112846BBCA04D`。M06 当前 HEAD 的**非视觉本地六路径判据已满足**；自然模型、视觉和完整 M01—M06 仍未评估/通过。
