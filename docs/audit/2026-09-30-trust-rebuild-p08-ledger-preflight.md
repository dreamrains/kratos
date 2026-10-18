# P08 Provider 账本与冻结边界的零调用核对

日期：2026-09-30。当前实施树 `codex/trust-rebuild-20260927@4bb7f85` 加保留的 dirty/untracked；供体 `D:\Project\Daily\data-agent@b181646` 只读。此处属于[唯一当前计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)的 R6 准备，不是新的 Provider 批次或正式默认授权。

## 已确认的缺口与修正

原 `ProviderLedger` 在 `completion()` 返回流对象时写 `dispatched`；HTTP 控制器只要求 `started == dispatched`，未区分真正消费完整流、提前关闭和流异常。账本第一次写入失败也没有锁定后续调用；因此旧检查可能把“拿到 stream 对象”误看成已完整响应。

现沿用原 `provider-calls.jsonl`，在物理请求前同步持久化 `started`；返回对象记 `dispatched`，非流返回另记 `completed`，流迭代自然结束记 `stream_exhausted`，异常/提前关闭分别记 `stream_failed` / `stream_closed`。HTTP 控制器及限额补测前检要求每个 `started` 恰有已分派且已结束的记录，遇失败、关闭、超额即停止账本验收。账本写入与 `fsync` 失败后锁定该进程的后续 Provider 请求；首次 `started` 写入失败时物理 transport 不执行。冻结和正式启动均要求 Git source tree 干净，避免 dirty 文件使 `source_commit` 不能代表实际代码。

离线 `tests/test_p08_real_matrix_launcher.py` **14 passed**：单次请求策略、冻结合同、干净提交门、流对象返回与完整消费的区分、中途关闭/异常、首次账本写入失败前拒绝 transport、非流结束和 HTTP 对缺少流终态的拒绝。未作真实 Provider 调用。正式冻结前仍须完成包 D、将必要代码与资料整理为确切提交、以不泄露密钥的方式装载并核对确切模型/端点、M01—M06 输入与 oracle、120 次上限及新账本路径。当前重建树仍 dirty，故此门会拒绝创建真实批次；这是预期的零调用结果。
