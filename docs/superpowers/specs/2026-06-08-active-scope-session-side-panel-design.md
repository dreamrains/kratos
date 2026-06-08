# Active Scope And Session Side Panel Design

## Purpose

The current Trust Inspector makes analysis state visible, but it still behaves mostly like a session-wide status panel. That is not enough for real multi-turn analysis.

Users may:

- upload a file, inspect it, then upload another file
- switch from data understanding to cohort, funnel, or trend analysis
- ask pure consulting questions without uploading data
- return to earlier datasets or artifacts later in the same session

The side panel must therefore distinguish between two layers:

- **Session memory:** everything the session has loaded, generated, verified, or exported.
- **Active analysis scope:** the dataset, route, goal, and evidence that matter for the user's current task.

The key product rule is:

> Preserve cumulative session state, but make the side panel default to the active analysis scope.

## Problems To Solve

### 1. Duplicate Recommendation Channels

The assistant can recommend analysis directions in chat, while the side panel also shows recommended routes. When these lists differ, users read that as inconsistency.

The intended difference is valid:

- chat can explain choices in natural language
- side panel should show routes supported or unsupported by the current data contract

But the product currently does not make that distinction clear.

### 2. Session-Wide State Can Pollute Current Work

Current trust refs are mostly session-level lists:

- `dataset_contracts`
- `preview_digests`
- `cleaning_logs`
- `route_proposals`
- `hypothesis_sets`
- `verification_reports`

If a user uploads new data, the system should not delete old refs. But the side panel should not flatten old and new refs into one undifferentiated view.

### 3. Pure Consulting Should Not Be Forced Into Data Workflow UI

If the user asks about methodology, metric design, or business framing without loading data, the side panel should not show a large stack of empty data-analysis cards.

### 4. Output And Export Features Must Remain First-Class

The side panel now competes with existing session functions such as export, reports, charts, and artifacts. New analysis-assist UI must not hide or weaken those capabilities.

## Product Shape

Rename the product concept from a single-purpose Trust Inspector to a broader **Session Side Panel**.

The side panel has tabs:

1. **当前分析**
2. **数据与历史**
3. **产出与导出**

Trust Inspector content lives mostly inside **当前分析**, but the side panel is no longer only a trust panel.

## Active Analysis Scope

Introduce an active scope model.

Suggested compact shape:

```json
{
  "active_dataset": "省钱卡订单",
  "active_route": "cohort",
  "active_goal": "分析省钱卡订单的用户留存",
  "active_mode": "analysis",
  "active_turn_id": "optional-turn-id",
  "related_ref_ids": {
    "dataset_contracts": ["duc_省钱卡订单_a79b9e9c"],
    "route_proposals": ["route_省钱卡订单_82ba0ac7"],
    "hypothesis_sets": ["hypotheses_item_cohort"],
    "verification_reports": ["verify_verify_ac0d83020"]
  },
  "updated_at": "2026-06-08 14:30:00"
}
```

Allowed `active_mode` values:

- `consulting`: no loaded data is required; user is discussing methods, metrics, or analysis plans.
- `data_loaded`: data exists, but the current turn has not selected a specific route.
- `analysis`: a dataset and route are active.
- `artifact_review`: user is looking at generated reports, charts, exports, or previous outputs.

## Active Scope Update Rules

### File Upload Or `load_data`

When a new dataset is loaded:

- set `active_dataset` to the new dataset
- clear `active_route` unless the user explicitly requested a route
- set `active_mode` to `data_loaded`
- keep old datasets and refs in session memory
- side panel defaults to the new dataset's data status and supported routes

If the new dataset can be linked to existing datasets, surface that as a cross-dataset suggestion, not as an automatic merge.

### User Selects Or Requests A Route

When the user clicks a route or asks for a route in chat:

- set `active_route`
- set `active_goal`
- set `active_mode` to `analysis`
- filter current analysis content to matching dataset and route where possible

### Pure Consulting

When the user asks a consulting or methodology question without data dependency:

- set `active_mode` to `consulting`
- do not show empty route, risk, hypothesis, or verification cards as if they are missing work
- show a compact guidance state, such as:
  - 当前是咨询模式
  - 如需数据验证，请上传包含哪些字段的数据

### Artifact Or Export Activity

When the user views, creates, or exports artifacts:

- keep active analysis scope unchanged unless the artifact clearly belongs to a different dataset or route
- make **产出与导出** tab available and visible
- do not bury export controls under analysis sections

## Trust View Filtering

The backend trust view should support active-scope filtering.

Default behavior:

- return current active-scope summaries first
- include session-level counts for all known datasets, routes, risks, hypotheses, and artifacts
- do not discard historical refs

Suggested response additions:

```json
{
  "active_scope": {
    "active_dataset": "省钱卡订单",
    "active_route": "cohort",
    "active_mode": "analysis",
    "active_goal": "分析省钱卡订单的用户留存"
  },
  "scope_counts": {
    "datasets": 2,
    "routes": 5,
    "risks": 3,
    "hypothesis_sets": 2,
    "artifacts": 4
  }
}
```

Filtering rules:

- `datasets`: show active dataset first; show other datasets only in **数据与历史**.
- `routes`: show routes for active dataset in **当前分析**; show all route history in **数据与历史**.
- `risks`: default to active dataset; include global/session risks only if they block current work.
- `hypotheses`: default to active dataset and active route.
- `verification`: show the report whose evidence signature or route best matches active scope; otherwise show latest with an "可能来自上一轮分析" marker.
- `artifacts`: keep in **产出与导出**, grouped by report/chart/export type and associated dataset when available.

## Recommendation Source Unification

The system should have one structured source for route capability:

- supported routes from `route_proposals`
- unsupported routes from `dataset_contracts.unsupported_analyses`
- route limitations from route artifacts
- cleaning risks from cleaning logs

Chat can still explain recommendations, but it should not invent a separate route list that conflicts with the side panel.

Recommended framing:

- Chat: "当前数据支持 2 个分析方向；另有 1 个方向需要补充数据。"
- Side panel: shows the structured list:
  - 可分析: cohort, funnel
  - 暂不支持: user_level_retention, reason

This avoids the perception that chat and panel disagree.

## Tab Information Architecture

### Tab 1: 当前分析

Purpose:

- answer "What is safe or useful to do now?"

Content:

- active scope summary
- active dataset readiness
- supported and unsupported analysis paths for active dataset
- risks that affect the active scope
- active hypothesis set summary
- matching verification status

Constraints:

- do not show all historical datasets by default
- do not duplicate long chat explanations
- route clicks fill the chat input but do not auto-submit

### Tab 2: 数据与历史

Purpose:

- answer "What has this session seen or done before?"

Content:

- loaded datasets
- dataset shapes and quality status
- historical analysis routes
- previous active scopes or goals when available
- option to switch active dataset or route

Constraints:

- switching scope should be explicit
- do not auto-run analysis when switching
- old risks remain visible here, but should not pollute current analysis unless selected

### Tab 3: 产出与导出

Purpose:

- preserve current export and artifact management workflows.

Content:

- export conversation controls
- reports
- charts
- generated artifacts
- downloads or open actions

Constraints:

- new Trust Inspector functionality must not remove, hide, or weaken export/session-output features
- this tab should remain useful even when no active dataset is selected
- avoid explanatory clutter; clear labels and empty states are enough

## Help And Localization

All side-panel labels, empty states, and new status labels should be Chinese-first.

Use lightweight help popovers instead of full modal dialogs by default.

Help trigger:

- a small `?` icon near section headings
- click or hover opens a short explanation
- no blocking modal unless content is long or has actions

Recommended help content structure:

1. 这是什么
2. 为什么重要
3. 你可以怎么做

Examples:

### 可分析路径

这表示当前数据结构支持的分析方向。它基于字段、数据粒度、质量风险判断，不等同于聊天中的泛建议。点击后只会填入输入框，你仍可以编辑。

### 风险边界

这表示当前分析可能受到哪些数据质量、清洗决策或字段缺失影响。如果这里出现阻塞项，结论应谨慎或需要先补充数据。

### 假设检验

系统会为一次分析保留主要解释、替代解释和基准解释。这样可以避免只验证一个看起来合理的结论。证据不足的假设不会被当作结论。

### 产出与导出

这里集中管理本会话生成的报告、图表、文件和会话导出。它与当前分析状态相关，但不应被分析建议或风险提示挤掉。

## No-Data And Consulting Modes

When no data is loaded:

- side panel should not render full analysis tabs by default
- show consulting mode or a compact prompt:
  - 当前没有加载数据
  - 可以继续讨论分析方法
  - 如需数据验证，请上传文件

When data is not required:

- do not manufacture risks or hypotheses
- do not imply verification is missing
- show data requirements only if the user asks how to validate with data

## Success Criteria

This redesign is successful when:

- uploading a second dataset makes it active without deleting the first dataset
- side panel default content follows active dataset and route
- old routes, risks, hypotheses, and artifacts remain accessible in history or output tabs
- chat recommendations and side-panel route lists use the same structured source
- pure consulting conversations do not show noisy empty analysis cards
- export, reports, charts, and artifacts remain first-class in **产出与导出**
- new side-panel text is Chinese-first
- section-level help explains value without interrupting normal use

## Non-Goals

This phase should not:

- build a full project-wide BI dashboard
- add new statistical methods
- force users through a wizard before chatting
- delete old session state automatically
- make route click auto-run analysis
- replace chat explanations with UI-only guidance

## Implementation Order

Recommended order:

1. Add active scope state and update rules.
2. Update trust view to expose `active_scope` and `scope_counts`.
3. Filter current-analysis data by active scope.
4. Unify route recommendation source for chat and side panel.
5. Refactor side panel into tabs: 当前分析, 数据与历史, 产出与导出.
6. Preserve and relocate export/artifact controls into 产出与导出.
7. Add Chinese labels and status text.
8. Add lightweight help popovers.
9. Add tests for multi-upload, consulting mode, tab content, and export preservation.
