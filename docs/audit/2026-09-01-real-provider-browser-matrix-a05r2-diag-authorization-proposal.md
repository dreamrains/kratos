# MATRIX-A05R2-DIAG authorization proposal

This freezes a pending real Provider plus real browser diagnostic batch. It is not authorization and starts no Provider call. The first A05 proposal failed closed during zero-call preflight and is preserved as superseded evidence.

- Batch: `MATRIX-A05R2-DIAG`
- Batch digest: `sha256:6654f45a94e7defaab0378078b4ca2aeced189385519bef7e9482e633314d661`
- Source digest: `sha256:89f9093a53a0120b33ee227687bfe324ef5f11effce1f514e8c0f58e5dc4bb42`
- Model: `openai/deepseek-v4-flash`
- M01-M06 serial; at most 9 analysis turns; 216 total started main plus auxiliary requests
- Non-transferable case caps: 32/40/32/32/32/48
- New isolation root: `tmp/real-provider-browser-matrix-a05r2-diag`

## Paste-ready authorization text

> 我授权执行已冻结的 MATRIX-A05R2-DIAG 真实 Provider＋真实浏览器诊断批次，批次摘要为 `sha256:6654f45a94e7defaab0378078b4ca2aeced189385519bef7e9482e633314d661`。固定模型 `openai/deepseek-v4-flash`，使用冻结数据、提示词与判定规则，M01–M06 串行，最多9个分析轮、216次主辅合计实际请求，各场景上限32/40/32/32/32/48，不转移余量，不复用 A01–A04 的旧授权、未用额度或历史消费；此前未授权的 A05 提案零调用预检失败且已被本提案取代，不得启动或复用。我同意携带已记录的非安全问题验证本轮系统修复并继续收集诊断证据，不将其预先视为验收通过。启动前仅使用该批次摘要，在 Provider 网络关闭且 socket/DNS 禁止的六个全新进程中重新通过零调用预检；候选文件必须重新核对源码、启动器、监督器、数据、提示词、判定规则和所选场景。实际批次只能由已冻结的本地监督器逐场景启动，且每场景控制目录必须与 Provider 收据同域隔离。普通判定偏差继续记录；Provider 传输失败、计数未知或损坏、数据归属异常、跨会话隔离失效、冻结不符、监督关系无法证明或正常退出无法证明时立即停止整批。不得重试、换模型、fallback、升级输出额度、补跑、转移余量或边测边改；必要时仅终止已核实属于本批的异常子进程并保全证据。批次结束后统一汇总，后续真实调用另行冻结并授权。禁止 Git 写操作、推送、部署及删除或回写原始证据。

The quoted paragraph is a proposal for the user to send. Its presence here is not consent.
