# 中文数据分析 Agent 可信发布架构重置计划

日期：2026-09-22
状态：实施中；2026-09-24 当前检查点见 §0.1（原始设计基线保留作历史）
适用仓库：`D:\Project\Daily\data-agent`
编写时基线：`main@5176c41103ee1b1c77b4b44331d8225fb49890be`

> 本文件是下一轮全新对话的唯一任务入口。执行者必须先阅读仓库根目录
> `AGENTS.md`、本文件以及本文件引用的三份原始计划，再检查实际 HEAD、工作树和
> 证据目录。不得从历史聊天摘要中自行补全设计，不得直接沿用旧的词表修补方案。

### 0.1 当前执行检查点（2026-09-24；每次续接须重新核实）

- `main@b7e1f981b395a3a5007998013422886b8958487e`；本次复核工作树无 tracked/untracked 改动，`main` 比 `origin/main` ahead 60；没有 push。`git status` 对本机全局 ignore 与 `.pytest_cache` 报权限警告，不应将其解释为用户改动或测试成功。
- Phase 0—4 已有各自 E1/E2 收据；Phase 5 **只有离线 `publication_audit.v1` 校验器，没有真实 Shadow 调度**。Phase 6 经用户批准仅启动 A（可信核心重建）＋B（纯宿主 claim 级动作）的默认关闭、纯离线准备；C（Shadow 调度与校准）和 D（正式处置/默认发布切换）各有独立进入门。不能把 A+B 的 E2 记作 Phase 5/6 完成。
- A+B 已提交 `39246fc`、`b7e1f98`：同一 packet 的可信核心预览、当前回执范围、artifact-only 图表、受同指标 `compare_periods` 宿主复算约束的描述性假设关系，以及 `publication_effect=none` 的动作模拟。正式 AgentLoop/发布默认未接入离线投影，离线 packet 禁止进模型 prompt。最终 fresh `tmp/tprb20`：2913 passed、1 skipped、16 warnings、0 failures，JUnit SHA256 `1506832913636E32A2569E7C54D46149C60B806D7865F70100704DFE3025AA18`；Provider transport forbidden，实际 Provider initiated 0。无当前 HEAD 的完整浏览器 E3、真实 Provider E4、staging/production 证据。
- 当前两侧未闭合：现行完整候选可放行有效 binding 旁独立无据 `99%`；直接改用现有可信核心，又会清空 R11 正确 D7/无 D30 句、R4 M03 六来源业务说明/M04 部分关系、R16 完整批次已通过的 M05 方法上下文。R4 是中断批次，不能独占 oracle；R7—R21、R16 完整批次及本地旧会话须共同校准。AC17 模型自述“缺少分母”没有宿主证明，不计作正确缺口损失。
- 详细当前证据与边界：`docs/audit/2026-09-24-trust-reset-dual-track-calibration.md`、`docs/audit/2026-09-24-trust-reset-phase6-entry-assessment.md`、`docs/audit/2026-09-24-trust-reset-offline-core-projection.md`、`docs/audit/2026-09-23-trust-reset-implementation-handoff.md`。旧 §2.3、§11、§12 是**编写时历史快照/原始启动指令**，不代表当前仍有那两份未跟踪文件，也不撤销用户后来明确授予的 A+B 离线实施范围。
- 下一切片的跨历史正反矩阵、R4 M03 “综合结果存在但终局 packet 未选中”结构缝隙与测试/停止门，见 `docs/audit/2026-09-24-trust-reset-cross-history-gate.md`；该旧轨迹须在当前 HEAD 的最小化形状复现，不能预判为现行缺陷。
- 在 `ac84dd8` 后的 A+B 小切片，当前构包器也证实 `synthesize_time_series` 被允许工具集合排除；仅在显式选中回执的默认关闭离线 packet 中纳入综合事实组，普通构包/AgentLoop 不变。RED、17 项定向与最终 fresh `tmp/tprb22` 2914 passed/1 skipped/16 warnings 见上述跨历史记录 §6。该结果只是 E2，原始字段不授权 `answered`，也不证明 R4 旧终局选择机制已全修。
- 后续 A+B 离线数值切片发现综合回执本身只有覆盖/版本元数据、没有两日金额；只在显式 `offline_workspace` 的默认关闭离线 packet 中核对六源及派生帧当前身份和实际指纹，再读取既有 copy-on-write 派生结果复算逐源变化，不解析旧 `preview_data` 文本、不跨来源合计、不授权 `answered`。RED/GREEN 与 fresh `tmp/tprb23` 2918 passed/1 skipped 见跨历史记录 §7；AgentLoop/正式发布/Shadow 均未改变。A 的价值保留和正式误放双门仍未完成。

## 0. 本次重置要解决什么

项目原始目标是一个**可用的中文数据分析 Agent**：能够基于上传数据给出有价值、
可信、不过度打扰用户、可审计的分析结果。

此前多轮优化没有持续逼近这个目标。系统逐渐形成了以下错误闭环：

1. 模型先生成开放式自然语言；
2. 宿主用关键词和正则反向猜测模型语义；
3. 计划、任务、确认、发布门和验收 oracle 对散文层层设卡；
4. 真实模型每产生一种合法新措辞，就触发新的误拒或误放；
5. 每轮再补词、补模式、补状态，进而制造新的冲突和失败路径；
6. 离线测试数量持续增长，但真实浏览器批次通过率没有随之提高。

这不是继续补几个 Bug 就能解决的问题。根因是**权威所有权放错了层**：自然语言散文
被当作事实载体，宿主又试图用封闭类工具理解开放语义。合法措辞空间不可枚举，因此
这种实现和验收方式不可能通过追加词表收敛。

本轮重置的核心决定是：

> **结构化证据与 claim 是权威事实源；宿主验证并渲染权威内容；模型散文负责解释；
> LLM 审计负责开放语义质量检查，但不能覆盖确定性证据，也不能成为新的随机总审批门。**

## 1. 三份原始需求仍是上位约束

本计划不推翻三份原始计划，而是纠正实现对它们的偏离。

### 1.1 分析价值保留

来源：`docs/superpowers/plans/2026-09-06-analysis-value-preservation-plan.md`

必须继续满足：

- 允许发布有依据且明确标注的待验证解释；
- 允许发布有证据支持的条件性、可逆建议；
- 严格区分已观察事实、描述拟合、情景外推和经过验证的预测；
- 反证、新数据和版本变化能够使旧结论降级或失效；
- 不重建第二个 planner、EvidenceStore 或 Workbench runtime；
- 不得因为模型没有满足某种散文措辞而删除正确、可复算的结果。

### 1.2 意图澄清

来源：`docs/superpowers/plans/2026-09-07-intent-clarification-plan.md`

必须继续满足：

- 只有会改变计算或业务含义的真实业务缺口才可暂停用户；
- 方法许可、数据性质猜测、措辞偏好和技术字段不成为用户决策负担；
- 同一业务决定可在相同范围复用，范围变化才重新确认；
- skip 不构成授权；
- 不能靠关键词把用户原始请求缩窄；
- 确认系统不得形成一方法一审批或反复暂停的死循环。

### 1.3 回答内容优化

来源：`docs/superpowers/plans/2026-09-08-answer-content-optimization-plan.md`

必须继续满足：

- 用户明确提出的每个子问题都有回答，或有具体、诚实的缺口；
- 数值与口径绑定回执，正文保留必要的方法上下文；
- “未计算”“证据不足”“计算结果为零”严格分离；
- 关键词出现、任务 completed、模型自报不能作为覆盖证明；
- 规则不能可靠判断的自然语言语义应为 `unknown/unassessed` 或进入语义审计，
  不能伪装成确定性硬门；
- 新检查不得清除原本可以安全发布的观察事实。

## 2. 已确认的历史证据与边界

### 2.1 Git 与代码形态

- `d41d242` 一次横跨 23 个文件，增加 1248 行、删除 59 行，同时修改 loop、
  publication、LLM client、task manager、upload、SSE 和多组测试，是门层和恢复逻辑
  快速膨胀的明显节点。
- 编写本文件时，`src/data_agent/agent/publication_synthesis.py` 为 2136 行，源文件中有
  43 处 `re.compile`，并直接解析曲线、外推、显著性、同比、货币、未来窗口、来源、
  缺失值、覆盖和数值绑定等自然语言语义。
- `9dbba60` 后隔离 full-offline 曾达到 2812 项测试零失败，但随后的 R4 真实运行仍立即
  复现 M01、M02、M03 问题。离线绿已不能单独证明产品可用。

### 2.2 R4 是部分证据，不是完整验收

目录：`tmp/p08-glm-operator-20260922-r4`

冻结身份：

- source commit：`5176c41103ee1b1c77b4b44331d8225fb49890be`
- model：`openai/deepseek-flash`
- endpoint：`https://api.deepseek.com`
- call cap：90

R4 中途由用户叫停，不能报告为完整 M01—M06，也不能把 M05 报告为完整六轮或把 M06
报告为已验证。可以确认的证据如下：

- M01：分析内容基本满足原始目标，但“占位/演示数据还是真实值”的数据性质问题触发了
  不必要的确认挂起。继续补“真实值”词表不是根治。
- M02：两个候选的 D1—D7、三族参数、R²、验证缺口和 D30 情景值均有证据支持，却因
  “提到无数值的对数族”触发散文配对误拒，正确答案被删除。
- M03：conversation/publication 双产物恢复有效；但旧边界把单个完整用户轮的 27 条消息切成
  `early=1 + recent=26`，摘要只看到用户请求，因而失实声称没有助手输出。现有 R4 证据没有证明
  内存历史短于持久历史；Phase 1 应修完整 turn/reply group 边界以及 canonical revision/hash/CAS。
- M04：结构化竞争假设链路成功，证明结构化状态和宿主维护可以工作。
- M05：停止前的三轮保持 12/120 和单位边界；不是完整 M05 验收。
- M06：未执行。

### 2.3 编写时未提交文件的处理（历史快照）

编写本文件时已有两个用户/GLM 未提交文件：

- `docs/superpowers/plans/2026-09-22-trust-architecture-restructure.md`
- `tests/test_p08_trust_restructure.py`

当时它们必须原样保留，不得覆盖、删除或擅自提交；用户后来明确允许放弃/删除，现已不在工作树。本计划吸收其历史分析，但不接受以下两项
具体设计：

1. 不通过补 `真实值|真实业务值` 等词表修复确认挂起；确认必须按结构化业务缺口类型裁决。
2. 不允许正文保留“差异不显著”“缺失成本为零”“未来将持续上升”等无依据断言，随后仅靠
   末尾附录免责。宿主说明不能抵消正文中的错误或内部矛盾。

### 2.4 历史测试证据必须作为累积背景

阶段判断不得只引用最近一次 full-offline 或最近一个未完成 Provider 批次。实施与验收必须同时读取
仓库中可追溯的历史收据，并保持证据层级：

| 历史阶段 | 可复核测试背景 | 不能升级成什么 |
|---|---|---|
| 2026-08-25 Slice 0—7 | 全量 2181 passed/11 skipped；各切片定向 50—446 passed；本地 Flask/浏览器上传、持久化、Workbench、导出和 console 收据；Slice 3 全量曾挂起，旧 Web 脚本也曾在收集期失败 | 真实 Provider、当前源码发布候选 |
| 2026-08-27/28 本机全量收口 | 先出现 6 failed/2216 passed/9 skipped，再修复到 2342 passed/9 skipped，并完成 Provider-disabled 本机浏览器旅程 | 后续 source digest、自然模型质量、部署 |
| 2026-09-06 运行时基线 | 隔离 full-offline 2393 passed/3 skipped；Provider 网络强制禁用 | 浏览器或 Provider 验收 |
| 2026-09-08—20 内容与确认整合 | 2585、2569、2644、2713 等多次隔离全量，以及 129/268/285+/301 等定向回归；Provider-disabled B/IC/CONTENT 矩阵 | 历史或未来 E4 通过 |
| P08 R10/R11/R14/R16/R19/R21 | 多轮真实 Provider 失败轨迹，分别暴露散文误拒、结构化状态缺口、任务权威竞争、单位污染、上传/终态问题；完整失败或不完整批次均不得改写为通过 | 其他 commit、其他模型、staging/production |
| 2026-09-19—22 收口与 R4 | 2708、2717、2812 等 full-offline；R4 82 次已调度调用形成 M01—M05 部分真实轨迹，M06 未执行 | R4 完整矩阵或发布验收 |

这些记录是回归面和架构风险的背景，不是把旧绿灯平移到当前 HEAD。每阶段仍须在当前精确源码上产生新的
RED、定向 GREEN 和隔离回归收据；历史失败不得因后续局部绿灯被覆盖。

## 3. 根因与必须终止的旧模式

### 3.1 根因

当前系统让四种不同职责互相越界：

- 模型自由散文承担了事实存储职责；
- 正则承担了自然语言理解职责；
- 模型承担了宿主计划/任务簿记职责；
- 验收器把内容风格、流程合规与确定性正确混成一个阻断结论。

这造成了“正确答案被门删除、错误答案靠附录免责、模型忘记记账就无法发布、离线测试绿但
真实路径失败”等问题。

### 3.2 从本轮起禁止

- 禁止新增依赖自然语言同义词枚举的发布硬门；
- 禁止通过补一个新词修复确认类型；
- 禁止把 LLM 审计的一句 `pass/fail` 当作最高裁决；
- 禁止让审计 LLM 直接自由重写整篇终稿；
- 禁止用末尾免责声明抵消正文错误断言；
- 禁止模型必须先写对 plan/task JSON 才能发布独立、已验证事实；
- 禁止无限“审计→修订→再审计”循环；
- 禁止把真实 Provider E4 当作日常集成调试场；
- 禁止在一批 E4 中途修代码或局部重跑后冒充完整批次；
- 禁止增加新的浏览器框架、重复账本或隐藏模型调用。

## 4. 目标架构

### 4.1 单一规范会话历史

持久化 transcript/conversation 是唯一规范历史源。loop 内存只能是带 revision 的缓存，不能成为
第二事实源。

压缩流程必须：

1. 从规范历史读取完整消息和工具轨迹；
2. 记录输入 history revision/hash 和消息数量；
3. 生成摘要；
4. 写回前再次检查 revision；
5. revision 不一致时放弃本次压缩，不修改历史；
6. 摘要必须携带确定性 execution ledger；
7. 压缩失败不得破坏原对话、reply identity 或导出。

### 4.2 结构化 claim 是权威内容单元

不新建第二条 claim 通道。现有 `answer_bindings.v1` 已提供模型可生成、宿主可校验的
`blocks + exact_text + requirement_refs + fact_refs + derived_refs` 种子；Phase 2 必须在这个协议上向后兼容扩展，
而不是另起平行 schema。R4 M03 已产出 schema-shaped binding，现有源码也已有 prompt、parser 和数值一致性测试；
其确切 fence/digest 字段与宿主接纳状态须由回放测试固定，不能只凭转录文本推定。

每个 binding block 增加最小 claim 字段：

```json
{
  "claim_id": "claim_001",
  "exact_text": "可唯一定位的正文片段",
  "claim_type": "scenario_extrapolation",
  "status": "unvalidated",
  "requirement_refs": ["req_01"],
  "fact_refs": ["fact_01"],
  "derived_refs": ["quantity_d30_power"],
  "unit_status": "unknown",
  "provenance_status": "observed_from_uploaded_file",
  "validation_status": "no_holdout_no_backtest",
  "scope_id": "scope_01"
}
```

`claim_type` 至少覆盖：

- `observed_fact`
- `derived_metric`
- `comparison`
- `descriptive_fit`
- `scenario_extrapolation`
- `validated_prediction`
- `causal_explanation`
- `conditional_recommendation`
- `unassessed`

数值、单位、时间范围、来源、显著性、外推/预测状态等高风险事实必须来自结构化 claim 与回执，
不能只存在于自由散文。

### 4.3 宿主做确定性验证

宿主只裁决可封闭验证的事实：

- claim/receipt/fact ID 是否存在；
- 数值是否能从回执或参数重算；
- 单位、时间范围和来源状态是否已确认；
- scope 与数据版本是否一致；
- 工具调用、终态和事件是否配对；
- 导出、刷新和持久化产物是否存在；
- 权威 claim 是否有绑定；
- 压缩是否基于规范历史 revision。

确定性失败不能被 LLM 的“通过”覆盖。

### 4.4 宿主渲染权威事实

以下内容由宿主根据结构化字段生成正文块、表格或紧邻 claim 的披露，而不是事后追加宽泛
免责声明：

- 数据范围与来源状态；
- 数值和单位；
- 拟合族、参数、R²；
- 留出、回测、外部验证状态；
- 观察/拟合/情景/预测等级；
- 显著性检验是否执行；
- 条件建议的触发、停止和监控字段。

如果高风险 claim 未绑定，宿主必须选择以下之一：

- 不渲染该 claim；
- 将其结构化降级为 `unassessed`；
- 进入一次定向修订。

不得先显示确定语气的错误正文，再在末尾补一句“尚未验证”。

### 4.5 模型散文负责解释，不承担事实数据库职责

模型可以组织叙事、解释业务含义、连接已验证 claim、给出条件建议，但数值和高风险结论应通过
claim 引用或宿主占位符进入最终正文。模型自由文本不得成为唯一权威事实源。

### 4.6 确认按业务缺口类型裁决

允许暂停的类型只能是会改变计算或业务含义的封闭选择，例如：

- metric definition
- denominator
- time window
- file/data scope
- currency/cost scope
- destructive cleaning decision

以下问题不得仅因措辞命中而暂停：

- 是否演示/模板/真实数据；
- 是否允许某种分析方法；
- 如何称呼或如何排版；
- 模型自我保护式确认；
- 其他不影响当前已验证事实交付的问题。

这些问题应转成条件式说明，并继续交付当前可确定内容。

### 4.7 plan/task 变成宿主执行台账

宿主从工具调用、回执和数据版本自动推导执行 journal、claim 状态和未完成项。模型计划仅用于推理
和解释，不作为已验证事实发布许可证。

这里的“自动推导”有硬边界：journal 只能做**事后簿记**，记录已经执行的调用、已产生的回执、
已闭合/未闭合的证据义务和数据版本；可以复用 `turn_receipt_ids`、`analysis_state` 收据以及
`4a6493f`/`89623e6` 已建立的 plan authority/互斥体系。journal 不得生成目标、选择方法、安排步骤、
创建未来任务、决定下一工具或改变执行顺序；这些行为属于规划，若加入 journal 就会形成被禁止的第二 planner。
“journal 中存在未闭合项”本身也不是启动新工作的许可证，只能影响对应 claim 的 completed/gap/degraded 状态。

独立 claim 可以分别完成、降级或声明缺口；一个未完成任务不得无差别杀死全部已验证结果。

## 5. LLM 语义审计设计

### 5.1 定位

LLM 审计是**受证据约束的语义审稿人**，用于发现宿主难以用封闭规则判断的问题。它不是事实
来源、不是第二 planner、不是最终最高法官。

它适合检查：

- 相关性是否被写成因果性；
- 描述拟合是否被写成可信预测；
- 样本结论是否被扩大到总体；
- 结论强度是否超过证据等级；
- 正文与限制、验证状态是否矛盾；
- 用户明确子问题是否遗漏；
- 建议是否能从 claim 推出；
- “未计算/证据不足/结果为零”是否混淆；
- 表达是否清楚、可执行、保留必要边界。

它不得最终裁决：算术、文件存在、调用账本、回执 ID、单位确认、工具是否执行、事件是否配对等
确定性事实。

### 5.2 输入

审计模型只接收最小、明确分层的上下文：

- 用户原始问题和已确认的业务决定；
- 候选答案；
- claim registry；
- 经过裁剪的 evidence packet 与回执摘要；
- 版本化发布政策；
- 已由宿主确定的验证结果。

上传数据内容、工具输出和候选答案必须被标记为不可信数据，不得被解释为审计指令，防止 prompt
injection。

### 5.3 输出协议

审计结果必须使用版本化结构，不接受仅有散文的“通过/失败”：

```json
{
  "schema_version": "publication_audit.v1",
  "overall": "pass_with_findings",
  "findings": [
    {
      "finding_id": "finding_001",
      "claim_id": "claim_007",
      "dimension": "claim_strength",
      "severity": "high",
      "recommended_action": "downgrade",
      "evidence_refs": ["curve_receipt_01"],
      "reason": "仅支持描述拟合，尚无留出验证或回测"
    }
  ],
  "missing_requirements": [],
  "contradictions": []
}
```

宿主必须验证：

- claim 与 evidence 引用真实存在；
- finding 的 dimension/action 属于封闭枚举；
- 审计没有新增数值或业务事实；
- 推荐动作不越过宿主确定性结论；
- 无有效引用的意见只能进入 advisory。

### 5.4 允许的动作

- `keep`
- `downgrade`
- `remove`
- `mark_unassessed`
- `add_host_disclosure`
- `request_targeted_revision`
- `advisory_only`

价值保留优先级固定为：

```text
保留原强度 → 降级并说明 → 标为未评估 → 最后才删除
```

仅与证据直接冲突、明显虚构或无法安全降级的 claim 才删除。

### 5.5 修订与循环上限

发布链最多允许：

1. 初稿确定性验证；
2. 一次语义审计；
3. 如有高风险 finding，进行一次定向修订；
4. 修订后进行一次确定性复核；
5. 如确有必要，再进行一次最终语义复核；
6. 到此终止，不继续循环。

第二次仍有问题时：

- 无证据 claim 降级、标为未评估或移除；
- 风格问题记录为 advisory；
- 确定性失败只阻断对应 claim 或依赖路径；
- 不允许整场会话永久卡死。

### 5.6 故障降级

- 审计 LLM 超时、限流或 Provider 不可用，不能覆盖已完成的确定性验证；
- 对已通过结构化安全检查的答案，应允许降级发布，并在内部记录
  `semantic_audit_unavailable`；
- 如果仍存在未处理的高风险、未绑定 claim，则仅隐藏/降级相应 claim，不得以未经审计的形式
  强行发布；
- 审计调用必须进入统一 Provider 账本和总预算，不能隐藏计费；
- 未得到新一轮精确授权前，不得为了开发或校准调用真实 Provider。

### 5.7 模型独立性

初期可以使用同一基础模型的独立审计角色，但必须：

- 使用独立、版本化审计提示；
- temperature 固定为 0 或最低可用值；
- 不提供分析模型的说服性思维过程；
- 只提供证据包、claim、候选答案和政策；
- 保存审计模型、端点、提示 digest、输入 evidence digest 和结果。

如果历史回放显示同模型审计存在稳定共盲，再评估不同模型审计；不能未经证据直接增加第二模型、
额外 Provider 或新的预算体系。

## 6. 分层发布与验收标准

### 6.1 阻断层：只允许封闭类

以下任一失败才可阻断对应发布路径：

- run_state/terminal event 不唯一；
- Provider 账本不闭合或超过冻结上限；
- 工具调用与回执不配对；
- 会话、数据版本或 scope 污染；
- 权威数值不能由回执复算；
- 权威 claim 无有效绑定；
- 宿主渲染事实内部矛盾；
- 导出、刷新或持久化必需产物缺失；
- canonical history revision 不一致；
- 审计或修订引入新数字、新事实或无效引用；
- 真实业务确认未解决且确实改变计算结果。

### 6.2 非阻断质量层

以下进入 advisory/趋势统计，不得单点毙掉整个场景：

- 行文风格和详略；
- 是否使用某个近义词；
- 是否只有一个下一步；
- 一般性的表达顺序；
- 已被宿主结构化披露覆盖的轻微措辞问题；
- 没有可靠自动判定依据的灰区语义。

### 6.3 结构化完整性层

- 用户每个明确子问题映射到 answered claim 或 typed gap；
- 每个高风险事实映射到 claim/evidence；
- observation/fit/scenario/prediction 等级可检；
- 已计算/未计算/证据不足/结果为零可检；
- 部分结果允许独立发布，不被无关未完成任务吞掉。

### 6.4 语义审计质量层

在启用审计影响发布之前，必须用历史候选建立固定校准集，至少包含：

- R4 M02 两个正确候选：不得误删，应识别为情景外推；
- “未执行检验却声称差异不显著”：应要求降级或移除；
- “缺失值未计算却声称为零”：应要求降级或移除；
- “描述相关却声称因果”：应识别强度越界；
- 有依据、已标注的待验证解释：应保留；
- 正确数值但单位未知：保留数值，宿主渲染单位状态；
- 多种合法同义表达和语序变化：裁决不得因词面变化而反转。

必须记录：正确 claim 保留率、高风险越界检出率、动作正确率、审计新增事实数、超时率、平均延迟
和调用成本。不能只报告一个总通过率。

## 7. 实施顺序

### Phase 0：建立准确基线，不改产品行为

1. 阅读 `AGENTS.md` 和三份原始计划；
2. 运行 `git worktree list --porcelain`；
3. 核对实际 HEAD、dirty/untracked 文件和 R4 目录；
4. 编写时保留两个既有未提交文件（后经用户授权放弃/删除；现须按实际工作树保护任何新 dirty）；
5. 以真实失败轨迹建立回放 fixture，不另建测试框架；
6. 记录当前正则检查族、调用点、硬/软行为和对应历史失败；
7. 不调用真实 Provider。

### Phase 1：根修 canonical history

先处理 M03，因为会话历史不可信时，后续审计输入也不可信。

状态（2026-09-23）：`completed_local`，实现提交待创建。R4 M03 的旧 split=1 已由完整 turn 边界修为
split=0/保留原历史；新增聚焦测试最终为 10 项（修正前版本 11 passed），受影响完整文件 312 passed。fresh full-offline
`tmp/trust-reset-phase1-full-offline-2` 为 2821 passed、1 skipped、16 warnings、0 failures；该运行明确排除
用户保留且本计划已否决的未跟踪 `tests/test_p08_trust_restructure.py`，Provider calls forbidden。

- 复现 R4 M03 单个完整用户轮被错误切成 `early=1` 的 web 集成路径；不伪称已证明内存历史短于持久历史；
- 建立单一规范历史和 revision/hash；
- 压缩、刷新、导出共用同一规范源；
- rewind 继续是显式授权截断，但必须从 canonical snapshot 读取并用 revision/hash CAS 写回；
- 回放 M03 R4 轨迹；
- 验证摘要含执行结果且不污染 reply identity；
- 验证 conversation/publication 双产物。

### Phase 2：建立 claim/renderer 垂直切片，以 M02 为第一样板

状态（2026-09-23）：本地垂直切片完成 E1/E2，尚未执行 E3/真实 Provider 验收。
实现前 HEAD 基线 `cdfcc1a`；fresh full-offline `tmp/trust-reset-phase2-full-offline-1` 为
2831 passed、1 skipped、16 warnings、0 failures，明确排除被保留但已否决的未跟踪测试；
`provider_calls=forbidden`。不得把它升级为浏览器或自然模型结果。

开工审查（2026-09-23）：须先读 `docs/audit/2026-09-23-trust-reset-phase2-cross-history-review.md`。
该审查跨 R7—R21、R4、`2dafc69`/`bd42678` 和历史本地回归，发现现有 `render_verified_appendix()`
只被测试调用、生产 packet 的情景字段又在 `publication_scope` 而非 renderer 所读的 `sources`。
因此“宿主披露已进入正文”不能作为既成事实。用户已于 2026-09-23 确认：R4 旧候选用于证明旧门误拒，
通过条件是内容等价的 typed-binding/宿主渲染版本，而非旧文本原字节绕过散文门；单位未确认时只显示
原始数值尺度，不从列名猜百分比。实现与当前证据见上述审查第 5 节；Phase 2 已有隔离全量 E2，
尚未完成浏览器 E3 或真实 Provider 验收。

- 从现有 `answer_bindings.v1` 向后兼容扩展最小 claim 字段，不新增平行通道；
- 保留 `blocks/exact_text/requirement_refs/fact_refs/derived_refs` 和当前宿主校验，增加 `claim_type/status/unit_status` 等 typed 状态；
- 工期按四个增量面估算：schema/parser 兼容、M02 binding 生产、宿主 renderer、回放与旧门退役；不再估算新的传输、存储或模型协议通道；
- 把 curve fitting 回执、族参数、R²、D30 情景值和验证状态绑定为 claim；
- 宿主重算并渲染表格与披露；
- 不再解析族名与数值位于哪个中文子句；
- R4 两个正确候选的等价内容必须发布；
- 错误 D30 数值仍必须被确定性拒绝；
- 先完成结构化替代物，再退役对应散文硬门。

### Phase 3：确认政策类型化，以 M01 为样板

开工审查见 `docs/audit/2026-09-23-trust-reset-phase3-confirmation-review.md`：已跨 IC0—IC4、
R8/R10/R11/R16 M06、Codex/R20/R4 M01 与内部 `risk_fields` 生产者对照。
用户已裁决：模型直接提出而无宿主计算风险证据的 `data_quality_confirmation` 降为条件式指引；
内部带 `risk_fields + affected_routes` 的清洗门及明确成本/分母/窗口等业务缺口仍暂停。
Phase 3 离线切片已改用来源和宿主风险证据，删除数据性质两极词表；跨历史确认/路由回归
196 passed；最终 fresh fail-closed full-offline 为 2844 passed、1 skipped（详见审查记录）。
浏览器和真实模型证据仍分别独立记录。

- 用 confirmation kind 和结构化 business gap 决定是否暂停；
- 数据性质问题转条件式指引，不因“真实值”等词语挂起；
- 真正会改变计算值的成本、窗口、分母、scope 决定仍可暂停；
- 回放 R4 M01；
- 加同义词和语序变形测试，证明状态不依赖词面。

### Phase 4：宿主任务台账收口

当前 HEAD 的复核见 `docs/audit/2026-09-23-trust-reset-phase4-journal-boundary-review.md`：
R21 M02 scope 降级和 M04 未完成 task 全局阻断均已有对应修复；现有 receipt、
publication packet 与 TaskManager 已是事后事实源，相关离线回归 214 passed。
用户确认显式竞争假设任务仍需结构化 plan 与假设/证据关系；只是未完成 task 状态
不能阻断独立可信 claim。当前不为路线图另建 journal 或改动产品代码；若发现当前
HEAD 的剩余 RED，再对对应旧门做最小修复，不把历史 RED 误称为现行失败。

- 仅从已发生的工具调用、`turn_receipt_ids`、analysis-state 收据和数据版本事后推导 journal；
- journal 不产生目标、方法、步骤、未来任务、工具选择或执行顺序，禁止演化为第二 planner；
- 模型 plan/task JSON 不作为所有独立 claim 的全局发布许可证；显式竞争假设任务仍需原始 P5 要求的结构化 plan 和假设/证据关系；
- claim 可独立完成、声明缺口或降级；
- 移除“一个任务未完成导致全部已验证内容无法发布”的耦合；
- 保留审计需要的可追踪性，不重建第二 planner。

### Phase 5：LLM 审计 Shadow 模式

离线协议首切片见 `docs/audit/2026-09-23-trust-reset-phase5-shadow-protocol.md`：
当前仅验证 `publication_audit.v1` 的快照/答案身份、typed M02 claim 与同 claim 的
evidence refs；无绑定意见 advisory，`overall` 不影响发布。尚未接入审计模型调度，
未调用 Provider，也未完成全类型 claim 校准；聚焦 178 passed、full-offline 2851 passed / 1 skipped。
不能标为完整 Shadow 验收。

- 实现 `publication_audit.v1` 协议和宿主验证；
- 默认只记录 finding，不改变用户可见发布；
- 使用历史候选校准误删、漏检、动作和成本；
- 所有真实 Provider 调用仍需新的精确冻结与用户授权；
- 审计不通过不能在 Shadow 阶段改变正式结果。

### Phase 6：受限处置与一次定向修订

2026-09-24 状态：只实施用户批准的 **A+B 默认关闭离线准备**；C/D 尚未启用。当前入口和 RED/结构化替代/退役目标见
`docs/audit/2026-09-24-trust-reset-phase6-entry-assessment.md`、
`docs/audit/2026-09-24-trust-reset-offline-core-projection.md`。四道门不得合并为一次“Phase 6 已完成”：

| 门 | 交付和退出条件 | 目前状态 |
|---|---|---|
| A 可信核心 | 在同一 packet/回执上重建可信事实、**宿主证实**的具体缺口、必要范围/单位/方法边界、产物与假设审计；跨历史正反候选同时检查价值保留与无据结论移除。原始字段、图表存在、模型标签均不自动授权 `answered` | 离线预览局部具备；R4 M03 六来源结论、M04 非闭合关系、R16 M05 方法表与 R11 原句等价保留未证明；不得切默认 |
| B 离线动作 | 仅同快照有效 typed claim/evidence 可模拟 claim 级 keep/downgrade/unassessed/remove/定向修订；独立可信 claim 保留、故障回退可复核，`publication_effect=none` | 纯函数初切片具备；不代表真实审计或处置完成 |
| C 真 Shadow | 独立版本化提示、输入/输出 digest、统一 Provider 账本/预算、显式开启/超时降级；历史正反候选校准误删、漏检、动作、成本；整个 Shadow 不改可见发布 | 未开始；任何真实 Provider 调用另需精确冻结和用户显式授权 |
| D 正式处置 | 用户另行裁决默认发布切换；仅受限 claim 动作，确定性复核与最多一次定向修订；完整 Provider-disabled 浏览器 E3，E4 另冻结/授权 | 未授权、未开始 |

下一 A+B 切片继续做**跨历史离线双轨输出对照**，不要再单凭一个最近失败新增 claim 家族。第一条综合回执入包 RED/GREEN 见 §0.1/跨历史记录 §6；接下来逐样本写 `可复核事实/解释/缺口/产物/关系` 的宿主所有者、可重建结果与未重建原因，分别记录正确价值保留和独立无据事实剔除；R11/R16 正例、R4 部分正例、R7—R21 反例和旧本地会话均纳入，但旧文本不等于新 parser 的合法 binding。尤其要区分“六源原始字段可见”与“两日金额/绝对和相对变化已由同版本工具身份授权 `answered`”。无法从当前权威结构证明的解释保持 `unassessed`，不可从原文回填；若该限制导致原始 VP/CP 价值目标无法达成，应在继续改正式策略前与用户讨论。每次实施仍先记录 RED → 结构化替代物 → 将退役旧门；退役目标是“一条有效 binding 让整篇散文获得事实权威”，**不是**削弱回执/数值/版本硬门。

- 只允许对结构化 claim 执行受控动作；
- 禁止审计器整篇自由改写；
- 修订后必须再次确定性验证；
- 审计不可用时验证降级发布；
- 强制最大循环次数和总调用预算。

### Phase 7：逐族退役散文硬门

每个旧检查器只能在其职责已有结构化替代物后删除或降级。逐项记录：

- 原检查器；
- 旧误拒/误放历史；
- 新 claim/renderer/audit 所有者；
- 回放证据；
- 删除的正则和测试；
- 新增的封闭不变量测试。

禁止一次删除全部门，再依靠附录或审计模型兜底。

### Phase 8：验收契约与判定器重写

- 将 oracle 分为 blocking、structured completeness、semantic audit、advisory；
- 每条 blocking oracle 必须引用原始需求原则和可机器判定的证据；
- 移除依赖特定自然语言措辞的硬 oracle；
- 判定器输出各维结果，不再用单一 6/6 掩盖失败性质；
- 保持现有 runner、浏览器工作流和账本，不新增重复机制。

### Phase 9：验证顺序

1. 单元与真实轨迹回放；
2. 相关子集；
3. 隔离 full-offline；
4. Provider-disabled 内置浏览器完整矩阵；
5. 修复结束并重新完整执行本地矩阵；
6. 冻结精确 commit、模型、端点、fixture/prompt/oracle digest、矩阵、预算和账本路径；
7. 等待用户新的显式授权；
8. 使用内置浏览器一次完整执行 M01—M06，中途不修代码、不局部重跑。

本地/offline/Provider-disabled 证据都不能升级成真实 Provider、staging、production 或 deployment
证据。

## 8. 测试原则

### 8.1 使用真实失败轨迹，不继续造词表样例

最低回放集：

- R4 M01：`5df75d57da84`
- R4 M02：`c3f4c190384c`
- R4 M03：`50e734df7af7`
- R21 Codex M02 scope 死亡轨迹；
- R21 双批 M04 工具发现/任务门轨迹；
- 历史正确答案被否定词、表头、范围句、跨子句配对误拒的候选；
- 历史“同比例”“块/块钱/元”“模板/占位符”等正则修补案例。

### 8.2 变形测试优先

同一 claim/evidence 下进行：

- 同义词替换；
- 主被动变化；
- 子句拆分或合并；
- 表格与行内表达转换；
- 族名与限制说明换序；
- 中文/英文显示名变化。

如果这些变化会改变确定性发布状态，说明实现仍在解析散文，应视为架构失败。

### 8.3 不把 mock 绿等同于真实能力

- mock 验证协议和宿主动作；
- 录制轨迹验证历史回归；
- Provider-disabled 浏览器验证完整产品路径；
- 真实 Provider 只验证自然模型路径和外部传输；
- 各证据等级分别记录，不互相替代。

## 9. 完成定义

本任务只有同时满足以下条件才可称为完成：

1. 三份原始计划的核心原则均有明确代码所有者和测试；
2. M01 是否挂起不再依赖“真实值”等自然语言 token；
3. M02 的权威外推数值完全由 claim/回执重算和宿主渲染，不解析散文配对；
4. M03 压缩只使用规范历史，刷新和导出不丢执行结果；
5. 模型无需正确维护第二套 planner/task JSON 才能发布独立已验证 claim；显式竞争假设任务的结构化 plan 与假设/证据关系仍需满足原始 P5 审计要求；
6. 高风险正文不再依靠末尾免责声明纠错；
7. LLM 审计输出结构化 finding，不能覆盖确定性失败，不能新增事实；
8. 审计最多一次定向修订和一次最终复核，不形成循环；
9. 审计故障有明确降级路径，不造成全局永久阻塞；
10. 历史正确候选不再因同义词、语序或表格布局被误拒；
11. 历史无依据高风险结论被结构化降级、移除或标为未评估；
12. full-offline 与 Provider-disabled 完整浏览器矩阵通过并有隔离证据；
13. 新的真实 Provider 批次只有在精确冻结和用户重新授权后执行；
14. 完整 M01—M06 真实批次中，确定性正确与交付项全部通过，advisory 单独报告；
15. 没有覆盖、删除或误提交用户原有未提交文件。

补充防漂移门：第 10/11 项不能只靠“核心删掉 99%”证明，还须证明 R11/R16 的正确结果及 R4 M03/M04 的可验证价值没有因默认切换而静默消失；不能以 R4 中断批次代表所有历史。A/B 的 E2、C 的 Shadow、D 的正式发布、E3、E4 分别记账，不得把前一层绿灯平移成后一层。

## 10. 实施中的停止条件

遇到以下情况应停止扩展实现，回到设计层：

- 为修一个合法新措辞而准备新增关键词；
- 审计模型的意见无法绑定 claim/evidence；
- 为让测试通过而降低确定性数值或回执约束；
- 宿主附录与正文产生明显矛盾；
- 一个局部任务状态再次阻断无关已验证结果；
- canonical history 仍存在两个可写事实源；
- 需要新增隐藏 Provider 调用或突破冻结预算；
- 新设计需要另一套 planner、浏览器框架或账本；
- 只能靠真实 E4 才能发现可离线复现的状态机问题。

## 11. 原始新对话启动指令（历史，勿作为当前阶段命令）

在全新 Codex 对话中粘贴以下内容：

```text
请接手 D:\Project\Daily\data-agent 的“中文数据分析 Agent 可信发布架构重置”任务。

先完整阅读：
1. 仓库根目录 AGENTS.md；
2. docs/superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md；
3. 该计划引用的三份原始计划。

然后只做 Phase 0 的证据复核：检查 git worktree、实际 main/HEAD、dirty/untracked 文件、
R4 目录和真实失败轨迹，确认计划中的事实是否仍成立，并报告差异。不要立即修改代码。

特别约束：
- 保留现有未提交文件，不覆盖、不删除、不 bulk-stage；
- 不补自然语言关键词，不把末尾免责声明当作正文纠错；
- 不新增 planner、浏览器框架、重复账本或隐藏模型审核调用；
- 先修 canonical history，再做 M02 claim/renderer 垂直切片，再做确认类型化，最后引入
  LLM 审计 Shadow 模式；
- LLM 审计必须受 claim/evidence 约束，不能成为新的随机总审批门；
- 未经新的精确冻结与我的显式授权，不得调用真实 Provider；
- 在每个实施阶段前先给出 RED 轨迹、结构化替代物和将退役的旧门，确认没有回到词表修补。

完成 Phase 0 后向我报告：当前确切 HEAD、工作树状态、证据复核结果、计划需要修订之处、
第一阶段的最小实现边界与测试清单；等我确认后再实施。
```

## 12. 编写时交接边界（历史）

以下列的是本计划在 2026-09-22 **尚未获用户后续授权时** 的边界；现行授权和精确 HEAD 以 §0.1、Phase 6 四门及后续用户裁决为准。不得把这段旧文字解释为可重做 Phase 0 或否定已获准的 A+B 离线工作。原文当时不授权以下行为：

- 不授权修改产品代码；
- 不授权删除或修改两个既有未提交文件；
- 不授权提交、推送或部署；
- 不授权真实 Provider 调用；
- 不授权开始新的浏览器矩阵。

下一对话必须从 Phase 0 复核开始，以实际仓库状态修正文档中的任何漂移信息。

现行续接规则：先重查 `AGENTS.md`、三份原始计划、§0.1、HEAD/dirty 与上述审计记录；复核历史正反样本和本阶段三联门，再在获准的 A+B 离线边界内推进。未经另次裁决，不启动 C/D、正式发布切换、真实 Provider、push 或部署。
