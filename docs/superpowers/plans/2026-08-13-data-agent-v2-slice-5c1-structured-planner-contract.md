# Data Agent V2 Slice 5C1：结构化模型 Planner 合同

- **日期**：2026-08-13
- **状态**：Completed
- **基线提交**：`8f830fc`（`feat(v2): add durable queued steering`）
- **分支**：`codex/data-agent-v2`

## 1. 为什么现在做

V2 已建立 Dataset、Method、Ledger、Projection、Publisher 和交互控制边界，但统一工作台仍要求用户自行选择 `analysis_kind` 和方法字段。这是一个明确的产品缺口：缺少数据科学知识的用户不应承担方法选择职责。

下一步不能用关键词分类器假装成 Planner，也不能直接把旧 Agent loop 接回 V2。Slice 5C1 先建立 provider-neutral 的结构化规划合同，使真实模型只能提出方法计划，不能写完成状态、Finding 或发布结论。

## 2. Planner 权限

Planner 可以：

- 读取用户原始问题和最小数据画像；
- 在已实现的方法目录中选择一个分析类型；
- 绑定指标、时间、分组、分析单位和候选因素；
- 对真正缺少且只能由用户提供的语义返回 `needs_input`；
- 对当前方法目录无法回答的问题返回 `unsupported`。

Planner 不可以：

- 写 Commitment 完成状态、Execution Event、Finding 或 Answer Block；
- 提供或改写计算结果；
- 将相关分析升级为因果结论；
- 自动生成或执行自由 Python；
- 根据列名相同自动连接多文件；
- 在一次规划请求中隐式重试或增加 provider 调用。

## 3. 输入与输出

输入是用户问题与最小 `DatasetPlanningContext`：文件身份、行数、列名及服务端推断的列角色。第一版不发送原始行或样本值。

模型必须调用唯一工具 `submit_analysis_plan`，返回：

- `status`: `ready | needs_input | unsupported`；
- `analysis_kind`: V2 已支持的结构化方法之一；
- `parameters`: 方法所需字段；
- `rationale`: 简短的方法选择理由，不得包含数据结论；
- `questions`: 仅在 `needs_input` 时提供 1–3 个具体问题。

服务端负责校验列存在性、列角色、方法必需参数、枚举和方法 claim ceiling。模型返回的自由文本不作为可执行计划。

## 4. 失败与调用边界

- 每次 `plan()` 最多调用 Provider 一次；schema 或语义不合法时返回确定性 `PlannerContractError`；
- 本切片使用假客户端验证，不发起真实 Provider 调用；
- 后续接入统一入口前，必须单独确定 provider 授权次数、失败呈现和是否允许一次显式 repair call；
- 本切片不切换 `/`，不改变当前显式方法入口。

## 5. 验收

- ready 计划只能引用画像内列，并满足方法字段与列角色；
- needs_input 不产生可执行 analysis kind；
- unsupported 不伪装为失败或随意 fallback；
- 自动规划不能选择 `exploratory_python`；
- 工具调用数量严格为一，文本回答不能绕过结构化合同；
- 原始用户问题保持不变，供后续生成 Commitment；
- 测试期间 Provider 调用次数为 0。

## 6. 实施结果

- 新增最小 `DatasetPlanningContext`，只包含文件身份、行数、列名、dtype 和服务端列角色，不发送原始行或样本值；
- 新增 `StructuredAnalysisPlanner`，只接受唯一 `submit_analysis_plan` 工具调用，自由文本不能成为可执行计划；
- ready 计划会校验方法目录、必需字段、列存在性、数值/时间角色、枚举、预测 horizon 和方法 claim ceiling；
- `needs_input` 与 `unsupported` 不产生可执行 route，自动规划明确禁止 `exploratory_python`；
- Planner 不能携带额外 Finding/结果字段，不能写运行事实或发布状态；
- 为共享 `LLMClient` 增加 `chat_once`：恰好一次请求、没有隐式重试；后续是否重试必须由外层显式决定并计入授权；
- 8 项 Planner 合同测试通过，其中 Provider 使用假客户端或 monkeypatch，真实 Provider 调用次数为 0；
- 本切片未接入 `/api/v2/analyze` 或工作台，显式方法入口行为不变。

## 7. 下一切片

Slice 5C2 应把 Planner 接到一个独立 preview/plan API，持久化规划请求与结果，并在 `ready` 时将服务端校验后的参数交给现有 Router。接入前还需明确：真实 Provider 的精确授权次数、失败时是否允许一次人工触发的 repair，以及 `needs_input` 的消息块与恢复合同。不得直接让 Planner 写 Commitment 完成状态或 Answer Block。
