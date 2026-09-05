# MATRIX-A06-DIAG authorization proposal

This freezes a pending real Provider plus real browser diagnostic batch after the matrix-resilience overhaul. It is not authorization and starts no Provider call. The executed A05R2 batch (M01 complete, M02 provider failure, stopped after M02) is consumed history and is not reused. Supersedes the pre-authorization freeze at commit d7ae06a after the final-review fix wave d7ae06a..1cd3227 changed the release source digest. The superseded batch was never authorized and made zero calls; this re-freeze carries the identical content rules.

- Batch: `MATRIX-A06-DIAG`
- Batch digest: `sha256:fae6d5fc949d6de5b385db8490f9badaa10661f71a11d5903c244c08c008887f`
- Source digest: `sha256:e4c1256823f838bb86c7d764f576c3f764d0d866ea3f26e8df84f7789fcfb736`
- Model: `openai/deepseek-v4-flash`
- M01-M06 serial; per-case analysis turns 1/2/1/1/1/3 (turn cap 9); 216 total started main plus auxiliary case calls, plus exactly one credential probe call (max_tokens=16, own receipt, before any scenario setup)
- Non-transferable case caps: 32/40/32/32/32/48
- Guard retry policy (frozen per case): at most one retry per started call for rate_limited/network_transient/server_error, 20-second backoff, retry consumes its own slot; no other retries
- Tiered stop: quota_exhausted or credential_invalid stops the batch immediately; three consecutive same-signature case failures stop the batch; other case failures close only that case
- New isolation root: `tmp/real-provider-browser-matrix-a06-diag`
- Launcher: `scripts/acceptance/real_provider_browser_batch.py` via `python -m scripts.acceptance.run_batch`

## Paste-ready authorization text

> 我授权执行已冻结的 MATRIX-A06-DIAG 真实 Provider＋真实浏览器诊断批次，批次摘要为 `sha256:fae6d5fc949d6de5b385db8490f9badaa10661f71a11d5903c244c08c008887f`。固定模型 `openai/deepseek-v4-flash`，使用冻结数据、提示词与判定规则（含 oracle_version 2026-09-05.1），M01–M06 串行，最多9个分析轮、216次主辅合计实际请求，另加一次探针调用（max_tokens=16、独立收据、先于任何场景），各场景上限32/40/32/32/32/48，不转移余量，不复用 A01–A05R2 的旧授权、未用额度或历史消费（A05R2 已执行 M01、M02 共17次调用并停止，不得补跑或转移）。限速、瞬时网络与服务器端错误按冻结策略每已启动调用至多重试一次（20秒退避，重试消耗自身额度，litellm num_retries 保持0）；配额耗尽或凭证失效立即停止整批；连续三个场景以相同错误签名关闭时停止整批；其他单场景失败只关闭该场景，后续冻结场景继续。我同意携带已记录的非安全问题验证本轮系统修复并继续收集诊断证据，不将其预先视为验收通过。启动前仅使用该批次摘要，在 Provider 网络关闭且 socket/DNS 禁止的全新进程中重新通过零调用预检；候选文件必须重新核对源码、启动器、监督器、数据、提示词、判定规则和所选场景。实际批次只能由已冻结的本地监督器逐场景启动，且每场景控制目录必须与 Provider 收据同域隔离。普通判定偏差继续记录；数据归属异常、跨会话隔离失效、冻结不符、监督关系无法证明、计数未知或损坏、正常退出无法证明、配额耗尽或凭证失效时立即停止整批。不得换模型、fallback、升级输出额度、转移余量或边测边改；被停止批次如需继续只能另行冻结并授权恢复批次。必要时仅终止已核实属于本批的异常子进程并保全证据。批次结束后统一汇总，后续真实调用另行冻结并授权。禁止 Git 写操作、推送、部署及删除或回写原始证据。

The quoted paragraph is a proposal for the user to send. Its presence here is not consent.
