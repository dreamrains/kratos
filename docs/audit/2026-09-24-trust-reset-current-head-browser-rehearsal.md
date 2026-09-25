# 当前 HEAD 的 Provider-disabled 浏览器复核与 E4 冻结前差异

日期：2026-09-24。执行源码：`main@e05d957b85b2f42e6643c20e578c1156dfb933b9`，启动前工作树无已列出的改动（本机 Git 全局 ignore 与 `.pytest_cache` 权限警告另计）。本记录是既有矩阵的本地 E3/零真实调用证据，**不是**真实模型、Phase 5 Shadow、Phase 6 正式处置或 Phase 7 验收。对照背景仍为 R7—R21、完整 R16、被中途停止的 R4 以及三份原始需求；不以本次脚本候选替代自然模型的正反样本。

## 冻结与操作边界

- 按根 `AGENTS.md` 先核对 worktree、现有 `.venv\Scripts\python.exe` 与 `scripts\testing\run_p7_browser_rehearsal.py`、新 run-dir 和空闲端口。使用仓库原有入口、Codex `iab` 单一 tab、可见上传标签加 `filechooser` 一次性附加每场景文件；没有开启 Provider、换浏览器/自动化栈或另建账本。初次默认命令通道未创建进程、监听器或目录；同一命令经批准的提升通道成功，未改变端口/入口。
- 服务 OS PID `12452`，保留的 exec session `86678`，端口 `5227`，隔离目录 `tmp/trust-reset-e3-20260924-e05d957-r1`。开始、分组和末尾健康检查均返回 `ok=true, provider_enabled=false`。批次结束后对原会话发送中断，端口已不监听；隔离证据保留。
- 启动脚本 SHA256 `FA6DF47758BEEBA916B4F7F81F0A2C4459C47332C8A8FED4DFF8241772A7A3A2`。完整 `runtime.jsonl` SHA256 `3C40959DD22A97C01BE1CAF1EF4C822461460665F08A358CCF5BC57ED5EB2ABF`；`server_start.provider_enabled=false`，`forbidden_provider_transport=0`，实际 Provider initiated calls **0**。控制台 `warn/error` 列表为空。

## 全批执行与可见结果

| 组 | 会话与已观察结果 | 证据限制 |
| --- | --- | --- |
| B01—B02/NEG | `dbf3e552c972` 给出 120/12 的有条件建议；`c9a185a57f69` 的 D1—D7/无据 D30 负例终局无 D30 确定数值，并留有拒绝候选。 | 只是脚本模型 + 真实 Web/AgentLoop/工具链，不证明自然模型措辞。 |
| B03—B04 | `138e9718920f` 六文件一次上传、`好的，继续。`、压缩/刷新/MD 导出；`63513c5f968d` 初轮加同会话第 2—13 步，持久化 1 plan、3 evidence、13 个 hypothesis-set 版本和 2 publication packets。 | B03 屏幕正文是简短概述；逐来源数值在同快照导出/来源说明，不能据此称真实 M03 的“正文逐来源”通过。 |
| B05—B06 | `8a98b52d2db5` 五种表达保持 120/12；`7b3854d057de` 明示缺失数据集；`d69d3b3e356c` 注入保存故障后 `unknown` 且界面 fail-closed；`4abb0976490d` 预算场景 `failed` 并显示限制。 | 后两者是预期故障路径，不是成功分析。 |
| IC-B01—B02 | `90fbf88a9ffe` 不因内部方法名挂起；`95a220ff9757` 九问题区分 `not_computed` 与 `evidence_insufficient`。 | 不证明旧 R11/R16 自然语义已等价保留。 |
| IC-B03—B06 | `a0bdc47c1095` 成本范围选“代金券及渠道成本”后在同范围复用，范围变化另问 7/30 天并选 7 天；旧 `ic-b05-legacy` 退役通用审批，跳过分母问题不授予计算许可；`3c3bf8805dad` 方法名不阻塞；`0688eb1ccb72` 询问自然周/最近 7 天并选自然周。 | 确认记录可复核：IC-B03/04 两条决定均 `resolved`；IC-B05 的 skip 不是批准。 |
| CONTENT-B03/B07 | `46d0f92f64d3` 六文件一次附加、同会话续轮、压缩/刷新与导出；`88cd9b825b98` 表格 120/12、KaTeX 公式、Plotly 图及备用链接刷新后仍在，741×805 下 document scrollWidth=clientWidth=741，导出存在。 | 内容值由脚本候选提供；本批不校准真实 LLM 的覆盖/解释质量。 |

16 个会话的 `run_state.json`：14 `completed`、1 预期 `failed`（预算）、1 预期 `unknown`（保存故障）；没有把这两类转成 completed。B03 的 MD 为 9620 字节、来源说明 9390 字节，均保留 `src_1`—`src_6`，来源 6 的 60/66；CONTENT-B03 相应导出亦为 9620/9390 字节，SHA256 分别为 `66D88EE28E99E8B6E814E4A4E2D3ABEE7DC6070DE8AE80C3F515F381505F3D12`、`12C134A826DE26A367F66171701D093204DF8F5143F9EF0E59D2D4A2D5F4B8B2`。CONTENT-B07 MD 为 56806 字节，SHA256 `A70E2363D37021D8F7889F2320F62ED332ACBE6F61208E7391401C02FAD73850`。刷新后界面与上述 `run_state` 相符。

本 run-dir 的 `runtime.jsonl` 只有 `server_start`、`scripted_round`、`auxiliary_call`、`injected_save_failure` 四类事件；没有持久化逐条 SSE terminal 序列。故本轮可确认每场景最后的 run_state/UI 收口，**不能独立证明每轮终态事件恰好一次**。后续 E4 冻结/执行记录须利用既有任务/会话事件接口核对，不能根据脚本回复自称“唯一”或补造探针家族。这个证据缺口使本次矩阵不应被写作 Phase 6 D 的完整 E3 通过；D 尚未获授权、也未接正式处置。

## 与目标/原始需求的差异及下一门

1. `scripts/testing/p08_real_matrix_contract.json` 当前 SHA256 `45DCA3D35BC4C5EF1E928605CF4945434D178AF181384A90DFE9903EEF120BFF`。M02 hard oracle 写死“D7 is 10%”和 D30 的百分点容差；但当前可核验证据只有原始 `retention=0.1`，没有百分比单位/尺度授权。用户已选择“原始数值尺度，标注单位未确认；仅明确单位证据时转换”。**冻结前应修订 oracle** 为该条件式尺度规则，不能让过时的 10% 预期倒逼宿主或模型补百分比。真实 R11 的正确自然边界仍须作为价值对照，不把其旧单位表述硬迁到新证据。
2. M04 hard oracle 含“failed v2 upload 恢复 v1 元数据”，而已冻结 scenario actions 只有 `inspect_workbench`、`refresh`，没有制造失败上传的动作；不能把未执行的负路径判 passed。建议将其从这次主矩阵 hard oracle 移至已有离线/独立负路径证据，或在下一次冻结中写明可执行且安全的动作、预期回滚与停止条件；**不在本批补测并冒充完整批次**。
3. B03/CONTENT-B03 的来源说明和导出保留了六源数值，但正文很短；这与原始“有价值的中文分析”和真实 M03 的“正文逐来源”不同。下一自然模型批次必须分开评分：可信事实、正文需求覆盖、导出可追溯、方法/解释价值。脚本 E3 绿灯不能关闭可信核心 A 的 R11/R16/M03/M04 正反保留门，也不能关闭正式散文旁无据 `99%` 误放。
4. Phase 5 仍无真实 Shadow 调度；Phase 6 仍只有 A+B 默认关闭离线准备，C 校准与 D 发布策略另设门；Phase 7 尚不能开始。下一步**不是**继续堆离线 `unassessed` 字段或词表：先同用户裁决上述 E4 oracle/动作差异，再用既有 `run_p08_real_matrix.py --preflight` 在新精确 HEAD 上零调用冻结模型、端点、固定 prompts/fixtures/oracles、预算、账本和运行目录；核对 manifest 后再单独请求真实 Provider 授权。未获授权，不得调用 `--authorized` 或真实 Provider。E4 结束后对照 R7—R21/R16/R4 聚类问题，再决定是否调整结构边界，不按一个失败补关键词。

本轮没有产品源码、发布默认、审计调用或 Provider 配置变更。上述 M02/M04 是**待裁决的冻结契约差异**，尚未修改契约，也未创建 E4 run-dir/ledger。

后续裁决（2026-09-24）：用户同意按上述建议修订 M02/M04，并授权在修订完成、精确零调用冻结且可行性核对通过后执行**本次**真实 Provider 批次，无须为同一冻结再次中断索取授权。授权不覆盖改模型/端点/预算/矩阵、扩大场景、补做探针、失败后局部重跑、push/部署；任何此类变化需重新冻结和确认。本段不改变本文件所记 `e05d957` E3 的源码时点证据。

修订时发现既有 `p08_scenario_audit.py` 的 M02 机械数字门仅搜索 `55`/`10`，对 `0.10` 与 `10%` 不具尺度识别能力。它已改为明示 `unassessed`、非阻断，真实 M02 必须检查同一源/回执/包/正文；未用新的关键词把旧误判搬到另一种写法。修改后须重新跑完整离线并以新 HEAD 冻结；修改前一次 full-offline 的 2962 passed/1 skipped 是中间时点，不作最终源码证明。

修订后定向矩阵/审计器测试 **25 passed**；fresh `tmp/trust-reset-fo-20260924-contract-r2` 全量离线 **2963 passed、1 skipped、16 warnings、0 failures**，JUnit `tests=2964/failures=0/errors=0/skipped=1`、SHA256 `4AD327F5EC398580B74B2178495FC51E50869087033C9CD25B2F4C6855E942FD`，runner `provider_calls=forbidden`。这仍只是 E2，不证明自然模型会按原始尺度作答；M02 机械项为 `unassessed` 正是为了避免把它误报为通过。

后续 M04 协议裁决：用户确认唯一两阶段上传例外。冻结契约现显式记录首轮前只上传 v1、首轮终态后同会话再上传 v2，且每一阶段仍用可见标签和一次 `filechooser`；其余场景不变。原 `1f4327e` 提交和 `r2` 离线收据是这一裁决之前的时点，不能作为最终冻结提交与测试收据。

M04 协议修订后定向 **26 passed**；fresh `tmp/trust-reset-fo-20260924-contract-r3` full-offline **2964 passed、1 skipped、16 warnings、0 failures**，JUnit `tests=2965/failures=0/errors=0/skipped=1`、SHA256 `ACF02767CD5613CC8AAD6B021CB94DB6D362CCB6BB2DBFB687948311876C4E7F`，runner `provider_calls=forbidden`。此时尚未执行零调用 preflight 或真实 Provider。项目运行时代码未改，先前 `e05d957` 的完整 Provider-disabled 浏览器批次是运行时代码等价证据；不能将它自动写成新 HEAD 的自然模型通过。

## 2026-09-25：Phase 8 分层验收后的当前 HEAD 完整 E3

本节是独立新批次，源码 `main@fbbc14741fa79901272fbcbd69cb48e15b7146b7`，启动前 clean。此前 fresh `tmp/tp8-layered-20260925-r1` full-offline 为 **3016 passed、1 skipped、16 warnings、0 failures**，JUnit SHA256 `163A6F9BFFE8CFE5237929127EC192E478D8A8F2AB8DCAAF3400B202F01422F4`，Provider transport forbidden。浏览器批次使用原入口 `run_p7_browser_rehearsal.py`（SHA256 `168820B56236DB0C418BD5979A01CA214D3D8B4002858FB2861E267EEF21E6E4`）、Codex `iab` 单 tab 6、端口 5235、隔离目录 `tmp/tp8-e3-20260925-r1`、OS PID 23740、保留 exec session 5856；stdout/stderr 同该 exec session，未单独重定向。启动前及 B05、IC、CONTENT 分组和结束健康检查均为 `ok=true/provider_enabled=false`。终局从同一 exec session 中断后 PID 消失、端口未监听，浏览器 tab 已关闭。

| 组 | 会话与实际结果 |
| --- | --- |
| B01、B02/NEG | `a52f084dce17` 保留 120/12 与有条件行动；`bfbfb70eedb3` 保留 D7=10% 且拒绝 D30 确定预测。这里的百分比是脚本候选文字，不构成当前 R11 数据单位授权。 |
| B03、B04 | `8ebde68ff94b` 六文件一次上传、同会话续轮、压缩/刷新/MD 导出；`b96c19c87237` 初轮及同会话第 2—13 步，刷新后 13 步仍在，持久状态有 1 plan、3 evidence、13 hypothesis sets、2 packets。 |
| B05、B06 | `3dc62023f20a` 五种表达均保留 120/12；`3f7f9183e33d` 缺数据集不发布计算结论；`4e57847458f5` 注入保存故障后 `unknown` 且界面明示未完成；`71af1a19b1c8` 预算耗尽后 `failed` 且界面明示限制。 |
| IC | `cb9336292978` 内部方法名不挂起；`68f61d086b3e` 九子问题区分未算与证据不足；`885c1d9bf408` 成本范围选“代金券及渠道成本”、同范围复用、窗口变化另选 7 天，两条确认记录 `resolved`；`ic-b05-legacy` 旧通用方法确认 `retired`、真实分母问题按矩阵跳过且未给确定复购率；`8e42c33a8eee` 方法许可非阻塞；`5dc46b4328d2` 自然周口径获选择。 |
| CONTENT | `67f2b39ed222` 六文件一次上传、续轮、压缩/刷新/导出；`5d58dd87ef6f` 刷新后标题、120/12 表格、公式与探索图仍可见，741×805 视口 document `scrollWidth=clientWidth=741`，视口已复原。 |

16 会话最终为 **14 completed、1 预期 unknown、1 预期 failed**，未把故障改写为完成。浏览器 console warn/error 为 0。B03 与 CONTENT-B03 的 MD 导出各 9620 字节，同会话计算来源说明各 9390 字节，保留 `src_1`—`src_6` 和来源 6 的 60→66；B07 导出 56790 字节。IAB 的 download 事件未到达，但服务对 `/export-reply` 与导出文件读取均返回 200，三个会话的持久 `reports/` 文件实际存在。脚本候选在 B03 的屏幕正文仍只是简短概述，不能据导出完整误称正文逐来源价值通过。

`runtime.jsonl` SHA256 `04D25863F126952672E6658D12D5BE876F30D5A75411FBA6395220C835A43C91`：`server_start=1`、`scripted_round=75`、`auxiliary_call=151`、`injected_save_failure=3`、`forbidden_provider_transport=0`，实际 Provider initiated calls **0**。本目录没有持久逐轮 SSE terminal 序列；UI 与 `run_state.json` 可证明各会话收口，不能独立宣称每轮 terminal 恰好一次。

同一当前审计器只读回放旧完整真实 P08 `tmp/trust-reset-p08-real-20260924-r1`，六个 M01—M06 场景均识别，报告在 `tmp/tp8-e3-20260925-r1/archived-p08-audit.json`（SHA256 `6178C7D6B01F37CE50DABE5A4BDBCB39EAFB75FA9F7ACB069028FDCBCF2C99DE`）：`verdict=failed`；执行与导出为 `failed`，证据与解释价值为 `unassessed`，声明为 `passed`。执行失败涉及 M04 缺结构化假设关系、M06 缺有效 claim binding；导出失败为既有会话缺 publication 导出。自然 M03-P/N 旧受控批次各 6 条可定位宿主 claim，但邻接解释/建议未审计、整批 `executed_not_accepted`；R11 百分比单位、R16 方法等价价值也不能由本次脚本候选证明。

**阶段边界**：Phase 8 的分维判定和当前 HEAD 的 E2/E3 完整矩阵已有可核收据；真实 E4 归档仍失败，开放语义仍未评估，故不称整体验收通过。按用户裁决继续保留 Phase 7 的现有自由散文门；没有足以逐族退役的正反证据。Phase 6 仍是默认关闭局部 typed 能力，不称 A/C/D 全部退出；正式发布默认、Provider 配置、Shadow 调度均未改变。本轮未新建词表、planner、账本或浏览器框架，也未调用真实 Provider。
