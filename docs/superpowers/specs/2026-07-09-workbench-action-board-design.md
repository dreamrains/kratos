# Workbench 行动看板（结论先行主视图）设计

Date: 2026-07-09

## 1. 目的与范围

为 Workbench 增设一个**结论先行的主视图——行动看板**，把分析结果组织成用户能直接交付
他人的结构：**已确认 / 仍不确定 / 建议下一步 / 为什么可以信任**，并可展开完整答案。
现有四象限诊断区（数据理解 / 文件关系 / 建议分析方向 / 结论覆盖）降级为下钻次级区。

**动机**：实测（见 `golden-answer-quality-harness` 结论）表明 agent 最终答案本身已有深度，
但当前 Workbench 是诊断/清单式（"有什么数据/关系/方向"），没有把**结论与可交付结构**
推到主位。用户目标是"能反馈不存在问题的分析结果 + 帮助拓展分析方向"——行动看板正好
服务这一目标。设计素材来自 `.superpowers/brainstorm/stage3c0b-workbench/content/
workbench-value-layouts.html`（结论先行/问题地图/行动看板三套，本设计采用行动看板）。

### 做什么

- 后端读模型：`workbench_view.py` 新增 `action_board` 段，纯 state 派生，无运行期改动。
- API：trust 端点在 `workbench` 下附加 `action_board` + `full_answer`（从已保存对话取末条
  assistant，不改运行期）。
- 前端：行动看板置顶为主视图；4 象限降为下钻；"查看完整分析"展开 `full_answer`。

### 不做什么（非目标）

- 不改运行期（loop/synthesis_policy/工具行为）。
- 不动 4 象限实现（保留诊断价值，仅降级为下钻）。
- 不做移动端（UX review 已知缺口，单独设计）。
- 不加总评分、不阻塞（与质量体系一致）。
- 不碰黄金测量校准（独立工作）。

## 2. 关键设计决策（已确认）

1. **骨架**：行动看板（已确认/仍不确定/建议下一步/为什么可以信任），非结论先行或问题地图。
2. **内容源**：主区用 state 派生的**结构化结论卡片**；底部"查看完整分析"展开 agent 答案原文。
3. **结构**：方案 A——行动看板置顶为主视图，4 象限降为下钻次级区（不替换、不并列）。
4. **full_answer 来源**：trust 端点读已保存对话（conversation）取末条 assistant 消息，不存、
   不改 state 运行期。

## 3. action_board 数据模型（纯 state 派生）

新增 `build_action_board(state) -> dict`。派生自现有 state 字段：
`evidence_records`（`claim`/`confidence`/`limitations`/`dataset`）、`verification_reports`
（末条紧凑引用：`overall_status`/`claim_count`/`failed_count`/`downgraded_count`）、
`route_capabilities`（`executable`/`exploratory`）、data brief
（`unanswerable_questions`/`needed_confirmations`/`datasets`）。

> 说明：state 上的 `verification_reports` 是**紧凑引用**（报告级 status + 计数），
> 不含逐条 claim 的验证状态。因此"已确认/仍不确定"按 **evidence 的 confidence** 派生，
> 报告级验证状态进入 `trust_basis`。

```python
action_board = {
  "confirmed": [        # 已确认：中/高置信度的结论
    {"claim": str, "confidence": "high|medium", "dataset": str, "summary": str}
    # 来自 evidence_records：confidence ∈ {high, medium} 且 claim 非空。≤6 条，按 confidence 降序。
  ],
  "uncertain": [        # 仍不确定：低置信结论 + 局限 + 数据缺口
    {"label": str, "reason": "low_confidence|limitation|data_gap", "detail": str}
    # 来源：evidence confidence ∈ {low, speculative}（low_confidence）；
    #       evidence limitations 去重平铺（limitation）；
    #       data brief unanswerable_questions（data_gap）。≤6 条。
  ],
  "next_steps": [       # 建议下一步：分析方向 + 待确认
    {"direction": str, "reason": str, "kind": "route|confirmation"}
    # 来源：route_capabilities executable+exploratory（route）；
    #       data brief needed_confirmations（confirmation）。≤6 条，kind=route 优先。
  ],
  "trust_basis": {      # 为什么可以信任
    "evidence_count": int,
    "verified_claim_count": int,    # verification claim_count
    "failed_count": int,
    "downgraded_count": int,
    "verification_status": "pass|pass_with_downgrades|fail|not_run",
    "datasets_used": [str, ...],    # data brief datasets 名称
  },
}
```

**约束**：无总评分；各列表有上限（≤6）防止噪声；空列表合法（如分析未开始时全空，
trust_basis 计数为 0、status=`not_run`）。

## 4. API 契约

`build_trust_view(state, session_id)` 返回的 `workbench` 下新增两段（与 `multifile_analysis`、
`details` 平级）：

```json
{
  "status": "...", "session_id": "...", "updated_at": "...",
  "workbench": {
    "action_board": { ... },          // 新增，置顶主视图
    "full_answer": "..." | null,       // 新增，对话末条 assistant 文本；无则 null
    "multifile_analysis": { "data_understanding":..., "relationships":..., "analysis_directions":..., "answer_coverage":... },
    "details": { "scope":..., "confirmation":..., "verification":... }
  }
}
```

- `action_board` 由 `workbench_view.build_action_board(state)` 产出，在 `build_workbench_view`
  内组装进结果（与现有 4 象限并存）。
- `full_answer` 由 trust 端点（`sessions.py:get_session_trust_view`）从已保存对话
  （`sessions/<id>/conversation.jsonl` 或 `.json`）取**末条 assistant** 消息文本，注入
  `workbench.full_answer`。读取失败/无内容 → `null`。**不写入 state、不改运行期。**

## 5. 前端

- `web/templates/index.html` + `web/static/js/app.js` + `web/static/css/app.css`：
  - 置顶渲染 `action_board` 四块（已确认 / 仍不确定 / 建议下一步 / 为什么可以信任），
    每块为卡片列表；空块显示占位（如"暂无"）。
  - 行动看板下方"查看完整分析"可展开/收起 `full_answer`（渲染为 markdown）。
  - 现有 4 象限移入"详情 / 下钻"次级区（如折叠区或次级 tab），不再作为主视图。
  - 沿用现有 Tailwind/Alpine 风格与中文文案；失败/空态有清晰占位。
- 选择方向卡片**仅展示**，不自动提交 chat（与既有"route suggestions display-only"一致）。

## 6. 测试

- **后端确定性**（pytest）：fixture state（含 evidence 各置信度 + verification 报告 + route
  capabilities + data brief）→ 断言：
  - `confirmed` 只含 confidence ∈ {high, medium} 的 claim，按 confidence 降序、≤6；
  - `uncertain` 含 low/speculative 结论 + limitations + unanswerable；
  - `next_steps` 含 route + confirmation；
  - `trust_basis` 计数与 verification 报告一致、status 正确；
  - 空 state → 全空列表 + status=`not_run` + 计数 0。
- **API**：trust 端点返回 `workbench.action_board` 与 `workbench.full_answer`（有对话时为字符串、
  无对话时为 null）。
- **前端**：现有 `test_web_workbench_replacement.py` 等 + 新增行动看板渲染契约测试（四块存在、
  空态占位、full_answer 展开）。

## 7. 复用与边界

- 复用：`build_workbench_view`（扩展，不重写）、`build_route_capabilities`、
  `build_user_data_brief`、`_flatten_limitations`、`_text/_int_value` 工具。
- 新增：`workbench_view.build_action_board(state)`；trust 端点读取对话末条 assistant 的辅助函数。
- 边界：measurement-only 不适用（这是用户面 UI 读模型）；不进入 agent 运行期决策。

## 8. 验收门

- 后端：`build_action_board` 在 fixture state 上派生正确（确定性测试全绿）。
- API：`/sessions/<id>/trust` 返回 `action_board` + `full_answer`。
- 前端：行动看板四块置顶渲染、空态正常、full_answer 可展开、4 象限降为下钻；现有 web workbench
  测试不回归。
- 非越界：未修改 `loop.py`/`synthesis_policy.py`/运行期（`rg` 自检）。
