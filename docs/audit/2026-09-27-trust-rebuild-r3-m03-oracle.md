# R3.1 M03 六来源普通 app 基线

冻结于 2026-09-27。产品 HEAD `50eb619e2253c6fde295fbe96aa7c6708fb3042b`，供体只读 `b181646`。本轮先做现有 B03 的 Provider-disabled 正常 app 基线，诊断后再按功能实施；不得把旧 R4 自然会话或 opt-in typed 试验当作当前 HEAD 的通过证据。

## 独立判据与控制路线

- 控制路线在批次前固定 `local_http_api`，现有 `run_p7_browser_rehearsal.py`，端口 8781，独立目录 `tmp/trust-rebuild-r3-m03-http-baseline-20260927-a`。经 `/api/upload` 六张票据、`/api/chat`、SSE、durable session、Markdown export；脚本模型替代 Provider，实际 Provider 调用应为 0。视觉上传选择器、图表、页面刷新是 `unassessed`。
- 现有 `F-SRC1.csv`—`F-SRC6.csv` 各两行，`date=2026-09-01/02`。第 n 张独立来源的 `amount` 原值为 `10n/11n`，增量为 `n`，相对变化 10%；每期记录数各 1。不得仅凭数值列名把单位写成货币，也不得把六来源合计当作已请求结论。原始两日不是同比。数据行数、完整性、变化关系和每个来源的回执身份分别核对，不以预览两行替代全量。
- 固定提示：`【B03】请分别比较当前六个来源在 2026-09-01 与 2026-09-02 的 amount 原始数值、变化和记录数，保留全部六个来源及方法/范围限制。` 期望六个来源在最终 publication packet、正文/可打开产物及 Markdown export 中逐一可核对；一个 turn_start/turn_end，session/export 与最终答案一致。若只有包内或导出尾部引用而无业务结果，记作价值缺口。
- 基线运行后的代码修复或路线变化必须新目录和结果身份；本文件记录缺口，不得重写基线结论。自然模型、浏览器视觉、真实 Provider 与正式默认独立授权。

## 基线 A：已执行，业务交付未通过

- HEAD `50eb619`；端口 8781、exec session `95933`、PID `4020`；健康 `ok=true/provider_enabled=false`；HTTP collector SHA256 `19d6f57b62920a8bc0618978975fcaee3607149b875f43fcb73567d998969731`，零退出。运行目录如上，会话 `2389ee3d608b`，一个 `turn_start/turn_end`、durable 状态 `completed`。
- 六张 ticket、12 条工具回执，最终 packet `pub_9423e00797e4` 选中六个当前 `compare_periods` 来源且无遗漏 source。每个来源的 facts 已含 `metrics.amount.period_a/period_b/diff/change_pct` 和 `period_a.rows/period_b.rows`；例如第 1 来源 10→11、增量 1、10%、每期各一行，第 6 来源 60→66、增量 6、10%。24 个非优先 fact group 有明确预算省略记录，不影响上述核心事实。
- 最终 `answer_bindings=null`，正文仅称“完成六来源汇总、导出时应保留金额与记录数”，没有任何来源的两日金额、增量或记录数；Markdown export 虽包含来源引用/事实附录，仍不能代替正文的逐来源业务结果。故 R3.1 的答案价值门失败。`runtime.jsonl` 无 Provider transport 违规，实际 Provider initiated calls 0；视觉未评估。
- 下一改动方向：在已选当前 `compare_periods` 事实中按来源闭合两期值、差额、相对变化与行数，扩展现有 `answer_bindings.v1` 的宿主 observed 类型并原位渲染主要比较结果；缺失或错配的来源局部标具体缺口。不能把六个来源合计、预览行数或货币单位补成未授权事实，不按 “B03” 或关键词启动产品 selector。

## 回放 B：批次前固定

- 产品候选按各已选 `compare_periods` 回执闭合事实与数据身份后产生 `observed_comparison` block；宿主复核每个 block 的事实引用并渲染表，缺损来源只给其自身缺口。独立模型解释通过原有发布校验后仍保留。定向 150 passed；曾发现单个不完整比较收据的旧发布路径被过度阻断，已在同一实现轮修正并重新跑定向。
- 新批路线 `local_http_api`，端口 8782，运行目录 `tmp/trust-rebuild-r3-m03-http-final-20260927-b`；同一六夹具 SHA/提示/独立数值 oracle、现有 Provider-disabled 入口和 collector。须先验目录/端口/健康/PID；一个终态、六个来源当前 packet 与正文每个 `10n→11n`、记录数、SSE/session/export 一致；实际 Provider 0。视觉仍 `unassessed`。

- B 已完成数值回放：端口 8782、exec session `82617`、PID `16316`，健康 `ok=true/provider_enabled=false`；同一 collector SHA256，脚本零退出。会话 `291702368e0d`，packet `pub_242f3a8d7a91` 的六条 `observed_comparison` block 各引用四个金额事实，正文六行均逐一给出 `10n→11n`、差额 `n`、10%、每期记录数 1；模型的独立泛述作为补充解释保留。单终态、SSE/session/export 正文相同，`runtime.jsonl` 无 Provider 传输，实际 Provider initiated calls 0。视觉未评估。
- B 后校核发现两项结构缺口：记录数和日期标签虽由宿主复核当前 packet，却未计入 block 的 `fact_refs`；期间 A=0 时相对百分比无定义，不应因此丢掉同来源仍正确的 A/B 原值、差额和记录数。下一实现批次同时修正并新目录回放，不把 B 当作 R3.1 完整验收。图表产物也未生成，仍需按原 R3.1 范围评估。

## 回放 C：批次前固定

- `observed_comparison` 的 fact_refs 现覆盖两期标签、两期记录数和同一指标的原值/差额/百分比；A=0 仅把相对变化标为未定义，保留原值、差额和另一独立来源。定向 151 passed。C 路线固定 `local_http_api`，端口 8783，全新目录 `tmp/trust-rebuild-r3-m03-http-final-20260927-c`，同六夹具、同提示、同 collector 与独立 oracle；需先核 worktree、目录、端口、健康/PID。Provider 0，视觉未评估。

- C 数值回放通过：端口 8783、exec session `11656`、PID `7620`，健康 `ok=true/provider_enabled=false`，零退出。会话 `7d7c660ed7bd`、packet `pub_ea5096d72bfb` 的六个 `observed_comparison` block 各引用 8 个当前事实（两期标签/行数与指标四项）；六个来源逐一有原值、差额、10%、各期一行，SSE/session/Markdown export 正文一致。`runtime.jsonl` 无 Provider 传输违规，实际 Provider initiated calls 0；服务已停止，视觉未评估。
- 图表仍是 R3.1 未完成项。为了保留冻结 B03 行为，D 另用既有 B03 组的 `B03-CHART` 变体：六张同 fixture、同两日期，脚本模型先执行六个 compare_periods，再调用现有 create_chart 为各个注册数据集生成原值 bar 图，purpose 明示 `exploratory`；宿主比较表仍来自独立比较回执，不把探索图升级成验证结论。D 路线批前固定 `local_http_api`，端口 8784，全新目录 `tmp/trust-rebuild-r3-m03-chart-20260927-d`；检查六个 HTML 图及元数据、出口引用，单终态/SSE/session/export 同一正文，Provider 0，视觉打开/刷新仍未评估。

- D 已执行：端口 8784、exec session `14336`、PID `17072`，健康 `ok=true/provider_enabled=false`；会话 `3a36a56aa8fa`、packet `pub_c5cad6e1628f`，六个独立比较结果、单终态及持久正文一致。六个 `create_chart` 各自产生已登记 HTML、PNG 和元数据，数据集/版本指纹与对应比较来源相同，标注为 `exploratory`。普通 Markdown export 产物实际包含六个图标题、六个 PNG 与六处探索级别说明；`/export` API 返回的是产物路径，本身不内嵌图内容，不能据此判为导出失败。`runtime.jsonl` 无禁用传输事件，实际 Provider initiated calls 0；服务已停止。
- D 的未满足项是主答案只有六源数值表，没有把六张已登记图与各自来源相连，也没有可打开的图表链接。图表虽在导出末部出现，不能替代主要业务结果中的逐来源产物交付。下一实现仅在当前比较回执与当前会话已登记图的 dataset、版本/指纹、轴/指标相符时，将探索图链接放入对应宿主比较块；错配或缺图只影响该来源图，不删除正确数值。新代码与回放使用全新 E 目录。视觉打开与刷新仍未评估。

## 回放 E：批次前固定

- 控制路线 `local_http_api`，产品 HEAD `50eb619` 加工作树内 R3 候选；端口 8785，全新 `tmp/trust-rebuild-r3-m03-chart-20260927-e`，现有 Provider-disabled rehearsal 入口及 `B03-CHART` 变体，HTTP collector SHA256 `a0f3b1abe89d84685c0c8f4a5362d8c4c19b0b64a4c422f9fd45f03d98fd0a4f`。六张同 fixture 和固定图表提示；先核 worktree/入口/目录/端口，健康后调用。独立判据：六源主答案各保留原值/变化/行数，逐源打开链接只指向当前比较版本和已登记探索图；普通 Markdown export 含同一正文及六图，SSE/session/export 单终态一致，实际 Provider 0。UI 打开/刷新仍 `unassessed`。

- E 已执行：端口 8785、exec session `74986`、PID `14936`，健康 `ok=true/provider_enabled=false`；会话 `37037ec473be`，packet `pub_f95643554c08`，一个 `turn_start/turn_end`，durable 状态 `completed`。六个 `observed_comparison` block 分别带同来源探索图；六行手算原值/差额/10%/各期一行均正确，正文与 Markdown export 相同。六条当前图 receipt 经同会话已登记 HTML、metadata、data identity 的 version/fingerprint、日期轴和 amount 指标验证；主答案六条 `/api/files/...` 链接均 HTTP 200。普通 Markdown export 含六条正文链接和六张嵌入 PNG，各图明确为探索级别。`runtime.jsonl` 无禁用 Provider transport，实际 Provider initiated calls 0；服务已停止。
- R3.1 六源主交付的数值、独立来源与图表 HTTP app/导出证据闭合。HTTP 路线未评估可视图表/上传选择器/刷新；超过两行及零分母目前为定向 E2 保护，预览截断/结果选择边界仍需 R3 后续矩阵，故 R3.1 不能仅凭本批判为完整产品验收。
- 当前 R3 候选在全新 `tmp/trust-rebuild-r3-full-20260927-a` 运行 `full-offline`，Provider 调用由 runner 禁止；结果 2874 passed、1 skipped、0 failed、16 warnings。此 E2 与 E HTTP app 分列，均不构成自然模型、视觉或真实 Provider 验收。

## 回放 O：四行源表与两行预览边界

- 目标 HEAD `f46b5bf`，供体 `b181646` 只读。保留原 B03 六源/图表批次结果身份；新增 `B03-PREVIEW` 脚本变体仅用于六源各四行的正常 app 行为。第 n 个 `F-SRCn-FOUR.csv` 的 amount 依日期 01—04 为 `10n,11n,12n,13n`；`preview_data(n=2)` 只展示前两行，不含 B 期。独立全量比较应为 A 两行 `21n`、B 两行 `25n`、差额 `4n`、相对变化 `4/21≈19.0476%`，六源独立，不默加；预览行数不能替代任一期的完整行数。
- O 批前固定 `local_http_api`、Provider-disabled 既有入口，端口 8799、全新 `tmp/r3m03previewo`；现有 bounded HTTP collector `tmp/r3_m03_http_probe.py --preview` SHA256 `b295258b8fbacc8cd894f116ce83a55ddf8741cbe9b2fa3796c668305a04ef66`，rehearsal SHA256 `d1c731c591fa443449633a916e4b7805711969284723c32dd09ee7beb4595869`。批前 worktree 目标 HEAD/分支与供体已核，`.venv`/入口在、目录不存在、port 空闲。健康/PID 后上传六 ticket 并核 SHA、SSE 唯一终态、持久 packet/正文/Markdown export、Provider 0。视觉 picker/图表/refresh `unassessed`。若控制失败，标记对应 oracle `unassessed`，不能算产品失败。
- O 未通过主答案业务门：端口 8799、exec session `60864`、PID `25572`，健康且 Provider 禁用，服务已停止；会话 `8d2b9bc057e9`、18 回执分别为 6 load/6 preview/6 compare，单 `turn_end`、durable `completed`、Provider 0。当前 packet 选中六条 compare 且各自有完整 A/B 原值、两期各 2 行、标签、差额和 19.05% 回执事实；前两行预览没有成为比较来源。然而 `answer_bindings=null`，正文只剩模型泛述。根因是宿主把工具已按两位小数舍入的 19.05% 与未舍入 `4/21×100` 用 `0.00001` 容差比较，六源都被当作无效。O 不能计为四行/预览边界的产品通过；这是比较回执精度契约缺口，不是预览控制失败。
- 候选让宿主按工具 `compare_periods` 的两位小数变化率精度核对，并匹配其负基数时使用绝对值分母；错值仍局部拒绝，另一个独立来源保留。正反定向比较/发布 153 passed；P 新目录重跑原六源四行/两行预览批次。若同一精度根因第二轮仍不收敛，转设计裁决，不做第三轮同型阈值补丁。
- P 批前固定 `local_http_api`、端口 8800、全新 `tmp/r3m03previewp`；六夹具/提示/独立 `21n→25n`、两期各 2 行、`4n`/19.05% 与预览仅 2 行的判据不变，collector/rehearsal SHA256 分别为 `b295258b8fbacc8cd894f116ce83a55ddf8741cbe9b2fa3796c668305a04ef66` / `d1c731c591fa443449633a916e4b7805711969284723c32dd09ee7beb4595869`。批前目标 HEAD `f46b5bf` 加精度候选/正确分支、供体 `b181646`，`.venv`/入口在、目录不存在、port 空闲。健康/PID 后核六 ticket SHA、单终态、六来源主答案/持久/导出、Provider 0；视觉 `unassessed`。
- P 已通过全量/预览边界：端口 8800、exec session `59832`、PID `4088`，健康且 Provider 禁用，服务已停止；会话 `3e8eb752c042`、18 条回执（6 load/6 preview/6 compare），六 ticket SHA 匹配。Packet 只选六条当前比较来源，六条 `observed_comparison` block；主答案分别为 n=1…6 的 A `21n`、B `25n`、差额 `4n`、19.05%、各期 2 行、单位未知/描述性限制，未把前两行预览充作全量或六源默加。一个 `turn_start/turn_end`，durable `completed`，SSE/持久正文相同、Markdown export 按换行规范化后包含完整答案。禁用 Provider transport 事件 0，实际 Provider initiated calls 0。视觉 picker/图表/refresh 仍 `unassessed`。
- P 候选在新短目录 `tmp/r3m03p` 跑 `full-offline`：2888 passed、1 个预设 live smoke skipped、0 failed、16 warnings，runner 禁止 Provider 调用。E2 与 P HTTP app 分列；不折算 synthesize 结果选择、视觉、自然模型或完整 R3 验收。

## 回放 Q：多父对齐、预览与分别比较

- 目标 HEAD `c3486ea`，供体 `b181646` 只读。用户明确请求将 `F-SRC1-FOUR.csv` 与 `F-SRC2-FOUR.csv` 按日期**并列对齐**，仅预览派生表前两行，再对完整四行分别比较两列；没有请求两来源加总。独立判据：派生表四日/两父版本，`src_1` A=21/B=25/差 4，`src_2` A=42/B=50/差 8，两期各 2 行，两列变化均 19.05%，单位未知、仅描述性。前两行不含 B 期；预览不能充当完整比较。错误合计 63/75 或遗漏任一来源均失败。
- Q 批前固定 `local_http_api`、Provider-disabled 既有入口，端口 8801、全新 `tmp/r3m03synthq`；rehearsal SHA256 `adb902ada68c1f2edd6ce1ab49e45d12116f147ad9bbc18f4fac076ef91d71e`，collector `tmp/r3_m03_http_probe.py --synth` SHA256 `2c639044f339c18e8cc40674edbc1607f0b20f97d24eff2e745a3f82b9cb7315`。批前核目标 HEAD/分支、供体、`.venv`/入口、目录不存在、port 空闲；健康/PID 后核两 ticket SHA、单终态、真实多父 `derived_identity`、packet/正文/导出、Provider 0。视觉 picker/刷新 `unassessed`。
- Q 已通过多父结果选择：端口 8801、exec session `34675`、PID `23812`，健康且 Provider 禁用，服务已停止；会话 `48c1fd913303`，两 ticket SHA 匹配，5 条回执为 2 load/1 synthesize/1 preview/1 compare。`aligned_pair` 的 `parent_version_ids` 精确包含 `src_1` 与 `src_2` 两个当前版本；packet 选择当前 compare 一来源、一条 `observed_comparison` block，正文有两行独立指标：`src_1 21→25 / 4 / 19.05%` 与 `src_2 42→50 / 8 / 19.05%`，两期各 2 行、单位未确认；未出现未经请求的合计。单 `turn_start/turn_end`、durable `completed`、SSE/持久正文一致，导出按换行规范化后包含同一答案；禁用 Provider transport 事件 0，实际调用 0。仅 rehearsal 场景新增，产品代码与 P E2 `tmp/r3m03p` 同身份；不重复完整 E2。视觉和自然模型仍未评估。
