# 回复内容优化实施差距关闭审计

日期：2026-09-08｜审计对象：`codex/answer-content-optimization`｜结论：先前自检列出的代码与文件面缺口已在独立分支补齐；AC40 仍是需另行授权的真实 Provider 外部验收。

## 1. 更正后的结论

前一版自检结论“第一阶段、整体未完成”在当时是正确的，也说明了第一次执行确实没有按原 CP0—CP6 完成。用户要求继续后，本分支没有把计划缩小为一个切片，而是逐项补齐当时列出的 `analysis_state.py`、`report.py`、`compact.py`、`context.py`、`evidence_input.py`、`app.js` 以及关联运行时、契约、测试和文档。

现在可以确认：CP0—CP6 的本地代码、E1/E2 自动化与 E3 电脑端脚本模型浏览器证据已完成。不能确认：未经授权的真实 Provider 内容质量、部署和生产行为。AC40 保留 `not_run_authorization_required`，不影响代码分支进入合并评审，但不能被写成真实效果通过。

## 2. 计划文件面与实际修改对应

| 计划修改面 | 是否修改 | 实际闭环 |
|---|---|---|
| `loop.py` | 是 | 最终快照重建、拒绝候选隔离、binding/revision/supersedes、artifact 与 session 写入失败回滚、先持久化后流式公开 |
| `publication_synthesis.py` | 是 | v3 packet、FactGroup、detail_ref、扫描/省略、需求生命周期、answer-bindings、派生数字显示校验、一次返回全部问题 |
| `analysis_state.py` | 是 | `answer_requirements`、`requirement_revision` 持久化和旧状态兼容 |
| `report.py` | 是 | 按具体回复的 packet/snapshot/answer hash 附来源；同会话 artifact 老包恢复；不再全局附最新包 |
| 工具结果/收据适配 | 是 | 每个工具结果写完整 detail JSON 与 byte hash，并把 FactGroup/scan/ref 放入收据 |
| `compact.py` | 是 | 保留 publication packet/snapshot/artifact 与 `tool_outputs` detail refs，需求状态由 analysis state 独立持久化 |
| `context.py` | 是 | 当轮 requirement IDs/revision 与既有 receipt IDs 同时进入终局构建 |
| 计划/证据契约 | 是 | requirements→FactGroup/measurement→answer binding 形成稳定引用链 |
| `evidence_input.py` | 是 | 向后兼容 measurements，并新增 derived measurements 的 operation/operands/result/unit/scale/rounding/scope/scenario |
| `evidence_contracts.py` | 是 | Decimal 重算与有限数、元数、零/负基数、单位、来源/版本、scope 和情景约束 |
| `prompts.py` / `synthesis_policy.py` | 是，来自先前提交 | 去除固定 2—4 节、普通分析 standard、明确简短仍 terse、内部 binding 协议由 publication prompt 注入 |
| `app.js` / `app.css` | 是 | 全角 chart wrapper、当前会话唯一匹配、歧义/缺失失败提示、去重、iframe title/loading/open link、可聚焦宽表 |
| tests/fixtures | 是 | 四个专项测试文件、publication 扩展、固定小中大 manifest、B07 桌面渲染场景 |

这也回答了用户此前点名的四个文件：

- `compact.py` 不能只依赖旧内容寻址能力，所以现在显式保存发布和详情引用。
- `context.py` 不能只使用 `turn_receipt_ids`，所以现在携带当轮需求 ID 与 revision。
- `evidence_input.py` 是原 CP4 的必要契约面，现在已经提供类型化派生量值输入。
- `analysis_state.py` 虽然旧代码能保存任意 packet dict，但需求撤回/替换必须有独立持久化字段，因此也已修改。

## 3. 前版十项代码风险关闭情况

| 原风险 | 关闭方式 | 验证 |
|---|---|---|
| FactGroup 被二次切开 | packet 只选择/省略完整 group，prompt 超限也按整组移除或生成 detail_required stub | AC10、AC12 |
| 扫描上限不闭合 | 记录 `scan_incomplete`、omitted/unknown count、detail_ref 与 hash | AC12、AC13 |
| 全部来源突破预算或后来源饿死 | per-source 公平预算、业务优先级、完整 omitted groups | B03 六来源每个 7 组 |
| 需求覆盖是窄临时规则 | 持久化生命周期、原文引用、撤回/替换、宿主验证 answer-bindings；不确定自由文本标 unassessed | AC16—AC21 |
| 数值检查没有证据绑定 | typed measurements/derived refs、Decimal 重算、source/version/unit/scope/scenario 校验 | AC22—AC27 |
| 只返回第一个修订问题 | coverage/numeric/scope issues 合并返回，共用一次恢复 | AC29 |
| artifact 写失败被吞 | 写入成功后才提交 packet；失败抛出并返回未完成 | AC05 |
| 回复与导出未一一绑定 | 消息保存四个 binding 字段，report 精确选择 packet 或同会话 artifact | AC04、AC36、B03 |
| 质量门拒绝候选先进入公开历史 | 拒绝候选标记为内部 rejected，公开投影过滤；成功正文持久化后才发 delta | AC06 |
| digest 契约不完整 | 纳入 session/turn、requirements/revision、完整 evidence measurements、dataset contract、extractor/policy、content revision 与 supersedes | AC02—AC04 |

浏览器演练还发现全角 chart ref 虽能内嵌，但原始 ref 没有用于 supplemental 去重，会把同一图显示两次。`supplementalArtifacts` 现在先规范化 ref 再查重；B07 刷新后只有一个 inline chart 且没有“补充图表”重复项。

## 4. CP0—CP6 自检

| 阶段 | 当前状态 | 退出条件核对 |
|---|---|---|
| CP0 | completed_local | 独立分支/基线/fixture/AC 映射/Provider 零调用边界齐全 |
| CP1 | completed_local | AC01—AC07 行为由新定向与既有 P08 回归覆盖；同步/流式共同使用终局持久化入口 |
| CP2 | completed_local | AC08—AC15 的事实完整、可恢复详情、扫描省略和方法数值保留已覆盖 |
| CP3 | completed_local | AC16—AC21 的需求、状态、撤回替换、协议解析与宿主绑定已覆盖 |
| CP4 | completed_local | AC22—AC29 的派生运算、单位/来源/版本边界和合并问题已覆盖 |
| CP5 | completed_local | AC30—AC35 的深度、偏好、图表安全与电脑端真实页面已覆盖 |
| CP6 | completed_local | AC36—AC39 的迁移/绑定/预算/全离线与浏览器证据齐全 |
| AC40 | not_run_authorization_required | 需要新的真实 Provider 冻结和明确授权，本次没有调用 |

## 5. 验证结果与证据边界

- E1/E2 定向：`129 passed in 16.57s`。
- E2 full-offline：`2585 passed, 1 skipped, 16 warnings in 170.91s`，退出码 0，目录 `tmp/r6`。
- E3 B07：会话 `944d1f86cbce`，1440×900 的表格、KaTeX、Plotly、备用链接、刷新与无整页溢出通过。
- E3 B03：会话 `b2306f8ccffb`，刷新与实际 MD 导出通过；导出绑定 `pub_adad40726489` 及其 snapshot/answer hash，六个来源均存在。
- 两个 E3 运行轨迹均没有 `forbidden_provider_transport` 事件；Provider 网络保持禁用。

唯一 full-offline skip 是需要 `GOLDEN_LIVE_SMOKE=1` 的真实 Provider agent smoke。警告来自既有 SciPy/statsmodels 数值边界和 pytest JUnit 属性兼容，不是本次新增失败。

这些证据证明当前 checkout 的本地实现和电脑端编排，不证明真实模型一定按提示生成同样丰富的自然语言，也不证明部署/生产通过。历史真实会话只作为诊断输入，没有在本任务中重跑或改写。

## 6. 合并前不再需要重复确认的事项

代码范围、文件面和本地验证已经完成，不需要再为 `compact/context/evidence_input/report/app.js` 是否遗漏做第二轮确认。后续合并仍需执行常规的目标分支冲突核对，特别是 `loop.py`、`publication_synthesis.py` 与并行 P08/确认策略改动，并在合并结果上重跑定向与 full-offline。

仍需单独决定的只有外部动作：真实 Provider AC40、推送、实际合并、部署。它们不能由本地提交或本报告代替授权。
