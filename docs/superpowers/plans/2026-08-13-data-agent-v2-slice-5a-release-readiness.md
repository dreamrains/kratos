# Data Agent V2 Slice 5A：发布准备度与替换判定

- **日期**：2026-08-13
- **状态**：Implemented; pending commit
- **基线提交**：`2d8a85d`（`feat(v2): add bounded exploratory python slice`）
- **分支**：`codex/data-agent-v2`
- **上位设计**：[`2026-08-13-data-agent-v2-architecture-design.md`](../specs/2026-08-13-data-agent-v2-architecture-design.md)

## 1. 当前判断

V2 已具备多个端到端 canary，但还不能接管 `/`：当前没有统一的会话级分析路由，没有当前源码绑定的 real-provider journey，也没有人工语义评审记录。此时直接删除旧运行时，会把“架构更干净”错误等同于“用户旅程可替代”。

Slice 5A 先让替换条件可计算、缺口可见。它不切换主页面，不运行真实 provider，也不删除旧运行时。

## 2. 分层验证合约

新发布合约只使用以下层名，不再使用 Gate E/F：

1. `owner_contract`
2. `incident_replay`
3. `sse_transport_contract`
4. `browser_interaction_journey`
5. `refresh_persistence_journey`
6. `real_provider_analysis_journey`
7. `human_semantic_review`

每张 receipt 必须绑定：

- 当前 `source_digest`；
- `scenario_id`；
- 单一验证层；
- `pass | fail | blocked | not_run` 状态；
- 具体 evidence refs；
- oracle identity；
- 首个失败阶段（非 pass 时）；
- provider 调用次数（仅 real-provider 层）。

禁止把活动计数、测试数量、浏览器能打开或旧 receipt 映射为产品 PASS。

## 3. Source Digest

`v2_release_source.v1` 覆盖 `src/`、`scripts/`、`tests/` 和 `pyproject.toml`。每个文件使用 Git clean filter 后的 blob identity，因此 LF/CRLF 等价检出；同时包含未跟踪但未忽略的发布源文件，并能反映删除。

receipt 的 digest 与当前 digest 不一致时一律视为 stale，不进入准备度计算。

## 4. 旅程矩阵

清单将每个场景声明为：

- `scenario_id` 与用户价值；
- 入口与 fixture；
- 需要的验证层；
- 必须出现的语义事件、终态、答案块或图表；
- 不应出现的确认或结论升级；
- 是否要求 provider 和人工评审。

第一版覆盖描述、因素关系、日期转换、分组比较、趋势、预测、多 Finding 和探索性 Python。矩阵声明需求，不伪造已执行 receipt。

## 5. 替换判定

判定状态只有：

- `not_ready`：至少一个必需场景/层缺失、失败、阻塞或 stale；
- `ready_for_human_decision`：所有矩阵要求均由当前 digest 的 PASS receipt 覆盖；

不存在自动 `product_pass` 或自动切换主页面状态。即使达到 `ready_for_human_decision`，是否切换 `/`、删除哪些旧模块仍需单独人工决定并形成后续切片。

## 6. 本切片不做

- 调用真实 provider；
- 生成虚构或回填的 PASS receipt；
- 复用旧 Gate E/F receipt；
- 切换 `/` 或删除旧聊天运行时；
- 将 canary 测试通过解释为整体产品可用。

## 7. 验收

- digest 对 LF/CRLF 等价、源文件修改、未跟踪源文件和删除敏感；
- stale receipt 不参与计算；
- 单个浏览器 PASS 不能覆盖 SSE、刷新、provider 或人工评审；
- 所有层 PASS 后仍只得到 `ready_for_human_decision`；
- provider 调用次数只能来自显式 receipt，本切片保持为 0；
- CLI 能输出当前 digest 和缺失矩阵，不产生外部写入。

## 8. 本切片验收记录

- RED 测试先因 `data_agent.v2.release` 不存在而失败，随后实现转绿；
- 发布准备度、digest、receipt 冲突/stale/不完整证据元测试：`9 passed`；
- 全量 V2 回归：`148 passed`；
- Python compileall 与 `git diff --check` 通过；
- 当前 `v2_release_source.v1` digest：`sha256:c1025f6e7c087f72db13c1fbf4144bfb00a0bd49df2b00fa7852b6468be074b8`；
- 当前矩阵包含 9 个场景 × 7 个独立验证层；未生成任何 receipt，因此 63 个要求均明确为 missing；
- 当前替换判定：`not_ready`；`provider_calls=0`；`root_switch_authorized=false`；
- 关键真实阻塞是统一分析入口尚未实现、当前源码无 real-provider journey、无逐维人工语义评审；
- 未调用真实 provider，未复用旧 Gate E/F receipt，未切换 `/`，未删除旧运行时。
