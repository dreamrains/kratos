# M01 同包结果需求的来源绑定

日期：2026-09-30。实施树 `C:\Users\duguy\.codex\worktrees\trust-rebuild\data-agent`，`codex/trust-rebuild-20260927@4bb7f85` 加保留的 dirty/untracked；供体 `D:\Project\Daily\data-agent@b181646` 只读。本记录从属[唯一当前计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)，不是独立计划。

## 改动和边界

最终模型可在原 `answer_bindings.v1` 的 `blocks` 内提出 `result_requirement_binding`：一个本轮精确 `result` 需求 ID、回执 ID、数据集、完整数据版本身份和该宿主块的完整字段集合。终局宿主先独立构造当前描述/比较 claim，再验证提案的 packet digest、本轮原文 span、当前回执、来源版本及字段集合；通过后只在同一个 `answer_bindings.v1` 内记 `result_requirement_links`。宿主值及渲染仍完全来自当前回执，不从模型提案取数。成功渲染后才将相应需求记 `answered/checked`。旧版本、缺字段、外来需求、坏字段格式各自拒绝，不影响其他 claim。

**语义边界：**提案选择“哪条原文需求对应哪个来源”仍是模型语义判断；宿主只能验证此关系所引用的封闭事实，不能凭 ID 与字段证明选择本身正确。以下 scripted app 收据验证机制和错误版本局部拒绝，不证明自然模型能作出正确映射，也不替代自然正反 oracle。跨轮旧描述没有当前结构化来源身份时仍不得复用旧答案。

## E1 与 Provider 禁用 app

定向比较/摘要测试 **21 passed**，涵盖同包两项正例，以及旧 packet digest、旧数据版本、缺字段、伪造需求 ID、坏字段格式的局部拒绝和终局渲染后覆盖。控制路线事前选择 `local_http_api`，两次均用现有 Provider 禁用演练入口、同一既有 HTTP 控制器、全新 run dir；picker、视觉、刷新为 `unassessed`。上传两文件票据 SHA 分别 `1e6629876a79225fceac0b2dc0f1d16071e532ca989b842c0489afc082f8e59d` / `a5374e58a931846541c13841523e1378a4525b9ce8dcab2cdd3837e74f0a8fc5`。

| 运行身份 | 当前包结果 | 冻结控制文件 SHA-256 |
| --- | --- | --- |
| `tmp/m01-result-links-20260930-r1`，端口 18779，监听 PID 14344，exec session 73551，会话 `6ac64dd7f92e` | `completed`，单一 SSE 终态；两项 `result` 各有本版描述/比较链接，均 `answered/checked`；12 行/120/含首尾 12 日和比较表保留，行动候选按默认门扣留；答案 SHA 与持久 packet 一致、导出已读取；Provider initiated 0，forbidden transport 0。 | launcher `a6495ce57bbbc4d3b64225e2236ead31455c091d6c7cad5dcf8b39a261e7003c`；HTTP controller `c8615c988b0b948d8a0d6f361eb984a0c4ce8d6199adf4dbb8797ae2851ad6b8`；control `0af45e760d1ee9ab0db7481d554abeef440baa767d3fa500780ecee94ab8b27a`；runtime `16475ee7b070f0f1dd0d866ee8abb61f39940ef351d9bd693e060111c8b644cb`。 |
| `tmp/m01-result-links-risk-20260930-r1`，端口 18780，监听 PID 512，exec session 88529，会话 `b20b48115bfc` | `completed`，单一 SSE 终态；描述来源 `version_id` 故意改旧，描述结果需求保持 `unassessed/unassessed`，当前比较结果仍 `answered/checked`；两宿主事实仍发布，错误行动候选按默认门扣留；答案 SHA 与持久 packet 一致、导出已读取；Provider initiated 0，forbidden transport 0。 | launcher `d9012e8fa8eed61d68fdd65b861d2f2acb7afa302596a6f82eacdee27a7f07d6`；controller 同上；control `38067e4256782e56bd0011f5042d1612288d7b5efd45c8395d7e9214d1381612`；runtime `c3bc5d4f659cd29548624ba78c743e146919af3e1652cda5bed63055411f4ff6`。 |

两服务已通过保留的 exec session 停止，18779/18780 不再监听。正式自然模型、完整 M01—M06 矩阵与官方浏览器视觉仍待执行。完整 E2 的新目录结果见唯一计划后续状态。
