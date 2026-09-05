# 矩阵测试韧性修复设计

日期：2026-09-05
状态：已获用户批准（分节呈现后无异议）
来源：用户反馈三症状 + 2026-09-05 A05R2 批次死后系统性诊断

## 1. 背景与根因摘要

用户反馈的三个症状：

- P1 矩阵测试无法稳定执行完整，总因各种问题中断；
- P2 已发现的问题未修复、依然出现；
- P3 整体测试时间极长，发现与修复效率低。

跨批次事实（08-30 至 09-05，6 次批次尝试，约 249 次真实调用，0 次验收通过）：

| 批次 | 死因 | 归因 |
|---|---|---|
| A01 | 共享计数器缺陷 | 验收框架 bug |
| A02 | 6/6 跑完但验收全败 | 产品契约（真实暴露） |
| A03 | 无法证明进程退出 | 观测证明缺口 |
| A04 | 手工转录 sha256 漏前缀 | 操作面设计缺陷 |
| A05 提案 | 预检内部传递未接通 | 验收框架 bug |
| A05R2 | M02 首次调用 BadRequestError → 整批停止 | 错误分类过粗 + 违规整批停止 |

2026-09-05 A05R2 死因链（已由用户在 provider 后台确认为**额度不足**，现已充值）：

1. `strict_provider_guard.py:248` 只记录异常类名，HTTP 状态码、provider 错误体、request ID 全部丢弃，导致 BadRequestError 无法归因；
2. `real_provider_browser_batch.py:338-339` 将任何 `provider_request_failed` 视为整批停止条件，违反冻结计划文档（2026-08-29-real-provider-browser-matrix-plan.md："相同错误签名本身不成为跳过其余场景的理由"）；
3. 零重试原则把瞬态错误升级为不可恢复。

Oracle 侧问题（A05R2 审计时发现）：

- `tmp/a05r2-preparation-01/audit_closed_case.py:125` 零值语义检查是三个硬编码字符串黑名单，把统计上正确的右删失表述也判违规；
- `audit_closed_case.py:128` `within_30s_completion_observation` 硬编码 `False`，该项检查永不通过，污染结果信号（M01 真实成绩应为 44/46 而非 42/46）；
- 审计 oracle 实现活在 `tmp/` 一次性脚本中，不进版本库，"每批换考卷且不可审计"。

版本控制问题：HEAD 停在 2026-08-28 `3b271d7`，工作区 53 个修改 + 175 个未跟踪文件（含 +2469 行系统性根修与全部批次证据）未提交，无回溯性。

结构性缺口（09-01 根因复盘自认）：离线用例覆盖理想形状，无真实模型输出回放库，每批真实调用都在上一轮未覆盖的契约层暴露新缺口。

## 2. 用户已确认的原则

1. **停批标准**：每批尽量执行完整矩阵以综合收集问题；仅严重、必然出现的全局错误才停止整批。Codex 此前对标准的实现有偏差。
2. **恢复语义**：全局错误修复后（如充值），恢复批次并重试被打断的场景；被打断场景的失败视为"未尝试"（原收据归档保留）；已完成场景不重跑；源码摘要必须未变。
3. **受控重试**：接受预算内、收据可见的单次退避重试。
4. **提交策略**：授权按问题逻辑分组提交当前工作区。

## 3. 设计

### S1. 错误观测与分类（P1 地基）

`strict_provider_guard` 的 `_finish` 增强为记录：HTTP `status_code`（litellm 异常属性）、`request_id`、错误消息正文（截断 ~500 字符，脱敏不含密钥）。

新增分类函数 `classify_provider_error(exc) -> ErrorClass`：

| ErrorClass | 判定 |
|---|---|
| `quota_exhausted` | 402，或 400 + 余额文案（"Insufficient Balance" 等，DeepSeek 余额不足是 400+文本） |
| `credential_invalid` | 401 / 403 |
| `rate_limited` | 429 |
| `content_rejected` | 其余 400（含未知文案，默认场景级，靠 3 连同签名兜底） |
| `server_error` | ≥500 |
| `network_transient` | 超时 / 连接类异常 |

latch code 携带类别（如 `provider_request_failed:quota_exhausted`），收据同步记录。

### S2. 分级熔断（P1 核心）

- 场景内：任何最终失败仍触发场景熔断（现状保留）。
- **整批停止仅限**：`quota_exhausted`、`credential_invalid`、连续 3 个场景以同签名失败（签名 = ErrorClass + HTTP status）。
- 删除 `real_provider_browser_batch.py:338-339` 的一刀切判断，替换为按错误类别判断；在计划文档增补修订记录，消除文档-实现矛盾。

### S3. 受控重试（P1）

- guard 对 `rate_limited` / `network_transient` / `server_error` 执行一次重试，固定退避 20 秒。
- 每次物理尝试是收据中独立 ordinal，带 `retry_of` 字段指向被重试的 ordinal；重试计入 call_cap。
- `quota_exhausted` / `credential_invalid` / `content_rejected` 不重试（必然重现）。
- 批次 policy 从 `num_retries: 0` 改为显式冻结的 `retry_policy` 字段（新候选必须携带）。

### S4. 批次恢复（P1+P3）

- 触发：整批因 `quota_exhausted` / `credential_invalid` 停止后，用户修复（充值/换凭证）。
- `derive_resume_batch(原批)` 机械派生恢复批：校验当前源码摘要与原批一致（不一致则强制全新批）、同 data/prompts/oracles/caps、新 attempt 目录（不复用旧目录）、`resumes_from: 原批次摘要`。
- 被全局错误杀死的场景标记 void：原收据归档保留不删改，在本恢复批重试一次（保持各场景一次尝试语义）；已完成场景不重跑。
- 用户授权新派生批次摘要（单 token，沿用现有授权机制）。

### S5. Oracle 治理（P2）

- 审计检查实现从 `tmp/` 脚本提炼进版本库（`scripts/acceptance/matrix_oracles.py`）；冻结候选的 oracle 字段带 `oracle_version`，审计报告标注所用版本。
- 字符串黑名单 → 属性断言：检查"未隔离的绝对化因果断言 / 无溯源域断言"属性；"右删失 / 删失而非真实 0"等正确统计表述入允许清单；"幂律区间"类未溯源域断言仍禁止。正反例用 A04/A05R2 真实文本固化。
- 观察证明缺口（如 30 秒内完成观测）移入独立 `observer_gaps` 字段，不计为 oracle 失败。
- `detect_data_quality` 未调用（A05R2 M01）：记入问题台账，先查 prompt/流程回归，不改 oracle。

### S6. 真实形状回放库（P2+P3）

- 从 A01-A05R2 已消费收据与会话记录提取真实响应形状（工具调用序列、参数组合、错误形状），脱敏后固化为 `tests/replay/` 参数化回放用例。
- 每批结束增量添加新形状；新修复先过回放库再上真实调用。

### S7. 提交策略（P2）

先全量离线回归确认绿，然后按四组提交：

1. 产品修复 + 对应测试（src/data_agent + tests）；
2. 验收基础设施（scripts/acceptance）；
3. web 变更（src/data_agent/web）;
4. docs/audit 证据记录（137 个未跟踪文件）。

`tmp/`、`artifacts/` 不提交。

### S8. 流程自动化（P3）

- 一键批次脚本：freeze → 零调用预检 → 打印授权摘要等待用户 → 授权后跑批 → 自动审计出报告。
- 预检探针：授权后、场景启动前 1 次最小调用（`max_tokens=1`，收据单列 `probe` 类）验证凭证/额度；失败即停（全局错误），不烧场景预算。批中途耗尽由 S4 恢复兜底。

### S9. 验收方式

- 每项修复 TDD 配离线测试。
- 故障注入回归覆盖：quota 错误 → 停批且可恢复；429 → 重试后继续；连续 3 同签名 → 自动停批；oracle 属性断言正反例。
- 端到端验收：一次真实批（A06，需用户授权）；目标为六场景全部尝试、单一全局错误不再报废整批。

## 4. 明确不做

- 不改产品 LLM client 的重试逻辑（分类/重试仅在验收 guard 层）。
- 不放松收据、计量、隔离、进程退出边界。
- 不引入模型/Provider fallback、补充旅程或额外提示词。
- 不提交 `tmp/`、`artifacts/`。

## 5. 风险与边界

- 文本匹配分类依赖 provider 错误文案；已知文案集进注入测试，未知文案默认 `content_rejected`（场景级），3 连同签名兜底识别全局性。
- 允许清单边界（删失允许 vs 域断言禁止）以真实文本正反例锁定，避免再次字符串过拟合。
- 恢复批扩展了授权语义（同源码跨批授权两次），须在计划文档修订中显式记录。
- 回放库是降低而非消除真实批次新层发现；真实调用仍是最高证据等级。

## 6. 验收标准

1. 离线：S1-S5 各项单测 + 故障注入回归全绿；全量离线套件通过。
2. 端到端：A06 真实批六场景全部尝试；任一全局错误停批后，`derive_resume_batch` 可产出合法恢复批并通过零调用预检。
3. 版本库：工作区除 `tmp/`、`artifacts/` 外清零；oracle 实现与批次证据全部入库。
