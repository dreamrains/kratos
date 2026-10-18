# Provider 禁用 M01—M06 当前树联合批次

批前冻结：2026-09-30，实施树 `C:\Users\duguy\.codex\worktrees\trust-rebuild\data-agent`、`codex/trust-rebuild-20260927@4bb7f858151d9e03dce0a78ec7316968d166b090` 加保留的在途 dirty/untracked；供体 `D:\Project\Daily\data-agent@b181646` 只读。从属[唯一当前计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)。这是包 D 的 Provider 禁用 scripted 正常 app 批次，**不是**真实模型或浏览器视觉验收。

控制路线固定 `local_http_api`，演练入口 `scripts/testing/run_p7_browser_rehearsal.py`，端口 18785，新目录 `tmp/trust-rebuild-pd-matrix-20260930-r1`，`DATA_AGENT_SEMANTIC_AUDIT_TRIAL=1` 只对本演练服务生效；Provider transport 必须禁止，实际调用目标为 0。HTTP 控制逐案核对上传 ticket 文件名/SHA、独立会话或指定同会话、SSE 唯一终态、durable 状态、packet/渲染、导出及持久身份。picker、视觉正文/图表与刷新为 `unassessed`。批中普通场景价值失败继续；服务、隔离、SSE 或 Provider 禁止边界失败才停止。场景输入和独立正反 oracle 沿用[包 A 清单](2026-09-29-trust-rebuild-package-a-call-chain-oracles.md)，M02 明确分开未确认原值 `0.1` 和真实确认 `fraction` 后的 `10%`，不重复旧矩阵混合判据。

执行顺序固定：M01 六轮表达、当前双窗口行动、跨轮已核描述+比较；M02 未确认、确认 `fraction`；M03 六源图表；M04 同会话版本/关系；M05 聚合；M06 缺失/旧成本、仅券、双成本、skip/旧确认。各控制器在同一服务新目录中写互不覆盖的结果文件。既有 M01 跨轮旧版重载负例已经有独立新目录收据，本批不把旧会话拼入联合身份。

冻结 SHA-256：launcher `869a25cb0169b5a5e9464849dd011bf7dc659de5f2ace47e4c733535cd2bb9d8`；M01 原/行动 `c82e13c396c35bc7d8828e918892f2374d5b188d0563358a10d7c6c806945b87`、跨轮 `f03a8fc0996c7ce25e5797ecd26bccd86caf71de47ecb12a6290a1efcd94c4c0`；M02 未确认 `30d087a3b932662e28a7f4031f1a846e7695bc01e1612406e03c513b465dfc86`、确认 `6f146611139abb8ee844dd414dedd3c1eb0be1583d0611de38a9c99ae7cb6181`；M03 `2c639044f339c18e8cc40674edbc1607f0b20f97d24eff2e745a3f82b9cb7315`；M04 `b3f885f5b7c13ce790281a02877f02a6e48159ebb0f055455318a11df943d70b`；M05 `7b74d443248146eafd7c2fd6903e6feb81e32700b217466dd89b7945fb6999f4`；M06 缺失/旧成本 `9819c630e84f1c562439e1d53e61cb2ebd0819d9f1fc8e9477b0881ca1768826`、仅券/双成本 `78167a1ccfb6ed1e927495b38f8ea53cc6a1169c776c72344b5d3165975c1ea8`、skip/旧确认 `032831a3723da4fe3661128eb044750a69c0f6a3d111df079cea1464c7599a7c`。

## 结果

`r1` 演练服务端口 18785，监听 PID 2376，保留 exec session 12368；批前/组间/批末健康均 `ok=true/provider_enabled=false`，服务已停止。11 个控制结果文件按冻结顺序产生，M01 两项同会话链各自保持会话身份，M04 13 轮同会话，M06 skip 与旧版本确认独立会话。251 条 runtime 事件，`forbidden_provider_transport=0`，实际 Provider initiated 0；13 个 Markdown 导出引用均在该 run dir 下有实际文件。M01 当前双窗口行动与跨轮结果需求在试验审核下均为 `answered/checked`；M02 未确认 0.1、`fraction` 确认后 10%；M03 六个比较 block、六个 HTML 图表；M04 旧关系 `data_version_changed` 为 stale；M06 仅券 96、双成本 86，skip 不计算，旧确认版本 1 对当前 2 返回预期 fail-closed。runtime SHA-256 `00730f236b3478e06b06725be9a7201c43194249f0f4a0853af2b0b4c01bda96`。

**批次结论：冻结控制缺口，不能算包 D 通过。** M05 调用了默认 `tmp/r3_m05_http_probe.py`，得到普通 F-SALES 的 12 行单组摘要；包 A oracle 要求 `--edge` 的 6 行、3 组、缺值/重复 ID/零分母边界。控制器本身未失败，但冻结输入与目标 oracle 不匹配。`r1` 不作局部补跑拼接；下一批完整换新目录及新身份，M05 明确固定 `--edge`。

## r2 批前冻结

端口 18786，新目录 `tmp/trust-rebuild-pd-matrix-20260930-r2`；控制路线、试验审核设置、脚本 SHA、M01—M06 顺序和其余正反 oracle 与 r1 相同，**M05 命令明确为 `tmp/r3_m05_http_probe.py --edge`**。这产生 `F-SALES-EDGE.csv` 的 6 行/3 个分组，需按包 A 独立核对 sum/count/size/nunique、缺失与重复 ID。r1 与 r2 结果不合并，r2 必须执行整批。Provider 与视觉边界不变。

## r2 结果与边界

`r2` 演练服务端口 18786，监听 PID 17608，保留 exec session 3284；批前、M01/M02 后、M03—M05 后及批末健康均 `ok=true/provider_enabled=false`，服务已停止。11 个结果 JSON、独立跨轮 `composed-control.json` 和 13 个 Markdown 导出均在新 run dir 完整生成。252 条 runtime 事件中 `scripted_round=81`、辅助调用 168、`forbidden_provider_transport=0`，实际 Provider initiated **0**；runtime SHA-256 `038915d36a3b04ade328cee15fbbddf132b8483aa52497cec26b8276cbe9ea99`。

| 场景 / 会话 | 独立 oracle 结果 |
| --- | --- |
| M01 六轮 `d7043b2598c2` | 六轮同会话 completed；每轮保留 12 行、120、2026-09-01—12 含首尾 12 日、单位未知和行动证据具体缺口，业务/分析/管理/白话/技术改写未丢宿主事实。 |
| M01 双窗口 `4099fc7ef285` | completed；比较保留 700/770、140/175、560/595、70/77 及两段七日，`conditional_action_inputs` 当前版本闭合；试验审核发布“下一同口径七日且双条件才小规模试验，否则暂停复核”，未来未观测且不宣称因果，当前行动需求 `answered/checked`。 |
| M01 跨轮 `353f3b9eaf18` | 两轮 completed、各一终态；第二轮同时含当前比较、行动输入和先前同版本描述回执，12/120/日期范围仍由宿主重读；三个行动需求和一个跨轮结果需求均 `answered/checked`。control SHA-256 `7e43fe26cfc22de43f14e087cab600da69fc93415539f03aff453fb22277f6f2`。旧版本重载负例仍以独立 `tmp/m01-prior-source-stale-20260930-r2` 收据为准，不拼入本批。 |
| M02 未确认 `8aef5f5cbc12` / 确认 `0797b09657e6` | 未确认时 D7 仅发布原值 0.1 和未知单位；真实 `fraction` 选择后同会话恢复为 10%。两路均将 D30 留作无观测/无留出验证、回测或外部验证的未知边界，未冒充已验证预测。 |
| M03 `3d9d865bc1ab` | 六个上传票据、六个 `observed_comparison`、六个 HTML 图表；10→11 至 60→66、各自差额/10%/记录数全部保留，导出含六源及 12 个端点值，无跨源总量。 |
| M04 `67a7da5f5b1a` | 13 步同会话均 completed；真实计划 `spec_d443bcb10ccd`，v1 的 amount 增长支持与平坦反证来自实际 `compare_periods`，v2 后旧关系为 `stale` 且审计原因 `data_version_changed`，其它假设保持 `inconclusive`，未升级因果。当前推断列正反另有 `tmp/m04-inferred-metric-app-20260929-r1` 收据。 |
| M05 `63eb500cf13b` | `--edge` 正确使用 6 行/3 组夹具；A 为 20/2/3/2，B 为 5/2/2/1，C 为缺失/0/1/0（sum/count/size/nunique），缺失未当零、重复 ID 未当唯一，完整 fact refs 原位渲染。 |
| M06 缺数据 `8aaf2688e5eb`、旧成本 `4469a3f375cd` | 缺数据 completed 且不给计算值；旧成本 B 确认后 completed，保留 12 行/120/含首尾 12 日，成本与促销净收益明确未计算，选择口径没有补数值。 |
| M06 仅券 `a99518f12880` / 双成本 `37fe73052cd8` | 各自先 suspended 再同会话 completed；当前回执宿主重算 110−14=96 与 110−14−10=86，result/gap 均 `answered/checked`，单位及因果仍未知。 |
| M06 skip `0c149fcc5193` / 旧确认 `91bab772b477` | skip 后 completed，但结果保持 `not_computed/checked`；旧确认以 expected version 1 对 current version 2 fail-closed，持久状态为 failed，不错误复用旧决定。 |

结果文件 SHA-256：M01 六轮 `1e121b9ffec70f46ec22619e81b29e9307499e0144e0ee34f7cbe0bf71635b09`、M01 行动 `2fa14de7c6c6e6cb45545fbffd2a4a4c93d3d21ac989641f5ecff774d5c1caae`、M02 未确认 `18ba39c287a4d30dd79ce5628d85c9c06952a3d406841f6c8b1b09079ec0d9cf`、M02 确认 `2eb9b9b3a826e267c7dface89b47d46b833bc1a3d57a1dbf06cdbf36070af0dd`、M03 `3c7d108fd1044f07e32ff154424fb2f4ef7360964bbcc46630dd6cff0d409338`、M04 `5b3d62efd0e41b34974196f3382c2515a2c84aa266b1b2737aa4528b5abce0bc`、M05 `2072da8258448227bb18eb4a58895ee51c481e56117629f5e2cff961fc7a9ee2`、M06 旧/缺失 `8075ebc383dcd848728c8e73b3b0b07ccc5991474080e0956acf8067506d656d`、仅券 `2ca3a05693f0b34691abcc7f18ef8d24d9b3b9f112aa555aa3a3a580dc2222bd`、双成本 `2d3e9838e4dbb69505ce79355e12a74bc21fd260f4b8b2b7765d5959169eeb1b`、负例 `c24ad07e12da13ea7a7865ce5268c966bd936b88a7e1ed79b4c16dd5e4c22304`。

**结论：r2 通过当前冻结的完整 Provider 禁用 HTTP 非视觉矩阵。** 这是 scripted E3；上传 picker、可视布局/图表、浏览器刷新和控制台仍为 `unassessed`，不构成完整浏览器 E3。自然模型的意图映射、typed 提案和开放审核质量也未由本批证明。逐族旧散文门的剩余调用仍须退役或给出封闭保留依据，因此本收据不单独宣告包 D/R5 全局出口。
