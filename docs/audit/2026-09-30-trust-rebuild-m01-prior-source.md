# M01 跨轮已核描述的当前来源绑定

日期：2026-09-30。实施树 `C:\Users\duguy\.codex\worktrees\trust-rebuild\data-agent`，分支 `codex/trust-rebuild-20260927`，HEAD `4bb7f858151d9e03dce0a78ec7316968d166b090` 加保留的 dirty/untracked；供体 `D:\Project\Daily\data-agent@b181646` 只读。本记录从属[唯一当前计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)。

## 决策及实施

当前 `result` 意图可以提出 `source_binding={"mode":"reuse_prior_verified","dataset":...,"source_token":...}`。`source_token` 必须来自当前问题的精确 span，并与同会话当前版本成功加载回执的文件名或 stem 精确对应。宿主只在先前已发布 packet 具有答案哈希、同版本 `describe_dataset` 回执、`observed_basic_summary` 块及渲染 trace 时，向当前 packet 加入该**回执 ID**。宿主重新从当前工作空间读取及渲染描述；不复制旧答案或让旧散文授权数字。当前轮已有同数据集描述时也不搬旧回执。现有 `answer_bindings.v1` 的 `result_requirement_binding` 随后验证需求精确 span、回执、字段全集和完整版本身份，渲染成功后才标 `answered/checked`。

条件行动预览现在先完成当前证据验证，再产生候选可引用的 packet digest；后续回执改变证据身份时重新验证并发新 preview。终局仍独立验证。此前预览与终局校验的次序造成正确候选引用过期 digest。

## E1 / E3 正反证据

定向跨轮、摘要、比较测试 **23 passed**。控制路线事前选定 `local_http_api`；运行均用本树现有 Provider 禁用演练入口、同一既有 HTTP 控制器和新 run dir，SSE 每轮一个终态、持久状态及导出核对。picker、视觉和浏览器刷新 `unassessed`；以下不是自然模型验收。所有服务已通过所保留的 exec session 停止，18781—18784 均不再监听。

| 身份 | 收据和结论 |
| --- | --- |
| `tmp/m01-prior-source-20260930-r1`，端口 18781，PID 21432，exec 23877，会话 `96ce95b340fb` | 两轮 completed；第二轮描述回执、12/120 与比较均在，但候选引用预览 digest `bd592…`、终局 `a073…`，结果需求未签收。这是生命周期次序失败，保留 RED。control SHA-256 `ba53ba20a0821a00d1f136cf16da5ff3a05fbaaead8f7e7fe08cb8ce7ada970c`。 |
| `tmp/m01-prior-source-20260930-r2`，端口 18782，PID 22888，exec 3344，会话 `9ebc5b6ca5d3` | 两轮 completed；第二轮 packet `pub_99055c8d90e0` 同时包含先前 `describe_dataset` 回执 `tr_83c7fe5160cf`、当前比较与行动输入；宿主仍给出 12/120、日期范围和比较。当前结果需求经原 `answer_bindings.v1` 链接至完整当前身份和 `source_rows`、`sums.amount`、`date_range.date`，为 `answered/checked`。行动因试验审核默认关闭而局部 `evidence_insufficient/checked`，不影响宿主事实。答案哈希、持久 packet、导出一致；Provider initiated 0、forbidden transport 0。launcher SHA-256 `d34df2ee8d712330d4a17de8a7bda55c8121b8bd1926ed96a711e3322a9958ad`，controller SHA-256 `1aff17ba7bde8cfe44d023eb111a859308364966c82aded193dfd6d0565e28c8`，control `091c221e72f14292680ea9dbb18fa2911e78cdc636d9d50a2e44ceb0e844dfcc`，runtime `7c1924296d5b862e1917382de9d4a1c9456bc84e1201b2e1becc281459a56441`。 |
| `tmp/m01-prior-source-stale-20260930-r1`，端口 18783，PID 4004，exec 79091，会话 `97ec50bc4cb6` | 控制脚本错误地用 `load_data` 试图覆盖 `f_sales`；工具按设计拒绝同名覆盖，版本未变。此批不能作旧版本负例。control SHA-256 `5876ad0d5db8a4ad8c52bb112edcf35dea686700e23d217fde29689fab1007d0`。 |
| `tmp/m01-prior-source-stale-20260930-r2`，端口 18784，PID 25468，exec 26417，会话 `78b95d692d6b` | 新控制提示明确要求用 `F-SALES-v2.csv` 更新 `f_sales`；现有 `reload_data` 成功产生当前 `dv_4546c91b10ff51df`。两轮 completed；第二轮仅有当前比较/行动输入，没有先前描述，旧结果需求 `unassessed/unassessed`，旧 120 未搬入，当前比较仍发布；答案哈希、持久 packet、导出一致；Provider initiated 0、forbidden transport 0。launcher SHA-256 `869a25cb0169b5a5e9464849dd011bf7dc659de5f2ace47e4c733535cd2bb9d8`，controller `f03a8fc0996c7ce25e5797ecd26bccd86caf71de47ecb12a6290a1efcd94c4c0`，control `1e2865b55fe4382079dc1d7820cf3bb5019512394460c0336774c38132b17834`，runtime `8e67533cf601f232b70ba3984b87aaf86834798f46b15bb551fd23e578e8b9b`。 |

这组收据只证明 scripted 来源提案、宿主版本约束和局部失效。自然模型能否正确选择跨轮来源、提交完整未来双条件行动并保持解释质量，仍需独立正反 oracle；完整 Provider 禁用矩阵与真实 Provider 批次仍未通过。

## 完整离线回归及账本测试契约

首次新目录 `tmp/trust-rebuild-e2-20260930-r3` 为 **2975 passed / 1 failed / 1 skipped / 16 warnings**。唯一失败 `test_p08_http_matrix_driver.py::test_provider_ledger_must_close_each_physical_call` 是旧测试仍把 `started+dispatched` 当成完整调用；这与已加固的 `stream_exhausted` 终态契约冲突。没有放宽产品账本。测试改为完整流结束才通过，并明确检验仅分派不结束时拒绝。账本定向 17 passed；新目录 `tmp/trust-rebuild-e2-20260930-r4` 完整 Provider 禁止回归 **2976 passed / 1 skipped / 16 warnings**。这只证明 E2，本记录的 HTTP 场景仍是局部 E3。
