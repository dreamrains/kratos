# 可信交付统一验收契约

版本：3.29；更新：2026-10-19。原标准与180编号追溯保持；实际阶段及接续以[唯一总计划§8/§9](../plans/2026-09-22-analysis-agent-trust-reset-plan.md#9-s4本地最终验收与自然准备)为准。

S3按127四包签收，128包含7930/0/2。S4当前426摘要dc78093b1264a060d9ddb51726f3fd9f914b08c513670fc63b3366980ad41ded；完整full3 7953通过/0失败/2skip、同源、7955原活跃节点无删减，m09新冻结HTTP47/90零失败、六链52/52、生命周期13/13。S4本地有限验收已于2026-10-19完成收口，详见[当前收据](../../audit/2026-10-18-s4-local-acceptance.md)。主LLMClient具名连接、fresh manager/loop冷恢复为当前E2；m07/m08实际1440/747、方法正文/表公式图/精确HTML按所有生产字节相同具名复用，m09自身HTTP-only的视觉不改称通过。新MD：2026-10-19用户具名确认已实际打开精确新b3a23f文件，表格120/12、公式120/12=10及图表显示符合（tmp/s4manual01/md-actual-open-user.json）；当前原件SHA再次一致，AC37该本地实际打开条件已核。此前工具内容/原图复核及queued限制仍保留，旧c802确认未被继承。

原full2 7879/74失败/2skip和全部失败轨迹保留；只修旧呈现观察器及纯helper登记，不重开105、不删测试或新skip。两个skip是禁用自然live smoke与Windows symlink权限，均不计通过。原180仍118完整/62局部/0待审，不是完成率；24补充原行保持，当前有限证据不升级原状态。F5缺原件、自然内容/方法质量、环境和性能问题保留，A/B/C未批准未实施。p04当前不可执行零调用候选包按用户选择保留自然launcher clean-source/配置/预算阻断；Provider/远端MCP0，不进入S5、不继承授权。以下§1—6标准与原180表保持原字节。

2026-10-19主线接续：用户授权C完整候选接管D/main，C原HEAD/索引/228项状态保持；main代码和资源身份一致，新的完整离线回归待完成。详见[主线接管收据](../../audit/2026-10-19-main-takeover.md)。D六项旧材料已按清理前SHA全部恢复；用户永久清理D历史tmp的不可完整恢复缺口已明确保留并获继续确认。S4旧签收仍属C，不代签新main执行；Provider/MCP0、不推送、S5未进入。

## 1. 身份、分母和证据

每个运行冻结case_id、源码/dirty摘要、环境/默认配置、输入文件SHA、原提示/顺序/恢复选项、控制路线、独立oracle、run_dir、session_id及适用Provider ledger。批次后修改必须新身份，不拼接局部通过。

验收分母来自原始用户要求及独立业务标注，不能从模型生成的计划、必要交付或最终coverage反向生成。每项标注：所需结果/方法、值和容差、对象/版本/粒度/单位/分母/窗口、可见位置、允许缺口原因及反例。整数精确；浮点按具体方法预先冻结容差。

同时报告两个指标：**响应覆盖**（结果或准确缺口）和**可计算项完成**（真实正确结果）。两者均须100%；数据及方法足够时，not_computed/failed/泛化缺口不算完成。预设缺口只在其对应条件成立时通过。全部必需维度逐项passed/failed/unassessed，不用平均分抵消硬失败。

| 证据标识 | 可证明 | 不能证明 |
| --- | --- | --- |
| E0 | 静态代码、差异和材料完整性 | 运行成功、全部语义正确 |
| E1 | 定向纯函数/结构/负例 | 正常完整用户链 |
| E2 | 当前完整离线和真实工具集成，Provider禁用 | 自然模型构造/解释质量 |
| E3-HTTP | 正常app上传/AgentLoop/工具/SSE/保存/导出，脚本模型 | picker、视觉、浏览器刷新或自然语义 |
| E3-VISUAL | 同一健康服务的真实页面、图/确认/刷新/导出检查 | 真实Provider语义 |
| E4 | 精确授权真实Provider，经正常app | 未运行场景、未测视觉、其他模型或生产部署 |

同一接受对象的字节/SHA严格不变；导出文本只按预先冻结的行尾归一化比较，下载文件原字节SHA另核。同题不同自然回答不要求逐字相等。

原文档E2/L2/E3/L3命名不一，迁移时按实际控制路线和观测内容转换，不能靠字母升级证据。HTTP可与浏览器检查组合，同一session留控制记录；picker未操作仍unassessed。

## 2. 咨询与多目标最低集

| Case | 输入 | 必须行为及负例 |
| --- | --- | --- |
| CONS-01 | 无文件：解释p值 | 概念、条件、示例；不要求上传，不声称分析用户数据 |
| CONS-02 | 无文件：电商留存分析方案 | 所需字段/粒度/窗口、步骤、方法和限制；不制造已检验结果 |
| CONS-03 | 有文件：只解释回归与相关，不执行 | 知识路由，执行工具调用为0 |
| CONS-04 | 有接受答案：改写给业务同事 | 精确原答案引用、事实不变、表达变化；不重算 |
| CONS-05 | 找不到原结果：解释刚才收入下降 | 具名定位缺口，可答一般知识；不得把通用解释计原结果完成 |
| INTENT-01 | 你好，请算总收入 | 问候不吞实际计算 |
| INTENT-02 | 不分析留存，只导出表 | 否定保持，实际导出，无擅自分析 |
| INTENT-03 | 先解释同比，再计算当前同比 | 两项均交付，知识与事实权威分明 |
| INTENT-04 | 九指标换序或同工具不同业务目标 | 全部义务独立，不强制选一项、不误去重 |
| INTENT-05 | 继续、同义reuse、换窗口、撤回后压缩 | 唯一任务继续；变更原子，旧义务不复活 |

覆盖中文/英文等价、否定、混合任务、非法局部结构及无有效提议。固定模型响应只证明解析和编排；这些场景不自动增加到历史真实调用授权。

## 3. 六条核心用户链的固定身份

原业务矩阵由现有scripts/testing/p08_real_matrix_contract.json及当前可核13CSV/20原提示/3恢复选项冻结。每轮具体文件、数值、方法和顺序从原合同带入oracle；下表是必需维度，不能替代完整原输入。

| Case | 必需交付 | 危险相邻行为 |
| --- | --- | --- |
| M01-CURRENT-ACTION | 当前12行/120/含首尾12天；全部原窗口事实组；未来AND条件行动 | 任一AND条件丢失，未来当本期，单位未知补币种，审核吞独立事实 |
| M02-CURVE | 实际观测、拟合候选/公式/参数/误差/范围、D30证据边界 | 未知比例变百分比；无holdout/backtest称已验证外推；聚合拟合强要个人数据 |
| M03-SIX-SOURCE | 六源10→11至60→66及变化/记录数、六真实trace、继续/压缩/导出 | 跨源无授权合计；漏第一/六项；错图；把文件存在当可访问交付 |
| M04-VERSIONED-HYPOTHESIS | 至少两竞争假设；v1/v2原测量、关系状态/依据/限制可见 | 旧版/错指标/同文本当支持；描述方向变因果；仅内部state正确 |
| M05-STYLE | 原六轮要求真实改变组织、深度、受众 | 六个同一摘要；改写数值/单位/版本；旧风格拒新风格 |
| M06-MISSING | 缺文件时具体缺口和一个明确数据动作 | 假计算、反复通用方法许可 |
| M06-CONFIRMED-PARTIAL | 原冻结成本选项只恢复一次；12/120/12天保留，未算净收益与增量证据不足分开；后续原版本链86/96逐项核实际公式与operand | skip/旧版/重复resume放行；缺成本归零 |
| M05-AGG-EDGE | 原分组A/B/C/D为1/2/3/999；D完整 | 此聚合边界不能冒充M05-STYLE通过 |

M02各历史fixture单位独立：原VP的D7=.10且比例已知为10%；71e23d0的.1单位未知仍未知。禁止跨批拼数值、单位或通过结论。

## 4. 必须穿过真实接口的新增硬门

每行需要当前反例RED、修复正例、危险相邻负例和相邻能力回归。可复用现有测试，不能只断言函数名/提示字符串/非空对象。

| Gate | 正例与通过判据 | 拒绝/失败判据与证明入口 |
| --- | --- | --- |
| CONTRACT | 每种合法交付的公开schema与结构validator一致；现有ID复用/边界值合法 | 未知字段/非法类型/超限在同一结构边界拒绝；原六次自然plan失败材料逐一解释；动态身份另核 |
| INTENT | 多目标及有效scope完整保留，等价reuse不合并不同目的 | window非法不得静默消失后全量算；原目标有定位错误；replace/withdraw不得半应用 |
| PHASE | 合法探索→正式计划→派发前绑定→真实回执→综合可达 | 无计划正式完成、事后补绑定、synthesis读原表、额外读取拒绝；同工具不同用途分别测试 |
| EVOLVE | 同目标/来源/范围追加table，原mean交付及ID/证据保留 | 缩小、换窗、旧revision、越界/超限拒绝；保存失败回滚；探索旧回执不自动覆盖新交付 |
| PRODUCT | 实际distribution_analysis对amount=1…30，mean=15.5；真实forecast三期31/32/33与跨度3绑定并可见 | 返回表不代替所问测量；parameters.periods不因字段映射丢失；错源/参数/值不能匹配 |
| DISTRIBUTION | 常数/两条/单条/全缺失/非有限/普通数值、Shapiro上界与显式选列；独立算值及正常应用保存刷新导出 | 退化伪正态、NaN/Infinity、列消失、错列静默、有限排除后签全部范围完成拒绝；可算均值不因无正态性而消失 |
| CORRELATION | 三方法及显式/自动列选择；独立公式核完整矩阵、弱/零相关、成对缺失样本、常数/单点null；正式计划→真实上传/派发→原回执→保存/刷新/导出 | 错方法/指标、矩阵缺格/越值、未知方法回退拒绝；元数据不签矩阵；Kendall常数对角线不得冒充1 |
| DID | 四格完整独立均值/方差oracle；完整、单条、缺格三种正常应用链；点估计与区间分别交付/缺口；原假设边界公开 | 缺格补零、单条零宽区间/显著性、非0/1截断、无限值、错列/效应/方差/p值/假设篡改拒绝；不把基线水平差当趋势 |
| OPERATION | 实际派生/清洗/类型/字段、文件写改、扩展效果；正式计划→真实对象→原回执→effect→SSE保存/刷新/导出 | 错参数/父版本/对象字节/权限/会话、无执行前绑定、提交前对象变更拒绝；不强造数据claim；ID重用不得误拒 |
| ALLOCATION | 独立逐维边界/目标算术；完整有效候选、未找到、负/零基数 | 重新分配后越界仍称可行、最优/最小二乘/数学不可行声明、坏候选空表签完成拒绝 |
| SKILLS | 两个真实AgentLoop和两条正常app会话的加载、卸载、列表、指令隔离；全局网页禁用/删除传播 | B未加载却注入A指令、B卸载影响A、全局禁用后仍注入、启用自动复活旧加载拒绝 |
| SENSITIVITY | 独立乘法与反向等比例oracle，完整11组、数值维度唯一身份、零总量未知，正常应用正式场景 | 分组截断、维度静默不匹配、零总量凭空分配、错参数借用场景、情景升级因果或已验证预测拒绝 |
| MODEL-SCENARIO | 当前回归模型、精确feature_changes、原逐行预测及独立均值/变化oracle，正式正常app | 旧模型/错参数/不完整预测/错均值、自动训练或因果/未来验证升级拒绝 |
| CLEANING | 六缺失策略、三IQR模式、去重/填补/删行分别计数、实际新表及六条正常应用链 | 未填文本也计filled、全空/原类型不兼容被换策略、未解决缺失签全部完成或旧答案复用消除缺口拒绝 |
| CONVERSION | 七公开类型与auto原筛选、category实际类型、原缺失/转换失败/新增缺失独立oracle和正常app | 原表未转却报成功、坏文本未转误计成功、新增缺失混同原缺失、部分效果被签全完成拒绝 |
| TRANSFORM | 八操作/pivot双分支、公开结构参数优先、显式默认值、全部merge父源及10条正常app链 | 旧JSON隐藏来源越域、只记首父源、错参数或父源从事实/效果另一通道放行、写能力误并行拒绝；count/size跨入口实际值一致、无列count拒绝；空桶/全缺失sum未知而真实零为零，日期排除范围与实际来源核对，事实/效果同为部分完成 |
| DAG | 第一节点事实＋解释，事实已核后可执行依赖第二计算；最终解释仍待核 | 无事实/错版本/伪completed/纯开放节点不能充成功事实依赖；独立步骤不被误阻断 |
| SOURCE | 当前输入、实际读、父版本/根源及原表→合法派生一致 | 同值异源、额外源、执行中换版、模型手写CSV假血缘拒绝 |
| GAP | 未执行/内部合同失败/缺数据/证据不足准确区分，已知可算项成功 | 有三期结果却称无序列、内部bug要求用户补数据直接失败 |
| CAPABILITY | 每注册入口及全部声明模式从schema/registry到实际效果、语义结果和可见交付闭合 | 仅tool存在、宽泛table/value、参数名含义替换、通用字符串错误恢复不算通过 |
| OPEN | 正确解释、未来AND行动、全篇共享限制与必要局部限定保留 | 无据因果/外推、条件丢失、审核无定位/错版本/超预算均不升级；仅相关开放义务未完成 |
| LIFECYCLE | 同步/流式/只读并行、确认恢复、压缩/重启/分支/导出读同一身份 | 重复terminal、先公开后保存、拒绝草案入历史、跨会话、过期确认被复活拒绝 |
| RELIABILITY | 合法字段顺序/措辞/步骤顺序/追加路径变化仍满足同业务oracle | 固定理想回包、事后注入目标、每轮新增词表都不能签收；自然门另见§6 |

PRODUCT的三期序列是既有本地确定性fixture的独立预期，不强迫真实M02等场景使用同一种预测方法。算法/验证范围仍核实际工具合同。结构schema生成和测试预期不能共同来自同一个缺陷匹配器。

## 5. 原需求机制替代与能力验收

| 原条款/ID | 当前处理 | 保留行为 |
| --- | --- | --- |
| VP-N10/N11，CP-AC29 | 单次局部审核；拒片段/具体缺口；已有一次格式恢复不新增语义复核 | 独立事实保留、不盲删、不无限重写 |
| IC-L01—04/L06、IC-B05旧恢复部分 | 旧协议只读，不执行迁移；新协议恢复另外验收 | 历史原文/事件保留、未知版不覆盖、无批准不运行 |
| IC-L05 | 原要求直接保留 | 不改写历史结果和event log |
| CP-AC21 | 当前结构草案/claim取代旧隐藏绑定块 | 伪协议不授信、坏引用不自报覆盖、内部协议不入用户正文 |
| CP-AC29/38 | 已批准一次数据相关开放审核计入既有预算/账本；纯咨询按适用范围豁免 | 无隐式调用/第二审核/无界扫描 |
| CP-AC36 | 旧正文只读；新协议round-trip与引用恢复 | 同答案身份、旧事实不越级、>20历史引用可恢复 |
| CP-AC33、旧表达规范图wrapper | 接受对象结构artifact引用由宿主渲染；旧wrapper不作LLM事实通道 | 正确图就近可见，错误/异会话/未知hash拒绝，邻近正确内容保留 |
| CP-AC40 | 同候选连续两次完整冻结自然批次均通过 | 每批独立授权、原矩阵、硬门及内容评分；部分批不算 |
| VP历史1—5软评分建议 | 统一采用§6的CP量表；解释/行动/假设/受众价值落实为具体内容要素 | 不挑最有利的评分表，不以排版分抵消事实错误 |

批准111（2026-10-17）：宿主已判非阻塞、同轮同语义的重复通用方法许可，沿当前原需求/正式计划/版本计入现有重复无效调用额度；耗尽走原共享终局保留真实独立结果和未决缺口，同批未执行工具补齐响应。真实业务确认、原决定复用及合法记录工具保持原规则，不增加预算、模型调用、散文解析或账本。批准原记录见[批准111](../../../tmp/b409/approved111.json)。

批准112（2026-10-17）：同一run_python原回执output保存完整stdout，取消原件的20000字符截断；模型上下文仍沿原摘要和完整请求预算。stdout只作原输出，不升级为测量事实，事实继续要求结构化result_data；不新增存储链、解析、模型调用或账本，历史原件不回写。原批准见[批准112](../../../tmp/b417/approved112.json)。

forecast方法裁决（2026-10-10用户确认）：只公开真实auto/backtest回测能力，退役simple/prophet误导别名；负例须明确拒绝，不静默改跑另一方法。不新增Prophet算法。

曲线零值口径（2026-10-10用户确认）：长表与宽表均先逐条按zero_values筛选，再对同一x或序列列求均值；exclude排除零，keep保留零。有效记录数及排除零值数必须来自实际观测。零值业务含义仍unknown，排除不证明未观测或未到期；此口径不授予预测或因果验证。验收覆盖长/宽×exclude/keep、同一x多条记录、全零x、原回执与可见序列一致，以及错口径/回执口径冲突拒绝。

A/B（2026-10-10用户确认）：恰好两组，单位先sum/mean聚合，有跨组同单位固定配对，配对不足不回退独立检验；配对设计拒绝显式Mann–Whitney/chi2，不换方法。退化t保留均值/差值，统计量/p值/区间未知；auto明确正态性未评估时的秩检验依据。

ML/SHAP（2026-10-10用户确认）：保留原随机按行留出、现有分类/回归算法与可选CV；公开实际算法、原留出预测与验证限制。分类统一编码，公开原标签、每类/宏平均指标和默认正类统计约定。TreeExplainer逐类绝对均值，完整分类总体各类等权平均；回归按样本平均。单分类输出保留实际类别，完整平均未知。模型属于当前会话、当前数据版；model_kind=auto/regression/classification，auto只用唯一匹配，两种都有效时明确要求选择，不静默挑一个。以上均不授予未来/外部验证或因果强度。

A/B独立oracle从实际单位样本算均值/样本方差、t分布、秩组合与列联计数；ML从原holdout预测算混淆/误差，不能用被测catalogue生成expected。SHAP另用可计算的逐类解释数组验证等权平均，真实TreeExplainer核形状/类别与应用链；错模型/版本/聚合不得关闭交付。测试fixture不能给模型注入状态或事实。

TOOLS逐族分母见[77入口及模式清单](../../audit/2026-10-10-capability-coverage.md)。每项记录来源合同、公开参数、全部声明模式、效果/业务量、方法前提、独立oracle、测试入口与实际状态。非事实工具验证其效果/权限，动态外部服务模拟只算接口合同；真实环境未经验证单列，不能当已实测。

独立知识创建指定判据（已批准）：用户已批准沿既有操作效果合同；派发前核当前会话、匹配声明/完整参数、配置的知识根/library/数据库及已有ID，未声明/错参数不得落盘。效果和提交核真实新ID、版本、元数据及正文SHA，展示创建效果，不授予数据事实强度。独立创建、上下文及其余知识/记忆模式分别验收，不得互相代签。历史批次见本节历史引用。

知识持久化/上下文指定判据：创建/更新/删除在可捕获文件、SQL语句、提交及回读异常时保持正文与索引一致；停用/恢复回读不先发布状态，真实空正文与源文件缺失区分，UTF8/混合换行精确重载。完整上下文链须贯通管理API、实际上传、正式计划、知识检索上下文与数据交付；不得以持久化或上下文证据代签全部知识/记忆模式。历史批次见本节历史引用。

规则持久化/操作效果指定判据（已批准）：公共registry更新在可捕获写入异常时保旧文件和缓存，落盘成功后才发布提示内容；全局+当前会话读取及正常注入一致。用户已批准update_project_rules沿既有操作效果合同，执行前绑定当前会话、配置的全局路径、完整新内容和旧/新SHA，未声明/错内容不得写入；效果读取和提交核真实文件/原回执/缓存提示内容。权限拒绝须为失败持久终局和真实未计算缺口/失败通知，不能作为成功操作；其他知识/记忆模式仍按各自合同验收。历史批次见本节历史引用。

任务权限指定验收（2026-10-12）：公开task_create/get/update/list沿现有会话/项目范围核真实任务和依赖身份；批量越界拒绝发生在任何归属或活动计划写入之前，不泄露外任务正文。单个/批量正常应用链只以真实数据回执关闭分析目标；普通待办completed不能替代数据事实或投影任务的已核交付。原管理API的管理职责保留，全部模式及独立任务请求仍须逐项验收。历史证据见本节历史引用。

文件范围指定判据（已批准）：短长read_file共用file_page.v1，独立UTF-8/CRLF/Unicode原字节SHA及完整逐页重组oracle；offset非负、max_chars为1—2000、limit为空或正整数且每页先到为准，坏类型/越EOF/来源SHA改变/坏UTF-8拒绝。独立文件原文及list_files目录只沿既有table和原回执，以file_scope=current_readable、file_output=content/entries精确匹配路径/页范围或glob；空文件/空枚举可交付，有不可访问或瞬时条目则部分完成。派发前宿主绑定当前会话、原路径权限、规范路径、原SHA和捕获枚举时点，原结果读取及commit重核；源变更、篡改原文/目录/范围/权限、无执行前绑定拒绝。自己的回执持久化和枚举后新增对象不得递归扩张原目录快照。普通数据测量不能借文件范围逃逸，文件内文字结论不因此受核。正常AgentLoop正式计划、真实工具、唯一SSE终局、保存/API刷新及MD导出和独立原值oracle均须贯通。

已有测试的隔离fixture可保留用途标识；完整应用出口必须从上传、真实原消息、record_analysis_plan、registry、派发前绑定走到回执、发布、SSE、保存及导出。不得事后注入绑定、直接改任务完成或mock掉受测验证器。替代私有实现测试按引用清单退役，原180行为保留。

### 既有工具边界与历史材料（裁决46—71）

预测裁决46/47（2026-10-11）：原auto/backtest有序留出与末值/线性选择、同时间求和保留；完整时间戳和真实有限筛样/重复汇总范围必须沿原回执交付，有排除则原范围部分完成，筛后重核点数/等间隔。1.96×留出残差样本标准差仅为未校准残差启发带，不表示95%预测覆盖；少于两条残差或不可算时上下界null，可算零宽带也不证明未来不确定性。实现错误修正并验证；要求校准覆盖率的目标仍未完成，不能以说明代替满足目标。按原入口/封闭产物/宿主实值/正常AgentLoop、SSE保存刷新导出正反例签指定范围；不是S3整体签收。

时段比较裁决48（2026-10-11用户确认）：可加数值仍按原sum，显式错列/非数值/重复指标或维度拒绝；只计算有限观测，各期/各组记录有效/排除数，原范围不完整标部分完成；无有效观测合计null而真实观测零仍0。保留原日历窗口/日均算术及ratio_of_sums的严格原操作数要求、非可加列必须给公式，不新增检验或归因。原回执/封闭产物/宿主实值核对及正常AgentLoop—SSE—保存刷新导出签指定范围。

2026-10-11裁决49：数据画像/就绪度仅作真实列级诊断；空表明确无可分析记录，通用缺失率、重复或样本量阈值不整体阻断目标。方法可行性由实际所选方法/列的真实前提决定；基础检查不授予方法验证。缓存必须绑定实际数据版本。

2026-10-11裁决50：用户同意模型视图按当轮正式必要交付及解释所需上下文投影；所有已请求来源、指标、图和必要限制必须保留，未请求且重复的完整审计详情保留在原宿主快照、回执及可恢复详情中。发布及完成状态仍由同一宿主合同裁决。用户随后批准实施完整请求token预算：65536 tokens软目标，必要交付可扩展到实际剩余上下文；按当前模型/端点输入、上下文及输出上限预留输出与10%余量，系统提示/历史/工具定义/响应格式全部核算。优先本地tokenizer，无匹配时明确标注UTF-8保守估算；MAX_TOKENS为空时保留Provider管理语义并预留已知最大输出。实际输入/输出/缓存用量和按显式价格估算的费用写原日志，未知不补零。超硬容量在传输前拒绝，不增加重试、审核或调用额度，不授权真实Provider调用。

后续历史切片中的批准行为继续生效，具体完整适用条件见[唯一计划裁决51—71](../plans/2026-09-22-analysis-agent-trust-reset-plan.md)。以下只整理标准，不把旧批次结果升级为当前通过。

| 工具责任 | 保留验收边界 |
| --- | --- |
| 记忆持久化/提取/提升 | 单资源状态回读与SQL事务一致；同库原子提升、单次提取整批原子提交，失败不留部分候选或旧候选来源刷新。create/confirm沿原操作效果核真实ID、规范行摘要/状态、执行前原权限与旧行；候选置信调整、已确认幂等和不支持状态拒绝沿原合同。 |
| 检索/工具发现 | limit仅精确整数且排除bool；非正整数空结果、不读取条目，保留原评分/过滤/预算。工具发现返回全部原排序匹配并公开数量，200字符摘要截断逐项标注，不增加检索算法。 |
| Skills/MCP目录及配置 | 元数据table不借数据事实身份；核当前会话/配置根、原文件SHA、真实loaded/连接/进程快照。配置新增/替换/开关/删除沿唯一原子转换/回读及执行前权限合同；MCP isError不能因非空文本误判成功。离线模拟不是实际远端MCP验收或授权。 |
| 会话导出（60/61） | 原已持久化历史前缀/版本/SHA和原AcceptedAnswer/图表冻结，后续追加不自动进入旧导出；原范围改写/删除、原答案或图源变化拒绝。核真实注册文件、内容与原回执；当前报告另按106先保存后精确导出，不混同默认历史范围。 |
| 规划/证据/回答目标登记 | 原持久化、产物/目录及状态回读保持一致，异常回滚原字节和内存；同ID更新/重用沿原合同，不留幽灵记录或错授host_verified。摘要不得以真假值漏掉真实sample_size=0。 |
| 用户提问 | 显式questions仅1—4题，完整验证后才写入/挂起；坏JSON/非法数组/空数组/第5题不截断或退回单题。多题归属及复用按91—93/101。 |
| 多文件综合（63/64） | 原自然日聚合/外对齐、各来源真实有效和排除范围、观测零与未观测null分别保留；混合时区/重复来源或指标拒绝。无save_as也交付完整aligned_data；save_as核真实派生表/父版本及原权限，不合并跨源业务口径。 |
| 沙盒（66/67） | timeout仅1—30精确整数秒（排除bool），默认30，非法值启动前拒绝，不强转/剪裁。合法技术恢复沿原预算/回执；失败不生成成功结果，原受限模块/读取版本/worker隔离/终止/重放合同继续。 |
| 图表来源（68/69） | 指定data只读唯一当前可见来源，缺失/不可读不回退；data_json与data/result_ref冲突写图前拒绝，纯JSON仅探索、不关闭注册数据图目标。result_ref沿原会话/文件/回执/当前版本核唯一来源，data只作同源断言。 |
| 图表聚合与系列（70/71及既有修复） | count按原指定列非缺失数、不强制数值或去重；sum全缺失为未知，真实零为零，未知pie在保存前拒绝。有效数及来源审计真实呈现。多指标bar按指标×颜色组生成trace，normalize按原组max(abs)=100并保留raw，raw不伪报归一化；原图种/保存/权限链继续。 |

历史实施叙述及所有批次路径保留在[编辑前完整原字节](../../../tmp/b365/2026-09-30-trusted-answer-pipeline-acceptance.md.before)；其中的旧审核数字仅描述历史候选，不作为当前状态。当前审核只见本文开头、唯一计划§8及逐条收据。

### 已批准后续边界（裁决90—110）

以下承接唯一计划的已批准选择；不新增验收分母、模型调用、账本或平行链。批准的具体适用条件和历史反例仍以唯一计划对应裁决为准。

| 原责任 | 当前判据 |
| --- | --- |
| 分布/窗口/假设呈现（90、99、108） | 原Renderer呈现真实分布业务表格、结构化日期窗口、当前宿主核定的原假设内容/中文证据状态及缺口；仅新答案采用新呈现，历史AcceptedAnswer/消息/事件原字节只读，同一正文保存/刷新/导出。假设内容不升级事实。 |
| 确认归属与复用（91—93、101） | 单张多题卡一次提交，只问真正未决题，逐题保存回答归属；普通业务回答仅在宿主精确绑定当前需求、对象/字段、版本和原权限时复用。新请求使未绑定旧待决卡过期并保留原记录；显式原决定/子题ID引用仍核原问题/选项身份，不由新措辞赋予新含义。 |
| 问题与真实生产者（94、96、105） | 宿主只能在当前正式交付证明全表行数/原生敏感性无窗口依赖时将窗口题降为非阻塞，混合时段或无法核定仍确认。紧凑引用的字段依赖须从当前原件/版本/原权限精确核定；缺证据的依赖交付保留未评估/证据不足，不以模型标签放行。 |
| 历史v2碰撞与工作台（95、98） | 原AcceptedAnswer终点分组只读呈现重复reply_id，失败说明用既有兼容算法生成稳定呈现ID，保存/刷新不迁移原记录。窄屏顶部入口打开同一工作台侧边抽屉；桌面布局与原接受片段保持同一数据链。 |
| 有限收敛与分层测试（97、100） | 内核完整枚举，正常AgentLoop按共同边界保留代表；保留独有算法/产物/权限/序列化及全部函数断言，不按文件大小删除。责任包先跨接口反例再正常链，整库在相关改动整体收敛/出口运行；退役审核及清理授权各有原证据，不自动扩大。 |
| 原F2成熟度/零值/权重/敏感性（102、104） | 同一curve_fitting显式weight_col/mature_through_col先筛成熟，再逐记录按批准零值口径处理，再普通/人数加权聚合；逐点有效数、权重和排除数真实保留。可选compare_weights复用同批观测，交付两均值、逐点绝对差及全点最大差/日龄，并与同一正式交付绑定；不从零值推成熟度，不新增拟合族、不外推。 |
| 声明单位（103） | 同一正式计划value_scale作为呈现声明，绑定当前需求/对象字段/版本/原权限；可将.10呈现10%，原值与“源单位未独立核定”同时保留。未声明未知，与有效原确认冲突拒绝，不把声明升级为源单位已验证。 |
| 当前复合导出（106） | 先可靠保存唯一AcceptedAnswer，再以精确reply_id沿原回复路径导出本次报告；成功/失败据实呈现，旧会话文件不代签当前报告。原正文/保存时交付状态不回写，失败不自动重算或重试。 |
| 坏表有限诊断（107、109） | 零有效值分布仅保留宿主可核诊断及未知统计量；detect_data_quality/quick_profile仅保留原声明质量问题、缺失/排除计数、列诊断和基础检查状态。当前原件/回执/版本/权限及宿主独立诊断须一致；缺证据/篡改/换版拒绝，实际分析数值/推断仍受质量门约束，不升级方法就绪。 |
| 逐假设区分性检验（110） | 当前宿主原假设冻结的结构化目的/角色、原件/计划/版本/原权限可核时，逐个呈现同窗指标对照、分组占比/组内变化、可比历史重复窗基线核对，明确尚未执行，不证明因果/显著性。未知角色/缺原件精确列缺口，不从列名或旧测量猜角色；原Renderer沿同一缺口正文保存/刷新/导出，不新增统计方法、执行、模型调用或账本，历史原字节只读。 |

历史批次引用：知识[独立创建r2](../../../tmp/s3-knowledge-20261012-r2/receipt.json)、[持久化/上下文r1](../../../tmp/s3-knowledge-20261012-r1/receipt.json)、[规则r2](../../../tmp/s3-rules-20261012-r2/receipt.json)、[任务范围r1](../../../tmp/s3-task-scope-20261012-r1/receipt.json)、[漏斗r1](../../../tmp/s3-funnel-20261010-r1/receipt.json)、[cohort r1](../../../tmp/s3-cohort-20261010-r1/receipt.json)只证明其各自冻结身份；不得标为当前通过。本次编辑前完整文档保存在[原字节前像](../../../tmp/b365/2026-09-30-trusted-answer-pipeline-acceptance.md.before)，SHA256为afb3126e7cbac1fe5fc30ea5f398311ad95afc45a58e5e9a312554787006ff34；过期进度叙述可从该前像追溯。

### R3/R4/R5联合目标与原DoD承接

封闭事实可用、开放内容正确保留/错误限制、被替代旧门退役必须同时通过；不得只签其中一项。下表保留原15项DoD的行为含义，旧协议/审核机制按本节已批准替代执行。

| 原DoD | 当前联合判据 |
| --- | --- |
| 1—3 | VP/IC/CP有责任与行为证据；M01不靠词语挂起；M02计算/外推依实际回执和方法，不从散文配对 |
| 4—5 | M03规范历史压缩、刷新和导出不丢结果；claim无第二Planner，假设仍绑定真实目标/计划/ID/回执 |
| 6—9 | 高风险断言不能靠尾注免责；finding定位且不能改事实或推翻确定性失败；一次审核、局部故障保留事实 |
| 10—11 | 合法同义/语序/布局不误拒；无据强断言限制或拒绝，不能仅贴待核标签后原样发布 |
| 12—15 | 当前完整离线/app/必要视觉有隔离证据；真实M01—M06另冻结授权且满足两次完整门；原文件及dirty保留 |

## 6. 本地、内容和自然出口

本地：当前full-offline、完整Provider禁用正常app、必要视觉分别有收据。相关失败为0；skip有影响说明，必需行为未测不能计通过。原3530项/47组90回合是历史证据，数量不构成当前门槛。Provider initiated calls=0，并核forbidden_provider_transport=0。

内容每份按以下0/1/2量表独立评分，附正文/产物定位与理由。0=缺失或错误，1=有但不够明确，2=完整清楚。

| 维度 | 必须看什么 |
| --- | --- |
| 需求覆盖 | 全部有效原问题、可算事实实际交付、允许缺口具体；分母不从模型生成 |
| 口径方法 | 单位/窗口/粒度/分母、方法/误差/验证范围，相关敏感性与候选对比 |
| 有效解释 | 连接业务问题；按请求给竞争解释及区分证据、条件行动/评估/停止条件；只要公式时不强塞建议 |
| 边界准确 | 观察/假设/推断区分，局部必要限定，无无据升级和机械误拒 |
| 阅读层次 | 结论与依据清楚，受众适配、真实图表可用，不倾倒内部JSON/路径 |

**全部维度至少1；覆盖与边界必须2；总分至少8/10。** 核心事实错、必答遗漏、关键错误升级、合规必测内容误拒任何一项直接失败，不得靠软分抵消。长度/标题/emoji/图数只作观察。

自然：用户2026-10-10批准**同候选、同M01—M06输入/判据连续两次完整通过**。两批均运行全部冻结轮次及有效恢复分支，分别所有硬门通过、内容合格、账本和唯一终态闭合。源码/模型/配置/输入/oracle改变后重新积累两次；任一产品失败本轮验收不通过，先诊断，不能反复抽样筛出两批绿灯。

每批新run_dir/session/ledger、精确冻结和单独用户授权；本规范不授权调用。普通场景失败继续收证，Provider/流/隔离/记账/整服务失败按AGENTS停止，不重试/fallback/续跑部分批。未到达项blocked_not_started/unassessed。两次通过只证明冻结样本，不证明任意输入可靠、UI未测部分或部署。

漏斗硬判据：B09→A10→B11仍须识别有效A→B；X10→10/Y90→0总体100→10（10%）且完整分组；重复A10/A20只输出A30一次。缺失步骤、零分母未知，非法计数拒绝。率列不虚构人数、不截比例，均值之比使用显示舍入前的原均值；精确mode/列/顺序/维度/window与正式计划一致。必须贯通实际上传、正式计划、原回执、唯一AcceptedAnswer、SSE、保存/API刷新及导出。历史收据不签当前候选。

cohort硬判据：一月首观测2用户、其中1用户三月再次出现，一月矩阵100%/0%/50%；二月首观测1用户、其后三月无事件，二月矩阵100%/0%/null。去重人数/分母保留，年龄轴0/1/2完整；排除原因重叠但联合排除只计一次，坏日期不能静默计全范围完成；末月不完整及首次观测口径公开，错事件列拒绝。必须贯通实际上传、精确列参数正式计划、原回执、唯一AcceptedAnswer、SSE、保存/API刷新及导出。历史源码/HTTP批次不签当前候选。

聚类硬判据：4条相同记录请求3簇只交付1个真实非空簇；3条各自成簇的样本标准差null。普通两簇各2条时均值/样本标准差对照独立算术；按列缺失可重叠而联合排除只计一次，缺失范围部分完成。错误/重复/非数值特征及任何非有限值拒绝，原特征/请求簇数/方法参数与正式计划及回执绑定，篡改不能交付；按记录计数，不制造业务差异或因果。六条正常app链及共同回归/原HTTP矩阵须核，未通过前不签当前候选。


TopN硬判据：n=-1/0/布尔/小数拒绝且不产生新对象；错误/重复返回列拒绝；0.423456789012345按原值交付。升降序、默认列、选列和上限大于来源条数均核真实范围；计划的排序列/方向/n/列序/产物类型不匹配不能关闭目标；篡改原值/排序/元数据不能发布。save_as核实际新表、父版本、执行前参数与权限，只保存目标不绑定数据claim；未指定save_as无操作效果。六条正常app链、综合scope隔离、共同回归和完整原HTTP矩阵须核，未通过前不签候选。


贡献分解硬判据：mean新组/消失组缺席均值null、实际条数/权重0，合并贡献对照独立算术，绝不把缺席均值写0。sum/mean都披露两期/各组有效条数、坏日期/缺失逐项和联合排除；排除原范围partial。负变化贡献百分比分母abs总变化，净变化/基线0时比例未知。11组完整、日均按原窗口日数、错参数/窗口/日期列/指标/交付类型不得关闭目标，原回执篡改拒绝。七条正常app链、旧有效分解入口、共同回归及完整原HTTP均需核；不授予因果归因。

因素分析硬判据：目标泄漏/重复特征/缺列拒绝；平衡正交样本以独立公式核OLS标准化系数、HC3区间、Holm与VIF。常数/样本不足/共线均严格JSON未知和具体缺口，筛样逐列与联合计数一致；单位/时间真实有效范围、重复及未聚类/未校正独立性边界可见。精确features/unit/time/target/output交付前冻结，篡改系数、推断、范围、身份/参数拒绝；七条真实上传/正式计划/registry/原回执/SSE单终局/保存/API刷新/实际MD导出链、共同回归及完整原HTTP均需验证。

时间序列硬判据：线性上升raw自相关1只作启发，不证明季节性；斜率每记录/未校正时间相关明确。0→10窗口绝对差10、百分比/阈值null；40点平方序列24个窗口/命中全部保留。常数/短序列未知推断及相关，坏日期/缺失/非有限原范围partial；重复日期/不规则跨度不聚合，实际选列/别名/错参拒绝。真实源/回执篡改拒绝，七条正常app完整上传—正式计划—原工具—SSE单终局—保存/API刷新/MD导出与共同回归/完整原HTTP均需核。

## 7. 原始VP/IC/CP全编号追溯

当前责任文件与既有验证入口候选见[180行为责任附件](../../audit/2026-10-10-original-behavior-map.md)。该附件已按有限责任包持续审核，逐条列当前分类、原条件缺口及各自证据身份；不继承旧通过状态。

以下180行来自本轮前统一映射及三个原验收首定义：VP84、IC56、CP40。原编号、源行、输入摘要及验收族保留；最后一栏由同一原180审核映射同步，仅作索引，具体缺口和证据层级见责任附件及逐条收据。源行号指[原字节归档](../../audit/archive/2026-10-10-plan-reset/manifest.json)中的文件，不是精简后的行号。机制冲突按§5明确替代；原主题验收保留每行原预期供对照。

### VP

来源：[2026-09-06-analysis-value-preservation-acceptance.md](2026-09-06-analysis-value-preservation-acceptance.md)。源行号指原字节归档。

| 原编号 | 源行 | 原输入或条件摘要 | 新需求与验收族 | 处理 |
| --- | ---: | --- | --- | --- |
| VP-I01 | 46 | 你好，请分析收入趋势 | PROD-I01—09；CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-I02 | 47 | 不要报告，只导出这张表 | PROD-I01—09；CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-I03 | 48 | 请分析收入下降原因并给出分析建议 | PROD-I01—09；CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-I04 | 49 | 中英文等价否定/转折请求 | PROD-I01—09；CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-I05 | 50 | “计算总收入”“什么是回归分析” | PROD-I01—09；CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-I06 | 51 | 同时出现咨询与执行，主任务不明确 | PROD-I01—09；CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-I07 | 52 | F-BAD-OTHER，只分析目标 sales | PROD-I01—09；CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-I08 | 53 | 同 I07，但 contracts 为 compact refs | PROD-I01—09；CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-I09 | 54 | F-RET7，只拟合聚合留存曲线 | PROD-I01—09；CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-I10 | 55 | 同时要求聚合曲线和个人留存 | PROD-I01—09；CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-I11 | 56 | 当前 scope 限定 A，文本提及 B | PROD-I01—09；CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-I12 | 57 | no-data、缺必要列、未解决高风险确认 | PROD-I01—09；CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-S01 | 65 | 同证据，“给出行动建议”与 recommend actions | PUB-06/07/11；OPEN / CONSULT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-S02 | 66 | 同证据，中文预测与英文 forecast | PUB-06/07/11；OPEN / CONSULT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-S03 | 67 | “请详细诊断原因” | PUB-06/07/11；OPEN / CONSULT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-S04 | 68 | “简短说明并给一个建议” | PUB-06/07/11；OPEN / CONSULT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-S05 | 69 | “只要公式，不需要建议” | PUB-06/07/11；OPEN / CONSULT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-S06 | 70 | pass_with_downgrades＋有效观察 | PUB-06/07/11；OPEN / CONSULT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-S07 | 71 | 某证据失败，另一独立证据通过 | PUB-06/07/11；OPEN / CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-S08 | 72 | 无任何业务证据 | PUB-06/07/11；OPEN / CONSULT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-N01 | 80 | D7 为 10%，当前不能预测 D30 | PUB-02/05/06/08；FACTS / OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-N02 | 81 | 建议继续收集至第30天再验证 | PUB-02/05/06/08；FACTS / OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-N03 | 82 | D30 留存预计为 5% | PUB-02/05/06/08；FACTS / OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-N04 | 83 | 不能预测 D30，但 D30 大约是 5% | PUB-02/05/06/08；FACTS / OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-N05 | 84 | 如果 D30 达到预先阈值，则继续试点 | PUB-02/05/06/08；FACTS / OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-N06 | 85 | F-TWO-SCOPE 中 B 的 D30 为 8% | PUB-02/05/06/08；FACTS / OPEN | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-N07 | 86 | 没做检验却说“差异不显著” | PUB-02/05/06/08；FACTS / OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-N08 | 87 | 某工具完成合法检验，另一无关主张没检验 | PUB-02/05/06/08；FACTS / OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-N09 | 88 | 有效统计工具类型不是 ab_test | PUB-02/05/06/08；FACTS / OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-N10 | 89 | 合规事实＋一个无依据解释，可可靠定位 | PUB-02/05/06/08；FACTS / OPEN | 机制按§5替代，原保护目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-N11 | 90 | 复杂混合句无法可靠定位/修订 | PUB-02/05/06/08；FACTS / OPEN | 机制按§5替代，原保护目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-N12 | 91 | 最终候选为空/含未执行工具标记/修订仍错 | PUB-02/05/06/08；FACTS / OPEN | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-C01 | 99 | F-SALES，statistical_inference=false | PROD-S02 / PUB-10；HISTORY | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-C02 | 100 | 同 F-SALES 却推断全部市场 | PROD-S02 / PUB-10；HISTORY | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-C03 | 101 | 单一来源、口径和完整性可核对 | PROD-S02 / PUB-10；HISTORY | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-C04 | 102 | 大样本但选择偏差或分析单位错误 | PROD-S02 / PUB-10；HISTORY | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-C05 | 103 | 365天结构化观察窗 | PROD-S02 / PUB-10；HISTORY | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-C06 | 104 | 时段无法解析或频率未知 | PROD-S02 / PUB-10；HISTORY | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-C07 | 105 | 缺失、零值含义未知 | PROD-S02 / PUB-10；HISTORY | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-C08 | 106 | 相关、前后对比、合法因果设计分别输入 | PROD-S02 / PUB-10；HISTORY | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-E01 | 114 | F-SIX，六项均为用户主要问题 | PUB-03/04；REQUIREMENTS / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-E02 | 115 | 当前收据第一项，其他计划占据最近四条 evidence | PUB-03/04；REQUIREMENTS / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-E03 | 116 | F-GROUP，最大值在第四组 | PUB-03/04；REQUIREMENTS / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-E04 | 117 | 比较值/组名/分母/时期处在不同字段 | PUB-03/04；REQUIREMENTS / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-E05 | 118 | 超大结果、上下文预算有限 | PUB-03/04；REQUIREMENTS / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-E06 | 119 | F-COMPACT，中等与大型输出 | PUB-03/04；REQUIREMENTS / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-E07 | 120 | 结果保存失败/同 id 不同内容 | PUB-03/04；REQUIREMENTS / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-E08 | 121 | 二次压缩已经压缩的消息 | PUB-03/04；REQUIREMENTS / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-E09 | 122 | 发布包创建后新增或修改证据 | PUB-03/04；REQUIREMENTS / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-E10 | 123 | 预算耗尽仍有未覆盖问题 | PUB-03/04；REQUIREMENTS / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-H01 | 131 | It is false that＋原假设 | PUB-09；HYPOTHESIS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-H02 | 132 | 完全文本相同，dataset 错误 | PUB-09；HYPOTHESIS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-H03 | 133 | dataset 同名，plan/version 错误 | PUB-09；HYPOTHESIS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-H04 | 134 | 只有文本重合或模型自报“已证明” | PUB-09；HYPOTHESIS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-H05 | 135 | 先有支持，后删除/失效依赖证据 | PUB-09；HYPOTHESIS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-H06 | 136 | F-HYP，合法引用、当前验证、要求与可计算谓词均满足 | PUB-09；HYPOTHESIS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-H07 | 137 | 满足判定条件的反向证据 | PUB-09；HYPOTHESIS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-H08 | 138 | 同时存在当前有效支持与反证 | PUB-09；HYPOTHESIS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-H09 | 139 | 中文与英文等价证据关系，结构化依据相同 | PUB-09；HYPOTHESIS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-H10 | 140 | 已有关系遇新问题/新版本/重新加载 | PUB-09；HYPOTHESIS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-H11 | 141 | 后续新证据、会话恢复、最终发布 | PUB-09；HYPOTHESIS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-H12 | 142 | 归因未能排除替代解释/字段不足 | PUB-09；HYPOTHESIS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-A01 | 150 | 我是业务人员，解释这些结果 | PUB-07；OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-A02 | 151 | 我是数据分析师，给方法细节 | PUB-07；OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-A03 | 152 | 给管理层汇报 | PUB-07；OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-A04 | 153 | 固定事实依次套 A01—A03 | PUB-07；OPEN | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-A05 | 154 | 先业务视角，后改分析师视角 | PUB-07；OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-A06 | 155 | 先专业术语，后要求用大白话 | PUB-07；OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-A07 | 156 | 未声明身份或仅数据中出现“经理” | PUB-07；OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-A08 | 157 | 混合受众、临时面向受众、会话恢复 | PUB-07；OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-U01 | 165 | 八条当前有效 verified 结论 | PROD-W01 / PUB-10；ARTIFACT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-U02 | 166 | 同时有已验证与待验证发现 | PROD-W01 / PUB-10；ARTIFACT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-U03 | 167 | 待验证项有依据、限制、下一步 | PROD-W01 / PUB-10；ARTIFACT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-U04 | 168 | 已验证证据指纹失效或版本改变 | PROD-W01 / PUB-10；ARTIFACT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-U05 | 169 | 最终 SSE 后刷新页面 | PROD-W01 / PUB-10；ARTIFACT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-U06 | 170 | 切换会话或重开历史会话 | PROD-W01 / PUB-10；ARTIFACT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-U07 | 171 | Markdown/HTML 导出 | PROD-W01 / PUB-10；ARTIFACT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-U08 | 172 | 折叠、展开、空状态及键盘操作 | PROD-W01 / PUB-10；ARTIFACT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-B01 | 182 | 加载 F-SALES → 中文分析＋建议 → 最终回复 → 刷新 | PUB-01/10/12；LIFECYCLE / ARTIFACT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-B02 | 183 | 加载 F-RET7 → 发布 D7＋不能预测 D30 → 尝试错误 D30 断言 | PUB-01/10/12；LIFECYCLE / ARTIFACT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-B03 | 184 | 多数据源/六子问题 → 中途压缩 → 综合回复 → 展开/导出 | PUB-01/10/12；LIFECYCLE / ARTIFACT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-B04 | 185 | 创建竞争假设 → 支持/反证 → 补新证据 → 修改版本 → 刷新 | PUB-01/10/12；LIFECYCLE / ARTIFACT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-B05 | 186 | 固定分析结果 → 业务/分析师/管理层连续追问 | PUB-01/10/12；LIFECYCLE / ARTIFACT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| VP-B06 | 187 | 工具失败、保存失败、修订失败、预算耗尽和待确认分别触发 | PUB-01/10/12；LIFECYCLE / ARTIFACT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |

### IC

来源：[2026-09-07-intent-clarification-acceptance.md](2026-09-07-intent-clarification-acceptance.md)。源行号指原字节归档。

| 原编号 | 源行 | 原输入或条件摘要 | 新需求与验收族 | 处理 |
| --- | ---: | --- | --- | --- |
| IC-Q01 | 34 | F2，仅要求拟合观测内留存公式，口径已明确 | PROD-C01；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-Q02 | 35 | F1，要求九项指标 | PROD-C01；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-Q03 | 36 | 要求描述性复购率，分母/窗口已明确 | PROD-C01；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-Q04 | 37 | 需要净收益但两种成本定义均合理、未提供答案 | PROD-C01；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-Q05 | 38 | 同 Q04，但当前请求已给出成本边界 | PROD-C01；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-Q06 | 39 | F3 指代不唯一且影响范围 | PROD-C01；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-Q07 | 40 | 预测/因果/分类计算，已授权分析且必要输入明确 | PROD-C01；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-Q08 | 41 | 技术工具失败，已有合法恢复方法 | PROD-C01；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-Q09 | 42 | 模型主动 ask：是否按留存方法继续 | PROD-C01；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-Q10 | 43 | 模型主动 ask：真实未决分母 | PROD-C01；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-Q11 | 44 | 一次多问题：已有答案+方法审批+真实窗口缺口 | PROD-C01；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-Q12 | 45 | 模型伪造 safe_default、dataset_ref 或“所有操作受阻” | PROD-C01；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-Q13 | 46 | D1—D7 留存数据；请求“解释 D7，并判断能否预测 D30；若不能说明缺失证据” | PROD-C01；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-Q14 | 47 | 已明确“提出并检验至少两种竞争性假设”的数据分析请求 | PROD-C01；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-R01 | 53 | 同一业务决定换措辞、换显示文案 | PROD-C01 / PUB-10；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-R02 | 54 | 消息数量变化，业务范围不变 | PROD-C01 / PUB-10；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-R03 | 55 | 同方法但复购改为到期续购 | PROD-C01 / PUB-10；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-R04 | 56 | 窗口 30 天改 7 天，或“包含成本”改“不包含成本” | PROD-C01 / PUB-10；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-R05 | 57 | 相关数据版本变化 vs 无关文件变化 | PROD-C01 / PUB-10；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-R06 | 58 | 相同文本来自另一 session | PROD-C01 / PUB-10；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-R07 | 59 | 重复提交同一 resume / 过期 version | PROD-C01 / PUB-10；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-R08 | 60 | resolved / skipped / cancelled / expired 的同类记录 | PROD-C01 / PUB-10；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-R09 | 61 | 同时到达等价 open candidate | PROD-C01 / PUB-10；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-R10 | 62 | advisory/reused/rejected、正常暂停分别经过同步/流式/恢复入口 | PROD-C01 / PUB-10；CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-L01 | 70 | 恢复 F5 纯模板审批 | PROD-S01/02；HISTORY / CONFIRM | 旧运行迁移替代为只读；其余目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-L02 | 71 | 恢复真正的旧窗口/字段决定 | PROD-S01/02；HISTORY / CONFIRM | 旧运行迁移替代为只读；其余目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-L03 | 72 | 未识别来源/范围的旧记录 | PROD-S01/02；HISTORY / CONFIRM | 旧运行迁移替代为只读；其余目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-L04 | 73 | 连续加载、刷新、重启 | PROD-S01/02；HISTORY / CONFIRM | 旧运行迁移替代为只读；其余目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-L05 | 74 | 已有历史结果和确认事件 | PROD-S01/02；HISTORY / CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-L06 | 75 | 新元数据由兼容旧代码读取，或代码回滚 | PROD-S01/02；HISTORY / CONFIRM | 旧运行迁移替代为只读；其余目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-M01 | 83 | 原始省钱卡九指标+连续付费/影响目标 | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-M02 | 84 | M01 改变“复购率”在列表中的位置 | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-M03 | 85 | “不要分析留存，只分析省钱卡收益” | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-M04 | 86 | “仅计算复购率，口径如下……” | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-M05 | 87 | 原始聚合留存公式拟合请求 | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-M06 | 88 | “拟合当前曲线，不预测 D30” | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-M07 | 89 | “预测后续留存”，数据/验证条件充足与不充足两组 | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-M08 | 90 | 收益、趋势、纯咨询、数据操作、问候+分析等对照 | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-M09 | 91 | F1 缺少成本/对照，但描述性支付指标完整 | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-M10 | 92 | F2 含 0/未成熟 cohort/权重歧义 | PROD-I01—09 / PUB-03；CONSULT / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-O01 | 100 | 合法 LLM 主方法、空 supporting | PUB-12；LIFECYCLE / CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-O02 | 101 | F6 各失败模式 | PUB-12；LIFECYCLE / CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-O03 | 102 | 必要/无关/复用/失效四种候选 | PUB-12；LIFECYCLE / CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-O04 | 103 | 固定验收集统计 | PUB-12；LIFECYCLE / CONSULT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-S01 | 104 | 无对照的购卡前后变化 | PUB-02/08；FACTS / CONFIRM | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-S02 | 105 | 只观测 D1—D7 的描述性拟合 | PUB-02/08；FACTS / CONFIRM | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-S03 | 106 | 跨 dataset/version/plan 的旧答案或证据 | PUB-02/08；FACTS / CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-S04 | 107 | 工具失败/无真实收据/未执行计划 | PUB-02/08；FACTS / CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-S05 | 108 | 所有 E1—E3 运行 | PUB-02/08；FACTS / CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-S06 | 109 | 必要语义仍未解决但用户 skip/cancel 或模型反复问通用许可 | PUB-02/08；FACTS / CONFIRM | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-B01 | 117 | 上传 F2，提交拟合请求 | PROD-C01/W01；CONFIRM / ARTIFACT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-B02 | 118 | 上传 F1，提交完整需求 | PROD-C01/W01；CONFIRM / ARTIFACT | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-B03 | 119 | 提交真正有成本/窗口歧义的请求，回答具体选项 | PROD-C01/W01；CONFIRM / ARTIFACT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-B04 | 120 | 将 B03 换措辞继续，再实质改变口径 | PROD-C01/W01；CONFIRM / ARTIFACT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-B05 | 121 | 恢复 F5，刷新/重启，再跳过真实语义问题 | PROD-C01/W01；CONFIRM / ARTIFACT | 旧运行迁移替代为只读；其余目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| IC-B06 | 122 | 脚本模型发无关方法 ask 与真实语义 ask 两种调用 | PROD-C01/W01；CONFIRM / ARTIFACT | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |

### CP

来源：[2026-09-08-answer-content-acceptance.md](2026-09-08-answer-content-acceptance.md)。源行号指原字节归档。

| 原编号 | 源行 | 原输入或条件摘要 | 新需求与验收族 | 处理 |
| --- | ---: | --- | --- | --- |
| CP-AC01 | 15 | 第8轮预览只有 early，后追加 late 结果与 evidence，再终局 | PUB-01/02；LIFECYCLE / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC02 | 16 | 同 receipt id 修改 result hash/数值；另测只改限制或验证状态 | PUB-01/02；LIFECYCLE / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC03 | 17 | 原数据 v1 已验证，切换 v2，夹入其他会话同名数据 | PUB-01/02；LIFECYCLE / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC04 | 18 | 同一最终候选重复回调、刷新、导出 | PUB-01/02；LIFECYCLE / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC05 | 19 | 终局来源文件写失败或 save 失败 | PUB-01/02；LIFECYCLE / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC06 | 20 | 同步与流式各走正常/修订/断流路径 | PUB-01/02；LIFECYCLE / FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC07 | 21 | P08 Python fallback 已算描述结果；无依据 D30；有效/孤立工具消息 | PUB-01/02；LIFECYCLE / FACTS | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC08 | 27 | Python stdout 前180字符是概览，尾部 weighted_delta=0.00277 | PUB-03/04；FACTS / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC09 | 28 | result 有收益/人数，replay 有代码/hash/timeout | PUB-03/04；FACTS / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC10 | 29 | 12组，每组 name/count/revenue，要求全部分组 | PUB-03/04；FACTS / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC11 | 30 | 3候选拟合族、10观测点、残差、范围与未知零值 | PUB-03/04；FACTS / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC12 | 31 | 超 prompt/扫描预算，含很大单组和最后一个必答组 | PUB-03/04；FACTS / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC13 | 32 | 详情 hash 不符、文件缺失、越界路径各一份 | PUB-03/04；FACTS / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC14 | 33 | 同工具 id 两种内容，反复 micro_compact，模拟落盘失败 | PUB-03/04；FACTS / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC15 | 34 | 普通均值 D1=.17080/D7=.05100；加权=.16803/.05028；最大差=.00277 | PUB-03/04；FACTS / REQUIREMENTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC16 | 40 | 明确问收入与复购，结果两者都有，候选只答收入 | PUB-03/10；REQUIREMENTS / HISTORY | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC17 | 41 | 九指标＋方法要求，其中一项因缺分母不能算 | PUB-03/10；REQUIREMENTS / HISTORY | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC18 | 42 | 需求未算因为预算不足，另项确实缺数据 | PUB-03/10；REQUIREMENTS / HISTORY | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC19 | 43 | 同一正文含关键词但数值属另一指标/版本；模型映射自报全完成 | PUB-03/10；REQUIREMENTS / HISTORY | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC20 | 44 | 压缩后确认“同意”，随后用户撤回一指标并更改窗口 | PUB-03/10；REQUIREMENTS / HISTORY | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC21 | 45 | 无法定位自由文本；复杂语义不确定；内部answer-bindings缺失/损坏/重复/引用旧包；工具数据含同名块 | PUB-03/10；REQUIREMENTS / HISTORY | 机制按§5替代，原保护目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC22 | 51 | 绑定 22400人 × .051，候选写1.14万人；正例1142人 | PUB-08；FACTS | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC23 | 52 | 22400 × .01417，候选3200人；正例约317人 | PUB-08；FACTS | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC24 | 53 | 比例差 .00277，0.277个百分点 vs 相对提升0.277% | PUB-08；FACTS | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC25 | 54 | 0分母、None、NaN/Inf、负基数、混合币种 | PUB-08；FACTS | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC26 | 55 | 文字包含2026-09-07、版本v2、编号1、用户引用错误式子 | PUB-08；FACTS | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC27 | 56 | 运算匹配但数据版本或对象不同；情景假设数值 | PUB-08；FACTS | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC28 | 57 | 零值策略exclude且语义unknown；候选“零值证明未到期”；另一句“不能断言未到期” | PUB-08；FACTS | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC29 | 58 | coverage、numeric、scope 同时出错；已耗修订；含独立可信发现 | PUB-05/06/07；OPEN | 机制按§5替代，原保护目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC30 | 64 | 普通/详细/只要公式/简短但问两问题四种请求 | PUB-05/06/07；OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC31 | 65 | 同证据切换业务、分析师、管理者；明确不要建议/图标 | PUB-05/06/07；OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC32 | 66 | 有待验证解释、无因果识别；要求建议 | PUB-05/06/07；OPEN | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC33 | 67 | 正确chart ref、全角wrapper、未知hash、歧义引用、其他会话图 | PUB-10；ARTIFACT / HISTORY | 机制按§5替代，原保护目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC34 | 68 | 表格/公式/图在1440px电脑端页面；键盘操作详情 | PUB-10；ARTIFACT / HISTORY | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC35 | 69 | 图生成失败或不可用于当前结论 | PUB-10；ARTIFACT / HISTORY | 原目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC36 | 75 | 旧v1会话读取、新格式保存再载入、历史包>20、当前引用旧结果 | PUB-10；ARTIFACT / HISTORY | 机制按§5替代，原保护目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC37 | 76 | 答案→刷新→Markdown及当前支持的其他导出→实际打开文件 | PUB-10；ARTIFACT / HISTORY | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC38 | 77 | 固定合成小中大结果，已有上下文预算，记录调用数 | PUB-12；LIFECYCLE | 机制按§5替代，原保护目标保留；[原条件完整（有限证据）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC39 | 78 | CP1—CP5改完，当前full-offline及全部40项记录 | PUB-12；LIFECYCLE | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
| CP-AC40 | 79 | 授权后新真实批次：P08 M01—M06＋冻结内容样本 | PUB-12；LIFECYCLE | 原目标保留；[局部已核（具名缺口保留）](../../audit/2026-10-10-original-behavior-map.md) |
