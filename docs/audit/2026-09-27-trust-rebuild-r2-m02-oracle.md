# R2.1 M02 纵向判据与本地控制路线

2026-09-28 R3 新 HEAD 同配置复核：`tmp/r3m02pair1` 在 `0cd4631`、`local_http_api`、Provider 禁用的同一服务（PID 17504/端口 18746）按未确认与确认 `fraction` 顺序运行，两个独立会话 `1c41ff495177` / `f99881628a0d` 均与各自 SSE、持久状态及 Markdown 导出一致。前者 D7 原始 0.1、单位未知；后者先悬挂业务确认 `measurement_f3360d94cb40626bd51e8579`，选择 `fraction` 后 D7=10%；两者 D30 均未升级为已验证预测。票据 SHA-256 同为 `98790ad7c3be06a98bc01399b3bf96a4a2ca05211dbcccfa108e600c0192f281`，`forbidden_provider_transport=0`、实际 Provider initiated 0，视觉未评估。未来矩阵合同已修正未确认原值与原始尺度容差；此结果不追认旧联合批，也不等于完整 R3/R4 退出。

冻结时间：2026-09-27。产品基座：`acf339d51c1230dbc0dc36ca5d34853a5b44b19f`；供体只读上限：`b181646ff66ea9ea3b0e6a38ffcd3d16b6687312`。

## 本地候选与控制

- 产品入口：现有 `run_p7_browser_rehearsal.py` 启动的普通 Flask `/api/upload`、`/api/chat`、SSE、session、export；普通 `AgentLoop`，仅模型传输由脚本替代，Provider transport 禁止。
- 首轮基线控制路线：`local_http_api`，端口 8769，独立运行目录 `tmp/trust-rebuild-r2-m02-http-baseline-20260927-a`。该路线只评估 app 路径及 durable 数据；上传选择器、可见图表、页面刷新等视觉判据为 `unassessed`，不能称浏览器通过。
- 固定输入：上传脚本生成的 `F-RET7.csv`（列 `day,retention`，七行 `1,0.55` 至 `7,0.10`），同一新会话提交 `【B02】请解释 D1 至 D7 的留存观测，并判断 D30 目前能支持什么；若用拟合外推，请明确模型族、拟合度和未验证边界。`。首轮只作基线，不把修复后运行拼接到此结果。
- 正式候选仍使用同一普通 app/AgentLoop 路径；修改代码后必须另开运行目录和结果身份。不得启用供体默认关闭的 `typed_trial` 作为验收对象，不运行真实 Provider P08 驱动。

## 独立判据

1. 上传票据返回文件名和 SHA256；聊天引用该票据，SSE 仅一个 terminal，session id 与 durable run state 对应；export 与持久答案一致。
2. 原 CSV 第 7 行的观测为 `day=7, retention=0.10`。在没有单位/分母业务确认时，宿主只可发布 `0.10` 原始尺度并标记单位未确认，不自动写 `10%`。七个 day 为相对日序号，不是日历日期。
3. `curve_fitting` 实际回执若成功，记录工具、当前数据版本、观测横轴 `1—7`、方法族和拟合度；图表/产物若生成须可定位，未生成则准确标缺口。只执行拟合不等于 D30 已验证。
4. D30 可以保持未知并解释缺少 D8—D30 观察与验证；若发布拟合情景，须由当前回执参数逐模型复算、列全部可用族与敏感性，标明无留出/回测/外部验证，不写成已验证预测。模型文本中的点估计不能成为数值权威。
5. 正常 app 最终 packet 中必须有当前回执生成的 `answer_bindings.v1` typed 结果，正文由同一宿主渲染；SSE、canonical history、session 刷新与 Markdown 导出均引用同一答案/快照。篡改、过期绑定不得升级，独立正确观测不得被错误 D30 结论吞掉。

基线失败只定位缺口；R2 退出需要改后完整新目录 app 路径收据。脚本模型不代表自然模型质量，HTTP 路线不验证视觉交互。

## 基线 A：普通 app 路径（已执行，未通过 M02）

- HEAD `acf339d`；`control_route=local_http_api`；服务 `127.0.0.1:8769`，exec session `59079`，监听 PID `2304`，健康响应 `ok=true / provider_enabled=false`；运行目录如上。控制脚本 `tmp/r2_m02_http_probe.py` SHA256 `797044d218bd9fa97653a76b2ccbd729ee7c89dff11d0556ce04d595fb236ff2`。
- fixture/upload SHA256 `98790ad7c3be06a98bc01399b3bf96a4a2ca05211dbcccfa108e600c0192f281`；票据 `746c575ceea24050b0cca030b6367725` 返回文件名与摘要一致；会话 `e75e20036531`。
- 一个 `turn_start`、一个 `turn_end`，SSE 与 durable run state 均为 `completed`；持久消息、Markdown export 已产生；原始记录 `tmp/trust-rebuild-r2-m02-http-baseline-20260927-a/m02-http-result.json`。
- 实际 `curve_fitting` 回执 `tr_35f2d6e04a72`，数据横轴 `1—7`，`unit_status=not_confirmed`，模型族 exponential/logarithmic/power，validation `none`。最终 packet `pub_77659d72060d` 的 `answer_bindings` 为 `null`。模型正文把原值 `0.10` 写成 `10%`，虽正确指出 D30 缺口，却未经单位确认；判据 2、5 未通过。
- `runtime.jsonl` 没有 `forbidden_provider_transport`，实际 Provider initiated calls 为 0。HTTP 视觉 oracle `unassessed`。下一步在正常 AgentLoop 生成/渲染同一 packet 的宿主绑定，再开全新目录复测。

## 回放 B：R2.2 初版（未通过，已定位）

- 新路线身份 `tmp/trust-rebuild-r2-m02-http-replay-20260927-b`，仍为 `local_http_api`；端口 8770，exec session `27209`，监听 PID `18184`，健康响应 Provider 关闭；会话 `e69262ab6064`，单一 SSE `turn_end`。
- 宿主确实从当前回执生成 observed/descriptive 两个绑定并渲染 D7 原值、全部族与 R²、D30 缺口；但为了保留被替代模型候选，初版将一条 `publication_rejected` assistant 与正式 assistant 连续写入历史。既有 `load_session` 合并相邻 assistant 时保留前者拒绝标志，使公开投影过滤了正式答案：SSE `text_delta` 有答案，`turn_end.reply_content` 为空，session/export 也不一致。
- 这属于完整事件/历史一致性失败，不计 R2 app 验收。已改为仅在最终 packet 记录被替代候选的摘要与原因，不再插入相邻 assistant；必须使用新运行目录和结果身份完整重跑。

## 回放 C：普通 app 纵向闭合（待最终批次归档）

- 新目录 `tmp/trust-rebuild-r2-m02-http-replay-20260927-c`，端口 8771、exec session `62778`、监听 PID `15660`，同一 `local_http_api` 路线、Provider 关闭；会话 `0a2ad7c8c018`。
- 一个 `turn_start`、一个 `turn_end`；`reply_content` 与 durable 正式 assistant 完全相同；导出文件包含同一正文。最终 packet `pub_8d5c6fdade13` 有同一回执的 `observed_fact`、`descriptive_fit` 两个 `answer_bindings.v1` block；答案 SHA256 `63b40c649265abbb69d8842d3a523adf2cdb9c367436c5fc9853c172c3f4caf2`。D7 由回执显示原值 0.1、单位未确认；D30 无已验证预测；全部三个拟合族和 R² 在原位；没有冒充已生成的图表文件。
- 控制脚本在完成上述全部断言并写出 `m02-http-result.json` 后，末尾控制台摘要因 Windows GBK 无法编码 `R²` 以非零退出；这是收据打印故障，不是 app/SSE/Provider 故障。已改摘要输出为 ASCII，下一次新目录运行须拿到完整零退出。`runtime.jsonl` 无 `forbidden_provider_transport`，Provider initiated calls 为 0；视觉 oracle `unassessed`。
- 同一正常路径的绑定/单位/篡改/过期判据还需回归并审查是否存在过窄的 M02 触发条件，不能把此回放直接标为 R2 整体验收。

## 回放 D/E 与当前边界

- D `tmp/trust-rebuild-r2-m02-http-final-20260927-d`：端口 8772、exec session `69427`、PID `11044`；脚本零退出，会话 `28aed59f6b43`。当前回执宿主生成 observed/fit 两个 typed block，SSE、session、导出正文一致；之后加强拟合度的事实引用，故 D 是前一代码版收据。
- E `tmp/trust-rebuild-r2-m02-http-final-20260927-e`：端口 8773、exec session `4570`、PID `11076`；脚本 SHA256 `398cb12ded5baeeb5d2594222fad406605a23a74640fa7813e2e628b17c0a071`，零退出。fixture/upload SHA256 `98790ad7c3be06a98bc01399b3bf96a4a2ca05211dbcccfa108e600c0192f281`，ticket `9a471860bb3c48d98f2928645c375852`；会话 `e4a18d9f0935`，一个 `turn_start`、一个 `turn_end`，durable `completed`。
- E 最终 packet `pub_4fb1abdbdc5b`，来源回执 `tr_a777ccefe0b1`，`answer_bindings.v1` 的 observed block 绑定 14 个 x/y 事实、fit block 绑定终点和三个模型族/R² 共 8 个事实；`reply_content` 等于公开 session 正文，正文 SHA256 与最终消息一致，Markdown 导出含同一正文。D7 原始 0.1、单位未确认；D30 保持未知；说明三个模型族、拟合度、验证缺口与图表文件缺口。
- E `runtime.jsonl` 只有 `server_start`、`auxiliary_call`、`scripted_round`，没有 `forbidden_provider_transport`；Provider initiated calls 为 0。HTTP 上传选择器、可视图表与页面刷新为 `unassessed`。本轮 `.venv` full-offline `tmp/trust-rebuild-r2-full-20260927-a`：2861 passed / 1 skipped / 0 failed；之后的拟合度事实引用补强通过发布/终态定向 148 项及 E app 回放。
- 这证明一个未确认单位的 M02 正常 app 会话纵向闭合；尚不能宣布 R2 整包验收：已确认单位尚无真实业务确认 app 会话，篡改/过期只做确定性负向测试，多个当前曲线回执的结果选择仍需设计与验证。自然模型、视觉、真实 Provider 仍未评估。

## 回放 F：多来源局部保留后的当前代码

- 单一来源的 E 会话保持正确后，移除宿主生产对“恰好一个当前曲线来源”的硬条件：逐个处理 packet 已选来源，完整来源输出自己的 typed 观测/拟合，不完整来源只给自己的缺口；无效来源不会吞掉独立正确结果。定向测试覆盖两个来源及第二来源缺 `points[6].y` 的情况，149 passed。
- 产品代码变化后使用新目录 `tmp/trust-rebuild-r2-m02-http-final-20260927-f`、端口 8774、exec session `56074`、PID `2528`；同一 SHA256 `398cb12ded5baeeb5d2594222fad406605a23a74640fa7813e2e628b17c0a071` 的 HTTP 控制脚本零退出。健康响应 `ok=true / provider_enabled=false`，会话 `2eb970b54ff6`，一个 `turn_start` 和 `turn_end`。
- 最终 packet `pub_baa74ca5afc0` 有 observed 14 个 x/y 引用及 fit 8 个终点/族/R² 引用；SSE 终态、公开 session、Markdown 导出一致；D7 为原值 0.1 且单位未确认，D30 未给无据预测。`runtime.jsonl` 无 Provider 传输违规事件，实际 Provider initiated calls 为 0。视觉、真实确认、自然模型和真实 Provider 仍未评估。

## R2.4 确认回放 G：预定控制路线与判据

- 路线在批次前固定为 `local_http_api`，沿用 Provider-disabled `run_p7_browser_rehearsal.py` 的普通 `/api/upload` → `/api/chat` → SSE confirmation → `/api/chat/resume` → durable session/export；不评估上传选择器、可视答案和刷新。运行目录 `tmp/trust-rebuild-r2-m02-confirm-20260927-g`、端口 8775，目录须为全新。脚本模型仅在现有 B02 组加 `B02-CONFIRM` 变体；没有真实 Provider 调用。
- 固定 fixture 仍为上述 F-RET7.csv 及 SHA256。新提示的唯一原文片段为「留存序列」；模型只提出该片段和 `ret_a.retention`、`day=1..7` 候选，宿主产生确认选项。HTTP 用户在当前确认 ID/version 上明确选择 `fraction`，其后执行当前版本的 `curve_fitting`。独立判据为 D7 显示 `10%`、确认 ID/response ID/数据版本/七个回执点同一，D30 仍未知，SSE/session/export 同一正文；跳过、旧版本、篡改不能升级。完整 run 记录、服务 PID、脚本摘要及 Provider 账留待执行后追加。

- G 执行：端口 8775、exec session `40669`、监听 PID `11444`、健康 `ok=true/provider_enabled=false`；fixture SHA 与冻结值相同。会话 `4ec010a7e19a` 的悬挂 ID `measurement_ab307cab98d9089829d18f8d`，HTTP 用户选 `fraction` 后普通 app 恢复并执行 `curve_fitting`。终态 `failed`：宿主把已确认原文「留存序列」加入发布要求，却没有在正文点名，触发 `missing_answer_requirement`；未产生可信正式答案。控制脚本另因恢复响应未带 session header 误报，已改为用初始会话 ID 校验。G 不作为通过收据；`runtime.jsonl` 未见 Provider transport，实际 Provider initiated calls 为 0。服务已停止。
- 修复后 H 独立批次预定路线仍为 `local_http_api`，端口 8776、全新目录 `tmp/trust-rebuild-r2-m02-confirm-20260927-h`；同一 fixture/提示/选项/oracle。宿主正文需明确引用已确认指标原文并保留当前回执数值。须重新核对 worktree、目录、端口、健康与服务 PID 后执行。
- H 执行：端口 8776、exec session `38490`、PID `17348`、健康 `ok=true/provider_enabled=false`；fixture SHA 一致，collector SHA256 `6b0c3f77a5a2ac702976d3e3559619a8adc32b1e314da092ad3caa7f8ce595dc`。会话 `9da5dc162144` 悬挂 ID `measurement_69720d2b6384e69a2b332e8a`，用户选 `fraction`，恢复后执行当前曲线，终态仍因 `missing_answer_requirement` 失败。collector 正确停在正式答案缺失断言。`runtime.jsonl` 无 Provider 传输违规，实际 Provider initiated calls 为 0；服务已停止。
- G/H 同根因设计裁决：发布门 `_answer_coverage_issues` 仅接受原文标签后 96 字中的词面结果标记；H 的宿主标题虽显示「留存序列」，也不能使该门成立。改为在当前 packet 的已确认 requirement 上，由已渲染 observed block 的事实引用、同一确认 context、回执点和版本身份闭合后标记 `checked/answered`。未绑定要求仍保留原门。I 回放须新目录/身份，不拼接 G/H。
- I 批次前冻结：`control_route=local_http_api`，端口 8777，运行目录 `tmp/trust-rebuild-r2-m02-confirm-20260927-i`，沿用 Provider-disabled 普通 app 入口和同一 F-RET7 fixture、`B02-CONFIRM` 提示、用户明确选 `fraction`；独立判据仍是同版本 D7 `10%`、D30 未知、单终态和 session/export 一致。`207` 项确认/发布定向测试通过；视觉 `unassessed`。执行前再验目录不存在、监听端口空闲及健康。
- I 已通过：端口 8777、exec session `20740`、PID `9856`，健康 `ok=true/provider_enabled=false`；collector SHA256 `6b0c3f77a5a2ac702976d3e3559619a8adc32b1e314da092ad3caa7f8ce595dc`，fixture SHA 与冻结值一致，脚本零退出。会话 `70588cf96dff`，初始和恢复阶段各一个 `turn_start/turn_end`，前者 `suspended`、后者 `completed`；确认 ID `measurement_2fd39bb096325d1db5e82e6f`、响应 ID `r2-m02-fraction-g`，回执 `tr_d8a788daa0d1` 与数据版本 `dv_87cdc48ae412c1ab`。最终 packet `pub_fe6f4dacc328` 的 observed block 引用七对 x/y 事实，已确认 requirement `rq_fef457882889` 为 `checked/answered`；fit block 引用终点及三个族/R²。D7 宿主输出 `10%`，D30 未知，SSE 正文、durable session 和 Markdown export 一致。`runtime.jsonl` 无 `forbidden_provider_transport`，实际 Provider initiated calls 0；视觉 `unassessed`。
- 确定性负向：`tests/test_r2_measurement_confirmation.py` 7 passed，使用真实 ConfirmationService 回答与当前 Workspace/receipt 构造 packet；分别验证 `fraction=10%`、`percentage_points=0.1%`、skip 原值、旧 frame 版本、错误列、缺回执点以及伪造 fact_refs/确认 context 均不升级。J 批次前固定 `control_route=local_http_api`，端口 8778，全新目录 `tmp/trust-rebuild-r2-m02-skip-20260927-j`；同 fixture/提示，实际 HTTP 用户选 `skipped`，预期 D7 保留 `0.1（单位未确认）`、D30 未知，单终态/session/export 一致，Provider 0，视觉未评估。
- J 已通过：端口 8778、exec session `55761`、PID `9308`、健康 `ok=true/provider_enabled=false`；collector SHA256 `6f146611139abb8ee844dd414dedd3c1eb0be1583d0611de38a9c99ae7cb6181`，fixture SHA 一致，脚本零退出。会话 `5b50e1702f26`、确认 ID `measurement_06123d37f8cde8e261b7fd99`，HTTP 用户选 `skipped` 后正常完成；D7 保留原值 `0.1（单位未确认）`、D30 未知，SSE/session/Markdown export 一致。`runtime.jsonl` 无 Provider 传输违规，实际 Provider initiated calls 0；视觉未评估，服务已停止。
- K 批次前固定 `control_route=local_http_api`，端口 8779，全新目录 `tmp/trust-rebuild-r2-m02-multi-20260927-k`；仍由现有 Provider-disabled 入口、同一 fixture 上传票据驱动，在 B02 组的 `B02-MULTI` 变体中建立 `ret_a` 与 `ret_b` 两个当前曲线回执。独立判据为两个数据集都各自保留 D7 原值与拟合度、不发生单一来源吞并；D30 仍未知、单终态、session/export 一致。视觉未评估，不是正式自然模型验收。
- K 已通过：端口 8779、exec session `24122`、PID `2744`、健康 `ok=true/provider_enabled=false`，fixture SHA 与冻结值相同；collector SHA256 `30d087a3b932662e28a7f4031f1a846e7695bc01e1612406e03c513b465dfc86`、零退出。会话 `cc3c633ae605`、packet `pub_613de55298d7`，两条独立曲线回执 `tr_3d0fafd36adf` 与 `tr_ffa2c42e7864` 各有 observed 14 refs 和 fit 8 refs，答案各自显示 D7 原值和三个拟合度；D30 未知。一个 `turn_start/turn_end`、durable session/export 同一答案。`runtime.jsonl` 无 Provider 传输违规，实际 Provider initiated calls 0；视觉未评估，服务已停止。
- 当前候选完整离线回归：新目录 `tmp/trust-rebuild-r2-full-20260927-b`，`run_regression.py full-offline` 退出 0，2869 passed / 1 skipped / 16 warnings，Provider 调用被 runner 禁止。`git diff --check` 无补丁错误。该结果只代表 E2，不能替代自然模型、浏览器视觉或真实 Provider 批次。
- L 批次前固定 `control_route=local_http_api`，端口 8780，全新目录 `tmp/trust-rebuild-r2-m02-negative-20260927-l`。仍由现有 Provider-disabled 普通 app 入口生成一个 B02 确认悬挂；HTTP 先提交伪造的 confirmation ID，预期 404，再在真实 ID 上提交旧 `expected_version` 与 `fraction`，预期一次失败终态且无正式 publication packet/百分比升级。fixture/提示沿用 I，SSE 与 durable 状态分别记录；视觉未评估。此批用于 app 控制入口负向，旧 frame 与回执篡改由 7 项确定性验证覆盖。
- L 已通过负向：HEAD `50eb619e2253c6fde295fbe96aa7c6708fb3042b`，端口 8780、exec session `38857`、PID `8180`，健康 `ok=true/provider_enabled=false`；collector SHA256 `4df12a2ad8e1f674202586026f9ca904dd90eafc8eedc061b37c398cc78e2a0e`。会话 `9f00a11b32b0` 的悬挂确认 ID `measurement_5ed0d9a827f645121fb8ca83`、version 2；伪造 ID 返回 404，旧 version 1 的 `fraction` 请求给一个 `error/turn_end`，run state 为 `failed`，错误明确 `expected version 1, current version is 2`，未生成正式 publication packet。`runtime.jsonl` 无 Provider transport，实际 Provider initiated calls 0；视觉未评估，服务已停止。
