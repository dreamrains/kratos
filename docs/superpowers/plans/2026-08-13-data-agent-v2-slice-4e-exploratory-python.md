# Data Agent V2 Slice 4E：探索性 Python 补充

- **日期**：2026-08-13
- **状态**：Implemented; pending commit
- **基线提交**：`3786139`（`feat(v2): add multi-finding synthesis slice`）
- **分支**：`codex/data-agent-v2`
- **上位设计**：[`2026-08-13-data-agent-v2-architecture-design.md`](../specs/2026-08-13-data-agent-v2-architecture-design.md)

## 1. 目标

完成 Slice 4 中尚未落地的自由 Python 边界：用户可以在一个已经由结构化方法回答的描述性问题后，运行显式提供的只读探索代码；结果作为可追溯的 supplemental artifact 和明确标注的 exploratory 答案块展示。

自由 Python 不是 ResultContract 方法，不能替代结构化方法，也不能因为输出了数字就升级为 Finding。

## 2. 硬不变量

1. 核心 Commitment 只接受 `analysis.describe` 的结构化 Finding；`exploration.python` 不在接受能力中。
2. Python 成功、失败、拒绝或超时均不改变核心 Commitment 的投影结果。
3. Python 输出只写 Execution Journal 和 `ExploratoryArtifact`，不得写 Evidence Ledger。
4. supplemental 答案块必须校准为 `exploratory`，不得声明 `claim_class` 或 `canonical_values`。
5. 执行只接收当前不可变分析副本的深拷贝；禁止 import、文件/网络读取、文件写入、反射和 dunder 访问。
6. 执行进程有硬超时；超时后终止子进程，不依赖无法取消的线程。
7. 输出与表达式结果均有长度上限；持久化代码摘要而不是原始代码。
8. 不为方法执行请求用户许可；代码和探索目的由用户在调用时显式提供。

## 3. 最小纵向旅程

1. 上传单个文件；
2. 注册 raw，并派生不可变 analysis 副本；
3. 用 `analysis.describe` 生成一个 core Finding；
4. 从事实计算核心 Commitment 已可发布；
5. 在隔离子进程对 analysis 深拷贝执行探索代码；
6. 追加探索执行事件并持久化 `ExploratoryArtifact`；
7. 发布“直接回答 / 方法边界 / 探索性补充”三个块；
8. SSE 显示结构化分析与探索执行的不同身份；刷新恢复块和补充产物。

## 4. 失败隔离

- 安全拒绝、语法/运行错误和超时只产生探索失败事件与具体限制块；
- 核心描述结论仍发布；
- 不把探索失败包装成数据分析受限；
- 不在失败后自动重试或改写用户代码。

## 5. 验收

- owner tests：成功、危险代码拒绝、硬超时、输出截断、artifact 不可变；
- runtime tests：Ledger 只有结构化 Finding，探索能力不能推进承诺，失败不删除核心结论；
- API/browser tests：真实 SSE、exploratory 校准、刷新恢复 supplemental artifact；
- 全量 V2 回归通过；
- 不调用真实 provider，不执行旧 Gate E/F，不接管主页面。

## 6. 本切片验收记录

- RED 契约先因 `exploratory` 与 `slice4e` 尚不存在而失败，随后实现转绿；
- 聚焦执行、运行时、API、页面和答案校准回归：`19 passed`；
- 全量 V2 回归：`139 passed`；
- JavaScript 语法检查、Python compileall 与 `git diff --check` 通过；
- 真实浏览器旅程显示结构化描述与探索 Python 两套独立工具进度，最终发布 3 个答案块；
- 刷新前后均为 3 个块，且始终只有 1 个 `data-calibration=exploratory` 块；
- 浏览器中位数输出被明确标注为“不作为结论证据”，Evidence Ledger 仍只有结构化 `analysis.describe` Finding；
- 本轮浏览器会话、上传副本、日志与本地服务已清理；
- 未调用真实 provider，未执行旧 Gate E/F，也不声明旧主页面或产品整体已经恢复。
