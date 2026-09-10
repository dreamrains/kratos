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
