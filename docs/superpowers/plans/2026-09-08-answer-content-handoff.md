# 回复内容优化：合并交接

日期：2026-09-09｜状态：CP0—CP6 已合入本地 `main@f8ee717`；合并后矩阵与 AC40 仍待执行

关联：[总计划](2026-09-08-answer-content-optimization-plan.md)｜[开发设计](../specs/2026-09-08-answer-content-design.md)｜[表达规范](../specs/2026-09-08-answer-presentation-contract.md)｜[验收矩阵](../validation/2026-09-08-answer-content-acceptance.md)｜[实施记录](../../audit/2026-09-08-answer-content-implementation-record.md)｜[差距关闭审计](../../audit/2026-09-08-answer-content-implementation-gap-audit.md)。

## 1. 分支与交付边界

- 工作树：`D:\Project\Daily\data-agent\.worktrees\answer-content-optimization`
- 分支：`codex/answer-content-optimization`
- 基线：`85f62794e24cfa95a864293d159e0208c8615a4b`
- 原工作树保持原状；本分支没有包含其未提交并行改动。
- 已经由整合提交 `9e51b81` 合入本地 `main@f8ee717`；尚未 push、部署或调用真实 Provider。

本分支完成回复发布快照、事实组和详情恢复、需求到正文绑定、类型化派生数字校验、桌面端 Markdown/图表呈现、刷新和回复级导出绑定。移动端 UI 经用户确认不在本次范围。

## 2. 已完成合并的保留项

| 重叠面 | 本分支必须保留 | 目标分支必须保留 |
|---|---|---|
| `loop.py` 终局 | 拒绝候选不公开；packet/artifact/session 成功后才发正文；回复级 binding | P08 fallback、确认策略、工具消息配对与终态唯一性 |
| `publication_synthesis.py` | v3 packet、完整 FactGroup、公平预算、requirements/bindings/derived 校验 | 目标分支后续证据/假设范围约束 |
| `analysis_state.py` / `context.py` | requirement lifecycle/revision 的可选字段与旧状态兼容 | 目标分支新增状态字段和加载默认值 |
| `report.py` | 每条回复使用自己的 packet 或同会话 artifact | 目标分支现有导出格式与安全路径处理 |
| `app.js` | 全角 ref 定向修复、会话隔离、歧义失败、图表去重和 fallback | 目标分支后续 Workbench/SSE 投影修复 |
| evidence schema | derived measurements 的向后兼容 schema 与 Decimal 宿主重算 | 既有 EvidenceRecord 必填项和统计验证 |

合并结果树与整合提交 `9e51b81` 一致，并已核对表中不变量。后续修改仍应按函数块审查，尤其不能为了通过内容覆盖而放宽无依据预测、因果、零值解释或跨版本证据边界。

## 3. 合并后验证命令

先运行本专项定向集：

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe -m pytest -q `
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

再运行完整离线：

```powershell
.venv\Scripts\python.exe scripts\testing\run_regression.py full-offline
```

源分支证据为 `129 passed` 定向和 `2585 passed, 1 skipped, 16 warnings` full-offline；整合分支另有必要澄清定向 301 passed。合并前 full-offline 的唯一剩余失败是隔离夹具多复制清单外文件，用户已接受用于合并，但不能记为合并后 full-offline 全绿。

## 4. E3 复验入口

脚本浏览器启动必须显式让 Python 导入目标 checkout 的 `src`，避免 editable venv 指向其他工作树：

```powershell
$env:PYTHONPATH='src'
.venv\Scripts\python.exe scripts\testing\run_p7_browser_rehearsal.py `
  --port 5150 --run-dir tmp\answer-content-browser
```

- `【B03】请逐一列出全部来源`：检查刷新和实际 MD 导出中的 packet/snapshot/answer hash、六来源及省略说明。
- `【B07-PRESENTATION】请生成包含表格、公式与图表的分析展示`：检查 1440×900 电脑端表格、KaTeX、唯一内嵌 Plotly 图、备用链接、刷新和整页宽度。

运行器禁用 Provider，仅证明页面和编排。测试后停止服务；`tmp` 与忽略的 Plotly vendor 副本不提交。

## 5. 回退与兼容

旧会话缺少新字段时按默认值读取，旧正文不会被重写。新 packet 超过内存保留窗口后，绑定回复仍可从同会话来源说明 artifact 导出。若需回退代码，先停止写入新格式的服务，再按 CP1—CP5 的文件块回退；保留历史 session、artifact 和审计文件，不删除用户数据。

## 6. 未执行的外部门槛

AC40 需要新的零调用预检，冻结真实输入文件 hash、完整提示、模型、源码提交、进程身份和调用预算，再取得明确 Provider 授权。历史批次或未用额度不能继承。本地实现完成不等于 AC40、部署或生产通过。

本地合并已经完成。push 与部署仍须用户指定目标和时点后执行，本交接不自行触发这些外部动作。
