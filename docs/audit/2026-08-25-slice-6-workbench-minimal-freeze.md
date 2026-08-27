# Slice 6 Workbench 最小投影冻结收据（Provider 除外）

日期：2026-08-25

## 源码与边界

- 基线提交：`5c7caf69f9d4c3662281b9098de3640db198de93`。
- 当前受控源码摘要：`sha256:9209e368ffab6e31063974af412afad8b486ba09fbfae1af001cd953988ee40e`（321 条）。
- 未调用真实 Provider；未触碰、暂存或提交 `artifacts/`、`tmp/`。

## 交付

1. Workbench 后端投影收敛为唯一 `verified_conclusions` 字段；仅当前 evidence fingerprint 匹配的高/中置信证据可投影，过期 verification 不得复活旧结论。
2. 删除 Workbench 的“仍不确定”“建议下一步”“可信度摘要”“分析范围”“完整叙述”“数据理解”“数据关系”和确认 banner；它们不再有 Workbench API schema、前端状态或隐藏入口。
3. 保留主对话及其审计/执行内部契约；保留产出物详情链接、HTML 和 Markdown 导出。

## 真实本地 Web 验证

- 用户明确允许临时将本地验证服务绑定到 `0.0.0.0:5055`；验证后已关闭该进程。
- 真实浏览器访问该进程：当前分析页显示“已验证结论”和空态；删除清单文字均未出现在 DOM；切换“产出与导出”后 HTML、MD 两个按钮可见；console `error` 为 0。
- 此为本地进程 + 真实浏览器证据，不是 Flask `test_client`。未上传文件、未调用 Provider，未验证 staging/production。

## 验证

- `pytest tests/test_slice6_workbench_minimal.py tests/test_web_local_vendor_assets.py tests/test_web_management.py tests/test_web_management_comprehensive.py tests/test_web_memory_candidates_phase2.py tests/test_web_memory_review_ui_phase2.py -q`：`50 passed`。
- `git diff --check` 与 Python 编译通过。
- 一个旧 SSE 脚本 `tests/test_sse_reactivity.py` 在收集阶段因缺失 `reference/workspace/test_sales.csv` 失败；未计入通过。
