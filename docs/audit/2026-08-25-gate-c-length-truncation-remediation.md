# Gate C 截断诊断修复（未执行新的 Provider）

日期：2026-08-25

## 已确认的真实批次事实

在 `sha256:e1b698fa7028c2099961e94fe0469f77ce407e51fe7ecb8f29875732100f921f` 上，C01 先恰好 1 次通过；随后 R01–R07 恰好 7 次执行完成。R02、R04、R07、R01、R05、R06 通过；R03 失败。该 R03 失败收据不是一般性的格式错误：

- `response_shape=empty`；
- `response_length_bucket=empty_or_non_string`；
- `response_finish_reason=length`；
- 请求冻结为 `max_tokens=1000`。

因此可以确认它在生成完整可验证响应前耗尽了本次 token 预算。不能从该历史收据确认 token 是可见输出、隐藏 reasoning 或网关行为消耗；原文与 reasoning 按边界没有保存。

## 本次离线修复

- `finish_reason=length` 现在在解析之前稳定标记为 `response_truncated` / `truncated_before_complete`，不再把截断混同为普通 `response_not_json`。
- 新增仅含分桶的 `response_reasoning_length_bucket`，供下一次收据区分 reasoning 是否可见；不保存 reasoning 正文。
- 完整 JSON 但 `finish_reason=length` 仍失败，避免把可能被截断的尾部误判为完整成功。

当前受控源码摘要：`sha256:f88febd834cb43fcf27cd40088b4ac80dd4c9ad824a243a737c21bc15d477006`。

## 验证与后续

- `26 passed`、`compileall`、`git diff --check` 通过；本修复调用 Provider `0` 次。
- 不能沿用先前任何 Provider 授权或报告作为当前源码通过证据。
- 下一步应先为 R03 的独立截断 canary 取得新的精确授权，并明确新的 `max_tokens`。推荐将上限提高到 `2000`；若该 canary 失败，不进入 R01–R07 全量批次，不重试。
