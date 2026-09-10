# 回复内容优化实施记录

日期：2026-09-08｜分支：`codex/answer-content-optimization`｜实施基线：`85f62794e24cfa95a864293d159e0208c8615a4b`｜状态：CP0—CP6 本地实现完成，AC40 待独立真实 Provider 授权

本记录替代先前“第一阶段”记录。完整逐项状态见 [验收矩阵](../superpowers/validation/2026-09-08-answer-content-acceptance.md)，此前指出的遗漏及其关闭证据见 [差距关闭审计](2026-09-08-answer-content-implementation-gap-audit.md)。

## 1. 分支与工作区

- 独立 worktree：`D:\Project\Daily\data-agent\.worktrees\answer-content-optimization`
- 独立分支：`codex/answer-content-optimization`
- 基线：`85f62794e24cfa95a864293d159e0208c8615a4b`
- 原工作树 `D:\Project\Daily\data-agent` 的 dirty/untracked 内容未被搬入、清理或覆盖。
- 本任务没有合并回原分支、推送、部署或调用真实 Provider。

## 2. 实际实现

### CP1：发布快照与公开回复闭环

- `loop.py` 在质量、确认与发布检查之前只保存带 `publication_rejected` 的内部候选；公开投影不返回它们。
- 最终正文通过 `_persist_accepted_answer` 先创建来源说明 artifact、提交 publication packet、写入精确绑定并保存 session，再发正式流式文本。
- 发布绑定由 snapshot digest 与 answer hash 生成；相同正文幂等复用，正文修订递增 `content_revision` 并记录 `supersedes_packet_id`。
- artifact 写失败不提交 packet；session 保存失败回滚本次公开消息和 packet，并返回明确未完成状态。
- `public_messages.py` 保留 `publication_packet_id`、`publication_snapshot_digest`、`answer_sha256`、`publication_artifact_path`，形成回复级绑定。
- `report.py` 只为对应回复附加其精确来源说明；包已轮换时可按同会话绑定 artifact 恢复，不把最新包错误附到历史回复。

### CP2：事实组、详情恢复与压缩

- `publication_synthesis.py` 使用 `publication_synthesis.v3`，提取稳定的完整 FactGroup，记录 source/scope/fields/units/detail_ref/evidence status 与扫描统计。
- 工具执行在 `tool_outputs/..._detail.json` 持久化完整结构结果及 SHA-256；发布 prompt 只选业务优先的完整组，不在组内截断数字或单位。
- 多来源预算按来源公平分配；明确全部来源时保留每个来源，超预算组进入完整 `omitted_groups` 清单。
- 超深、超长列表和 stdout 扫描上限均披露未扫描数量或 unknown；必要大组变为 `detail_required` stub。
- `read_publication_detail` 只读取当前 session 的 `tool_outputs/*.json`，校验规范化路径和字节哈希；缺失、越界或不匹配失败关闭。
- `compact.py` 在压缩附录中保留 publication packet/snapshot/artifact 和 detail_ref，不覆盖原始详情。

### CP3：需求生命周期与正文覆盖

- `analysis_state.py` 持久化 `answer_requirements` 与 `requirement_revision`；`context.py` 记录当轮 requirement IDs/revision。
- `update_requirement_lifecycle` 保存用户原句、来源引用、撤回和窗口替换关系；状态变化可追溯。
- 最终模型可在正文末尾给出唯一 `answer-bindings.v1` fenced block；解析器限制位置、数量、大小、schema 和当前 snapshot digest。
- 宿主核对 requirement/fact/derived refs 和正文定位；损坏、重复、旧包或未知引用不受信，协议块在公开正文、刷新和导出前移除。
- 覆盖状态区分 `answered`、`not_computed`、`evidence_insufficient` 与未评估语义；缺口不再统一写成数据不足。

### CP4：类型化量值与派生计算

- `evidence_input.py` 接受向后兼容的 `measurements` 和 `derived_measurements`。
- `evidence_contracts.py` 只用 `Decimal` 重算 sum、difference、product、ratio、percent_change、percentage_point_change，不执行表达式字符串。
- 校验有限数、元数、零/负基数、scope、source/version、单位、舍入和 scenario；跨版本、跨币种与无标签情景失败关闭。
- 正文数字校验绑定已验证派生量值，区分百分比与百分点及“万”缩放；日期、版本号、编号和明确纠错引文不会被当成新业务运算。
- coverage、numeric、scope 问题一次合并进入现有 publication recovery，不增加模型审核调用或额外重试额度。

### CP5：内容深度、Markdown 与图表

- 普通分析默认深度为 standard，显式简短仍保持 terse；章节由问题与事实决定，不受固定 2—4 节限制。
- `app.js` 只规范化已识别的全角 `［［chart：...］］`，并按当前 session 查找唯一 artifact；缺失、歧义和异会话引用不嵌入。
- 内嵌图表带标题、延迟加载和新标签页备用链接；全角引用经规范化后不会再重复出现在“补充图表”。
- Markdown 表格进入可聚焦的横向滚动容器。项目本次按用户确认只验收电脑端 UI；没有加入移动端专项样式。
- 数据型 Mermaid 不作为图表失败的伪造回退；图失败时沿用可信表或具体缺口。

## 3. 修改文件面

| 文件 | 作用 |
|---|---|
| `src/data_agent/agent/loop.py` | 候选隔离、终局绑定、先持久化后公开、失败回滚、需求生命周期接入 |
| `src/data_agent/agent/publication_synthesis.py` | v3 packet、FactGroup/detail_ref、需求与数字校验、收据渲染 |
| `src/data_agent/agent/analysis_state.py` | 需求生命周期持久化与旧状态兼容 |
| `src/data_agent/agent/context.py` | 当轮 requirement refs/revision |
| `src/data_agent/agent/compact.py` | publication/detail 引用跨压缩保留 |
| `src/data_agent/agent/evidence_contracts.py` | 类型化派生量值宿主重算与来源/单位约束 |
| `src/data_agent/tools/evidence_input.py` | evidence schema 扩展 |
| `src/data_agent/tools/analysis_flow.py` | derived measurements 进入统一验证 |
| `src/data_agent/session/public_messages.py` | 公开回复精确 publication binding 投影 |
| `src/data_agent/tools/report.py` | 回复级来源附录和同会话 artifact 恢复 |
| `src/data_agent/web/static/js/app.js` | chart wrapper、会话隔离、表格/图表桌面呈现 |
| `src/data_agent/web/static/css/app.css` | 桌面表格容器和图表备用链接样式 |
| `scripts/testing/run_p7_browser_rehearsal.py` | Provider 禁用的 B07 表格/公式/真实图表浏览器场景 |
| `tests/test_answer_*.py`、`tests/test_publication_synthesis.py` | AC02—AC38 定向正反例 |
| `tests/fixtures/answer_content/manifest.json` | 固定小中大预算 fixture |

`prompts.py` 和 `synthesis_policy.py` 的深度/表达修订来自本分支先前提交，并继续由完整回归覆盖。

## 4. 验证证据

### E1/E2 定向回归

```powershell
$env:PYTHONPATH='src'
..\..\.venv\Scripts\python.exe -m pytest -q `
  tests\test_answer_content_coverage.py `
  tests\test_answer_numeric_consistency.py `
  tests\test_answer_presentation_contract.py `
  tests\test_answer_publication_contract.py `
  tests\test_publication_synthesis.py `
  tests\test_export_conversation.py `
  tests\test_output_rendering_contracts.py `
  tests\test_analysis_quality_guard_scope.py `
  tests\test_execution_control.py
```

结果：`129 passed in 16.57s`。

### E2 完整离线

```powershell
..\..\.venv\Scripts\python.exe scripts\testing\run_regression.py full-offline --run-dir tmp\r6
```

结果：`2585 passed, 1 skipped, 16 warnings in 170.91s`，退出码 0。唯一 skip 是需要 `GOLDEN_LIVE_SMOKE=1` 的真实 Provider agent smoke。脚本禁用 Provider 网络并使用隔离 workspace/sessions；这项证据不代表真实模型或生产环境。

### E3 电脑端真实浏览器与脚本模型

浏览器连接普通 Flask 页面，走真实 SSE、AgentLoop、工具、artifact、session 保存、刷新和导出；仅模型传输由确定性脚本替代，运行时设置 `DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED=0`。

- B07，会话 `944d1f86cbce`：1440×900 下 Markdown 表格、KaTeX 公式、单个真实 `create_chart` Plotly iframe 和备用打开链接可见；刷新后保持；`documentElement.scrollWidth=1440`、`innerWidth=1440`，无整页横向溢出；无重复“补充图表”。
- B03，会话 `b2306f8ccffb`：六来源回答刷新后保留；实际打开的 MD 导出包含 `pub_adad40726489`、对应 snapshot digest、answer hash 和 `src_1`—`src_6`；packet 的每个来源均保留 7 个完整 FactGroup。
- 两个运行目录的 `runtime.jsonl` 中 `forbidden_provider_transport=0`，且没有真实 Provider 调用。

E3 证明桌面页面与编排路径，不证明自然模型会稳定产出更丰富的内容。自然模型对照必须由 AC40 的独立授权批次完成。

## 5. 合并与剩余边界

CP0—CP6 的本地实现和证据已闭合。AC40 随后已在 `main@1516337`、冻结 SHA-256 `c0bd787f64e2c7b8f05b2026db0a73ffa1336c9cb3b6d6f44ff2caca16a6c46` 的真实浏览器＋真实 Provider 批次执行；账本为 77 started / 77 dispatched / 0 failed，但 M03 的发布收敛/Workbench、M05 的金额单位漂移和 M06 的原始图表标记使 AC40 未通过。没有把历史授权、旧真实会话、离线结果或局部通过项转记为 AC40 通过；修复后须新冻结、新授权并完整复验。

合并时应把本分支提交并入届时目标分支，按函数块解决 `loop.py` 等并行冲突，再运行本记录中的定向与完整离线命令。不要用整文件覆盖主分支后续改动。Git 忽略的 `tmp/r6`、浏览器运行目录和 Plotly vendor 测试副本不进入提交。
