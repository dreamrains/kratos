# M03 完整预览自然模型受控试验 r2（2026-09-25）

## 冻结与执行身份

用户在本轮明确提前授权真实 Provider 验证，且批准内置浏览器为新服务创建标签。零调用预检在 clean `main@2f09e70c158686540c058c8065a4e5f67cd76e73` 生成 `tmp/typed-trial-natural-m03-20260925-r2/freeze.json`，SHA256 `18BCC802FCB0C516660D0009D01A902ECF0EA53C179B2259DCD9D109233A411A`。冻结含 launcher/合同、两例提示与 oracle、六份 fixture 各自哈希；模型 `openai/deepseek-flash`、端点 `https://api.deepseek.com`、顺序 `M03-P`→`M03-N`、最多 30 次物理发起、每次输出上限 65536 token、墙钟上限 600 秒、`ONE_SHOT` 无重试。正式发布默认与 Shadow publication effect 均不变。启动前账本与结果不存在，源提交、配置、冻结输入在启动时重验。

现有 launcher `run_typed_trial_real.py --authorized` 以端口 8774、PID 20416、exec session 82062 启动，health `ok=true/provider_enabled=true/typed_trial=true/source_commit=2f09e70...`。浏览器只用 Codex IAB tab 5；两例独立会话，每例六份冻结 CSV 经可见标签一次 filechooser 上传，发送冻结提示。服务 stdout 留在 exec session，无独立 stderr 文件；测试结束服务已停且端口关闭。未重试或局部补跑。

## 两例实际收据与 oracle

| 案例 | 会话 / turn | 执行与宿主身份 | 价值与剩余缺口 |
| --- | --- | --- | --- |
| M03-P | `d2cb0464bb3a` / `t_41ddcb` | `completed`；恰六份 `preview_data`、无 `compare_periods`；终局 `ready/final`，6 个 `answer_bindings.v1` comparison、6 个唯一回执、6 条原位 trace；刷新后六张 10→11 至 60→66 表仍在 | 逐来源两日值和差额正确，单位未确认，需求覆盖仍 `unassessed`，无跨源合计或独立性正断言。模型在六块之外另写未绑定汇总表、置信度与方法解释；不能因局部 typed 有效便认可整篇自由散文。尤其“2 个点不足以判断趋势方向”混淆已观察变化方向与较长趋势判断。 |
| M03-N | `7e6dfed8a125` / `t_00a999` | `completed`；同样六份 `preview_data`、6 binding / 6 trace；刷新后保留 | 模型把 99% 与七天当作错误说法，把来源独立性保持无法验证，没有将三者写成已证结论。但六块外仍有未绑定的 `+10%` 汇总表、置信度及“提供 9 天以上”等未获宿主授权的建议；“趋势类结论至少需要多个时间点，当前不满足”与两天数据的字面数量相冲突。反例的**内容拒绝**可观察，现行正式门仍允许邻接散文，因此严格邻接安全 oracle 不通过。 |

两个会话各有一份持久 Markdown 导出并经 IAB 刷新恢复；浏览器 console warn/error 为 0。IAB 未提供可靠的 download 事件回执，因此只计服务 200、导出文件存在与 SHA。runner 未单独保存逐轮 SSE terminal 序列，不声明 terminal 恰好一次。`tmp/typed-trial-natural-m03-20260925-r2/results.json` SHA256 `904AA2D6CAB0A5CE3B62E2102792B6D5FC6EE104BA34CD8F0085F2A47A73263D`：两例实际提交消息 SHA256 分别为 `255446F6D18212CB580A7CFBA14C983AAD2658897F27FA7344B3687AA1B7A4AD`、`6E0A699DC5739AEDAB312742D61851592EC4DEFEA73EA033C95FE6C9B124E97A`；均以冻结提示为前缀，额外仅为浏览器加入的六个分析文件行。两例最终答案 SHA 与 packet/历史一致，12 条 trace 范围及片段 SHA 全部匹配。导出 SHA256 分别为 `57D67A08662BE62B8406D6B7E8232AC6AD141DF12F1114B231301E7068B5FAE3` 和 `624AB415AAD02D604451A372A2FFFA041D624D56EC664AC8C7CCC504F5999A81`。

唯一 Provider 账本 `tmp/typed-trial-natural-m03-20260925-r2/provider-calls.jsonl` SHA256 `7A0622BDEA5AE5D6BCDA2D75503982A6CF639F353D571C9B65CAE9004522B434`，**11 started / 11 dispatched / 0 failed / 0 denied**，没有重试。账本记录的 `3680/1200/4880` prompt/completion/total token 只来自报告 usage 的非流式调用；流式调用未报告完整用量，不能把 4880 写作批次真实总 token，也没有可核对的 `finish_reason`。

## 阶段判定与下一门

这批证实默认关闭入口在真实自然模型下可以由完整 `preview_data` 形成六个可定位、同回执、宿主原位渲染的 typed claim，补上 §49 的 0/0 生产缺口。P 的局部数值保留和 N 对三个错误断言的可见拒绝成立；**整批 `executed_not_accepted`**，因为有效 typed 旁仍有未经原位绑定的事实复述、置信度和建议，正式整篇自由散文门尚未退役。Phase 6 A 的自然局部生产可标为有正反实证，但全历史价值门仍未退出；Phase 5/C 的自然 Shadow 质量分母、Phase 6 D 的正式处置与 Phase 7 均未完成。本冻结授权已消费，不得用剩余额度做补测。

下一最小 RED 应用本批真实 P/N 的同内容形状：在已有 6 条 trace 旁加入一处独立无据 `99%`、一处正确但未绑定的重复汇总，以及一处开放方法建议，分别判定宿主可保留、降级或必须隐藏的边界。结构替代继续使用同一 packet/trace/`answer_bindings.v1` 的可信核心与受限局部解释；是否将默认关闭试验的可见答案收窄到宿主渲染核心、如何保留正确的上下文解释，属于产品价值与 D 前置取舍，须先与用户裁决。当前不改正式发布、不新增词表、planner、账本、浏览器框架或隐藏模型总审。

补充零调用价值对照：直接对两份已接受 packet 调用现有 `render_verified_partial_answer`，P 的 2271 字、N 的 2728 字正文都会收敛为 **1203 字的同一宿主核心**，六个来源均在，错误的 99%/独立/七天正断言均不在；“怎么理解”“核对”等解释也全部消失。这证明纯核心足以保住本例数值，但不足以替代所有正确解释。下一默认关闭正文边界已提交用户裁决，不能把这次离线对照当成正式处置授权。
