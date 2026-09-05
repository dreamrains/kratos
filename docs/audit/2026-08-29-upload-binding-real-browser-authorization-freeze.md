# 上传绑定缺陷真实 Provider 浏览器验收授权冻结

日期：2026-08-29

## 当前停止点

本冻结只准备一次真实 Provider 的本机完整浏览器旅程，不构成授权。当前真实 Provider 调用为 **0**；零调用预检已返回 `ready=true`，随后本地服务已停止。Provider 调用收据与最终报告路径均不存在。

本冻结不授权暂存、提交、推送、部署、staging、production、删除原会话或处理既有 `artifacts/` / `tmp/`。只有用户明确发送下方完整授权文案后，才执行一次冻结旅程。

## 冻结事实

| 项目 | 冻结值 |
|---|---|
| 分支 / HEAD / `origin/main` | `main` / `3b271d7cdf7d4bafaafb0ade8d7bba69baf777d6` / `3b271d7cdf7d4bafaafb0ade8d7bba69baf777d6` |
| release source digest | `sha256:97d51421f2481689c48f4ac6036a60b9e783b32a78eb0296a162cdff1dae2c42`（345 项） |
| 模型 | `openai/deepseek-v4-flash` |
| candidate | `docs/audit/2026-08-29-upload-binding-real-browser-candidate.json` |
| candidate SHA-256 | `sha256:9a9c2204a4f2dd533ead725fef715aebaaf981bc12e5929f519be60eb2d0caa4`（CRLF 规范化为 LF 后） |
| 数据 | `reference/test_doc/游戏B留存.xlsx` |
| 数据 SHA-256 | `sha256:63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0` |
| prompt SHA-256 | `sha256:c8f72b37f9c75c73e7cd722553a444496f09b8111a0fff380f5dbebfda95402a` |
| oracle SHA-256 | `sha256:4cf601ee726c1ee84726c196640b24f2a758457719b32b4b0c06e925cc039f3e`（canonical UTF-8 JSON） |
| 计数启动器 | `tmp/upload-binding-real-browser-counted-server.py` |
| 计数启动器 SHA-256 | `sha256:8a3e3fe514b55812dcf45fc47afcd2592bc7bf1a9639d20e56f989eef3b6ed81` |

精确用户提示词：

```text
请根据数据为我拟合新用户留存率的公式，比较幂律、指数和对数曲线，并给出参数、拟合优度和适用限制。
```

## 调用与失败纪律

- 只执行 **1 次 Web 用户旅程**：新会话上传冻结文件、发送冻结提示词、必要时仅确认既有 `method_confirmation`、等待真实工具与最终回答、刷新同一会话。
- 底层 Provider 请求与全部辅助 LLM 请求共用硬计数器，总上限 **24 次**。
- `temperature=0.0`、`timeout=120s`、初始 `max_tokens=8000`。
- 仅当一次响应为无可见正文的 `finish_reason=length` 时，允许产品现有的 `8000 → 32000 → 128000` 有界升档；每档至多一次。
- 强制 `num_retries=0`；禁用 stream→sync 补发；禁止模型切换、Provider fallback、失败后重跑和补充旅程。
- 任一预检项不匹配则 Provider 0；调用异常、计数上限、非预期确认、文件恢复提问或工具错误均立即停止，并按实际已消费次数记录失败，不重试。
- 真实旅程结束后授权立即消费，无论通过或失败均不得复用。

## 验收 oracle

1. 上传返回不泄露路径的完整性票据；文件在首个模型请求前已归属新会话并加载为 `游戏B留存__raw` / `游戏B留存`，形状 62×13。
2. 不得出现“文件不存在、重新上传、提供完整路径”类 `ask_user_question`。
3. 必须真实执行 `curve_fitting`，工具 error event 为 0，并给出非空、基于数据的拟合回答。
4. 会话源文件必须位于该会话的 `uploads/<upload_id>/`；不得生成共享 inbox 副本。
5. 刷新后最终回答仍可恢复；浏览器 error/warning 日志为 0。

## 唯一写入路径

- 隔离 workspace：`tmp/upload-binding-real-browser-provider/workspace`
- 隔离 sessions：`tmp/upload-binding-real-browser-provider/sessions`
- Provider 精确计数收据：`tmp/upload-binding-real-browser-provider/provider-calls.json`
- 最终报告：`docs/audit/2026-08-29-upload-binding-real-browser-provider-report.json`

## 授权前证据

- 当前源码零 Provider 全量测试：`2357 passed, 9 skipped, 39 warnings in 473.20s`。
- 定向上传/SSE：`15 passed`；Python 编译、Node 语法、`git diff --check` 通过。
- 当前源码本地真实浏览器（桩模型）已通过：上传、会话前预加载、合法方法确认、`curve_fitting`、最终回答、刷新恢复；移除未发送附件后暂存目录从 1 变 0；浏览器 error/warning 为 0。
- 零调用授权预检：source / candidate / prompt / oracle / data hash 全匹配，`call_cap=24`；预检启动后已停止，未生成 Provider 收据。

## 精确授权文案

```text
我授权上传绑定缺陷的真实 Provider 完整浏览器验收：仅在 release source digest sha256:97d51421f2481689c48f4ac6036a60b9e783b32a78eb0296a162cdff1dae2c42 上，使用 openai/deepseek-v4-flash、candidate sha256:9a9c2204a4f2dd533ead725fef715aebaaf981bc12e5929f519be60eb2d0caa4、数据 sha256:63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0、prompt sha256:c8f72b37f9c75c73e7cd722553a444496f09b8111a0fff380f5dbebfda95402a、oracle sha256:4cf601ee726c1ee84726c196640b24f2a758457719b32b4b0c06e925cc039f3e 和计数启动器 sha256:8a3e3fe514b55812dcf45fc47afcd2592bc7bf1a9639d20e56f989eef3b6ed81，执行 2026-08-29-upload-binding-real-browser-authorization-freeze.md 冻结的 Web 用户旅程恰好 1 次；全部主请求与辅助请求共用硬上限 24 次，temperature=0、timeout=120 秒、初始 max_tokens=8000，仅无可见正文且 finish_reason=length 时允许按 8000→32000→128000 每档至多一次升档；强制 num_retries=0，禁止 stream→sync 补发、模型切换、Provider fallback、失败重试和补充旅程。预检任一不匹配则零调用；执行异常、非预期确认、文件恢复提问、工具错误或达到上限时立即停止并记录实际已消费次数。只允许写入冻结的隔离 workspace、sessions、Provider 计数收据和 docs/audit/2026-08-29-upload-binding-real-browser-provider-report.json；不授权 Git 写操作、部署、staging、production 或删除原会话。
```
