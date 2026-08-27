# Slice 7 历史、迁移与回归冻结收据（Provider 除外）

日期：2026-08-25

## 源码与边界

- 基线提交：`134b5b2842e3d7a5a1c5d2058d68a3ba9cf58ac7`。
- 当前受控源码摘要：`sha256:febcfe9dff84c1204920e061c0ce85f329c82f2b88771e6d03a74c52eeef3e42`（321 条）。
- 未调用真实 Provider；未上传任何数据；未触碰、暂存或提交 `artifacts/`、`tmp/`。

## 交付

1. `data_agent.migration` 新增可复现的 `audit_route_a_migration()`：默认 dry-run，逐会话列出数据集、identity 状态、原始文件/备份可用性、artifact 引用、缺失引用、JSON 损坏项与内容 SHA-256。
2. 迁移只在显式 `apply_route_a_migration()` 或 `python -m data_agent.migration --apply` 时写入；不双写旧/新运行时。原始文件仍可读时才写入 raw identity；缺原始文件会话写为 `read_only_missing_original`，不会从备份伪造原始上传。
3. `load_session()` 返回持久化迁移状态；`AgentLoop._restore_workspace()` 对此状态禁止 backup fallback，保留原文件可用时的正常恢复。
4. 将遗留 Workbench 测试迁移到 Slice 6 的单一 `verified_conclusions` 契约；数据理解、关系、确认和完整回答仍在主链内部契约中，不再要求出现在 Workbench。

## 验证

- 迁移、会话恢复、R07 evidence/oracle、Slice 6 和现代 Web 契约：`142 passed`。
- Slice 2–6 定向完整性：`26 passed`。
- `pipeline_comprehensive`：`92 passed`。
- `phase_comprehensive`：拆分运行 `51 passed` 与 `32 passed`。
- scoped workspace：`179 passed`。
- 任务、版本、Skills/MCP、记忆、确认 API：`39 passed`。
- 本地 Web 管理、Vendor、记忆 UI、Overhaul 和 Workbench 静态契约：`156 passed`。
- 真实本地多文件分析 oracle：`10 passed`。
- `compileall`、`git diff --check`：通过。
- 真实本地 Web 进程 + 浏览器（临时 `0.0.0.0:5055`，后已关闭）：仅验证当前页的“已验证结论”、HTML/MD 导出入口、删除项不在 DOM、console error 为 0。未上传、未发聊天、未调用 Provider；这不是五条数据分析浏览器旅程的替代品。

## 已知排除与下一闸门

- `tests/test_web_gui.py` 为导入即执行的旧式脚本，在 pytest collection 前失败，不能冒充当前 pytest Web 契约；现代 Web 契约已由上述 156 项覆盖。
- 不执行真实会话目录的 `--apply`：这是对用户历史会话的持久化改写，必须先审阅该目录的 dry-run 结果并单独确认。
- R07、R02、R03、R04、长回答/停止/刷新/下载五条真实浏览器数据旅程尚未运行，因为会涉及上传和/或 Provider 调用；不得以 Flask `test_client` 代替。
- Gate C 仍需用户按冻结单授权模型、数据 hash、场景、每场景调用数和总次数；任何失败停止且不自动重试。
- 未推送、合并、部署、切根或删除历史实现。
