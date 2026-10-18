# `71e23d0` 真实 Provider M01—M06 批次收据

日期：2026-09-30。实施树 `C:\Users\duguy\.codex\worktrees\trust-rebuild\data-agent`，分支 `codex/trust-rebuild-20260927`；供体 `D:\Project\Daily\data-agent@b181646` 保持只读。本收据从属[唯一当前计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)。

## 精确冻结、授权与控制路线

候选提交固定为 `71e23d0ac26091365508ae1b50fa7dd88b238591`，运行目录 `tmp/trust-rebuild-p08-real-71e23d0-r1`，冻结文件 SHA-256 `73dd8d99d53a3c0bb98ebe63f2ffeabd190b7eef05ae6cbeb534eef32dbf0a37`。控制路线为 `local_http_api`，模型 `openai/deepseek-flash`，端点 `https://api.deepseek.com`，M01—M06 顺序执行，调用上限 120，`one_shot`，语义审核关闭。

launcher、HTTP driver、合同和矩阵计划摘要分别为 `sha256:aa30a83fb2a5cd445750e97ee5b67e8bbb62949ec9d79c688857358f8d0ae74f`、`sha256:54ea459916edc530c760cee359ec06c0259a6555279dc7d689537a415801c347`、`sha256:04ea9c8a43fa509d40ae339f028475163eef3f58df6e6b04d6723022798261ee`、`sha256:24b70af71f16396e69bf0df1059004c9a14ac0213b2250a1bcda4b106fa58043`。M06 冻结恢复值为 `voucher_plus_channel`。

用户精确授权向该端点发送 `71e23d0` 的 M01—M06 冻结输入，最多 120 次 Provider 调用。服务端口 18789、监听 PID 24556；批次只执行一次，没有重试或局部续跑，证据收集后服务关闭并确认端口不再监听。HTTP picker、浏览器可视正文/图表和刷新仍为 `unassessed`。

## Provider 账本与传输

`provider-calls.jsonl` 记录 94 started、94 dispatched、45 completed、49 stream_exhausted，0 denied、0 failed、0 stream_failed、0 stream_closed。累计调用点为 M01 15、M02 27、M03 38、M04 55、M05 76、M06 94；没有越过 120 上限。账本 SHA-256 为 `5c7917e2757e8493bb8a70f89958eac098b728edb9460a753b79f4f9987bf804`，HTTP 矩阵 SHA-256 为 `7390f79f7d6d1f9576d459962c11e6e98d9422db7bfb90b26d16466719b397b`。

六个场景的每轮 SSE 均只有一个 `turn_end`，持久状态与终态一致；M06 为 completed → suspended → resume completed，确认快照完整性为 `ok`，唯一确认已解析，pending 列表为空。服务、会话和 Provider 计账没有全局失败。

## 独立 oracle 判断

| 场景 / 会话 | 结果 |
| --- | --- |
| M01 `2c29e7b7631b` | 两轮 completed。首轮宿主保留 12 行、amount 合计 120、单位未知、2026-09-01 至 09-12 含首尾 12 日。第二轮保留 700/770、140/175、560/595、70/77、两个七日窗、未知单位、未来窗口未观测与非因果边界。自然候选含完整 AND 行动规则，但语义审核关闭时被 `withheld_pending_semantic_binding`；行动需求仍为 `evidence_insufficient`。封闭事实通过，开放条件行动未交付，M01 整体不通过。 |
| M02 `b477b37b94dd` | completed、导出和持久重载成功。D1—D7 原始值、D7 `0.1` 单位未知、模型族与 R²、D30 未观测以及未做 holdout/backtest/external validation 均保留。非视觉 oracle 通过。 |
| M03 `2a5b014d3229` | completed、压缩、导出和持久重载成功。正文保留六来源 10→11 至 60→66、逐源绝对/相对变化和记录数，没有跨源业务总量或因果表述。图表 JSON 含 6 条独立 trace，`y_cols` 完整列出六来源；pivot JSON 失败未复发。非视觉 oracle 通过。 |
| M04 `47d7cd745563` | v1/v2 两轮 completed。持久结构中 v1 为 supported 1 / inconclusive 3，v2 为 refuted 1 / inconclusive 3；回执分别支持 10→20→20、斜率 +5/日、p=0.333 和 10→10→10、斜率 0，版本与计划 ID 分离。可见终局却只给基础摘要和一个不等窗聚合比较，没有交付竞争假设审计。内部结构正确不能代替正文，M04 不通过。 |
| M05 `2131683fb69e` | 六轮 completed、导出和重载成功，事实始终为 12 行、120、含首尾 12 日、单位未知。六轮可见答案都是相同宿主基础摘要；业务负责人、分析师、管理者、大白话和技术表达的自然候选均被扣留，技术方法也没有在恢复轮交付。M05 不通过。 |
| M06 `bf0c85cacb7c` | 缺失数据集轮由宿主明确缺口并只给一个上传动作；成本口径确认以稳定值恢复并完成。恢复后的宿主正文仅给 12 行/120/12 日/单位未知，没有把选定口径下净收益“未计算”和促销增量“证据不足”分开；需求仍 `unassessed`。缺数据与确认生命周期通过，最终内容不完整，M06 整体不通过。 |

**批次结论：不通过 R3/R4/R5 联合自然验收，也不构成完整浏览器 E4。** M02、M03 的非视觉 oracle 满足；M01 的开放行动、M04 的可见假设审计、M05 的表达价值和 M06 的状态分离仍失败。正确宿主事实均保留，失败没有改写为整批通过。

## 批后结构裁决

四个失败集中在同一终局边界：`_render_terminal_publication` 先发布宿主事实块，并在语义审核关闭时把比较/基础摘要的自然候选整体扣留。这样保护了数字、范围、单位和版本，却同时吞掉了条件行动、竞争假设、表达改写和状态解释。不能再为每种措辞追加关键词或让自由散文覆盖宿主事实。

后续按原 `answer_bindings.v1` 收敛，但在实现前先执行[控制复盘](2026-09-30-trust-rebuild-control-review.md)的场景统一、零调用路径核对、自然收据重放与删减门：

1. M04 从当前计划、假设集、已核关系、同版本工具回执和数据身份生成宿主 `hypothesis_audit` claim；历史 v1 与当前 v2 分开渲染，历史证据不得升级为当前结论。
2. M06 把已解析确认、当前描述回执和缺少结果/比较回执组合成宿主结果状态块，明确区分已计算、`not_computed` 与 `evidence_insufficient`。
3. M01 的开放条件行动继续只在结构输入和有界语义审核同时通过时发布；本批审核关闭，不能倒填通过。
4. M05 属于开放表达价值，需统一的受限候选发布机制；不能把六种样式做成六个词表分支，也不能直接发布可能新增事实的整段候选。

本授权已由该 94 调用批次消耗。任何后续真实 Provider 运行都需新的干净提交、精确冻结、独立账本和明确授权；正式默认与外部 Git 仍各自单独授权。
