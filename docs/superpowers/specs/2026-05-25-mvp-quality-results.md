# MVP Quality Validation Results

## Fixture Set

- Fast fixtures:
  - `游戏B留存.xlsx`
  - `游戏A内购数据.xlsx`
  - `省钱卡订单_20260507.xlsx`
- Slow fixture:
  - `省钱卡用户最近流水_20260511.xlsx`

## Validation Summary

This document records validation results for the knowledge and memory MVP.

## Accepted Constraints

- Candidate extraction remains rule-first.
- Candidate memories do not enter retrieval before confirmation.
- Evidence retrieval requires an explicit evidence character budget.
- Large-file checks stay out of the default fast unit suite.

## Browser Smoke Validation

- Date: 2026-05-25
- Target URL: `http://127.0.0.1:5001`
- Passed checks:
  - Management center opens from the sidebar and shows the `返回应用` control.
  - Memory page shows `提取当前会话记忆`.
  - Candidate memory cards show summary, status, review state, extraction reason, source count, confidence, and review actions.
  - Memory source lookup with a missing evidence id shows the empty state instead of stale source content.
  - Memory edit drawer shows the content, summary, type, confidence, domain, project, reason, evidence ids, review flag, and review note fields.
  - Skill page renders with search and add controls.
  - MCP server page renders with search and add-server controls.
- Issues found: None.
- Fixes applied: None.
- Notes:
  - Browser validation seeded temporary local memory candidates through the management API; these are runtime data only and are not committed.
  - Screenshot captured for local QA at `workspace/mvp-management-memory-drawer.png`.
