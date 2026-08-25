# Slice 5 开放分析完整性冻结收据（Provider 除外）

日期：2026-08-25

## 源码与边界

- 基线提交：`1d078ae7260a7fef044d9734227a46e805253042`。
- 当前受控源码摘要：`sha256:92b7b3a34fa2cab3ff15ac15d770894d78259e590fe4bf7f9ef1393772aca704`（320 条；`src`、`scripts`、`tests`、入口和依赖清单）。
- 未调用真实 Provider；未触碰、暂存或提交 `artifacts/`、`tmp/`。

## 交付

1. `tool_search` 在搜索前确保完整工具发现；搜索命中后仍通过既有 group activation 使高级能力可达，不建立平行 planner/registry。
2. `run_python` 保持现有 workspace scope 约束，并在共享 AST 边界禁止 pandas/NumPy 的文件或网络 I/O；返回 `exploratory_sandbox` 标签和 `sandbox_replay.v1`（代码、SHA-256、受限超时）收据。探索输出并不自动成为 verified conclusion。
3. synthesis instruction 统一要求将 material statement 标为 direct evidence、inferential evidence 或 suggestive context；明确索要建议时，只要证据支持便给条件化、可逆建议，不能仅因没有因果证明而全局清零；未解驱动结论须写竞争解释与区分证据。
4. 知识/记忆仍先 candidate、后 confirm；冲突披露保留来源。自动冲突不再以 token/CJK bigram overlap 断言语义等价：仅共享显式标识符，或同一用户显式检索主题下的相反极性，生成 `REVIEW` 提示而非事实裁决。
5. 压缩先保存完整 transcript；另以确定性附录保留早期用户消息中的 dataset/version/fingerprint 和明确义务，且标为 context-not-evidence，不能替代当前数据证据。

## 真实数据 oracle 与范围

- R06/R08 的离线真实文件路径使用 `tests/test_mvp_retrieval_budget_real_data.py` 的 canonical reference-data manifest：真实 `省钱卡订单.xlsx` 会话证据只有在显式 evidence budget 下可被取回；游戏付费分析的 memory candidate 在确认前不进入 prompt，确认后才以低优先级 memory hint 进入，并受 retrieval budget 约束。
- R09 的 provider-neutral reachability 使用真实 registry discovery：`synthesize_time_series` 可由 `tool_search` 命中并激活 EDA group；未以函数存在代替可达性。
- 这不是正式真实 Web 或 Provider journey：未使用 Flask `test_client`、fixture 或离线 oracle 冒充浏览器/Provider 验证。真实多文件/长回答/刷新浏览器旅程仍属于 Slice 6；真实 Provider 仍需 Gate C 精确次数授权。

## 验证

- `pytest tests/test_slice5_open_analysis_integrity.py tests/test_tool_recovery.py tests/test_synthesis_policy.py tests/test_knowledge_integration.py tests/test_knowledge_tools_phase1.py tests/test_knowledge_tools_phase2.py tests/test_pipeline_comprehensive.py -q`：`160 passed`。
- `pytest tests/test_slice5_open_analysis_integrity.py tests/test_slice4_multifile_integrity.py tests/test_slice3_method_integrity.py tests/test_slice2_workspace_versions.py tests/test_stage3c0b_execution_scope.py tests/test_stage3c0b_evidence_replenishment.py tests/test_web_overhaul.py tests/test_intent_classification.py tests/test_prompt_system.py -q`：`446 passed`。
- `pytest tests/test_mvp_retrieval_budget_real_data.py tests/test_intent_classification.py tests/test_llm_intent.py tests/test_knowledge_comprehensive.py tests/test_knowledge_retrieval.py tests/test_retrieval_budget_phase2.py tests/test_knowledge_tools_phase15.py -q`：`257 passed`。
- `python tests/test_tools_comprehensive.py`：`104 PASS, 0 FAIL`。
- 额外尝试包含 `tests/test_comprehensive_analysis_flow.py::TestMultiTurnConversation::test_turn1_load_data_turn2_analyze` 的旧组合门禁时，该集成用例在本轮超过 30 秒未完成；未将其计入通过，也未修改该非 Slice 5 旧链路。
