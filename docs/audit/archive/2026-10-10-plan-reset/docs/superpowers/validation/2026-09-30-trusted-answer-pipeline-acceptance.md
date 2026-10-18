# 可信回答单路径验收契约

初版：2026-09-30；本次更新：2026-10-09。需求版本：产品PRD1.7/发布PRD1.4；本文件定义行为判据，状态只见唯一总计划§0.8。最新f7210e1/r3仅M01部分执行后停止，未通过；§19是系统审查后三项批准裁决的新增跨接口门，尚未实施通过。旧阶段收据只适用于其原身份。

依据：[产品 PRD](../../product/data-agent-product-requirements.md)、[发布 PRD](../../product/trusted-answer-publication-requirements.md)、[设计](../specs/2026-09-30-trusted-answer-pipeline-redesign.md)。进度只记录在[唯一总计划](../plans/2026-09-22-analysis-agent-trust-reset-plan.md)。本文件定义判据，不是另一个实施计划。

## 1. 统一身份与判定

每个运行固定 case_id、输入文件 SHA、提示及顺序、有效业务选项、候选源码、默认配置、控制路线、独立 oracle、run_dir、session_id、Provider ledger。失败后的修改必须产生新运行身份。既有真实批次保持其原始输入，不在复盘中改 oracle。

同一 case 在 E1/E2/E3/E4 含义不变。`M05-STYLE` 是六轮表达，`M05-AGG-EDGE` 是分组边界；后者通过不能替代前者。IC 原 M 编号必须使用 `IC-Mxx` 前缀，不能冒充真实 Provider 矩阵 M01—M06。

判定分开记录：事实正确、覆盖完整、解释/建议价值、禁止升级、生命周期、可见输出、持久身份。每个维度为 passed / failed / unassessed；缺失证据不计通过。所有必需维度满足才通过，不用总分抵消失败。

独立 oracle 从原 fixture 和业务需求建立，不调用产品 renderer / coverage / verifier 来生成预期值。文字质量可以人工或预先冻结的独立语义评估判定；禁止仅检查最后一轮数字子串、固定关键词或内部 state。显示内容可变化，命题、条件、归属和缺口必须正确。

## 2. 必须新增的咨询与路由场景

| Case | 固定最小输入 | 用户行为 oracle | 禁止的相近行为 |
| --- | --- | --- | --- |
| CONS-01 | 新会话无文件：什么是 p 值，如何正确解释？ | 直接给概念、适用条件和示例；无分析工具执行或上传阻塞 | 声称已分析用户数据；将无 receipt 当整篇失败 |
| CONS-02 | 无文件：为电商留存设计分析方案，列出所需字段和步骤 | 方案、指标定义、数据粒度/窗口、方法局限完整 | 强制先上传；制造已检验假设或结果 |
| CONS-03 | 已有文件：只解释回归和相关的区别，不执行分析 | 保持知识路由；实际没有执行型工具调用 | 因数据存在/方法关键词自动训练模型 |
| CONS-04 | 已有接受答案：换成给业务同事看的说明 | 读取原答案身份，事实不变，表达有实际变化 | 重算、丢事实、改单位、复用其他会话结果 |
| CONS-05 | 无可定位原结果：解释刚才的收入下降 | 明确缺少可定位结果，可说明通用分析思路 | 从相似历史或记忆拼出当前数据结论 |
| INTENT-01 | 有 sales：你好，请计算总收入 | 问候不吞执行；从真实工具得到结果 | 只回复问候 |
| INTENT-02 | 有数据：不要分析留存，只导出当前表 | 数据操作保留否定和导出对象 | 启动留存方法或分析报告 |
| INTENT-03 | 有数据：先解释同比含义，再算当前文件的同比 | 咨询和执行两项均回答；定义与数值来源分别正确 | 主意图标签吞掉一项 |
| INTENT-04 | 九指标请求；将复购率在列表中换序 | 主目标与全部覆盖不变 | 只执行首个匹配方法；强迫选一个指标 |
| INTENT-05 | 改为新窗口或撤回一项，随后压缩/续问 | 需求 revision 可追踪，撤回不在分母，新窗口生效 | 从摘要复活旧窗口/撤回需求 |

中文/英文等价、否定、混合任务及分类失败回退需成对覆盖。脚本化分类与模型输出只证明编排；自然路由质量需后续新冻结并获授权的场景验证，不能自动加入既有 M01—M06 授权。

## 3. 现有真实矩阵的行为身份

| Case | 必需交付 | 独立负例与校验 |
| --- | --- | --- |
| M01-CURRENT-ACTION | 当前 12 行/120/含首尾 12 天；比较各完整事实组；未来 AND 条件行动 | 未来窗口不能当本期；条件任一不满足不能触发；单位未知不补币种；正确事实不被行动审核吞掉 |
| M02-CURVE | 实际观测/拟合、参数误差、范围和 D30 缺口 | 观测值比例/单位以 fixture 元数据为准，不能把未知单位自改百分比；无 holdout/backtest 不称已验证外推 |
| M03-SIX-SOURCE | 六来源分别 10→11 至 60→66，完整变化/记录数、六 trace、压缩和导出 | 不跨源加总业务量，不丢第一/第六项，非规范历史和错图表引用拒绝 |
| M04-VERSIONED-HYPOTHESIS | v1 与 v2 假设、关系、依据和限制在正文可见 | 当前原测量决定描述性支持/反驳；错指标、旧版、纯措辞、无据因果仍未决 |
| M05-STYLE | 原冻结六种表达要求在同会话实际改变组织、深度和读者语言 | 核心事实/缺口一致；六个相同摘要不通过；详细不编造 |
| M06-MISSING | 无文件时给具体缺口和一个明确数据动作 | 不计算假值、不反复询问方法许可 |
| M06-CONFIRMED-PARTIAL | 冻结成本口径选项只恢复一次；保留 12/120/12 天，成本净收益未计算与增量证据不足分开 | skip/旧版本/重复 resume 不能授权；未知成本不归零 |
| M05-AGG-EDGE | A/B/C/D 数值 1/2/3/999 等原边界 fixture 的分组完整性 | 最大值 D 不被截断；这项不能替代 M05-STYLE |

M02 历史不同 fixture 的 D7 单位曾不同，不能在新 oracle 中混为一个。`71e23d0` 收据的 D7 为 `0.1`、单位未知；原 VP F-RET7 明确比例时为 10%。各自保留身份，禁止拼接预期。

## 4. 发布和系统行为验收族

| 族 ID | 正例与失败注入 | 对应要求 |
| --- | --- | --- |
| FACTS | 同版本数值/日期/单位/分组原位渲染；零/负/缺失/NaN/旧版/错摘要/伪 receipt、算术舍入与零分母 | PUB-02/04/08、PROD-E01/03 |
| REQUIREMENTS | 六来源、九指标、撤回、窗口替换、部分计算；未知需求或自报完成不能获得 coverage | PUB-03/05 |
| OPEN | 合法解释、条件行动、同义改写；无据因果、错误窗口、遗漏 AND 条件；审核超时/无定位/预算耗尽/错版本 | PUB-05/06/07 |
| HYPOTHESIS | 当前 compare/time_series 实测、inferred_columns；同文本错指标、反向原测量、冲突/旧版/不足；正文状态可见 | PUB-09、PROD-E02 |
| CONFIRM | 方法许可不暂停；真分母/窗口/成本歧义暂停；复用、相关版本改变、skip、cancel、expire、重复恢复 | PROD-C01 |
| HISTORY | 规范历史、工具成对、尾部详情可恢复；压缩、轮次回退、旧会话只读、拒绝草案隔离 | PROD-S01/02、PUB-10 |
| ARTIFACT | 指定答案导出/刷新、表格/公式/真实图、跨会话拒绝、附件丢失及保存失败 | PUB-10、PROD-O02/W01 |
| TOOLS | 注册 schema→registry.execute→真实工具输出；工具搜索激活；高级方法/文件/知识/任务入口保留 | PROD-A/D/T/K/X |
| SCOPE-DAG | 独立与综合、坏表隔离、不存在/自依赖/环、错任务/会话/计划及依赖缺失 | PROD-A04/T02 |
| LIFECYCLE | 同步/流式/确认恢复同终局；取消/超时/保存失败；每轮唯一终态；预算和 ledger 闭合 | PUB-01/10/12 |
| CONSULT | 无文件与有文件纯咨询、既有结果追问、实际工具权限与路由 | PROD-I01—09、PUB-11 |

TOOLS 必须穿过注册入口，不能只直接 import 同名函数。对已有低风险功能不叠加无意义测试；仅补当前未覆盖的真实入口和本次变更的行为。旧私有实现测试应随新行为承接而删除，不同时维护两套同功能验收。

## 5. 证据阶段与入口门

```mermaid
flowchart LR
    R[需求及原编号可追溯] --> N[新行为正反例与原问题 RED]
    N --> C[单路径接入并删除旧入口]
    C --> Z[零调用默认路径审查 历史材料可用性核对]
    Z --> E2[新目录 full-offline]
    E2 --> E3[相同矩阵 Provider 禁用正常 app]
    E3 --> V[必要视觉 oracle]
    V --> F[新候选精确冻结与授权]
    F --> E4[完整自然 Provider 批次]
```

E1 是局部结构/行为，E2 是完整离线，E3 是 Provider 禁用正常 app，E4 是真实 Provider 正常 app。HTTP picker/视觉/浏览器刷新未测必须 unassessed；控制路线按 AGENTS.md 在批前选定，改变路线产生新身份。不因浏览器能力不可用停止无关引擎与 HTTP 证据工作。

真实 Provider 前必须同时满足：所有必需默认路径可达；新旧入口无并存；独立正反例覆盖；历史原始材料可用性单列，只有可读取且摘要核对后才能记作重放；用户已确认缺失时保持unassessed、新链自然行为归P5；调用预算含默认一次审核；当前 HEAD/dirty、全部输入/oracle/driver/模型/端点/ledger 精确冻结。账本文件、历史摘要或旧授权不能替代新授权。

### 5.1 当前核心收据的判定边界

[本地核心合同实施收据](../../audit/2026-09-30-trusted-publication-contract-implementation.md)记录 `test_trusted_publication_pipeline.py` 与 `test_trusted_publication_facts.py` 的新预期行为：空 facts 咨询、严格草案、坏引用局部拒绝、一次审核失效、九项独立需求与缺口/撤回、实际回执文件/当前身份、附件 byte SHA 和需求归属；并通过既有受限 workspace 合同验证回执核验不扩大原数据权限。

这是 CONSULT / FACTS / OPEN / REQUIREMENTS / ARTIFACT 的核心切片；输入需求语义绑定、自然风格生成、M04 原测量状态、确认恢复、app lifecycle、工作台/压缩/导出还没有被此收据承接。脚本 accept_all 不签收开放内容语义质量；手写六种表达不计 M05-STYLE 通过；符号链接创建 skip 不计该负例通过。完整离线当前树仍含旧运行链，不计 P4 新链或 E3/E4。

### 5.2 原生测量与需求身份的局部证据

[2026-10-01 语义绑定收据](../../audit/2026-10-01-trusted-publication-semantic-bindings.md)新增 36 个预期行为用例：真实规范历史九项/替换/撤回与局部来源失效、实际注册工具和回执的混合描述/比较、原精度/零/负基数、当前已注册假设的原测量支持/反驳及正文状态、真实 durable 业务决定引用。原失败目录和判据保留。

该切片承接 FACTS / REQUIREMENTS / HYPOTHESIS / CONFIRM 的部分边界；确认引用不代表 app resume 已通过，手选需求跨度/绑定不代表自然意图语义已通过。其他原生族、整链需求语义、历史压缩、M01—M06 新 app、唯一终局、自然审核和 R5 删除仍未签收；原编号表仍按目标保留，不因局部通过批量改写状态。

## 6. 原始 VP/IC/CP 全编号追溯

以下从三个原验收文档的**首个定义行**提取，不复制历史 passed 状态。共 VP 84、IC 56、CP 40 项。表中“待新验收”不表示旧行为未存在，只表示不得继承旧验收身份。原编号完整保留以便逐项审核，需求表述以链接原文为准。

替代项：IC-L01—04/L06 的旧运行迁移改为旧会话只读；IC-L05 原事件/结果保留仍有效；IC-B05 的旧恢复部分同理。CP-AC21 的旧隐藏块由新结构协议替代但不信任伪协议的行为保留；AC29/AC38 的零新增审核规则由已批准默认一次审核替代；AC36 的旧 reader 兼容改为只读历史。其余目标继续有效。

### VP

来源：[2026-09-06-analysis-value-preservation-acceptance.md](2026-09-06-analysis-value-preservation-acceptance.md)。源行号按本次基线记录。

| 原编号 | 源行 | 原输入或条件摘要 | 新需求与验收族 | 处理 |
| --- | ---: | --- | --- | --- |
| VP-I01 | 46 | 你好，请分析收入趋势 | PROD-I01—09；CONSULT | 目标保留；待新验收 |
| VP-I02 | 47 | 不要报告，只导出这张表 | PROD-I01—09；CONSULT | 目标保留；待新验收 |
| VP-I03 | 48 | 请分析收入下降原因并给出分析建议 | PROD-I01—09；CONSULT | 目标保留；待新验收 |
| VP-I04 | 49 | 中英文等价否定/转折请求 | PROD-I01—09；CONSULT | 目标保留；待新验收 |
| VP-I05 | 50 | “计算总收入”“什么是回归分析” | PROD-I01—09；CONSULT | 目标保留；待新验收 |
| VP-I06 | 51 | 同时出现咨询与执行，主任务不明确 | PROD-I01—09；CONSULT | 目标保留；待新验收 |
| VP-I07 | 52 | F-BAD-OTHER，只分析目标 sales | PROD-I01—09；CONSULT | 目标保留；待新验收 |
| VP-I08 | 53 | 同 I07，但 contracts 为 compact refs | PROD-I01—09；CONSULT | 目标保留；待新验收 |
| VP-I09 | 54 | F-RET7，只拟合聚合留存曲线 | PROD-I01—09；CONSULT | 目标保留；待新验收 |
| VP-I10 | 55 | 同时要求聚合曲线和个人留存 | PROD-I01—09；CONSULT | 目标保留；待新验收 |
| VP-I11 | 56 | 当前 scope 限定 A，文本提及 B | PROD-I01—09；CONSULT | 目标保留；待新验收 |
| VP-I12 | 57 | no-data、缺必要列、未解决高风险确认 | PROD-I01—09；CONSULT | 目标保留；待新验收 |
| VP-S01 | 65 | 同证据，“给出行动建议”与 recommend actions | PUB-06/07/11；OPEN / CONSULT | 目标保留；待新验收 |
| VP-S02 | 66 | 同证据，中文预测与英文 forecast | PUB-06/07/11；OPEN / CONSULT | 目标保留；待新验收 |
| VP-S03 | 67 | “请详细诊断原因” | PUB-06/07/11；OPEN / CONSULT | 目标保留；待新验收 |
| VP-S04 | 68 | “简短说明并给一个建议” | PUB-06/07/11；OPEN / CONSULT | 目标保留；待新验收 |
| VP-S05 | 69 | “只要公式，不需要建议” | PUB-06/07/11；OPEN / CONSULT | 目标保留；待新验收 |
| VP-S06 | 70 | pass_with_downgrades＋有效观察 | PUB-06/07/11；OPEN / CONSULT | 目标保留；待新验收 |
| VP-S07 | 71 | 某证据失败，另一独立证据通过 | PUB-06/07/11；OPEN / CONSULT | 目标保留；待新验收 |
| VP-S08 | 72 | 无任何业务证据 | PUB-06/07/11；OPEN / CONSULT | 目标保留；待新验收 |
| VP-N01 | 80 | D7 为 10%，当前不能预测 D30 | PUB-02/05/06/08；FACTS / OPEN | 局部离线：实际D7原值.1按真实fraction/percent/skip决定呈现；原F-RET7与自然整场景待核 |
| VP-N02 | 81 | 建议继续收集至第30天再验证 | PUB-02/05/06/08；FACTS / OPEN | 目标保留；待新验收 |
| VP-N03 | 82 | D30 留存预计为 5% | PUB-02/05/06/08；FACTS / OPEN | 局部离线：未知D30结构引用拒绝＋一次固定审核扣留错误断言；自然判断待核 |
| VP-N04 | 83 | 不能预测 D30，但 D30 大约是 5% | PUB-02/05/06/08；FACTS / OPEN | 局部离线：固定审核扣留错误D30片段并保留实际观测；自然混合句质量待核 |
| VP-N05 | 84 | 如果 D30 达到预先阈值，则继续试点 | PUB-02/05/06/08；FACTS / OPEN | 目标保留；待新验收 |
| VP-N06 | 85 | F-TWO-SCOPE 中 B 的 D30 为 8% | PUB-02/05/06/08；FACTS / OPEN | 局部离线：实际A7/B30＋当前fraction原确认，B点.08渲染8%、A冒用/倒序/同名换版拒绝；原F-TWO-SCOPE整场景及自然待核 |
| VP-N07 | 86 | 没做检验却说“差异不显著” | PUB-02/05/06/08；FACTS / OPEN | 目标保留；待新验收 |
| VP-N08 | 87 | 某工具完成合法检验，另一无关主张没检验 | PUB-02/05/06/08；FACTS / OPEN | 目标保留；待新验收 |
| VP-N09 | 88 | 有效统计工具类型不是 ab_test | PUB-02/05/06/08；FACTS / OPEN | 目标保留；待新验收 |
| VP-N10 | 89 | 合规事实＋一个无依据解释，可可靠定位 | PUB-02/05/06/08；FACTS / OPEN | 目标保留；待新验收 |
| VP-N11 | 90 | 复杂混合句无法可靠定位/修订 | PUB-02/05/06/08；FACTS / OPEN | 目标保留；待新验收 |
| VP-N12 | 91 | 最终候选为空/含未执行工具标记/修订仍错 | PUB-02/05/06/08；FACTS / OPEN | 目标保留；待新验收 |
| VP-C01 | 99 | F-SALES，statistical_inference=false | PROD-S02 / PUB-10；HISTORY | 目标保留；待新验收 |
| VP-C02 | 100 | 同 F-SALES 却推断全部市场 | PROD-S02 / PUB-10；HISTORY | 目标保留；待新验收 |
| VP-C03 | 101 | 单一来源、口径和完整性可核对 | PROD-S02 / PUB-10；HISTORY | 目标保留；待新验收 |
| VP-C04 | 102 | 大样本但选择偏差或分析单位错误 | PROD-S02 / PUB-10；HISTORY | 目标保留；待新验收 |
| VP-C05 | 103 | 365天结构化观察窗 | PROD-S02 / PUB-10；HISTORY | 目标保留；待新验收 |
| VP-C06 | 104 | 时段无法解析或频率未知 | PROD-S02 / PUB-10；HISTORY | 目标保留；待新验收 |
| VP-C07 | 105 | 缺失、零值含义未知 | PROD-S02 / PUB-10；HISTORY | 目标保留；待新验收 |
| VP-C08 | 106 | 相关、前后对比、合法因果设计分别输入 | PROD-S02 / PUB-10；HISTORY | 目标保留；待新验收 |
| VP-E01 | 114 | F-SIX，六项均为用户主要问题 | PUB-03/04；REQUIREMENTS / FACTS | 局部离线：实际六来源各10n→11n/3与4记录＋独立Python结果并存；原F-SIX完整app/自然待核 |
| VP-E02 | 115 | 当前收据第一项，其他计划占据最近四条 evidence | PUB-03/04；REQUIREMENTS / FACTS | 目标保留；待新验收 |
| VP-E03 | 116 | F-GROUP，最大值在第四组 | PUB-03/04；REQUIREMENTS / FACTS | 目标保留；待新验收 |
| VP-E04 | 117 | 比较值/组名/分母/时期处在不同字段 | PUB-03/04；REQUIREMENTS / FACTS | 局部离线：实际维度、七日分母及原1818→684/-1134、47/24行、两期合并71行/30日保留，重叠并集和错值拒绝；全矩阵待核 |
| VP-E05 | 118 | 超大结果、上下文预算有限 | PUB-03/04；REQUIREMENTS / FACTS | 目标保留；待新验收 |
| VP-E06 | 119 | F-COMPACT，中等与大型输出 | PUB-03/04；REQUIREMENTS / FACTS | 目标保留；待新验收 |
| VP-E07 | 120 | 结果保存失败/同 id 不同内容 | PUB-03/04；REQUIREMENTS / FACTS | 目标保留；待新验收 |
| VP-E08 | 121 | 二次压缩已经压缩的消息 | PUB-03/04；REQUIREMENTS / FACTS | 目标保留；待新验收 |
| VP-E09 | 122 | 发布包创建后新增或修改证据 | PUB-03/04；REQUIREMENTS / FACTS | 目标保留；待新验收 |
| VP-E10 | 123 | 预算耗尽仍有未覆盖问题 | PUB-03/04；REQUIREMENTS / FACTS | 目标保留；待新验收 |
| VP-H01 | 131 | It is false that＋原假设 | PUB-09；HYPOTHESIS | 目标保留；待新验收 |
| VP-H02 | 132 | 完全文本相同，dataset 错误 | PUB-09；HYPOTHESIS | 目标保留；待新验收 |
| VP-H03 | 133 | dataset 同名，plan/version 错误 | PUB-09；HYPOTHESIS | 目标保留；待新验收 |
| VP-H04 | 134 | 只有文本重合或模型自报“已证明” | PUB-09；HYPOTHESIS | 目标保留；待新验收 |
| VP-H05 | 135 | 先有支持，后删除/失效依赖证据 | PUB-09；HYPOTHESIS | 目标保留；待新验收 |
| VP-H06 | 136 | F-HYP，合法引用、当前验证、要求与可计算谓词均满足 | PUB-09；HYPOTHESIS | 目标保留；待新验收 |
| VP-H07 | 137 | 满足判定条件的反向证据 | PUB-09；HYPOTHESIS | 目标保留；待新验收 |
| VP-H08 | 138 | 同时存在当前有效支持与反证 | PUB-09；HYPOTHESIS | 目标保留；待新验收 |
| VP-H09 | 139 | 中文与英文等价证据关系，结构化依据相同 | PUB-09；HYPOTHESIS | 目标保留；待新验收 |
| VP-H10 | 140 | 已有关系遇新问题/新版本/重新加载 | PUB-09；HYPOTHESIS | 目标保留；待新验收 |
| VP-H11 | 141 | 后续新证据、会话恢复、最终发布 | PUB-09；HYPOTHESIS | 目标保留；待新验收 |
| VP-H12 | 142 | 归因未能排除替代解释/字段不足 | PUB-09；HYPOTHESIS | 目标保留；待新验收 |
| VP-A01 | 150 | 我是业务人员，解释这些结果 | PUB-07；OPEN | 目标保留；待新验收 |
| VP-A02 | 151 | 我是数据分析师，给方法细节 | PUB-07；OPEN | 目标保留；待新验收 |
| VP-A03 | 152 | 给管理层汇报 | PUB-07；OPEN | 目标保留；待新验收 |
| VP-A04 | 153 | 固定事实依次套 A01—A03 | PUB-07；OPEN | 目标保留；待新验收 |
| VP-A05 | 154 | 先业务视角，后改分析师视角 | PUB-07；OPEN | 目标保留；待新验收 |
| VP-A06 | 155 | 先专业术语，后要求用大白话 | PUB-07；OPEN | 目标保留；待新验收 |
| VP-A07 | 156 | 未声明身份或仅数据中出现“经理” | PUB-07；OPEN | 目标保留；待新验收 |
| VP-A08 | 157 | 混合受众、临时面向受众、会话恢复 | PUB-07；OPEN | 目标保留；待新验收 |
| VP-U01 | 165 | 八条当前有效 verified 结论 | PROD-W01 / PUB-10；ARTIFACT | 目标保留；待新验收 |
| VP-U02 | 166 | 同时有已验证与待验证发现 | PROD-W01 / PUB-10；ARTIFACT | 目标保留；待新验收 |
| VP-U03 | 167 | 待验证项有依据、限制、下一步 | PROD-W01 / PUB-10；ARTIFACT | 目标保留；待新验收 |
| VP-U04 | 168 | 已验证证据指纹失效或版本改变 | PROD-W01 / PUB-10；ARTIFACT | 目标保留；待新验收 |
| VP-U05 | 169 | 最终 SSE 后刷新页面 | PROD-W01 / PUB-10；ARTIFACT | 目标保留；待新验收 |
| VP-U06 | 170 | 切换会话或重开历史会话 | PROD-W01 / PUB-10；ARTIFACT | 目标保留；待新验收 |
| VP-U07 | 171 | Markdown/HTML 导出 | PROD-W01 / PUB-10；ARTIFACT | 目标保留；待新验收 |
| VP-U08 | 172 | 折叠、展开、空状态及键盘操作 | PROD-W01 / PUB-10；ARTIFACT | 目标保留；待新验收 |
| VP-B01 | 182 | 加载 F-SALES → 中文分析＋建议 → 最终回复 → 刷新 | PUB-01/10/12；LIFECYCLE / ARTIFACT | 目标保留；待新验收 |
| VP-B02 | 183 | 加载 F-RET7 → 发布 D7＋不能预测 D30 → 尝试错误 D30 断言 | PUB-01/10/12；LIFECYCLE / ARTIFACT | 目标保留；待新验收 |
| VP-B03 | 184 | 多数据源/六子问题 → 中途压缩 → 综合回复 → 展开/导出 | PUB-01/10/12；LIFECYCLE / ARTIFACT | 目标保留；待新验收 |
| VP-B04 | 185 | 创建竞争假设 → 支持/反证 → 补新证据 → 修改版本 → 刷新 | PUB-01/10/12；LIFECYCLE / ARTIFACT | 目标保留；待新验收 |
| VP-B05 | 186 | 固定分析结果 → 业务/分析师/管理层连续追问 | PUB-01/10/12；LIFECYCLE / ARTIFACT | 目标保留；待新验收 |
| VP-B06 | 187 | 工具失败、保存失败、修订失败、预算耗尽和待确认分别触发 | PUB-01/10/12；LIFECYCLE / ARTIFACT | 目标保留；待新验收 |

### IC

来源：[2026-09-07-intent-clarification-acceptance.md](2026-09-07-intent-clarification-acceptance.md)。源行号按本次基线记录。

| 原编号 | 源行 | 原输入或条件摘要 | 新需求与验收族 | 处理 |
| --- | ---: | --- | --- | --- |
| IC-Q01 | 34 | F2，仅要求拟合观测内留存公式，口径已明确 | PROD-C01；CONFIRM | 目标保留；待新验收 |
| IC-Q02 | 35 | F1，要求九项指标 | PROD-C01；CONFIRM | 目标保留；待新验收 |
| IC-Q03 | 36 | 要求描述性复购率，分母/窗口已明确 | PROD-C01；CONFIRM | 目标保留；待新验收 |
| IC-Q04 | 37 | 需要净收益但两种成本定义均合理、未提供答案 | PROD-C01；CONFIRM | 目标保留；待新验收 |
| IC-Q05 | 38 | 同 Q04，但当前请求已给出成本边界 | PROD-C01；CONFIRM | 目标保留；待新验收 |
| IC-Q06 | 39 | F3 指代不唯一且影响范围 | PROD-C01；CONFIRM | 目标保留；待新验收 |
| IC-Q07 | 40 | 预测/因果/分类计算，已授权分析且必要输入明确 | PROD-C01；CONFIRM | 目标保留；待新验收 |
| IC-Q08 | 41 | 技术工具失败，已有合法恢复方法 | PROD-C01；CONFIRM | 目标保留；待新验收 |
| IC-Q09 | 42 | 模型主动 ask：是否按留存方法继续 | PROD-C01；CONFIRM | 目标保留；待新验收 |
| IC-Q10 | 43 | 模型主动 ask：真实未决分母 | PROD-C01；CONFIRM | 目标保留；待新验收 |
| IC-Q11 | 44 | 一次多问题：已有答案+方法审批+真实窗口缺口 | PROD-C01；CONFIRM | 目标保留；待新验收 |
| IC-Q12 | 45 | 模型伪造 safe_default、dataset_ref 或“所有操作受阻” | PROD-C01；CONFIRM | 目标保留；待新验收 |
| IC-Q13 | 46 | D1—D7 留存数据；请求“解释 D7，并判断能否预测 D30；若不能说明缺失证据” | PROD-C01；CONFIRM | 目标保留；待新验收 |
| IC-Q14 | 47 | 已明确“提出并检验至少两种竞争性假设”的数据分析请求 | PROD-C01；CONFIRM | 目标保留；待新验收 |
| IC-R01 | 53 | 同一业务决定换措辞、换显示文案 | PROD-C01 / PUB-10；CONFIRM | 目标保留；待新验收 |
| IC-R02 | 54 | 消息数量变化，业务范围不变 | PROD-C01 / PUB-10；CONFIRM | 目标保留；待新验收 |
| IC-R03 | 55 | 同方法但复购改为到期续购 | PROD-C01 / PUB-10；CONFIRM | 目标保留；待新验收 |
| IC-R04 | 56 | 窗口 30 天改 7 天，或“包含成本”改“不包含成本” | PROD-C01 / PUB-10；CONFIRM | 目标保留；待新验收 |
| IC-R05 | 57 | 相关数据版本变化 vs 无关文件变化 | PROD-C01 / PUB-10；CONFIRM | 目标保留；待新验收 |
| IC-R06 | 58 | 相同文本来自另一 session | PROD-C01 / PUB-10；CONFIRM | 目标保留；待新验收 |
| IC-R07 | 59 | 重复提交同一 resume / 过期 version | PROD-C01 / PUB-10；CONFIRM | 目标保留；待新验收 |
| IC-R08 | 60 | resolved / skipped / cancelled / expired 的同类记录 | PROD-C01 / PUB-10；CONFIRM | 目标保留；待新验收 |
| IC-R09 | 61 | 同时到达等价 open candidate | PROD-C01 / PUB-10；CONFIRM | 目标保留；待新验收 |
| IC-R10 | 62 | advisory/reused/rejected、正常暂停分别经过同步/流式/恢复入口 | PROD-C01 / PUB-10；CONFIRM | 目标保留；待新验收 |
| IC-L01 | 70 | 恢复 F5 纯模板审批 | PROD-S01/02；HISTORY / CONFIRM | 旧运行迁移替代为只读；其余目标保留 |
| IC-L02 | 71 | 恢复真正的旧窗口/字段决定 | PROD-S01/02；HISTORY / CONFIRM | 旧运行迁移替代为只读；其余目标保留 |
| IC-L03 | 72 | 未识别来源/范围的旧记录 | PROD-S01/02；HISTORY / CONFIRM | 旧运行迁移替代为只读；其余目标保留 |
| IC-L04 | 73 | 连续加载、刷新、重启 | PROD-S01/02；HISTORY / CONFIRM | 旧运行迁移替代为只读；其余目标保留 |
| IC-L05 | 74 | 已有历史结果和确认事件 | PROD-S01/02；HISTORY / CONFIRM | 目标保留；待新验收 |
| IC-L06 | 75 | 新元数据由兼容旧代码读取，或代码回滚 | PROD-S01/02；HISTORY / CONFIRM | 旧运行迁移替代为只读；其余目标保留 |
| IC-M01 | 83 | 原始省钱卡九指标+连续付费/影响目标 | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 目标保留；待新验收 |
| IC-M02 | 84 | M01 改变“复购率”在列表中的位置 | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 目标保留；待新验收 |
| IC-M03 | 85 | “不要分析留存，只分析省钱卡收益” | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 目标保留；待新验收 |
| IC-M04 | 86 | “仅计算复购率，口径如下……” | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 目标保留；待新验收 |
| IC-M05 | 87 | 原始聚合留存公式拟合请求 | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 目标保留；待新验收 |
| IC-M06 | 88 | “拟合当前曲线，不预测 D30” | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 目标保留；待新验收 |
| IC-M07 | 89 | “预测后续留存”，数据/验证条件充足与不充足两组 | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 目标保留；待新验收 |
| IC-M08 | 90 | 收益、趋势、纯咨询、数据操作、问候+分析等对照 | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 目标保留；待新验收 |
| IC-M09 | 91 | F1 缺少成本/对照，但描述性支付指标完整 | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 目标保留；待新验收 |
| IC-M10 | 92 | F2 含 0/未成熟 cohort/权重歧义 | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 目标保留；待新验收 |
| IC-O01 | 100 | 合法 LLM 主方法、空 supporting | PUB-12；LIFECYCLE / CONSULT | 目标保留；待新验收 |
| IC-O02 | 101 | F6 各失败模式 | PUB-12；LIFECYCLE / CONSULT | 目标保留；待新验收 |
| IC-O03 | 102 | 必要/无关/复用/失效四种候选 | PUB-12；LIFECYCLE / CONSULT | 目标保留；待新验收 |
| IC-O04 | 103 | 固定验收集统计 | PUB-12；LIFECYCLE / CONSULT | 目标保留；待新验收 |
| IC-S01 | 104 | 无对照的购卡前后变化 | PUB-02/08；FACTS / CONFIRM | 目标保留；待新验收 |
| IC-S02 | 105 | 只观测 D1—D7 的描述性拟合 | PUB-02/08；FACTS / CONFIRM | 局部离线：原工具观测/三族拟合/未验证显式情景范围及真实单位选择；原完整场景待核 |
| IC-S03 | 106 | 跨 dataset/version/plan 的旧答案或证据 | PUB-02/08；FACTS / CONFIRM | 目标保留；待新验收 |
| IC-S04 | 107 | 工具失败/无真实收据/未执行计划 | PUB-02/08；FACTS / CONFIRM | 目标保留；待新验收 |
| IC-S05 | 108 | 所有 E1—E3 运行 | PUB-02/08；FACTS / CONFIRM | 目标保留；待新验收 |
| IC-S06 | 109 | 必要语义仍未解决但用户 skip/cancel 或模型反复问通用许可 | PUB-02/08；FACTS / CONFIRM | 目标保留；待新验收 |
| IC-B01 | 117 | 上传 F2，提交拟合请求 | PROD-C01/W01；CONFIRM / ARTIFACT | 目标保留；待新验收 |
| IC-B02 | 118 | 上传 F1，提交完整需求 | PROD-C01/W01；CONFIRM / ARTIFACT | 目标保留；待新验收 |
| IC-B03 | 119 | 提交真正有成本/窗口歧义的请求，回答具体选项 | PROD-C01/W01；CONFIRM / ARTIFACT | 目标保留；待新验收 |
| IC-B04 | 120 | 将 B03 换措辞继续，再实质改变口径 | PROD-C01/W01；CONFIRM / ARTIFACT | 目标保留；待新验收 |
| IC-B05 | 121 | 恢复 F5，刷新/重启，再跳过真实语义问题 | PROD-C01/W01；CONFIRM / ARTIFACT | 旧运行迁移替代为只读；其余目标保留 |
| IC-B06 | 122 | 脚本模型发无关方法 ask 与真实语义 ask 两种调用 | PROD-C01/W01；CONFIRM / ARTIFACT | 目标保留；待新验收 |

### CP

来源：[2026-09-08-answer-content-acceptance.md](2026-09-08-answer-content-acceptance.md)。源行号按本次基线记录。

| 原编号 | 源行 | 原输入或条件摘要 | 新需求与验收族 | 处理 |
| --- | ---: | --- | --- | --- |
| CP-AC01 | 15 | 第8轮预览只有 early，后追加 late 结果与 evidence，再终局 | PUB-01/02；LIFECYCLE / FACTS | 目标保留；待新验收 |
| CP-AC02 | 16 | 同 receipt id 修改 result hash/数值；另测只改限制或验证状态 | PUB-01/02；LIFECYCLE / FACTS | 局部离线：原来源/版本重核；诊断metadata不授予事实；完整场景待核 |
| CP-AC03 | 17 | 原数据 v1 已验证，切换 v2，夹入其他会话同名数据 | PUB-01/02；LIFECYCLE / FACTS | 局部离线：当前身份/跨会话拒绝；完整场景待核 |
| CP-AC04 | 18 | 同一最终候选重复回调、刷新、导出 | PUB-01/02；LIFECYCLE / FACTS | 局部离线：实际同answer_ref幂等提交/读取/trace摘要；浏览器刷新与完整导出场景待核 |
| CP-AC05 | 19 | 终局来源文件写失败或 save 失败 | PUB-01/02；LIFECYCLE / FACTS | 目标保留；待新验收 |
| CP-AC06 | 20 | 同步与流式各走正常/修订/断流路径 | PUB-01/02；LIFECYCLE / FACTS | 目标保留；待新验收 |
| CP-AC07 | 21 | P08 Python fallback 已算描述结果；无依据 D30；有效/孤立工具消息 | PUB-01/02；LIFECYCLE / FACTS | 目标保留；待新验收 |
| CP-AC08 | 27 | Python stdout 前180字符是概览，尾部 weighted_delta=0.00277 | PUB-03/04；FACTS / REQUIREMENTS | 局部离线：D1原.17080/.16803差.00277经真实Python result_data保留；旧stdout猜值按v2替代，原长输出整场景待核 |
| CP-AC09 | 28 | result 有收益/人数，replay 有代码/hash/timeout | PUB-03/04；FACTS / REQUIREMENTS | 局部离线：真实Python业务结构值进入claim，replay/code/hash/risk不作公开事实；原收益/人数整场景待核 |
| CP-AC10 | 29 | 12组，每组 name/count/revenue，要求全部分组 | PUB-03/04；FACTS / REQUIREMENTS | 局部离线：原12组name/count/revenue经实际Python完整保留原顺序和数值；全app/自然待核 |
| CP-AC11 | 30 | 3候选拟合族、10观测点、残差、范围与未知零值 | PUB-03/04；FACTS / REQUIREMENTS | 局部离线：实际原points/fits/残差与未验证情景完整保留；原10点及全部零值整场景待核 |
| CP-AC12 | 31 | 超 prompt/扫描预算，含很大单组和最后一个必答组 | PUB-03/04；FACTS / REQUIREMENTS | 局部离线：原150组及最后一组完整；超限完整交付待核 |
| CP-AC13 | 32 | 详情 hash 不符、文件缺失、越界路径各一份 | PUB-03/04；FACTS / REQUIREMENTS | 局部离线：实际详情SHA/不存在/越界拒绝；全矩阵待核 |
| CP-AC14 | 33 | 同工具 id 两种内容，反复 micro_compact，模拟落盘失败 | PUB-03/04；FACTS / REQUIREMENTS | 目标保留；待新验收 |
| CP-AC15 | 34 | 普通均值 D1=.17080/D7=.05100；加权=.16803/.05028；最大差=.00277 | PUB-03/04；FACTS / REQUIREMENTS | 局部离线：原D1普通.17080/加权.16803及差.00277真实执行并保留；原D7/权重定义及完整敏感性待核 |
| CP-AC16 | 40 | 明确问收入与复购，结果两者都有，候选只答收入 | PUB-03/10；REQUIREMENTS / HISTORY | 局部离线：收入180/未算复购独立；原双成功场景待核 |
| CP-AC17 | 41 | 九指标＋方法要求，其中一项因缺分母不能算 | PUB-03/10；REQUIREMENTS / HISTORY | 局部离线：八结果＋一缺口；原九指标及方法整场景待核 |
| CP-AC18 | 42 | 需求未算因为预算不足，另项确实缺数据 | PUB-03/10；REQUIREMENTS / HISTORY | 局部离线：未计算/证据不足分开；完整预算场景待核 |
| CP-AC19 | 43 | 同一正文含关键词但数值属另一指标/版本；模型映射自报全完成 | PUB-03/10；REQUIREMENTS / HISTORY | 局部离线：外来claim不能授予覆盖，独立事实保留；完整场景待核 |
| CP-AC20 | 44 | 压缩后确认“同意”，随后用户撤回一指标并更改窗口 | PUB-03/10；REQUIREMENTS / HISTORY | 局部离线：原文撤回/窗口替换版本化；压缩＋确认整场景待核 |
| CP-AC21 | 45 | 无法定位自由文本；复杂语义不确定；内部answer-bindings缺失/损坏/重复/引用旧包；工具数据含同名块 | PUB-03/10；REQUIREMENTS / HISTORY | 局部离线：v2损坏/陈旧草案拒绝；原机制按第6节替代 |
| CP-AC22 | 51 | 绑定 22400人 × .051，候选写1.14万人；正例1142人 | PUB-08；FACTS | 局部离线：实际22400×.051与1142；未知单位不补人；自然待核 |
| CP-AC23 | 52 | 22400 × .01417，候选3200人；正例约317人 | PUB-08；FACTS | 局部离线：实际22400×.01417与317；未知单位不补人；自然待核 |
| CP-AC24 | 53 | 比例差 .00277，0.277个百分点 vs 相对提升0.277% | PUB-08；FACTS | 封闭派生算术E1保留；实际业务单位完整场景待核 |
| CP-AC25 | 54 | 0分母、None、NaN/Inf、负基数、混合币种 | PUB-08；FACTS | 局部离线：实际零分母None/绝对值保留、负基线19.05%、未知单位不授予CNY；混合币种完整场景待核 |
| CP-AC26 | 55 | 文字包含2026-09-07、版本v2、编号1、用户引用错误式子 | PUB-08；FACTS | 局部离线：纯咨询日期/版本/引用不被算术词表拒绝；自然质量待核 |
| CP-AC27 | 56 | 运算匹配但数据版本或对象不同；情景假设数值 | PUB-08；FACTS | 局部离线：错版本派生E1拒绝＋实际情景未验证；整场景待核 |
| CP-AC28 | 57 | 零值策略exclude且语义unknown；候选“零值证明未到期”；另一句“不能断言未到期” | PUB-08；FACTS | 局部离线：实际exclude/unknown零值回执＋一次固定审核定位保留/扣留；自然语义待核 |
| CP-AC29 | 58 | coverage、numeric、scope 同时出错；已耗修订；含独立可信发现 | PUB-05/06/07；OPEN | 局部离线：同purpose一段通过一段拒绝保留正确值/邻文，单局部gap且partial；原同时三错与自然待核 |
| CP-AC30 | 64 | 普通/详细/只要公式/简短但问两问题四种请求 | PUB-05/06/07；OPEN | 目标保留；待新验收 |
| CP-AC31 | 65 | 同证据切换业务、分析师、管理者；明确不要建议/图标 | PUB-05/06/07；OPEN | 目标保留；待新验收 |
| CP-AC32 | 66 | 有待验证解释、无因果识别；要求建议 | PUB-05/06/07；OPEN | 目标保留；待新验收 |
| CP-AC33 | 67 | 正确chart ref、全角wrapper、未知hash、歧义引用、其他会话图 | PUB-10；ARTIFACT / HISTORY | 局部离线：实际chart登记/当前源/跨需求artifact ref拒绝，旧源不可用；全角wrapper按v2替代、视觉/跨会话整场景待核 |
| CP-AC34 | 68 | 表格/公式/图在1440px电脑端页面；键盘操作详情 | PUB-10；ARTIFACT / HISTORY | 目标保留；待新验收 |
| CP-AC35 | 69 | 图生成失败或不可用于当前结论 | PUB-10；ARTIFACT / HISTORY | 目标保留；待新验收 |
| CP-AC36 | 75 | 旧v1会话读取、新格式保存再载入、历史包>20、当前引用旧结果 | PUB-10；ARTIFACT / HISTORY | 按第 6 节替代机制；原保护目标保留 |
| CP-AC37 | 76 | 答案→刷新→Markdown及当前支持的其他导出→实际打开文件 | PUB-10；ARTIFACT / HISTORY | 目标保留；待新验收 |
| CP-AC38 | 77 | 固定合成小中大结果，已有上下文预算，记录调用数 | PUB-12；LIFECYCLE | 局部离线：原3/40/150规模、65000字符与零Provider；自然成本待核 |
| CP-AC39 | 78 | CP1—CP5改完，当前full-offline及全部40项记录 | PUB-12；LIFECYCLE | 目标保留；待新验收 |
| CP-AC40 | 79 | 授权后新真实批次：P08 M01—M06＋冻结内容样本 | PUB-12；LIFECYCLE | 目标保留；待新验收 |


## 12. 本轮行为收据与未核范围（2026-10-02）

本表更新为具体“局部离线”维度，未将完整原场景改记 passed。当前新摘要/复用组合65项、十文件组合194项的 run 与失败迁移见[同一切换收据第7节](../../audit/2026-10-01-p123-single-publication-cutover.md)。完整r8对冻结371文件为3205 passed /2 failed /2 skipped；两个咨询控制回归已修正并联合218 passed，完整r9为3207 passed /2 skipped、371摘要核对无变化。此后曲线/来源/确认128项和原生方法族122项为另行局部收据，不能借用r9冻结签收。

CONS-03 的实际执行禁止、五咨询路由不要求文件、INTENT-03 混合咨询/执行、INTENT-05 130轮撤回/替换历史、chat-only分支和rehearsal v2终稿已有局部编排证据。自然分类与知识解释、完整M01—M06、图表视觉/刷新、全部180原编号仍按原维度签收。脚本审核固定决定不能证明自然审核质量。

普通局部组合三次首次Flask/Werkzeug初始化异常的根因仍未确认。诊断105项与当前194组合通过不能追认原失败；不提前import、不skip、不修改依赖。全部失败目录保留。


23个native方法名已有实际registry/原回执检查；其中本轮16族有runtime publish/commit/reload案例，原7族既有不同深度局部证据，不能统一称全部模式整链passed。训练规模/CV、画像列、预览原精度和SHAP二选一当前模型要求有具体RED/GREEN。聚合业务名raw确认已有203联合收据，原币种与复杂单位场景仍待核。对应PRD PROD-A/E/C，具体来源/局限见切换收据7.5—7.8。


本轮跨源/单位111及72、原行动86、比较147、审核175项是另行局部身份，保留各自失败。新完整r11在本轮改动之后通过3245 passed /2 skipped /16 warnings，371冻结摘要均未变；结束后只修审核测试EOF空行，AST/全部非EOF字节相等证明单列。r10保留此前完整身份，未拼接签收。更新的7个原编号仅列实际已核维度，原180编号和未核要求保留，P4/P5及自然质量未通过。审核请求的完整原规则、未观测未来、原工具分母与一轮额度有证据；不能把固定审核当自然正反验收。详见同一切换收据7.9—7.11。

聚合14个原函数全部改走真实工具/确认/规范历史，所有原函数名保留；综合92原函数中本轮7项迁入新链，其余仍需逐项处理。局部193项与新八文件358项收据见切换记录7.12/7.13。新增原4行→2组、类型化日期4日、缺失成本/skip/旧源、原62点a=.18800129/R²=.98240474、原71行/30日及重叠并集负例；不把这些局部证据签收为所有180场景passed。

审核未派发的独立诊断在相同实际行动文件复现：unavailable、claims约58KB、无确定性issues，连同原需求/片段超过64KB。限定精确claim_refs后，一次固定审核与完整宿主事实同时保留。未扩大预算，不增加Provider调用，不证明自然审核质量。完整r12为3266 passed /3 failed /2 skipped /16 warnings，371摘要无变化；三旧断言更新为两期59/61＋合并120日和精确scenarios引用，原值/错误文本及全部公开事实继续断言。五文件56 passed，新full-offline r13正在重新冻结运行，r12失败和r11此前身份均保留。


完整r13已通过3269 passed /2 skipped /16 warnings，371冻结摘要无变化。原聚合正文需同时明确源4行与真实派生by_channel2行，追加原断言得到1 failed /32 passed；同一native原循环三行封闭标签/计数单位补齐后157联合通过，原业务未知单位不改变。当前r14在新371文件冻结上完整复验；此前绿灯不签收后改源码。详见切换收据7.15。


完整r14为3265 passed /4 failed /2 skipped /16 warnings，371摘要未变；失败为原业务名称测试把记录数“条”和业务金额单位一并要求未知。仅将断言精确区分原rows字段1条、全部业务测量单位None，五响应/旧源/伪币种拒绝均保留。167项联合通过，当前r15完整复验；相对r14所有产品源码不变，只一个测试字段断言修订。切换收据7.16记录全部失败、字节与冻结，不签收自然语义或全180场景。


当前完整r15通过3269 passed /2 skipped /16 warnings、332.44秒，371冻结摘要均未变；结束后未再修改源码或测试。两个原skip/16原warnings保持，r12/r14失败不倒填。当前只签收本轮离线门，全部180原场景、70旧依赖行为、正常app/视觉及自然语义仍未完成，见切换收据7.17及唯一计划。


## 13. 当前原行为承接、历史裁决与P4准备（2026-10-02）

本节为当前状态，前述r8—r15及局部收据保留历史身份。最后70原函数迁入唯一v2，综合92原函数名/顺序/全部parametrize装饰器保留；两个旧源码模块已按精确用户授权删除，全部测试/字节备份保留，源码import0。原一年365观测/原64KB内完整结果组/末组999预算正反与328项联合通过仅签收本地结构/编排，原自然解释/意图/审核质量不因此通过。完整r16为3271 passed /2 skipped /16 warnings、395.78秒，369文件集合/摘要均未变，见切换收据7.21。

用户确认ddb9daa/71e23d0精确原材料缺失时历史重放保持unassessed，两原失败不变，新链自然验收归P5。原自然材料不再作为P2无法推进的阻断，也不伪造重放或批准任何新的Provider调用。

P4准备身份为 `tmp/p4-preparation-20261002-r1`。20fixture和SHA、候选端口/新目录、local_http_api控制路线、M01—M06与咨询/生命周期组及独立原值oracle记录在preparation.json；完整原180行清单记录在original-180-oracle-checklist.json。清单全场景为unassessed，现有原行的局部证据仍保留；每个原编号必须按原输入/正反/阶段签收，不用M矩阵覆盖全部原能力。

现有launcher支持主要B/IC脚本族；CONS/混合路由无专用脚本transport、auxiliary默认执行意图，须在同一入口补足后冻结所有prompt/upload/confirmation值才运行完整批次。本准备文件有待展开marker，**不是可执行完整freeze**。不新建控制框架/Provider账本，不用真实P08 driver驱动禁用服务。新服务只用既有run_p7_browser_rehearsal.py，必须新目录、端口空闲、health ok=true/provider_enabled=false，保存exec/PID/端口、SSE每轮唯一终态、durable状态、原导出及runtime transport=0。

HTTP picker、可见正文/图表、浏览器刷新/console仍unassessed；必要IAB视觉单列身份。P4机制与正常app通过仍不等于P5自然质量。R5当前净-5864只签收收缩，R3/R4联合产品出口在P4/P5继续签收。没有新Provider授权、服务、浏览器、正式配置变更、部署或外部Git。


## 14. P4咨询准备的真实入口证据（2026-10-02）

CONS-01/02中文英文空数据与已加载数据、CONS-03零数据执行、CONS-04原答案/当前原事实、CONS-05缺原答案局部evidence_insufficient及INTENT-01/03实际计算已有13参数用例；五文件346通过。具体128前清理通过、r2三断言失败、r3真实缺源失败及r4闭环见切换收据7.22，固定脚本不签收自然语义质量。CONS-04原source_answer_id断言在规范需求状态，HostSnapshot只投影原claims；不能误读字段层次。

10个scripts和全部原test函数/装饰器保留，只清两处无调用helper16行。TESTING及历史退役说明已核现役范围。当前新完整r17在369文件冻结上运行；其结果尚不升级P4正常HTTP/必要视觉或P5自然质量。原180行未改passed，旧历史重放unassessed、两自然失败保持。

当前准备目录r2有21fixture及13咨询输入，完整joint提示/上传/确认/历史操作和INTENT-02/04/05仍待展开冻结。HTTP route准备与service health分开；尚无service/PID/browser，Provider initiated0。代码R5合并净-5803；产品联合R3/R4/R5仍按各阶段行为签收。


当前完整r17已签收3284 passed /2 skipped /16 warnings、480.12秒，369文件集合/摘要均未变；两skip/16warning仍独立列出，见切换收据7.23。原180行未改passed；咨询准备是13参数真实控制合同＋完整E2，尚未执行HTTP/视觉或自然语义。完整joint及其余控制冻结仍为P4下一工作，不据此发起Provider。


## 15. 当前P4正常app诊断与明确未通过项（2026-10-02）

当前完整r18 3289 passed /2 skipped /16 warnings、463.61秒，369文件集合/摘要未变。正常app r5（freeze r4）完整35组/68 SSE终态，13咨询/混合列明维度通过，实际工具/接受答案/导出独立身份和Provider0在同一切换收据7.24—7.25及tmp/p4-app-binding-20261002-r1中核对。此前r2/r3控制中断与r4六check失败保持，不能倒填。现役transport补七个实际selector且只读同计划假设；108 runtime通过。生产源码不变，合并净-5787行，原180行未改passed。

M04-INFER的当前计划ID缺源导致两轮failed；M05-PY-NOROW原Python对象没有所请求inclusive_days却整项answered，被独立oracle拒绝。事实原值存在和完整终态不能替代子需求交付。两项未关闭前P4不通过；不得补散文词表/引用旧假设/降低oracle。六源在实际测量回合逐dataset检查，后续纯继续回合不冒充重算；edge严格按amount sum/count/size与order_id nunique，缺失sum保持null。

INTENT-02/04/05、原180行完整正反、M03/M04部分selector、M06真实typed公式成本scope/skip/版本及必要官方IAB视觉仍待签收。HTTP picker/可见正文图表/刷新/console和固定脚本的自然语义质量全部unassessed；P5未就绪，无新的Provider授权。最后演练进程已停止，所有失败/输入/原函数/备份保留。


## 16. 精确结果子项和当前计划续接；中断身份保留（2026-10-06）

M04/M05原r5两失败在新p4-local-http-20261006-r1完整35组/68回合身份关闭；已列case/turn检查0失败、实际Provider0。M04同当前计划三轮支持/重载失效/当前反证，错误trend_slope候选仍拒；M05实际12天独立字段必须在对应规范义务与accepted render trace中交付，整段JSON存在不替代。缺字段not_computed、正确金额answered、stdout/metadata无权威和原答案字段重述均有实际工具测试。快速明确路由只继承等于当前宿主ID的continuation，旧/外来/无scope均拒。

局部187通过，完整r20 3307 passed /2 skipped、369源摘要未变；r19没有最终JUnit、r6只17组/24记录回合均保留为中断身份，不能拼接通过。原41个runtime顶层函数/类AST相等；完整收据见切换记录7.26及tmp/p4-recovery-20261006-r1。

原180行和各自未核目标保留；新批次不是全180通过。INTENT-02/04/05、M03/M04细分coverage、M06完整typed公式/skip/版本、视觉仍未签收。natural generation/semantic review、picker/visual/refresh/console均unassessed；P5尚未冻结授权。


## 17. P4本地联合签收（2026-10-08）

当前P4列明本地出口已签收，完整r29 3341 passed /2 skipped /17 warnings、369源摘要未变；新r4完整47组/90回合检查0失败及必要官方IAB、实际压缩/两种导出/标题/刷新同源。原180逐项/268原函数与41AST保留、净-5507行；Provider0，服务已停止。具体身份、原失败、控制桥接未评估、自然行为P5边界见[联合收据](../../audit/2026-10-08-p4-local-joint-signoff.md)。不倒填历史失败、不把脚本审核当自然质量、不授权新Provider/正式默认/部署/外部Git。

## 18. 历史辅助与模型可变输出验收（2026-10-08用户确认）

本节完善既有REQUIREMENTS/OPEN/HISTORY/CONFIRM/CONSULT验收，不新增框架或付费judge；原VP/IC/CP及本批50条hard oracle原文保留。

| 材料 | 可以证明 | 当前源签收条件与禁止混用 |
| --- | --- | --- |
| 历史冻结原请求、实际响应、回执、确认及失败 | 原版本故障、旧能力、当前反例与回归线索 | 记录源/模型/输入/SHA/路线/单位，穿当前实际入口；缺材料unassessed，不倒填 |
| 本批M01/M03/M04/M05/M06原材料 | 咨询误阻塞、需求丢失、短续问绕过、风格/版本/确认故障 | 原反例先保持；不先改selector/审核/用户答案。协议变化时明确旧格式回放边界 |
| 新协议固定正反输入 | 结构与宿主控制、上下文隔离、事实绑定及相邻能力 | 合法措辞/顺序变化可接受，错误来源/数值/版本/授权拒绝；不宣称自然可靠性 |
| 新授权完整自然批次 | 新源与模型在本批输入下的实际交付 | 新身份、完整矩阵、有限预算、原账本；不挑选重跑或拼历史通过 |

重点断言：唯一当前任务的“继续”保留未完成交付、复用正确来源但不增加业务范围；有多个可能对象才问。明确唯一新版映射、精确命名、失败加载保旧、相关确认重判与无关文件不误伤；风格按当前偏好变化，全篇边界及局部解释合规。

同题不同自然答案不做逐字相等断言；事实值以fixture定义的精度/单位和独立数学oracle核对，覆盖以原需求结果或具体缺口核对，方法路径不同仍要满足原要求及适用边界。图按真实产物及数值来源核对；开放语义用原需求和已定位审核结果/人工内容核查，不新增词表猜测。模型输出JSON解析及schema/引用校验是协议验证，不得变成从随机散文恢复事实的正则补丁。

保留不可变原答案字节/SHA、跨SSE/持久化/导出同对象身份断言；导出正文只按预先定义行尾归一化比较文本，下载字节SHA另验。新旧模型措辞可以不同，不表示同一已接受对象可以被悄悄改写。


### 18.1 批后固定协议的新增相邻验收

当前源需完整复验：对象关系唯一直接绑定、不唯一经原对象选项后再公式确认；新旧值86/96由原实际工具及确认operand产生；AgentManager重启不能丢票据身份或恢复旧计划；所有材料映射逐项确认后才计算；数据加载不重复分类或登记第二份需求。上传持久化故障检查命名、元数据、血缘、日志及原票据字节完全恢复。多对象候选歧义保留原问题与具体缺口，不生成公式授权。

发布快照顺序用同步与流式正常入口实际下发的摘要核对，不能测试客户端临时重算掩盖宿主变更。审核六字段只读事实视图逐值核对，完整proof仍从宿主原快照验证；原自然语句、未知单位、外推和行动reject控制保留。

HTTP复验使用原47组/90回合及独立oracle，全新source/test摘要和冻结身份；首轮继承旧head/source摘要的控制已停止为invalid，不计入签收。离线失败、定向通过、完整app、自然Provider与视觉分别记录；详见[修复收据](../../audit/2026-10-08-p5-repair-implementation.md)。


### 18.2 当前 changed source 的本地签收（2026-10-09）

同一401 source/test冻结，完整离线r6为3427 passed/2 skipped/17 warnings；Provider禁用HTTP r5完整47组/90回合、检查0失败，369源集合与摘要未变，Provider initiated0、forbidden transport0，服务已停止。对象/公式/版本/局部审核的新协议与全部相邻正常app场景通过；表格/公式/图原内容、数值与覆盖oracle保留。新知识数据示例目标的版本登记和新增目标授权分别验证；多来源部分加载需登记全部初始版本，既有版本改变拒绝。

当前本地签收仅属E2及HTTP非视觉正常app。两skip为未授权live smoke及Windows不允许symlink创建；picker、visual、refresh、console、natural generation/review仍unassessed。原P5失败、r1/r2/r5离线失败、r4离线中断及HTTP r1无效/r2失败均保留，不拼接。参见[修复收据](../../audit/2026-10-08-p5-repair-implementation.md)和`tmp/p5-repair-source-20261008-r6/final-receipt.json`；不据此变更原180行或真实50条hard oracle状态。


## 2026-10-09 用户确认的需求—执行—发布职责调整

验收对照[已确认PRD](../../product/trusted-answer-publication-requirements.md)，原VP/IC/CP与自然oracle不降低。真实M02结构材料经实际工具/TaskManager进入synthesis，数据存在不能生成缺失gap，模型list/get保持受限；缺失/过期/跨会话仍拒绝。M03核等价表述、不同业务目标误共用、六来源六图；M06核多个已有对象的唯一换版、真实歧义、同版复用和限定血缘公式。咨询、表达、必要事实和审计可用性分别核。零调用重放明确原材料与新host身份，不修改原model draft的snapshot_digest冒充自然成功。切片后再完整离线与原app矩阵，新真实批次另冻结授权。

### 合同回放的独立验收口径

1. 原快照/原草案的请求体积诊断必须保持原摘要不变，只签收字节预算和运输投影；离线审核桩不证明自然语义质量。新目标登记的实际工具回放另记身份，不能改原model draft摘要后当自然通过。
2. M03逐来源核两期值、变化、记录数和六图，全部交付完成后才关闭目标；原回执明细仍完整可查，未请求内部claim不强制进正文。M04各竞争假设必须有当前可核状态或带其真实ID的具体缺口。
3. 损坏/过期/算术不一致的已尝试回执标证据不足，未执行目标标未计算；局部失效不删除另一来源的正确事实。工作台只显示已请求且当前可核的结论。
4. 完整离线门和原47场景/90回合Provider禁用正常app矩阵分别签收，失败身份保留。控制目录触发Windows路径限制属于验证环境问题，不能称产品上传缺陷。新的自然生成、语义审计、视觉和正式默认仍分别验收。


## 19. 系统审查后的跨接口联合验收（2026-10-09，已批准）

扩充既有合同/实际工具/正常app测试，不新增框架或付费judge。原VP/IC/CP及M01—M06硬oracle保留；下表为同一需求的跨边界缺失覆盖，不能用新条目替换旧功能。反例基线 `tmp/system-review-20261009-r1`；审查Provider0。

| 门 | 正确行为与相近反例 | 证据与限制 |
| --- | --- | --- |
| CONTRACT | 公开schema和validator结构约束同源：kind/quantity/parameters/条件必填/集合上限/操作分支；r3六计划原材料重现后有精确字段错误及有限恢复；动态revision/来源仍严格拒绝 | 真实注册schema与实际validator，不检查提示包含某单词；schema接受不代表动态当前性通过 |
| INTENT | 坏scope/条目保留原目标和明确未决原因，独立合法目标继续；R-intent中的7日不能静默丢成无约束执行；多目标reuse原自然响应保留全项 | actual classifier→register_request，固定响应Provider0；不测试自由散文关键词 |
| PHASE | 无文件咨询不跑数据；有限探索可达且受范围限制；正式计算无前置交付则拒绝；声明后实际派发绑定正确；探索回执不能被倒填签收 | 正常AgentLoop三入口，测试不能补写丢失的execution_binding；简单订单任务成功交付 |
| EVOLVE | 原目标/范围不变，保留mean交付再追加table合法；旧ID/未完成项保留；删除/改窗口/错版本/超限/事务失败不破坏原目标 | R-replan与实际record_analysis_plan/TaskManager往返；追加后的新结果必须新派发 |
| PRODUCT | 实际distribution amount均值15.5成为amount/mean交付；实际forecast三期结果与业务跨度3闭合，跨度冲突只拒相关项；错误类型/量纲/源/方法拒绝 | R-distribution/R-forecast；独立真值，不用catalogue/renderer生成expected，不以宽泛table/value代替业务量 |
| DAG | 同一业务步骤有事实与解释时，事实依赖满足可推进下一计算；解释缺失仍使最终答案partial；中间解释不伪装事实completed | R-open-dag；多来源/循环/失败/相关换版正反例；明确最后解释节点与中间计算依赖的不同 |
| CAPABILITY | 77工具逐项记录合法效果、阶段、业务产物/限制、现有测试/收据；统计/预测/假设等逐族真实结果到用户交付；非事实工具不造claim | 基线tool-capabilities.json；工具名/函数数/文件存在不证明行为，未测家族标unassessed且不签整体完成 |
| GAP | 分别呈现未执行、方法证据不足、内部合同/执行失败、必要业务确认；有原预测序列而映射不匹配不得说缺数据/无序列 | 原CP AC18、IC Q08，真实失败原因到公开答案/工作台/导出一致；局部独立事实保留 |
| JOURNEY | 核心六链完整：M01咨询/12与120/窗口/未来AND；M02观测拟合与D30边界；M03六源六图；M04竞争假设/换版；M05六轮风格；M06缺数据/86/复用/96 | 固定脚本仅证明编排；原自然输入/oracle保持，旧部分批次不拼接为完整通过 |
| RELIABILITY | 同业务不同合法措辞/顺序/交付组合仍满足原值、范围、目标及局部保留；开放语义可能不同，按原专业价值量表评价 | 本地固定变体进入现有框架；自然变体/有限重复规模另行冻结讨论授权，不新增运行时语义猜测器 |

### 19.1 证据不能互代

单元测试允许隔离/人工绑定，但收据必须标注；跨接口应用门必须通过真实声明/派发/回执链，不允许测试执行后补ID。原自然材料与当前接口不兼容时保留原失败，另记新协议固定输入，不能改原draft/snapshot摘要冒充自然重放。

当前源改动完成后再做同源full-offline、原47组90回合Provider禁用app矩阵；需要验证的视觉由原Browser路线单独记证据。控制成功、单终态、正文身份一致不等于业务完整；诚实缺口保留率和已可计算目标成功交付率分别核对。完整离线通过数只说明原断言，不是产品质量分。

### 19.2 进入自然验收的前置门

S1—S3完成且无已知静态结构/顺序/产物映射/依赖断点，全部保留能力的承接表有明确结论。先完成新候选零调用预检，再提出精确输入、模型、端点、预算、控制路径和账本授权；不得继承旧批剩余调用。原硬oracle不以模型措辞变化而改变，自然解释采用原内容要求和定位材料人工核查。

新自然批若再暴露这些本应本地可验证的断点，回到共同合同和全部调用者复审，不在批中修复或续跑。一般模型质量波动、Provider故障、确定性产品缺陷分别报告；历史和当前unassessed不折为通过。
