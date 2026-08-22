# Data Agent V2 Slice 5C3C：工作台显式规划旅程

- **日期**：2026-08-13
- **状态**：Implemented（待提交）
- **基线提交**：`fbf031a`（`feat(v2): add recoverable planning input`）
- **分支**：`codex/data-agent-v2`

## 1. 目标

把服务端 Planner 接入 V2 Workbench，让缺少数据科学知识的用户可以通过一次明确点击由系统选择方法；现有手工方法选择继续保留为专家路径。

## 2. 用户旅程

```text
选择文件 + 输入问题
  -> 点击“估算系统规划（不调用模型）”
  -> 上传（如需要）
  -> 展示完整请求预计输入 token、模型窗口、输出预留和可用输入
  -> 点击“确认并开始分析（调用模型 1 次）”
  -> 服务端签发并消费一次授权
  -> ready: 自动执行持久化计划
  -> needs_input: 显示稳定问题块
       -> 用户填写完整回答
       -> 点击“保存回答并估算（不调用模型）”
       -> 完整保存回答并展示新请求 token 预算
       -> 点击“确认并重新规划（调用模型 1 次）”
       -> 新授权 + 派生计划
       -> ready 后自动执行
```

## 3. 不变量

- 页面加载、文件选择、上传、刷新恢复、错误恢复不签发授权、不调用 Provider；
- 每次可能调用 Planner 的动作都由带有“调用模型 1 次”字样的独立点击触发；
- token 估算复用 Planner 实际 system、messages 和 tools；授权签发及 plan 创建前均重新校验；
- 只按实际模型上下文窗口减去配置的 Provider 输出上限判断；不设置回答字符、成本或任意 token 门槛；
- 超过模型能力返回 `planning_context_too_large`，包含预计输入、模型窗口、输出预留和可用输入，不裁剪、不摘要；
- 规划相关 JSON 请求保留 1 MiB 传输安全上限，该限制不适用于文件上传；
- ready plan 自动执行结构化分析，因为方法工具不是用户许可门；
- `needs_input` 回答不设应用层字符或成本限制，不截断、不自动摘要；
- UI 不信任或提交模型选择的方法参数，分析执行只提交 `plan_id`；
- 刷新可恢复 source plan、问题块和已持久化回答；
- Provider 失败不自动重试；用户再次点击会创建新的 request identity 和新授权。

## 4. 非目标

- 不切换根入口；
- 不删除专家手工方法入口；
- 不调用真实 Provider；
- 不将静态页面测试或浏览器旅程等同于数据分析产品验收。

## 5. 实施结果

- 工作台新增系统规划主按钮，标签明确声明一次模型调用；专家手工方法入口继续保留；
- 系统规划改为“先估算、后确认”两阶段；估算不签发授权，确认按钮才允许一次模型调用；
- 工作台在授权前展示完整请求 token 预算；`needs_input` 回答同样先完整保存和估算，再由独立按钮确认；
- 新增 `PlanningContextBudget` 和 `/api/v2/planning-estimates`；估算与 Provider 请求共用同一个 Planner request builder；
- 当前官方 DeepSeek API 的 `deepseek-v4-flash/pro` 使用 1,000,000 token 上下文；其他 LiteLLM 未识别模型要求配置 `MODEL_CONTEXT_WINDOW`，不使用猜测默认值；
- Provider Authorization Ledger 保存签发时的 planning context 预算；plan 创建前再次计算，超限不会消费授权或调用 Planner；
- 上传与规划分离，只有规划按钮事件会签发服务端授权并创建 plan；
- ready plan 只以 `plan_id` 自动执行，前端不提交或覆盖模型选择的方法参数；
- `needs_input` 稳定问题块在页面内显示，回答不设置 `maxlength`，保存后由第二次明确点击签发新授权并派生 plan；
- plan、planning input 和 turn identity 写入 URL，刷新按 `turn_id` 或 `plan_id` 恢复，不自动执行或重新规划；
- 网络响应丢失时保留 client action/request identity，显式重试恢复旧记录而不是增加 Provider 调用；
- JavaScript 语法、工作台静态契约、完整 V2 与配置回归共 234 项通过；
- 本地浏览器假 Planner 两阶段旅程：首次估算显示 296 / 1,000,000 tokens，授权事件为 0；确认后才签发授权；接受并完整保存 4060 字符回答，回答后估算为 5080 tokens，估算阶段授权事件不增加；再次确认后完成 `needs_input -> ready -> SSE analysis`，控制台无错误；
- 浏览器旅程使用假 Planner，真实 Provider 调用次数为 0。

## 6. 下一切片

Slice 5C4 应把 Planner 旅程纳入新的真实 Provider 分析验收设计，并评估 V2 Workbench 是否具备替换根入口的条件。真实调用必须由用户另行给出精确次数授权；在此之前先补齐 provider-neutral 浏览器回归和失败/重试页面状态测试。
