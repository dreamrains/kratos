# 路线 A 纵向切片实施计划（2026-08-25 修订）

> **本文件是当前唯一实施计划。Gate A 已由用户于 2026-08-25 确认，Slice 0 已实施并进入收口验收。** 2026-08-23 版横向 R0–R6 计划已被本版替代；旧版“按任务自动提交”“基线测试已绿”“先搭多层基础设施再做真实闭环”等表述不再有效。
>
> 本计划不授权真实 Provider 调用、提交、合并、推送、部署、根路由切换、历史数据迁移或删除旧实现。以上动作均需用户单独确认。

- 审阅日期：2026-08-25
- 当前分支：`rebuild`
- 当前 HEAD：`6ae6abe0a49d5c0d42b559645127b14a5ea7f9a2`
- 7 月 13 日源码底座：`HEAD:src` 与 `1d57061:src` tree 均为 `f3769ad16f903e644995ab8810031cec03f7e10b`
- 当前受控源码清单摘要：`sha256:c6aa82e6361db126cb0ad6adde4bb64ad4330bf3c9049ba0f0dd3553988f5500`（298 个 Git 条目；范围为 `src tests scripts main.py pyproject.toml uv.lock start.bat start.sh`）
- Slice 0 当前源码摘要：`sha256:f604620595eec095e472623463d5cc3cecbc719877bb6eae2256ad9e549fd471`（307 个当前存在的受控源码条目；收据见 [Slice 0 工程基线收据](../../audit/2026-08-25-slice-0-engineering-baseline.md)）
- 当前工作树进入审阅前已有未跟踪目录：`artifacts/`、`tmp/`；必须保留，不纳入本次清理

## 0. 决策依据

本计划与以下三份 Gate A 台账共同构成实施边界：

1. [7 月 13 日能力保全台账](../../audit/2026-08-25-capability-preservation-ledger.md)：定义保留、强化、合并、内部化和删除的能力；覆盖 Gate A 时的 76 个模型工具及非工具 Agent/Web/资产能力。Slice 0 按台账删除 3 个 deprecated 报告工具后，当前正式工具面为 73 项。
2. [7 月以来提交取舍台账](../../audit/2026-08-25-post-july-commit-decision-ledger.md)：覆盖 7 月恢复线 101 个提交和 V2 线 73 个提交；V2 整体弃用，局部算法、schema、测试和诊断只作供体。
3. [历史故障与真实数据验收矩阵](../../audit/2026-08-25-failure-acceptance-matrix.md)：把 F01–F33 事故、当前 9 个真实文件、R01–R09 场景和分层发布证据转成验收门禁。

其他输入：

- `docs/audit/2026-08-23-v1-0713-base-real-data-test.md`
- `docs/archive/v2/quality-system-test.md`
- `docs/archive/v2/parity-audit.md`
- `docs/archive/v2/july-overhaul-audit.md`
- `docs/archive/v2/codex-review-and-revised-plan.md`
- `docs/archive/v2/system-design-iteration-plan.md`
- `docs/archive/v2/architecture-design.md`
- `docs/archive/v2/release-closure.md`
- `docs/archive/v2-retrospective.md`
- 7 月以来两条提交历史与当前源码、测试、依赖和真实文件目录

旧会话和其他模型整理的文档只作为问题发现与对比依据，不作为质量真值。所有数值、功能和发布结论需由当前源码重新验证。

## 1. 已确认的基线真相

### 1.1 源码底座没有被 V2 覆盖

当前 `src` tree 与 7 月 13 日目标提交一致，因此后续直接在现有 AgentLoop/Web 入口上改造，不创建第二个产品、第二个 planner 或 `/v2` 兼容入口。

### 1.2 完整测试当前不绿

完整测试先后暴露两批旧真实数据契约失败：

- `1073 passed, 12 skipped, 5 failed`，在 49% 因 `maxfail=5` 停止；
- 排除首批两文件后为 `1146 passed, 12 skipped, 5 failed`，在 53% 停止；
- 排除全部 8 个引用失效真实文件/绝对路径的测试文件后，核心基线为 `1846 passed, 3 skipped`。

因此 Slice 0 的首要任务是修复测试真相，而不是把“核心子集通过”描述为“全量通过”。

### 1.3 当前依赖与设计存在未决差异

现有依赖包含 `statsmodels`、`scikit-learn`、`shap`、`prophet`、`plotly`、`openpyxl` 等，但没有 `pyarrow`。任何 Parquet 数据版本方案必须先做依赖、安装体积、启动和平台预检；未通过前不能成为架构既成事实。

当前 registry 静态发现 76 个工具，同时存在：

- `record_insight_record` 死引用；
- 已标记 deprecated 的报告生成器仍残留于代码、prompt 或测试；
- Workbench 前后端仍承载用户要求删除的内容。

这些问题进入 Slice 0/6，不用兼容层保留。

## 2. 不再重蹈覆辙的架构纪律

1. **单产品入口。** 所有新能力接入现有 AgentLoop、session、data workspace、tool registry、SSE 和 Web；禁止平行运行时。
2. **纵向切片。** 每个切片都从上传/提问开始，经过真实工具、证据、答案和 Web 展示到产出结束；不能连续数月只搭横向底座。
3. **能力先保全，合并后置。** 76 个工具和非工具能力先证明保留/可达；重复接口只有在行为等价和迁移测试通过后才能合并。
4. **确定性计算作为工具供体。** V2 的分组、时间、因子、预测等算法可以提取为现有 registry 工具或共享库，不能带入 V2 planner/store/product shell。
5. **单一身份链。** session → turn/task → logical dataset/version → tool call/result → evidence/claim → chart/artifact 使用同一组稳定 identity，禁止审计层自建第二份事实。
6. **原始数据不可变。** 转换、清洗、聚合生成派生版本；材料性语义选择才询问用户，安全计算不确认。
7. **真实完成与发布。** 工具调用、阶段完成或模型自述都不能单独标记任务完成；verified conclusion 只由成功计算和绑定完整的证据投影。
8. **允许诚实降级，不允许静默删题。** 高级方法不可用时保留已验证结果，明确未覆盖范围、原因、替代路径和证据等级。
9. **图表按问题触发。** 不强制通用图；图表必须引用已执行计算、稳定数据版本和持久化 artifact。
10. **source-bound 验收。** 旧截图、旧录像、fixture、`test_client()` 或其他源码摘要的收据不代表当前候选通过。
11. **无兼容债。** 新结构确认后一次迁移并删除废弃入口/字段/测试引用；不长期维护双写和别名。
12. **授权边界不扩张。** 文档实施不自动授权 Provider、Git 写操作、部署、数据删除或生产切换。

## 3. 状态与 Gate

| Gate/切片 | 目标 | 当前状态 | 放行人/证据 |
|---|---|---|---|
| Gate A | 三份台账 + 本计划审阅 | **已通过** | 用户于 2026-08-25 确认并授权开始 Slice 0 |
| Slice 0 | 测试真相、依赖预检、RED 事故与表面清理 | **已通过** | [工程基线收据](../../audit/2026-08-25-slice-0-engineering-baseline.md)：2181 passed；73 项工具面；离线真实浏览器 L3 smoke；Provider 0 |
| Slice 1 | 单文件可信分析黄金链路 | **已完成（Provider 除外）** | [R07 收据](../../audit/2026-08-25-slice-1-r07-freeze.md)：真实 D03 上传、本地 Web、回执链、证据/图表/确认投影、刷新、导出与停止；Provider 0 |
| Slice 2 | 脏数据、配对分析、版本和确认边界 | **已完成（Provider 除外）** | [R02/R03 冻结收据](../../audit/2026-08-25-slice-2-r02-r03-freeze.md)：真实 D04/D05、本地 Web 浏览器、版本血缘、配对和脏数值契约；Provider 0 |
| Slice 3 | 时间、曲线、因子、预测等统计能力 | **已完成（Provider 除外）** | [方法完整性冻结收据](../../audit/2026-08-25-slice-3-method-integrity-freeze.md)：D09 曲线 oracle、回测预测、因素降级、模型 identity 与本地 Web 上传；Provider 0 |
| Slice 4 | 多文件综合、关系与范围完整性 | **已完成（Provider 除外）** | [多文件完整性冻结收据](../../audit/2026-08-25-slice-4-multifile-integrity-freeze.md)：R04 三源对齐、多父血缘、R05 many-to-many 拒绝；Provider 0 |
| Slice 5 | 开放分析、建议、知识/记忆与长上下文 | 未开始 | R06、R08、R09；探索与 verified 分离 |
| Slice 6 | Workbench 精简与 Web 交互收口 | 未开始 | 只保留已验证结论、产出、导出；5 条浏览器旅程 |
| Slice 7 | 历史、回退、分支、迁移与完整回归 | 未开始 | 无损迁移 dry-run；全部旧切片回归 |
| Gate C | 真实 Provider 冻结与授权 | 未开始 | 用户确认精确模型、prompt、数据、调用次数、零重试 |
| Gate D | 发布候选审阅 | 未开始 | 当前 digest 的 L0–L4 收据；用户决定是否进入部署流程 |

每个切片结束时停止并交付：源码摘要、工作树、改动、测试、未通过项、真实调用消耗（若有）、风险和下一切片提案。不会因计划写了“下一步”就自动提交或继续高风险动作。

## 4. Slice 0 — 恢复可相信的工程基线

### 目标

让后续任何“通过/失败”陈述都可复算，并把历史事故先变成会失败的测试。只做共享契约和明显死引用清理，不改变产品分析策略。

### 实施内容

1. 以当前实际目录 `reference/test_doc` 建立唯一 manifest：9 个实际文件、内容指纹、sheet、用途、敏感边界；记录用户最初给出的 `reference/test/_doc` 当前不存在，并移除测试中的仓库外绝对路径和旧文件名。
2. 修复 8 个陈旧真实数据测试，使“文件缺失”“测试前置失败”“产品行为失败”有不同错误。
3. 固定 portable source digest 算法及纳入范围；验证不同 checkout/换行环境一致。
4. 为 F01–F33 建立测试索引；优先实现 completion、publication、binding、chart、artifact、SSE、multi-file、dirty numeric、method routing 和 dependency preflight 的 RED。
5. 对 Gate A 时的 76 工具建立 registry/prompt/schema/tests 一致性检查；删除 `record_insight_record` 死引用，并按已确认边界移除 3 个 deprecated 报告工具，形成 73 项当前工具面。
6. 处理 deprecated 报告生成器：证明主回答+统一输出服务覆盖后一次删除 registry/prompt/测试引用，不保留别名。
7. 预检 `pyarrow` 方案；若收益不足或依赖不可接受，选择无需新增重依赖且满足不可变/血缘的格式，记录客观基准。
8. 建立当前浏览器启动、构建、vendor、SSE 和下载的最小 smoke，但不把它当分析质量通过。

### 验收

- 完整测试不再因旧真实文件名或机器路径失败；
- 核心测试、真实数据前置和浏览器 smoke 分开报告；
- 全部保留能力都有测试/可达性责任人或明确后续切片；
- 依赖声明与实际可导入能力一致；
- 无业务分析能力删除，无 Provider 调用。

## 5. Slice 1 — 单文件可信分析黄金链路

### 用户旅程

在现有 Web 上传 D03 的冻结小样，提出一个包含趋势、异常、解释和图表的分析问题；系统完成数据理解、计划、真实工具计算、证据、最终回答、已验证结论、产出、导出和刷新恢复。

### 实施重点

1. 统一 turn obligation：用户问题、数据范围、必需计算、可选增强和停止条件。
2. 修复“阶段成功=任务完成”“工具成功=verified”“final 先于持久化”等公共契约。
3. 将 evidence 从工具结果自动投影，模型不能自证；答案中的数值、结论卡、图表和导出绑定同一 identity。
4. 实现按问题触发的 create_chart 与 artifact 持久化；刷新后恢复。
5. 回答结构保留 7 月 13 日的信息量优势：先结论、依据、So-What、限制、建议；不复制旧答案，不编造统计量。
6. 运行真实 Web 进程和浏览器 R07，覆盖长回答、停止、刷新和下载的最小组合。

### 验收

- F03–F05、F09–F13、F15、F24、F29、F31 的适用项通过；
- R07 的数值可复算，核心质量维度为 4，其余适用维度 ≥3；
- Workbench 中 verified conclusion 与正文/图表/导出一致；
- 失败时可恢复且不产生假完成。

## 6. Slice 2 — 脏数据、配对分析、版本与确认边界

### 用户旅程

- R02：D04 购卡前后分析，自动识别同一用户配对与窗口截断，给出主 estimand、补充口径、分群和安全建议。
- R03：D05 脏数值与组合单位分析，安全转换后直接计算，不因方法风险弹确认。

### 实施重点

1. raw snapshot + copy-on-write analysis version + 多父血缘；原始文件只读。
2. 类型建议与执行分离；高成功率安全转换自动创建派生版本，披露转换率与损失行；材料损失进入 `needs_input`。
3. 提取/重写 V2 的配对识别、多组比较和 group ranking 算法为现有工具能力。
4. 建立 metric/denominator/unit/window/cohort/estimand identity；配对主口径和描述性补充口径不得混写。
5. 确认只用于用户独占语义或外部副作用，不用于安全、非破坏计算。

### 验收

- F07、F08、F16、F18、F19、F21 通过；
- raw 指纹不变，派生版本可回溯、刷新和回退；
- D04/D05 真实数据离线 oracle 与真实浏览器旅程通过；
- 不用兼容别名保留旧 data workspace 字段。

## 7. Slice 3 — 统计方法深度与确定性供体

### 范围

在保留既有统计/ML 工具的前提下，补强真正缺失或错误的计算路径：

- curve fitting：幂律/指数/对数等候选、回测/诊断、外推边界；
- paired/independent/multi-group：分析单位、重复观测和多重比较；
- factor/regression：恒等式、共享分子分母、时间趋势、共线性、稳健误差和零结果降级；
- forecast/time series：完整周期、基线、回测、区间和失败降级；
- classification/SHAP/what-if：只有前置模型和数据身份完整时可达。

### 实施方式

1. 从提交台账 A 类供体中逐函数提取算法和测试，不取 V2 planner/slice/store/answer/workbench。
2. 复用现有工具名或在确有独立语义时增加能力；新增前先证明原工具无法表达，禁止另造九个重叠入口。
3. 所有结果使用统一 ToolResult、method assumptions、effective N、effect/interval、limitations 和 data identity。
4. `run_python` 继续用于开放探索；只有确定性重放成功的结果可晋升 verified。
5. provider-neutral 路由测试证明 Agent 会选到能力，而不只做函数单测。

### 验收

- R01 及 R09 的适用子场景通过；
- F19、F20、F22、F23、F32 通过；
- 旧 `最强砖块记录.xlsx` 场景先用冻结 fixture 做恒等式/共线性/降级 oracle，不宣称真实数据已复测；
- 不因新增方法缩减既有 76 工具面。

## 8. Slice 4 — 多文件综合与范围完整性

### 用户旅程

- R04：D06+D07+D08 按日期对齐，分析广告、内购、结构迁移和关系；
- R05：D02+D03 订单与优惠关系、分母和可行动分群。

### 实施重点

1. 会话内多个逻辑数据集同时可见，不用“最后上传文件”覆盖前一个。
2. 显式 join keys、时间粒度、覆盖窗口、重复键、缺失区间和多父血缘。
3. planner/Agent obligation 逐项对账用户问题；缺文件或不可连接时必须列出未覆盖部分、原因和可继续路径。
4. 图表与结论可引用多数据集 identity；刷新、重发、分支后关系不丢失。
5. 防止 stale task/dataset binding 和旧事件推进新轮。

### 验收

- F11、F16、F17、F18、F25、F28 通过；
- R04/R05 无静默收窄；关系、占比和趋势都可复算；
- 多文件上传、删除/替换其中一个文件、刷新和导出有真实浏览器覆盖。

## 9. Slice 5 — 开放分析、建议、知识与长会话

### 范围

1. `tool_search` 让高级工具动态可达，默认工具组不能形成事实阉割。
2. `run_python` 沙箱、超时、无网络/任意文件边界、探索标记和确定性重放。
3. 建议分为证据直接支持、推断性、提示性三类；用户明确索要建议时不因缺因果证据而全局清零。
4. 竞争解释与区分证据进入回答纪律；删除 token-overlap 假设判定。
5. 保留知识、记忆候选→确认、来源与冲突；长上下文压缩后身份和义务不丢失。
6. 保留闲聊、知识问答、分析咨询、无数据澄清和结果追问，不让所有输入都进入分析流水线。

### 验收

- R06、R08、R09 通过；
- F06、F21–F25、F30、F32 通过；
- 会话 A 确认知识/记忆，会话 B 正确使用且披露来源/冲突；
- 长会话压缩、刷新和追问不引用旧轮数据。

## 10. Slice 6 — Workbench 精简与 Web 交互收口

核心分析质量优先于视觉微调，但用户明确要求的 Workbench 删除属于产品架构收口，必须做前后端一致删除。

### 保留

- 当前分析 tab 中的“已验证结论”；
- 产出列表、详情和持久链接；
- HTML/Markdown/数据等统一导出。

### 删除

- 仍不确定；
- 建议下一步；
- 可信度摘要；
- 分析范围；
- 完整叙述；
- 数据理解/关系下钻；
- 确认 banner 等仅属于 Workbench 投影的非目标内容。

删除范围包括 UI、前端状态、后端 projection/API、prompt、schema、样式和测试；若某数据仍为主对话或审计所需，应留在主链的内部契约，不再作为 Workbench 功能。不会保留隐藏入口或兼容字段。

### 同批修复

- 任务面板真实状态与折叠稳定；
- SSE 进度/正文/终态；
- Plotly/Markdown/表格/KaTeX/Mermaid 长内容；
- 停止、确认、刷新恢复；
- 未上传/上传失败文案；
- 桌面和窄屏核心路径。

### 验收

运行当前源码的真实服务进程和真实浏览器，至少覆盖 R07、R02、R03、R04、长回答+停止+刷新+下载五条旅程；console、network、DOM 内容、截图和产物下载均留 source-bound 收据。

## 11. Slice 7 — 历史、分支、迁移与完整回归

### 实施内容

1. 补齐/验证回退重发、branch session、项目、任务、知识/记忆、Skills/MCP、CLI 与 Web 共用同一运行语义。
2. 为新 identity/data version/artifact 结构编写一次性迁移；先 dry-run，输出逐类计数、缺失引用和内容 hash。
3. 迁移不做双写兼容；历史缺原文件会话只读并明确状态，不能伪造重建。
4. 重跑全部旧切片、F01–F33、R01–R09、9 文件离线矩阵和 5 条浏览器旅程。
5. 形成 release source digest、环境清单、测试结果、blocked 项与回滚材料；不自动发布。

### 验收

- F01、F02、F26–F33 全部适用项通过；
- 能力保全台账每项都有实现/删除证据；
- 迁移前后计数、引用和内容一致；
- 当前 source digest 的 L0–L3 完整，才可申请 Gate C。

## 12. Gate C — 真实 Provider 验证（需要另行授权）

### 候选批次

- 主模型：R01–R07 的高价值分析旅程；
- 异构模型：从 R01、R02、R04、R07 中选择高风险子集，验证方法/范围/发布语义，而不是逐字答案一致；
- R08 主要由 provider-neutral 与 Web 验证，是否消耗真实调用另行决定；
- R09 只选真实适用的高级能力，不为覆盖而强行调用。

在申请授权前先用离线回放测出每个旅程的实际调用结构，然后向用户提交精确冻结单：模型、prompt、文件 hash、场景、每场景调用次数和总次数。授权格式必须是可计数的；任何失败立即停止整批，不重试、不换模型、不修复后补跑。

### 评估

- 零容忍 F 项不得出现；
- 数据范围/绑定、数值正确、方法适配、完成/发布真实性必须 4/4；
- 其余适用维度不低于 3/4；
- 规划稳定性按安全、方法、范围、路由和结果语义判断，不要求措辞或 advisory 风险标签完全相同；
- 现有会话仅作差异对照，不作真值。

## 13. Gate D — 发布候选，而非自动发布

只有以下条件全部满足，才能称为“当前源码的本地发布候选”：

1. 三份台账逐项闭环；
2. 完整测试、9 文件离线矩阵、真实 Web 浏览器和获授权 Provider 批次通过；
3. 收据均绑定同一个 release source digest；
4. 工作树状态、依赖、配置、模型和数据 manifest 明确；
5. 无未审阅兼容层、平行运行时、死入口或迁移缺口；
6. 用户审阅剩余风险并决定是否提交、合并、推送或部署。

本地发布候选不等于 staging 或 production 已验证。部署和外部环境验收另立授权与收据。

## 14. 每切片的固定交付格式

每个切片交付必须包含：

1. 分支、HEAD、tracked/modified/untracked、受控 source digest；
2. 本切片触达的能力 ID、故障 ID、真实场景 ID；
3. 实际修改和明确未修改内容；
4. RED 证据、实现后测试、完整回归及排除项；
5. 本地真实 Web 进程和浏览器证据（适用时）；
6. Provider 调用的授权与实际精确次数（没有则明确为 0）；
7. 新发现的问题、风险、假设与下一切片提案；
8. 是否需要 Git、迁移、删除、部署或下一 Provider 批次的单独授权。

## 15. Gate A 已确认事项

用户已于 2026-08-25 确认以下边界，并授权只实施 Slice 0：

1. 是否接受 V2 整体弃用、仅将确定性算法/schema/测试作为供体；
2. 是否接受本计划从横向阶段改为 Slice 0–7 纵向切片；
3. 能力台账中“内部化流程元工具、合并数据导出、删除 deprecated 报告模型工具”的边界是否合理；
4. Workbench 的保留/删除范围是否与需求完全一致；
5. F01–F33、当前 9 文件和 R01–R09 是否有遗漏；
6. 是否接受每个切片都先做 L0–L3，Provider 另行冻结精确次数后授权；
7. 是否同意 Gate A 通过后的第一项代码工作仅为 Slice 0，不提前大规模迁移统计引擎或改 Web 外观。
