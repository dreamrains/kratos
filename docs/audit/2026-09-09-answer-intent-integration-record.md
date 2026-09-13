# 回答内容优化与必要澄清整合记录

日期：2026-09-09｜整合分支：`codex/answer-intent-local-acceptance-20260909`｜基线：`d6e478005b4b7d375a99e6e3c278b5c31e3abc75`｜本地 `main` 合并：`f8ee717af81134e8f854510a35e63abda37bb43a`

## 1. 范围与分支

- 在独立 worktree 中从 `vp-analysis-value@d6e4780` 建立整合分支；原 dirty 主工作树未被清理、覆盖、reset 或批量暂存。
- 按顺序 cherry-pick 回答内容优化提交 `61e7b47`、`bd42678`，生成整合提交 `1cd415e`、`5446e1a`。
- 复用既有浏览器演练入口扩展提交 `0eb3111`，生成 `e494261`；未新增测试框架、探针、模型审核调用或重复记录机制。
- Git 未产生文本冲突；整合树与先前同基线的两提交整合结果逐字节一致。`loop.py` 与 `tests/test_execution_control.py` 仍按函数和回归检查确认两侧契约并存。
- 用户接受当前离线结果后，本地 `main` 以双父提交 `f8ee717` 合并整合提交 `9e51b81`；合并提交的文件树 `7aa91b669171ae77d7daf9c9e2361009db90b156` 与 `9e51b81` 完全一致。旧 `main` 历史作为第一父保留，已退役文件未恢复。

## 2. 关键不变量核对

- 必要澄清：只有范围绑定的业务语义缺口才悬挂；方法许可降级为非阻塞响应；已解决决定按业务范围复用，范围或相关数据版本变化后重新判断。
- 工具协议：续传序列化保留 `assistant.tool_calls` 与 `tool.tool_call_id`；Provider 投递副本剔除孤立消息并在发送前校验完整块。
- 发布闭环：质量门前候选仅以 `publication_rejected` 内部保存；正式正文在发布包、来源 artifact、回复级 binding 和 session 保存成功后公开。
- 失败与终态：artifact/session 写入失败回滚本轮公开消息和 packet；同步与流式路径复用同一最终化入口，保持一次终态。
- 内容完整性：FactGroup、detail_ref、需求生命周期、`answered` / `not_computed` / `evidence_insufficient` 和类型化派生量值契约均保留。
- 证据边界：竞争假设的支持、反证、冲突、未决和失效状态继续由结构化关系、范围和数据版本约束；没有放宽因果、预测或零值解释门槛。

## 3. 本地测试证据

| 范围 | 结果 | 证据边界 |
|---|---|---|
| 回答内容定向 | 129 passed | E1/E2；Provider 禁用 |
| 必要澄清与意图定向 | 301 passed | E1/E2；Provider 禁用 |
| full-offline 第一次 | 2492 passed、56 failed、62 skipped | 失败集中于独立 worktree 缺 Git 忽略 Excel 夹具和 Windows 长路径；整套已跑完 |
| full-offline 第二次 | 2608 passed、1 failed、1 skipped | 缩短 worktree、补齐夹具后唯一失败为多复制了清单外 `游戏C改版.xlsx`；用户接受当前结果用于合并，不记作 full-offline 全绿 |

隔离运行目录分别为 `tmp/integration-20260909-target-content`、`tmp/integration-20260909-target-intent`、`tmp/integration-20260909-full-offline` 和 `tmp/f1`。runner 设置 loopback API、禁用真实 Provider 网络；本阶段没有发起真实 Provider 调用。

## 4. 合并后本地浏览器验收

- 运行身份：`main@be5ee9ac6305c15aec20f9981bf4f3ed25701fa5`；时间 2026-09-09 20:33—20:48（Asia/Shanghai）。
- 入口：`.venv\Scripts\python.exe scripts\testing\run_p7_browser_rehearsal.py --port 5179 --run-dir tmp\main-ic4-browser-20260909-be5ee9a`。复用既有演练入口，未新增测试框架、探针、模型审核调用或重复记录机制。
- 矩阵：B01—B06、IC-B01—IC-B06、CONTENT-B03、CONTENT-B07 均完整执行并通过。普通异常未触发中途修复或局部重跑。
- 关键终态：B06-SAVE 的 `run_state.status=unknown`；B06-BUDGET 为 `failed` 并显式停止；其余应完成会话为 `completed`。未发现错误证据升级、跨会话归属或终态重复。
- B04 会话 `431233c26bd0` 保留 supports/refutes 结构化关系和未决状态；数据指纹改变后，旧证据以 `reason=data_version_changed` 进入排除列表，未升级到新版本。
- IC 矩阵证明：安全可逆方法不悬挂；成本范围、时间窗口和分母等真实业务口径正常悬挂/恢复；同范围决定可复用，范围或相关数据版本变化后重新确认；跳过不当作批准；旧通用方法审批仅以 `policy_retired` 保留审计。
- CONTENT-B03 会话 `c2c77b29d01e` 产生六来源发布报告与 9380 字节 Markdown 对话导出；导出菜单未产生浏览器标准 `download` 事件，但应用按既有契约在 session `reports` 中生成了可读文件，六个来源的金额与条数均可追溯。CONTENT-B07 会话 `a5ccf75b6f20` 在 1440×900 下显示表格、KaTeX、Plotly 和备用链接，无可见整页横向溢出。
- 运行轨迹：`server_start.provider_enabled=false`；`scripted_round=72`；`auxiliary_call=145`（本地脚本客户端）；`forbidden_provider_transport=0`。真实 Provider initiated calls=0。浏览器控制曾短暂断开，本地 HTTP 始终为 200；重连后沿用原 run-dir 从 B04 继续，未重跑 B01—B03。

## 5. 当前边界与未完成项

- IC4 已完成本地 E3/L3 验收，不外推为真实自然模型、正式 Web 进程、staging、生产或部署证据。
- 整合前 full-offline 结果仍为 2608 passed、1 failed、1 skipped；唯一失败是多复制清单外 `游戏C改版.xlsx` 的隔离夹具例外，用户已接受用于合并，仍不记为 full-offline 全绿。
- `be5ee9a` 已经一次普通非强制 push 更新远程 `refs/heads/main`；本次后续文档提交尚未 push，没有部署。
- IC5 / AC40 / P08 已在后续冻结提交 `1516337` 上执行一次真实浏览器＋真实 Provider 完整批次；批次有效但未通过，不能以其中的通过场景或既有本地绿灯转记为整体完成。详见下节与 [P08 阶段记录](../superpowers/validation/2026-09-06-value-preservation-stage-records.md)。

## 6. 合并后真实 Provider 完整批次

- 运行身份：`main@15163374b5acf6f4a78acfd1b59bcf89db07300b`；冻结文件 `tmp/p08-real-provider-20260909-1516337-r1/freeze.json`，SHA-256 `c0bd787f64e2c7b8f05b2026db0a73ffa1336c9cb3b6d6f44ff2caca16a6c46`；模型 `openai/deepseek-v4-flash`；端点 `https://api.deepseek.com`；`request_policy=one_shot`；物理调用上限 120。
- 用户按上述精确身份授权后，M01—M06 于 2026-09-10 12:38—12:52（Asia/Shanghai）顺序执行，每个场景使用独立会话；没有修改代码、提示、夹具、oracle、模型、端点或预算，也没有局部重跑。
- Provider 账本 `tmp/p08-real-provider-20260909-1516337-r1/provider-calls.jsonl` 最终为 **77 started / 77 dispatched / 0 failed**，SHA-256 `7c3cd0a6a1fc84a177dd598caf8fe185a30f837358e34456e4540be0208e8d14`；分场景调用数为 M01 8、M02 12、M03 11、M04 15、M05 19、M06 12，未超过授权上限。
- 场景结果：M01 passed；M02 failed；M03 failed；M04 failed；M05 failed；M06 passed。批次本身有效，但 P08 / IC5 / AC40 均为 **executed_failed / not_accepted**。
- 主要问题：M02 的 D7/D30 合规回答未能发布并以 `run_state=failed` 终结；M03 虽在正文和 Markdown 中保留六来源事实，但 fallback 收敛失败且 Workbench 无已验证结论；M04 对明确任务错误弹出 `trend` / `period_compare` 路线确认；M05 大白话回合把未知金额单位改成“块钱”；页面还记录两次含 `NaN` 的 `tool_result` SSE JSON 解析错误。M06 的业务口径确认、一次恢复以及已计算/未计算/证据不足区分正确，但正文残留 `[[chart:]]` 原始标记，作为呈现缺陷记录。
- 会话隔离和工具消息配对仍闭合：六会话分别为 `14dbe7e4889a`、`c96e79aebde9`、`499dde01fa82`、`e86b389e1eec`、`29537e77db9a`、`f3b5907370a5`；对应 assistant tool calls / tool messages 为 7/7、12/12、14/14、16/16、2/2、6/6，无孤立工具消息。M04 的无效路线确认以 `cancelled` 留存；M06 成本口径记录 `integrity_status=ok`、`status=resolved`、回答“代金券及渠道成本”。
- 本结论只到 E4/L4 的本地真实浏览器＋真实 Provider；没有执行 staging、生产、部署或 push。本次未修改产品代码，后续修复后必须重新冻结并执行新的完整 M01—M06 批次，不能只补跑失败项。

## 7. 真实批次失败项的本地修复（2026-09-10）

- 产品修复提交：`main@13c129a`（父提交 `9bafaf1`）；未改动 R5 的冻结文件、账本、提示、fixture 或 oracle。
- M02/M03：fallback Python 结果后的策略拒绝改为可恢复的非终态工具结果，保持 assistant/tool 与 SSE 事件配对；D30 缺观测的明确否定可发布，正向预测仍拒绝。
- M04：跨版本关系“重新判断/评估/检验”识别为明确重判任务，不触发内部路线选择确认。
- M05：表达回合仅在已接受快照与当前数据身份一致时复用来源；未知金额单位不能改写成币种，混合日期窗口不能笼统认作全部未来。
- 跨场景：SSE 将 NaN/Inf 转为严格 JSON `null`；空 `[[chart:]]` 转为既有缺失引用提示。
- 回归：确认/控制组 130 passed（`tmp/repair-control-targeted-20260910-r2`）；内容/Web 组 208 passed（`tmp/repair-content-targeted-20260910-r1`）；最终聚焦 173 passed（`tmp/repair-publication-targeted-20260910-r2`）；quick-offline 235 passed。均禁用 Provider。
- full-offline `tmp/test-runs/repair-full-offline-20260910-9bafaf9`：2616 passed、1 failed、1 skipped。唯一失败为 golden funnel 报告落盘的瞬时 `FileNotFoundError`；同一单例与整个 golden 文件在新目录复跑分别 1 passed、5 passed。本记录不把整套写成全绿。
- 浏览器初查：`tmp/repair-browser-20260910-r2` 的页面、静态资源和核心 API 返回 200；当时把通用 Playwright 模块加载失败误记成“内置自动化驱动不可用”。后续确认当前内置浏览器应通过已安装 Browser 插件的 `browser-client.mjs` 连接，该初查结论已由下节 E3 实跑取代。
- 结论：本地 E1/E2 修复完成；新的 E3 已完成，E4 仍为 `revalidation_pending`。P08 / IC5 / AC40 保持 `executed_failed / not_accepted`，后续须在新提交上重新冻结并取得新的明确 Provider 授权。

## 8. 修复提交后的内置浏览器复验（2026-09-10）

- 运行身份：`main@176f5f2`（产品代码仍为 `13c129a`，其后仅有状态文档）；隔离目录 `tmp/repair-browser-20260910-r3`；入口仍为既有 `run_p7_browser_rehearsal.py`，未新增测试框架、探针、模型审核调用或重复记录机制。
- 根因：上一轮错误地从 Node 环境直接加载通用 Playwright；仓库页面和演练脚本没有退化。改用 Codex 已安装 Browser 插件的内置客户端后，复用原 5038 标签页即可读取可访问树并执行交互。
- 联合矩阵：B01—B06、IC-B01—IC-B06、CONTENT-B03、CONTENT-B07 均完成并达到既定终态。B01/B05 的 120、12、范围和证据等级在五种表达间不变；B02 的 D30 数值候选在同会话负例中被拒绝；B04 完成 supports/refutes/未决/版本变化后 stale；B06 工具失败不发布，保存失败为 `unknown`，预算耗尽为 `failed`。
- 澄清：IC-B01 与 IC-B06-METHOD 没有因内部方法名称暂停；IC-B03、IC-B04-CHANGE、IC-B05、IC-B06-SEMANTIC 只在成本范围、窗口或分母等业务口径处暂停并恢复；同范围成本决定复用，窗口变化重新询问，skip 不视为批准。
- 内容与呈现：CONTENT-B03 会话 `2cc0a85c9d1f` 的正文和刷新保留六来源；页面生成 9380 字节对话 Markdown 与 9150 字节发布报告，二者均含 `src_1`—`src_6`、金额与来源。CONTENT-B07 会话 `51fe66986d44` 实际渲染表格、KaTeX、Plotly 与备用链接；741×805 的内置视口下文档宽度等于视口宽度，无整页横向溢出。
- 刷新：B01 会话 `46e9d6c43b28`、B04 `18cbef03ada1`、CONTENT-B03 `2cc0a85c9d1f`、CONTENT-B07 `51fe66986d44` 重新导航后均保留目标正文和状态。浏览器控制台没有记录错误或 JSON 解析异常。
- 运行轨迹：`server_start.provider_enabled=false`；总计 `scripted_round=69`、`auxiliary_call=98`、`forbidden_provider_transport=0`，真实 Provider initiated calls=0。总数包含两条不计入矩阵的诊断探测：它们在独立空会话直接执行 B02-NEG，缺少标准 B02 先加载 `ret_a` 的前置条件；按 B02→B02-NEG 同会话链路复核后发布门正确输出“不能预测 D30”。
- 证据边界：本节完成修复后的本地 E3；不改变 R5 的真实 Provider 失败记录，也不代表新 E4、staging、生产、部署或 push 已完成。

## 9. 修复后的真实 Provider 完整复验（2026-09-12）

- 运行身份：`main@3873ff99301f47023e6da422f97316bbf345684a`；冻结文件 `tmp/p08-real-provider-20260910-3873ff9-r1/freeze.json`，SHA-256 `7156c9e115f9f6451249396bdb28e7dd970e1d81d2f5c78a15a45777a8827f44`；模型 `openai/deepseek-v4-flash`；端点 `https://api.deepseek.com`；调用上限 120。用户按该精确身份授权后，使用 Codex 内置浏览器在端口 5182 串行执行 M01—M06，每个场景使用新会话；批次内未修改代码、提示、夹具、oracle、模型、端点或预算，也未局部重跑。
- Provider 账本 `tmp/p08-real-provider-20260910-3873ff9-r1/provider-calls.jsonl` 最终为 **80 started / 80 dispatched / 0 missing / 0 orphan / 0 denied**，SHA-256 `f272a2791910a53dd9affbf0d944bff11bb677dd6c81800af8335712e8cf46dd`；调用号连续 1—80，分场景为 M01 7、M02 11、M03 14（含一次压缩请求）、M04 17、M05 19、M06 12，未超过授权上限。
- 场景结果：M01 passed；M02 failed；M03 failed；M04 failed；M05 passed；M06 passed。六会话分别为 `5ca39d702f63`、`66a96196bb27`、`2fc39f5f2a14`、`29e4536464f3`、`76e0f71fa8ff`、`3c9b81654363`；对应工具调用/工具消息为 4/4、9/9、21/21、29/29、3/3、6/6，均无缺失、孤立或重复 ID。除 M02 `run_state=failed` 外，其余五会话均为唯一 `completed` 终态；浏览器 error console 为 0。
- M01：页面、刷新和工作台保留 12 条、金额合计 120、未知金额单位、来源与条件性建议；没有因果或总体外推，达到 oracle。
- M02：工具已计算 D7=10%，正文也拒绝无依据 D30，但发布门以 `[unbound_time_point_claim]` 误判“能否预测 D30”的边界段落，`run_state=failed`；刷新后只剩图表/空回复壳。126594 字节 Markdown 虽已导出，页面、终态与导出不一致，未达到 oracle。
- M03：正文、刷新、14994 字节 Markdown 和发布报告完整保留六来源逐项事实与合计，未发生摘要裁剪；但冻结的“压缩上下文”动作在 `/api/compact` 返回 500，根因为 `_auto_save()` 对 `workspace_scope=None` 直接访问 `.phase`。该动作已发起一次已记账 Provider 请求，随后本地保存失败；因此 M03 按完整场景记失败，不能用正文通过覆盖操作失败。
- M04：两轮真实模型均直接执行，没有出现 `trend` / `period_compare` 等方法名确认；正文正确区分 v1/v2，声明 v1 的 +100% 与正斜率在 v2 未再现。不过刷新后的工作台仍在“已验证结论（6/7）”列出 v1 的 +100% 等旧结论，没有 stale/excluded 标记，违反跨版本证据失效 oracle，因此记失败。
- M05：事实摘要、业务负责人、分析师、管理者、大白话、技术表达六轮均保留 12 条、合计 120、2026-09-01—09-12、未知金额单位及受限证据等级；没有再次出现“块钱/元/人民币/美元”漂移。刷新和 9377 字节 Markdown 一致，技术方法与来源绑定可恢复。
- M06：缺失 `missing_orders` 时只说明数据缺口与唯一上传动作；载入销售数据后只对会改变净收益的成本口径提问，选择“口径B：代金券及渠道成本”后恢复一次。确认快照 `integrity_status=ok`、记录 `status=resolved`；最终只发布已计算总金额 120，并把促销增量收入、代金券成本、渠道成本和净收益列为未计算/证据不足，没有用用户选择替代缺失数据。刷新和 16608 字节 Markdown 保留该边界；刷新时确认提问所在的中间 assistant 气泡显示“（无回复内容）”，作为非终态呈现问题记录，不改变唯一完成终态。
- 结论：本次 E4 批次有效且调用核算闭合，但 P08 / IC5 / AC40 仍为 **executed_failed / not_accepted**。后续只应针对 M02 发布门、M03 空 workspace scope 压缩保存、M04 工作台跨版本失效投影修复；修复后必须新提交、新冻结、新授权并完整重跑 M01—M06。没有执行 push、部署、staging 或生产验证。

## 10. R8 失败项的本地修复与复核（2026-09-12）

- 产品修复提交：`main@d9164fa`。M02 的发布检查不再把“能否预测 D30”这类无数值断言的问句/标题当作正向预测；M03 `_auto_save()` 在 `workspace_scope=None` 时跳过工作区持久化但继续保存会话；M04 Workbench 以活动的 `*-vN` 数据集为当前版本，同系列非活动版本不再进入当前 verified，并在待验证区显示为 stale 历史。
- 回归：相关模块 135 passed（`tmp/test-runs/20260912T110259Z-dec8066d`）；同一次 runner 随后完成 full-offline，结果 **2620 passed、1 skipped、16 warnings**，Provider 网络保持禁用。
- Provider-disabled 内置浏览器复核：`tmp/repair-browser-20260912-r9`。M02 会话 `4342b3edf76b` 发布并在刷新后保留 D7=10% 与“不能预测 D30”；M03 会话 `a67927a591d1` 保留六来源回答，随后 `/api/compact` 返回 200；M04 脚本会话 `e97030bfa704` 完成支持、反证与同名数据重载。对 R8 真实 M04 会话 `29e4536464f3` 的 `analysis_state.json` 作只读重放后，Workbench 当前 verified 仅含 4 条 v2 结论，v1 假设显示为 stale。
- `runtime.jsonl` 只含 `server_start(provider_enabled=false)`、`auxiliary_call` 和 `scripted_round`，没有 `forbidden_provider_transport`，因此本次真实 Provider initiated calls=0。
- 证据边界：本节只关闭本地修复与 E1/E2/E3 复核，不改写第 9 节已失败的真实批次。P08 / IC5 / AC40 继续为 **executed_failed / not_accepted**；下一次 E4 必须以 `d9164fa` 之后的确切文档提交重新冻结并取得一次新的明确授权。未 push、未部署。

## 11. `dc44382` 真实 Provider 完整批次（2026-09-13）

- 运行身份：`main@dc44382f873c2842d77307d7c8075bbd1e5f6233`；冻结 SHA-256 `087974003fdb023e64fc86aec4f4c39a8431d89ecdbcb70832c039ea4c79e451`；模型 `openai/deepseek-v4-flash`；端点 `https://api.deepseek.com`；物理调用上限 120；内置浏览器。
- Provider 账本 `tmp/p08-real-provider-20260912-dc44382-r1/provider-calls.jsonl` 为 **78 started / 78 dispatched / 0 failed / 0 denied**，调用号 1—78 连续，SHA-256 `df8045038700236c24108a4b60034f7b07a2eb72780173117437384041aff3c7`。分场景为 M01 7、M02 11、M03 12、M04 15、M05 19、M06 14。
- 结果：M01/M04/M05 passed；M02/M03/M06 failed。M02 将无数值的 D30 假设边界误拒；M03 的六来源内容、刷新、导出和压缩完整，但把相邻两日变化误称“同比”；M06 未造数且正确区分未计算/证据不足，但真实成本范围问题被误标为方法确认，宿主未暂停，确认 ledger 为空。
- 六会话 `b3dcb3370dfe`、`80657c554ead`、`082344612717`、`062b7cebfa07`、`c8a8d856d396`、`13c4cdfd474d` 的工具消息分别为 5/5、11/11、5/5、15/15、3/3、9/9，均闭合；浏览器 error console 为 0。批次内未修复或局部重跑。
- 结论：批次身份和调用核算有效，但 P08 / IC5 / AC40 仍为 **executed_failed / not_accepted**；该授权已消耗，不能复用余额或会话。

## 12. R10 失败项修复与本地复核（2026-09-13）

- 产品修复提交：`main@16d2257`。发布门允许不带具体数值的非预测假设边界、仍拒绝未观测率；显式日期的错误“同比”标签进入一次修订；宿主把明确成本/窗口/分母业务口径从误标的 `method_confirmation` 恢复为业务决定并持久化，真正方法许可保持非阻塞。
- 隔离测试：`tmp/test-runs/20260913-r10-targeted-1` 152 passed；`tmp/test-runs/20260913-r10-targeted-confirmation` 126 passed；`tmp/test-runs/20260913-r10-full-offline` 2626 passed、1 skipped、0 failures。直接 pytest 曾因复用仓库默认 sessions 产生 5 个 ID/状态污染失败，改用既有隔离 runner 后全部通过；该污染结果不计为产品失败，也未删除或改写用户数据。
- Provider-disabled 内置浏览器：`tmp/repair-browser-20260913-r10`。B02/B02-NEG 会话 `cf46a735a5c0` 以 D7=10% 和 D30 边界 completed；CONTENT-B03 `6d00e72c303f` 在压缩、刷新和 9380 字节 Markdown 中保留六来源金额、变化、日期与记录数；IC-B03 `62f33fd6ade2` 只有一个成本范围确认，选择“代金券及渠道成本”后恢复一次并 resolved；IC-B06-METHOD `a254cdfd4ffe` 不暂停。四会话 run_state 均 completed，确认快照均 `integrity_status=ok`。
- `runtime.jsonl` 明确 `provider_enabled=false`，没有 Provider 传输记录，真实 Provider initiated calls=0。该 E3 只验证修复后的本地页面、HTTP/SSE、持久化、压缩、刷新、导出与确认恢复，不把第 11 节改写为通过；未 push、未部署。

## 13. `fe83160` 真实 Provider 完整批次（2026-09-13）

- 精确身份：`main@fe831601b7adef52a831317adaf93c2aeba760ba`；冻结 SHA-256 `c41c6064dac6887339512874705097e9f8d90087b0c73886c565e9b60309d7e0`；模型 `openai/deepseek-v4-flash`；端点 `https://api.deepseek.com`；物理调用上限 120；Codex 内置浏览器。
- Provider 账本 `tmp/p08-real-provider-20260913-fe83160-r1/provider-calls.jsonl` 为 **89 started / 89 dispatched**，调用号 1—89 连续，无 missing/orphan/duplicate 或超额；SHA-256 `7081EB193F260715A5AE0208335176C06A014CB3AA0183BFE14434C0063B28C3`。分场景为 M01 9、M02 13、M03 12（含压缩）、M04 23、M05 20、M06 12。
- 六会话依次为 M01 `ae0f19610090`、M02 `72b58ee16e69`、M03 `10baecd73ca0`、M04 `0b3090c608fa`、M05 `86aebe9517fb`、M06 `11b7fc3fedef`。assistant tool calls / tool messages 分别为 6/6、12/12、14/14、24/24、2/2、6/6；无缺失、孤立或重复 ID。每个会话各有一个终态；M02 failed，其余 completed；浏览器 error/warning console 为 0。
- 结果：M01/M03/M05/M06 passed；M02/M04 failed。M01 的 12 条、合计 120、未知单位、范围与限制在刷新后保留；M03 的六来源 10→11 至 60→66、合计 210→231、记录数、`日环比`、刷新、压缩和 5523 字节 Markdown 一致；M05 六种表达保持 12/120、日期、未知单位、证据等级与技术来源；M06 只对 `metric_definition` 成本口径暂停，选择“代金券成本 + 渠道成本”后恢复一次，最终分开已计算总额 120、未计算成本/净收益与证据不足。
- M02 已给出 D7=10% 且没有 D30 数值，但发布门以 `[unbound_time_point_claim]` 误拒“当前数据不足以支持对 D30 的预测，因此我不报告任何 D30 数值”，`run_state=failed`。M04 正文正确区分 v1 10→20→20 与 v2 10→10→10，也没有方法确认；但模型多次未满足 `record_analysis_plan` 契约，普通 measurements 又被严格 Stage3C0B 路径拒绝，最终 `analysis_state.json` 为 `evidence_records=0`、`hypothesis_sets=0`，不能以正文正确替代结构化审计闭环。
- 结论：批次身份、调用核算、会话隔离、工具消息配对和终态唯一性有效，但 P08 / IC5 / AC40 仍为 **executed_failed / not_accepted**。该授权已消耗；批次后已关闭服务和浏览器，没有追加 Provider 调用、push、部署、staging 或生产验证。

## 14. R11 失败项修复与本地复核（2026-09-14 收口）

- 产品修复提交：`main@bed3b15`。`publication_synthesis.py` 识别“不报告/不给出/不提供/不发布 Dxx 数值”的非预测边界，同时保留同句含正向预测时的拒绝；`record_analysis_plan` 向模型公开既有 Stage3C0B schema 并兼容对象/JSON 字符串；普通 measurements 不再被误当严格计划证据；显式竞争假设/重判任务在证据前建立稳定 hypothesis IDs，继续使用现有状态、账本和一次修订路径。
- 隔离测试：`tmp/test-runs/20260913-r11-targeted-2` 为 131 passed；`tmp/test-runs/20260913-r11-targeted-3` 为 80 passed；`tmp/test-runs/20260913-r11-full-offline` 为 **2630 passed、1 skipped、16 warnings、0 failures**。runner 禁止 Provider 网络。
- Provider-disabled 内置浏览器：`tmp/repair-browser-20260913-r11`。B02 会话 `abc88e4eaaf4` 发布 D7=10% 与 D30 边界，B02-NEG 的无依据 5% 候选经既有一次修订后完成；B04 会话 `470a4d26e812` 完成支持、反证、冲突、未决、版本更新与 stale，持久化包含 3 条 evidence records、4 个 plan-scoped hypothesis sets、8 条 receipts、3 个 publication packets，旧版本证据进入 exclusions。刷新后状态保留，浏览器控制台 error/warning 为 0。
- 运行轨迹：`server_start=1`、`auxiliary_call=26`、`scripted_round=19`、`forbidden_provider_transport=0`，因此真实 Provider initiated calls=0。该 E1/E2/E3 证据不改写第 13 节 E4 失败结论；新的完整 M01—M06 E4 尚未冻结或授权。未 push、未部署。
