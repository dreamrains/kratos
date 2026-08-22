# V2 系统设计迭代计划（2026-08-22）

- 决策依据：用户 2026-08-22 决策——**系统设计方案迭代，不做止血**（不引入"目录外 fallback 到 legacy AgentLoop"）；项目尚无大规模用户，无历史负担
- 输入：`docs/audit/2026-08-22-v2-real-data-quality-system-test.md`（真数据质量测试，6 场景 4 死路）+ 本文 §2 的代码级归因（全部经源码精读验证，非文档推断）
- 上位架构：`docs/superpowers/specs/2026-08-13-data-agent-v2-architecture-design.md`
- 质量标准（继承 M2-D 共识）：严谨（最高标准）+ 数据为本 + 方法合规完整 + 完整性（丰富是方法完整执行与忠实合成的自然结果）

---

## 1. 总体判断（架构层面）

V2 的**信任骨架是健全的，值得保留并作为迭代基座**：
- commitment → finding → projection → `compile_answer` 的证据链（claim_class 上限、canonical_values 数值一致性、support_refs 实存校验）是旧系统没有的严谨层，也是直连 LLM 基线（编造全部统计量）证明必需的层
- `answer.py:189-262` 的编译器**不关心 narrative 由谁撰写**——它只校验引用/等级/数值。这是本计划的关键架构支点：**叙述文本的生产可以从模板换成 LLM，而信任边界不动**

问题集中在四个可分离的层，每层都有精确的代码位置：
1. **引擎层的全有全无门**（数据形状不匹配 → 拒绝，无降级阶梯）
2. **规划层的窄目录**（8 种 kind、单路线、单数据集、单列单位）
3. **表达层的模板化**（f-string 叙述 + 建议层结构性死亡 + 范围收窄不披露）
4. **交互层的产品化缺口**（验收用 Workbench ≠ 产品入口）

## 2. 代码级归因总表（测试问题 → 根因 → 缺陷类别）

| # | 测试现象 | 根因（file:line，均已精读验证） | 类别 |
|---|---|---|---|
| A1 | S1 拟合请求 unsupported | `_AUTOMATIC_KINDS` 仅 7 种自动 kind，无拟合类（planner.py:241-249）；exploratory_python 仅限手动（需显式 code 参数，router.py:193-202）且沙箱禁 import（exploratory.py:100-101），纯 Python 手写最小二乘不可行 | 目录缺失 |
| A2 | S2 因素分析零结果无信息量 | VIF≥10 一次性剔除 10/13 因素（factor.py:274-278）→ 剩余 3 因素 Holm 后不显著 → null_result（factor.py:349-380）；**无双变量关联排序降级路径**（slice2.py:305-328 的 null 分支只有一句话）；恒等式排除仅查两两精确算术恒等（factor.py:100-136，rtol=1e-8），确认率（与目标共享"确认"分子语义的三列比例）漏网 | 引擎降级缺失 + 检测浅 |
| A3 | S2b 13 组对比拒绝且无部分输出 | `len(group_values) != 2 → limited`（group_comparison.py:123-130），该分支不传 groups 摘要（groups=()）；无多组聚合排序能力 | 目录缺失 + 无部分输出 |
| A4 | S4 配对前后设计拒绝 | `working[unit].duplicated().any() → limited`（group_comparison.py:114-121）——把订单级数据的正常形状当致命错误；**引擎本可先聚合到单位级**（metric 已 to_numeric coerce，group_comparison.py:107）；同单位跨两组=配对设计，应走配对检验而非拒绝；对照：factor 对同一形状用 cluster SE 处理（factor.py:338-347），两引擎对重复单位处理不一致 | 引擎能力缺失 |
| A5 | S4 显式索要建议 → 零建议 | 三级确认：① planner 合同无 recommendation_intent/action_risk/reversible 字段（planner.py:257-270 `_CONTROLLED_PARAMETER_FIELDS`）② router 默认 intent="none"（router.py:54-61）③ v2.py 仅在客户端显式传参时透传（v2.py:420-428），workbench 不传 → `decide_recommendation` 恒走 NONE 分支（recommendation.py:48-52）→ slice4a:373-391 的建议块永不构建。**建议层在产品流程中结构性死亡**；且即使触发，输出也仅一句固定话术（recommendation.py:57-101） | 表达层死亡代码 |
| A6 | S3 多文件请求被静默收窄 | `DatasetPlanningContext` 单数据集构造（planner.py:125-131）；单 kind 单路线 schema（planner.py:1010-1075）；runtime 单 filename（router.py:106）；**而 DatasetRegistry 本身支持多 logical dataset（dataset.py:164-207）——存储层已就绪，规划/web 层未跟上**；planner rationale 中的范围收窄推理只落 plans.jsonl，不进答案 blocks（slice 模板无范围披露块） | 规划层窄 + 披露缺失 |
| A7 | S5 脏列（卖量收入 object）不可绑定 | `_infer_column_role` dtype 优先（planner.py:1255-1262），object→TEXT；metric/target/features 枚举仅含 NUMERIC 角色列（planner.py:728-750），参数校验 numeric=True 硬拒（planner.py:1620-1625）——**而引擎内部本来就会 coerce**（group_comparison.py:107、factor.py:80-81）；角色推断无"数值可转换性探测" | 数据层探测缺失 |
| A8 | S5 组合分析单位不可表达 | analysis_unit 枚举=仅已确认单列（planner.py:734-738），校验强制等于确认列（planner.py:1689-1698）；无组合列/派生单位概念 | 规划层窄 |
| A9 | S2b/S4 未运行分析却输出 Welch 方法模板 | slice4a.py:346-350 `method` 叙述无条件生成，与 result.status 无关（limited 时 executive_answer 已切换为拒绝话术但 method 块仍是"主估计使用 Welch"） | 模板一致性 bug |
| A10 | S1/S5 拒绝文案为英文长段、无出路 | unsupported 的 rationale 是 planner 英文自由文本（planner.py:993-997 non_empty_text），直接渲染进 UI；无中文转译、无替代问法/最近似能力建议 | 表达层缺失 |
| A11 | S3 直答不指名指标口径 | 叙述模板只嵌数值不嵌指标身份（slice4b 等模板）；口径信息在方法目录区/图表，不在答案正文 | 表达层细节 |
| A12 | 预测仅 3 种朴素模型 | forecasting.py:217-219（naive_last/drift/seasonal_naive）+ MASE≤1.25 发布门——对"拟合公式/预测"类业务需求的深度上限 | 目录缺失（低优先） |
| A13 | 环境层：deepseek 思考失控 | LLMClient 无 thinking/extra_body 控制（llm/client.py:137-176），自由分析任务实测耗尽 32k 输出预算于 reasoning（76k 字符 0 正文）——影响一切未来 LLM-in-loop 设计 | 基础设施 |

## 3. 目标架构（系统设计迭代的终态）

**核心原则：确定性计算 + 受约束的 LLM 表达。LLM 回到流程中，但永远不产生"数值"与"证据等级"，只产生"路由决策"与"经校验的叙述"。**

```
用户问题 + 数据画像
   │
   ▼
[规划层] LLM #1（沿用现合同 + 扩展）
   │  多路线计划（一个 turn 可含 2-3 条路线）／多数据集上下文／组合单位
   │  新增：recommendation_intent 由用户问题推导（或 needs_input 确认），进入合同
   ▼
[引擎层] 确定性能力（目录扩展 + 降级阶梯）
   │  每个引擎输出：主结果 或 降级结果链（配对→双变量→描述排序）
   │  数据自愈：数值可转换性探测在角色推断时完成，转换即派生数据集版本（有 lineage）
   ▼
[表达层] LLM #2（新增，受约束叙述生成器）
   │  输入：verified findings + claim ceiling + canonical values + 范围收窄事实
   │  输出：AnswerBlockDraft 的 narrative/headline（业务翻译、So-What、金字塔结构）
   │  约束：数值只能引用 canonical_values（compile_answer 硬校验已存在）；
   │        越数据范围的判断必须落入 advice/limitation 块并标注"提示性"
   │  建议：基于 findings 的 investigate/act 分级（复活 recommendation.py 的分级思想，
   │        话术由 LLM 按 findings 定制，风险等级规则保留）
   ▼
[编译层] compile_answer（不改核心）→ blocks → SSE/UI
```

与"止血方案"的本质区别：不引入 legacy AgentLoop 作为兜底路径（避免双系统、双信任模型、双 UX）；目录外需求的目标状态是**目录内可表达**，过渡期的 unsupported 保留但必须携带出路信息。

## 0. 决策记录（2026-08-22 用户确认）

| 决策点 | 结论 |
|---|---|
| 总路线 | 系统设计迭代，不止血（不 fallback legacy）；新目标 = 可靠使用的数据分析智能体（"尽快发布"为旧目标，作废） |
| 多部分问题应答形态 | **分步应答**：单次一条主路线 + 范围披露 + 一键追问建议；多路线 routes[] 降为后续独立增强批（视分步效果决定优先级） |
| 聚合/口径确认门 | **自动默认 + 披露**：金额类默认求和、比率类默认均值；答案显著披露口径，可改后重跑；不 needs_input 打断（遵循 M2-D 会话内自动推进标准） |
| 实施归属 | Claude 从 B1 第一片（配对比较）开始按批推进；Codex 并行测试工作需与之协调共享文件（planner.py/group_comparison.py 等） |
| B3 表达质量验收 | **人工维度为主**（现有 10 维 + 新增信息量/可操作性 2 维）；与基线覆盖差百分比仅作参考，不设硬门槛 |
| 提交授权 | v4 证据链 + 本计划 + 审计文档已提交（b343620）；后续批实施遵循"源码与证据分开提交" |

### 3.1 能力阶梯（"永不罢工"设计，2026-08-22 补充）

用户核心关切：目录永远不可能覆盖所有真实问题，没有 run_python 式兜底时，目录外需求 = 系统罢工。系统性答案不是恢复任意代码执行，而是**四级降级阶梯**——最坏情况是"带信任标签的探索性答案"或"带出路的诊断"，永不沉默：

| 层级 | 机制 | 信任等级 | 状态 |
|---|---|---|---|
| L1 目录引擎 | 一等确定性引擎（配对/多组/拟合/趋势/因素/预测/综合…），按真实需求频率扩容 | verified：inferential/predictive 断言，canonical values 硬校验 | B1 扩容中 |
| L2 组合与降级 | 既有原子的确定性重组（聚合排序、双变量降级链、范围披露+一键追问）；引擎内降级而非拒绝 | verified（descriptive 等级）或诚实标注的降级 | B1 已落地部分，B2 扩展 |
| L3 探索性兜底 | planner 可路由到**受约束沙箱**：白名单库（numpy/pandas）、无网络无文件 IO、超时、输出**永久 supplemental**（不作证据、不进 claim 体系）；答案以显著标签呈现"探索性、未经结构化验证合同" | exploratory：明确不承诺可信度，但给出答案与口径 | **本节新增，B2 实施**（原计划中 exploratory 仅手动直连） |
| L4 诊断性 unsupported | 连 L3 都不可行（缺数据/需网络/语义不明）时：结构化拒绝——缺什么、为什么、最近似可行问法、旧版入口 | 无断言，只有诊断与出路 | B3 表达层实施 |

关键区别于 V1：V1 的问题不是"能跑代码"，而是**自由代码的输出与验证过的输出以同等自信呈现**。L3 允许兜底存在的前提是信任标签成为架构属性（块类型、UI 样式、claim 体系三重标注），而非模型自觉。

配套机制：**unsupported 遥测闭环**——每次 L4（及 L3 命中）都已持久化于 plans.jsonl（question + rationale + 数据指纹），定期挖掘该清单即数据驱动的引擎扩容优先级（需求频率 → L1 产品化），使 L3 是过渡层而非常态层。

边界（保持不变）：无网络/无外部数据获取（设计使然，非缺陷）；L3 结果不因用户依赖而"转正"，高频模式走产品化。

## 4. 分批实施计划

每批独立可验收、可提交；批内遵循既有纪律（RED 先行、离线优先、成组 Provider 授权、source digest 冻结）。验收场景直接采用本次测试的 S1-S6 作为回归金标准，另加两个旧会话（5/18 留存拟合、7/11 因素+策略）作为"对标重放"。

### B1 引擎层：配对/聚合/多组/拟合/自愈（消 A1 A2 A3 A4 A7）

1. **group_comparison 单位聚合 + 配对路径**（group_comparison.py 重构）
   - 行为单位重复时：先聚合到 unit×group（sum/mean 由参数选择，默认 needs_input 确认口径），聚合后单位唯一 → 继续 Welch
   - 同单位跨两组（配对队列）→ 配对差检验（Wilcoxon 符号秩 + 配对 t + 中位数差 CI），新 FindingKind.PAIRED_COMPARISON，claim ceiling 仍 inferential
   - 验收：S4 重放 = 配对 n=61、实收 -30.7%、Wilcoxon p=0.028 被正确发布（与独立核算一致）；订单级非配对数据走聚合路径
2. **多组聚合排序**（新引擎 group_ranking）：>2 组时输出按指标聚合排序的分组表 + 置信标注（描述性）+ 图；不冒充推断
   - 验收：S2b/S5 重放 = 13 策略/互推组合的排序表 + 图，明确"描述性排序，非因果"
3. **曲线拟合 kind**（新引擎 curve_fitting）：幂律/指数/对数三族对数线性化最小二乘 + R²/残差/模型对比表 + 拟合曲线图；claim ceiling = descriptive（拟合描述，不外推；外推需求走 forecast）
   - 验收：S1 重放 = 幂律参数与 R²（≈0.1879/0.7164/0.9825，与 5/18 会话独立核算一致）+ 模型对比表 + 图
4. **数值自愈探测**（planner.py `_infer_column_role` 扩展）：object 列 to_numeric 成功率 ≥99%（可配置）→ 角色 NUMERIC（带 `coerced` 标记）+ 自动派生转换数据集版本（复用 DatasetRegistry.derive，lineage 完整）；成功率不足 → 角色不变并在 needs_input/unsupported 中给出可诊断原因（"该列 N% 值无法转为数值"）
   - 验收：S5 重放 = 卖量收入可绑定为指标（或明确报告转换损失）
5. **factor 零结果降级链**：饱和模型无显著项时自动补双变量关联排序（Pearson+Spearman+Holm，descriptive 等级，明确标注"未经多变量调整"）；恒等式排除扩展到三列比例同源检测（如 X/A 与 Y/B 共享分母/分子语义的启发式 + 相关|r|>0.999 警示）
   - 验收：S2 重放 = null 结果之外附"人均访问 r=0.65（未调整）"排序表，诚实分级

### B2 规划层：多路线/多数据集/组合单位/建议意图（消 A5 A6 A8）

1. **多数据集规划上下文**：`DatasetPlanningContext` → 支持多 dataset（列表），schema 中路线参数增加 dataset 维度；web 上传支持多文件（DatasetRegistry 已支持，改 upload/planning-estimates/plans 端点与前端）；跨数据集时间对齐的趋势并列/关联作为新 kind（multi_dataset_synthesis，输出 per-dataset findings + 对齐图，不做跨源因果声明）
   - 验收：S3 重放 = 三文件问题至少给出"内购趋势 + banner/激励视频未提供需补充"的范围披露，多文件上传后给三源并列分析
2. **多路线计划**（**已按决策降级为后续增强批**）：B2 首版实现**分步应答**——单条主路线 + 答案内范围披露块 + 结构化的"建议追问"（一键以预填参数发起下一路线）；routes[] 多路线一问全答推迟到分步形态验证后再评估
   - 验收：S3 重放 = 内购趋势答案 + "banner/激励视频未提供"披露 + 一键追问卡片；不要求单 turn 三源全答
3. **组合分析单位**：analysis_unit 支持 `[列A, 列B]` 组合（planner 枚举 + 校验 + 引擎 groupby 接口）；或引入"派生组合列"转换（复用 date_transformation 的确认机制）
   - 验收：S5 重放 = 流量主+广告主组合单位可用
4. **建议意图进入合同**：recommendation_intent 由问题推导（"请给建议/怎么办"→ investigate 默认；act 需显式）或 needs_input 确认一次；action_risk/reversible 采用 fail-closed 默认（unknown/不可逆）——**不做**旧 5C5AA 时代的"模型猜业务风险"，风险来自用户/业务上下文或 unknown
   - 验收：S4 重放 = 用户索要建议 → 至少 investigative 建议块出现，且内容针对 findings（依赖 B3）
5. **探索性兜底路由（L3，"永不罢工"层）**：planner 新增可路由的 exploratory 变体（无目录引擎匹配时可选）；沙箱升级为白名单库（numpy/pandas）+ 无网络/文件 IO + 超时；代码由第二次受约束 LLM 调用生成（输入=数据 schema+问题，输出=纯代码，不可产生结论文本）；执行结果**永久 supplemental**（块类型+UI+claim 三重标注"探索性、未经结构化验证"）；授权记账扩展（探索性 turn = 2 次调用）
   - 验收：构造一个目录外问题（如"计算每行两列的比值分布偏度"）→ 得到带探索性标签的答案而非 unsupported；白名单外 import/IO 被拒并降级到 L4 诊断
6. **unsupported 遥测闭环**：plans.jsonl 的 unsupported/needs_input 事件定期汇总为引擎扩容优先级清单（工具化脚本，输出需求频率排序）
   - 验收：脚本对当前 sessions 的 plans.jsonl 输出"目录外需求 Top N"报告

### B3 表达层：受约束叙述生成器（消 A5 A9 A10 A11，最大价值批）

1. **叙述生成器（LLM #2）**：新模块 narrative_generator
   - 输入：findings（含 uncertainty/limitations）+ 用户问题 + 范围收窄事实（来自 planner rationale 结构化后的 scope_notes）+ 允许的 claim ceiling
   - 输出：各 block 的 narrative 草稿（金字塔：直答先行、业务翻译、So-What）+ 范围披露块（scope_disclosure：哪些部分未答、为什么、建议怎么补）
   - 硬约束（编译器既有 + 新增）：数值必须 ∈ canonical_values（answer.py:101-119 已硬校验）；越数据范围建议只能进 advice 性质块并自我标注；中文输出；thinking 控制（A13：LLMClient 增加 extra_body/thinking 参数）
   - 失败降级：生成失败/校验失败 → 回退现有模板（现模板保留为 fallback 层）
2. **建议引擎复活**：recommendation.py 的分级决策保留为"等级判定"，话术由叙述生成器按 findings 定制；action_risk fail-closed 规则不变
3. **模板一致性修复**：limited/拒绝路径的 method 块改为事实叙述（"已执行：单位重复性诊断；未执行：组间检验"），Welch 模板仅在 supported/null 分支出现（slice4a.py:346-350 同类问题全 slice 排查）
4. **拒绝文案产品化**：unsupported 输出结构化（中文原因 + 最接近的可行替代问法 + 缺失能力清单），英文 rationale 仅入 plans.jsonl 供审计
   - 验收：S1（在 B1 完成前）= 拒绝页给出"当前支持 X/Y/Z，拟合需求将支持"类出路；S4 = 三部分问题都有回应（结论/限制/建议）；B 基线对照 = 同题答案覆盖差（业务翻译/建议维度）≥ 基线的 70% 且数值零编造（compile 校验 + 抽查）

### B4 交互层：产品入口（Workbench → 真正的网页入口）

对标 7/11 会话的对话体验 + M2-D 已确认的 UX 优先级（流程>质量>呈现>雕琢，故排在引擎/表达之后）：
1. 对话式主界面：消息流 + 结论卡片（blocks 渲染）+ 图表邻接呈现；规划确认/needs_input 以对话内卡片出现（沿用现确认纪律）
2. 多文件上传与会话内数据集管理（依赖 B2）
3. 任务/进度呈现：SSE 实时（已有）+ 可折叠 overlay（沿用）
4. 旧版入口保留至 B6
   - 验收：真实用户旅程（浏览器 evidence 机制复用）+ 人工语义评审 10 维度 + 新增"信息量/可操作性"维度

### B5 发布流程适配

- release matrix 增加层：真实业务问题覆盖率（S1-S6 + 两个旧会话对标重放作为常驻场景）；叙述生成器的诚实性 oracle（数值一致性编译校验 + 抽样人工）
- Provider 授权预算：叙述生成器使每 turn 调用数 =1(规划)+1(叙述)（+needs_input 重规划），成组授权口径更新
- 既有 5C6 机制（digest 冻结/evidence 重建/人工评审）原样复用

### B6 Legacy 移除（最后，独立授权）

- B1-B4 验收 + 稳定观察后，审计并删除旧 AgentLoop 入口与代码；与首次切换解耦（既有规则）

## 5. 批次顺序与依赖

B1（引擎）→ B3（表达）为关键路径：B1 产出更丰富的 findings，B3 才有可叙述的内容；B2 与 B3 可并行（不同层）；B4 依赖 B2 的多文件与 B3 的卡片化内容；B5 每批滚动更新；B6 最后。
建议节奏：B1 → B3 → B2 → B4 → B6，每批一个 source 冻结 + 成组真实验证。

## 6. 风险与开放问题（需在批内决策）

1. **叙述生成器的诚实性**：编译器能保证数值/等级合规，但"选择性陈述"（LLM 避重就轻）无法完全机器校验——缓解：范围披露块强制覆盖问题分解 + limitation 块必选 + 抽样人工评审入 matrix
2. **成本与延迟**：每 turn 2 次 LLM 调用（规划+叙述）；deepseek-flash 成本可忽略，延迟 +3-8s 需在 SSE 上做渐进呈现（findings 先出，叙述块增量出）
3. **多路线计划的授权记账**：routes[] 使"恰好一次规划调用"语义不变（一次调用产多路线），但执行时间上升；stop/steer 语义需回归测试
4. **配对检验的口径选择**（sum vs mean 聚合）：**已决策（2026-08-22）**——自动默认（金额求和/比率均值）+ 答案显著披露 + 可改重跑，不 needs_input 打断
5. **B3 的 fallback 双轨**：模板作为降级层保留意味着两套表达质量——接受为过渡态，matrix 中标注叙述来源（generated/template）

## 7. 明确不做

- 不引入 legacy AgentLoop 作为产品路径或兜底（用户决策）
- 不允许**无信任标签**的任意代码输出进入答案体系（L3 探索性兜底以"永久 supplemental + 三重标注"为前提，与 V1 的自由执行有本质区别）
- 不放松 fail-closed 安全边界（授权/source-binding/claim ceiling/canonical values 校验）
- 不改 compile_answer 的核心合同（它是信任边界；只增块类型与校验维度）
- 不为单一场景加特例补丁（沿用 5C6 的"修共享根因"原则）
