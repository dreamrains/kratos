# MATRIX-A04-DIAG authorization proposal

This document freezes a pending real Provider plus real browser diagnostic batch. It is not authorization and does not start Provider execution.

- Batch: `MATRIX-A04-DIAG`
- Batch digest: `sha256:c55c513b43ab60b696e584bfd58722cba6185169a188f8c2b7e7a57bc1fe0e30`
- Source digest: `sha256:f7a3149ff9db419897d36570e898770f3276d054bb004833b36ff775a57be2dc`
- Model: `openai/deepseek-v4-flash`
- Order: M01-M06 serial; at most 9 analysis turns and 216 started primary plus auxiliary requests
- Non-transferable case caps: 32/40/32/32/32/48
- Launcher: `tmp/real-provider-browser-matrix-a04-diag-counted-server.py`
- Frozen supervisor: `scripts/acceptance/browser_process.py`
- New isolation root: `tmp/real-provider-browser-matrix-a04-diag` (must not exist before execution)

The current-source offline suite passed 2530 tests with 1 skip and 8 warnings. Six zero-Provider browser rehearsals passed 194 checks at 1440x1000 with 27 datasets, 24 exports and 82 locally closed scripted requests. M03's 15 dense combined labels had zero measured overlap. These results do not establish real Provider acceptance.

After explicit authorization, all six zero-call preflights must be rerun before the first real call. A Provider transport failure, unknown or corrupt accounting, data attribution or isolation failure, frozen identity mismatch, current supervisor proof failure, or unproven normal exit stops the whole batch. There is no retry, fallback, model change, output limit increase, supplementary run or repair during the batch.

## Paste-ready authorization text

> 我授权执行已冻结的 MATRIX-A04-DIAG 真实 Provider＋真实浏览器诊断批次，批次摘要为 `sha256:c55c513b43ab60b696e584bfd58722cba6185169a188f8c2b7e7a57bc1fe0e30`。固定模型 `openai/deepseek-v4-flash`，使用冻结数据和提示词，M01–M06 串行，最多9个分析轮、216次主辅合计实际请求，各场景上限32/40/32/32/32/48，不转移余量，不复用 A01、A02 或 A03 的旧授权及未用额度。我同意携带已记录的非安全问题收集诊断证据，不将其视为验收通过。启动前以 Provider 网络关闭且 socket/DNS 禁止的方式重新通过六场景零调用预检；实际批次只能由已冻结的本地监督器逐场景启动，且每场景控制目录必须与 Provider 收据同域隔离。普通偏差继续记录；Provider 传输失败、计数未知或损坏、数据归属异常、跨会话隔离失效、冻结不符、监督关系无法证明或正常退出无法证明时立即停止整批。不得重试、换模型、fallback、升级输出额度、补跑或边测边改；必要时仅终止已核实属于本批的异常子进程并保全证据。批次结束后统一汇总新旧问题，继续离线根修及离线/零 Provider 浏览器回归；后续真实调用另行冻结并授权。禁止 Git 写操作、推送、部署及删除或回写原始证据。

The quoted paragraph is a proposal for the user to send. Its presence here is not consent.
