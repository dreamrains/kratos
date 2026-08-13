# Data Agent V2 Slice 0–1 实施计划

- **日期**：2026-08-13
- **状态**：Slice 1 canary implemented；主链路迁移未开始
- **分支**：`codex/data-agent-v2`
- **基座**：`1d570617332103a04a1e944cc7f8be774901a938`
- **设计**：[`2026-08-13-data-agent-v2-architecture-design.md`](../specs/2026-08-13-data-agent-v2-architecture-design.md)

## 1. 目标

先建立一条最小但真实的 V2 纵向路径，而不是一次迁移所有分析能力：

```text
Commitment
→ Execution Events
→ Structured Finding
→ Read-only Run Projection
→ Typed Answer Blocks
→ Persisted V2 turn
→ Semantic SSE contract
```

Slice 1 只声明支持单文件描述性场景。因素关系、推断、预测、因果、多文件综合和运行中 steer 不在本切片承诺范围内。

## 2. 实施边界

### 本切片实现

1. V2 领域契约：Commitment、ExecutionEvent、Finding、Outcome、AnswerBlock。
2. 只读 Run Projection；没有完成状态 setter。
3. Append-only Execution Journal 和 Evidence Ledger 的会话级持久化。
4. Typed Answer Compiler 的确定性校准与 Canonical Renderer。
5. V2 消息块持久化和刷新读取。
6. 语义 SSE 事件映射。
7. 一个确定性单文件描述性 canary，随后接入真实 Agent/LLM 路径。
8. 事故回放、owner tests 和 browser contract tests。

### 本切片不实现

- 不迁移旧 `analysis_requirement.v1`、`evidence_record.v2` 或 `final_answer_audit.v1`；
- 不实现复杂 Planner；Slice 1 Planner 仅生成一个描述性 core Commitment；
- 不升级 `run_python` 为 verified Finding；
- 不迁移旧 task manager；
- 不替换当前 main；
- 不运行真实 provider，除非后续得到明确授权。

## 3. 交付顺序

### Step A：领域状态与事故回放

- RED：任意成功工具不能使 Commitment 完成；
- RED：没有显著发现可以投影为 `null_result`；
- RED：方法失败可以投影为 `unavailable`；
- RED：可选图表失败不阻塞 core Outcome；
- RED：过程语不能影响 Outcome；
- 实现最小 contracts 和纯投影函数。

### Step B：事实持久化

- Execution Journal 只追加；
- Evidence Ledger 只接受通过结构校验的 Finding；
- 唯一 ID，禁止秒级文件名承担身份；
- 保存后重新加载得到相同投影；
- 同一个 `event_id`/`finding_id` 幂等，不允许内容冲突。

### Step C：Typed Answer Compiler

- 输入为 Outcomes + Findings + 数据诊断；
- 材料性块必须绑定 support refs；
- claim class 不得超过 Finding 上限；
- canonical values 与 Finding 不一致时拒绝该块；
- 单块失败不删除其他块；
- `null_result`、`limited` 和 `unavailable` 可生成完整答案。

### Step D：V2 Turn 与 SSE

- 最终 Answer Blocks 先持久化，再发 `turn_completed`；
- 事件类型使用设计中的语义事件；
- 刷新直接读取消息块，不解析工具文本；
- 图表使用 artifact ID 和 block relation。

### Step E：Slice 1 浏览器 canary

- 上传真实 schema fixture；
- 创建 raw/analysis 数据版本；
- 执行结构化描述工具；
- 写 Finding；
- 投影 Outcome；
- 编译并显示答案；
- 条件图表；
- 刷新恢复；
- 当前切片验收通过后，才开始 Slice 2。

## 4. 测试矩阵

| 层 | 首批用例 |
|---|---|
| Owner | projection、journal、ledger、answer compiler、message store |
| Incident | 56 字过程语、any-success、无正向 Finding、optional chart failure |
| SSE contract | 进度早于 final、persist 早于 completed、事件字段 |
| Browser | 上传、进度、完整答案、条件图表、刷新 |
| Quality | 方法说明、局限、直接回答、无旧 marker |

## 5. 完成定义

Slice 1 只有在以下条件全部满足时才完成：

1. 当前切片 owner tests 全绿；
2. 已知事故回放全绿；
3. 单文件描述性 canary 通过真实浏览器路径；
4. 刷新后消息块和 Outcome 一致；
5. 没有使用旧 task/evidence/publication schema 作为权威；
6. 设计文档、实现计划和实际代码一致；
7. 未声明 Slice 2+ 能力已经可用。

## 6. 2026-08-13 实施检查点

本次完成的是隔离的 V2 Slice 1，不是旧系统修复完成，也不是产品切换完成。

- 已实现 Commitment、Execution Journal、Finding、只读 Run Projection、Typed Answer Blocks、会话级持久化和语义 SSE；
- 已实现 raw/analysis 不可变数据版本、指纹、父子血缘与原子持久化；
- 描述工具成功本身不会推进完成，必须出现契约匹配的 `estimate` 或 `null_result` Finding；
- 全空或全非数值指标会发布可解释的 `null_result`，不会用异常或 `NaN` 伪装成答案；
- 浏览器 canary 已验证真实文件上传、进度先于答案、答案块发布、刷新恢复和零控制台错误；
- 本次问题是“当前数据的平均值”，不需要图表，因此未生成图表；图表 Artifact/Message Block 仍是后续适图场景的显式验收项；
- V2 聚焦测试 37 项通过；相邻的 chart contract 21 项、chart semantics 29 项、本地静态资源 2 项通过；
- `tests/test_web_gui.py` 不是 pytest 测试集合，而是在模块导入期直接访问 5001 端口并调用完整聊天/真实分析的历史脚本。它虽然已在 `tests/conftest.py` 的 `collect_ignore` 中，但显式把文件名传给 pytest 会绕过这层隔离。本轮误收集共触发 4 个未授权真实聊天请求；没有形成有效验收结果，服务与生成会话均已清理。现已增加模块级保险：即使显式交给 pytest，也会在发出网络请求前停止。后续应把它移出 `tests/`，拆为可控的 browser journey 与需要逐次授权的独立 real-provider journey。

下一检查点不是接管旧 `/` 主页面，而是先补齐 V2 的块级校准、Chart Artifact/Message Block 和场景适配判定，再决定 Slice 2 的真实 Agent 接入边界。
