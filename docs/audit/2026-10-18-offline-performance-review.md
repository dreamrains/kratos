# 2026-10-18 离线整库性能与测试有效性审核

状态：**方案待讨论，尚未实施优化**。这是唯一总计划§8的审核附件，不是新的阶段计划。用户随后要求在新会话实施S4，当前入口见[S4交接](2026-10-18-s4-handoff.md)；这不表示采用本文A/B/C提案。本轮未启动S4/S5或性能测量，Provider与远端MCP调用均为0。

## 1. 已核基线与结论

实施树仅C:/Users/duguy/.codex/worktrees/trust-rebuild/data-agent；分支codex/trust-rebuild-20260927，HEAD f7210e170d4dd1945abec15d57e364e04942eae4。424文件摘要437f271efb906fafa9dcf422279aa888bafbba3efa6593a6fef3485ddb46d93f与本次JUnit完全一致；索引c5d7162d88d68139842eca5717fc5ad3bb6f59126aeade8aa5bac01042d653c3、218项dirty/untracked均保留。D盘只读。

官方full3为7930通过、0失败、2跳过，3062.846秒（51分02秒）。本次只读取原JUnit和已有profile，未重新运行测试，未改生产或测试源码，未删除任何材料或重开105组退役审核。**保留全部7932个现有实例、参数和独有断言；3—5分钟不是验收目标。**

结论：应先核并减少真实共享路径的重复I/O和重复派生工作，同时补齐测试层之间的证据连接。继续拆文件、关闭存储、减少正常链或把全量改称局部通过，都不能解决本次问题。

## 2. 51分钟具体花在哪里

数据来自[完整JUnit](../../tmp/ay1x/junit.xml)、[逐例原记录](../../tmp/acu11-full3/case-results.json)和[可复核派生统计](../../tmp/tp02/junit-analysis.json)。派生程序逐一核对7932个JUnit节点、类方法身份及时间，未只选慢例。

| 文件 | 实例数 | 累计秒数 | 占逐例总耗时 |
| --- | ---: | ---: | ---: |
| test_slice3_method_integrity.py | 607 | 579.916 | 18.99% |
| test_publication_runtime_tabular.py | 273 | 259.309 | 8.49% |
| test_source_unit_boundary.py | 263 | 196.836 | 6.45% |
| test_publication_runtime_sessions.py | 88 | 194.067 | 6.36% |
| test_publication_runtime_records.py | 391 | 180.518 | 5.91% |
| test_publication_runtime_inference.py | 93 | 175.077 | 5.73% |
| test_publication_runtime_charts.py | 414 | 148.975 | 4.88% |
| test_publication_runtime_chart_axes.py | 237 | 127.459 | 4.17% |
| test_publication_synthesis.py | 157 | 115.239 | 3.77% |
| test_trusted_publication_native_families.py | 658 | 109.650 | 3.59% |

前4文件1230.128秒，占40.28%；前10文件占68.34%，前16占84.94%。最慢10个实例仅187.083秒，占6.13%；最慢500个实例占52.36%。因此只优化一两个长例不足以显著收敛，需要处理许多链共同经过的责任。

逐例时间合计3053.737秒，占JUnit总时长99.703%，差额9.109秒。本机pytest的junit_duration_report默认total，包含每例setup/call/teardown，不能据此把全部归给测试函数本体，也不能精确把9秒解释为全部收集/启动开销。它足以表明：文件拆分、模块导入不是当前51分钟的主要解释。

原巨型runtime已拆，核心目前536行、44实例、21.904秒，仅占逐例时间0.72%。现最大方法文件443,263字节/4479行；其可维护性仍可改进，但再次拆分不作为本轮性能收益。105组分层退役结论不重审。

同一424源码的完整图表责任包500例与full3对应500例，逐例累计分别197.433/200.158秒，仅差2.725秒（约1.38%）。这是一对同源观察，不能证明所有环境波动都小；至少没有证据把本批51分钟主要归咎于临时机器抖动。该包JUnit总时长200.508秒含包级开销，不能拿它直接减full3逐例时间。

## 3. 已有profile核到的共享开销与证据限制

复用[95例原前后对照](../../tmp/p6e01/performance-comparison.json)、[前profile](../../tmp/p6e01-prof/profile.pstats)、[后profile](../../tmp/p6e01-prof2/profile.pstats)，本次摘要为[profile-review.json](../../tmp/tp02/profile-review.json)。原95节点前后完全相同，95个函数/参数身份都能唯一映射到本次整库；映射只证明节点可定位，不证明历史AST、输入或耗时仍相同。

裁决115已经实施并包含在full3。原观察为67.659→48.382秒，真实SQLite connect均2081次，migration从1215次到60次。不能再将这项重复列为新优化，也不能把28.49%当作整库预计收益。前后不同源码、单次测量且多项未变I/O耗时也有差异，因果收益必须限定。

下表为**115之后的旧95例profile**，累计时间有父子重叠，严禁相加或线性外推51分钟。

| 路径 | 次数 | 累计秒 | 已核代码行为 |
| --- | ---: | ---: | --- |
| history.save_session | 377 | 17.928 | 每次保存后同步调用自动索引 |
| _try_index_session_evidence | 377 | 15.725 | 每次构造EvidenceStore，再index_session |
| EvidenceStore.index_session | 377 | 12.589 | 读全部消息，DELETE当前会话旧索引、逐条INSERT，再自动抽取候选 |
| _try_extract_memory_candidates | 377 | 7.178 | 再构造EvidenceStore/MemoryStore及其数据库对象 |
| KnowledgeDatabase.__init__ | 1215 | 8.353 | 已免重复迁移，但每次仍核身份/schema及开真实连接 |
| EvidenceStore._read_messages | 2994 | 2.688 | 其中2617次来自逐条content_ref hydration，反复读同一会话文件 |
| ConfirmationStore._write_snapshot | 676 | 3.182 | 626次来自load，50次来自append；load无变化也重写并fsync |
| nt.fsync（全部） | 726 | 2.453自耗时 | 676次快照、50次事件；不能简单关闭它 |
| count_request_tokens | 262 | 3.650 | 真实完整请求计量，CoreBPE自耗时3.011秒 |
| create_app | 10 | 0.348 | 本样本不支持把应用构造当首要瓶颈 |
| discover_tools | 66 | 0.089 | 本样本不支持优先扩大fixture共享范围 |

原件访问链核查见history.py:64/263、knowledge/evidence.py:18/23/111/128/157、knowledge/candidates.py:46/51/85；确认快照见confirmation/store.py:106/203。每个原索引调用中，抽取N条记录会N次重新读conversation文件；随着消息长度增加，存在重复读取放大的结构原因。**这不是证明本次整库有多少秒一定能省。**

当前full3没有函数级profile或分阶段耗时；原cProfile也不能完整覆盖worker线程和子进程，父线程等待不能当作纯CPU成本。下一步先以同源有限样本补核，不再直接跑51分钟profile。

## 4. 可执行的三个责任包（采用后才实施）

### 包A：测量、影响选择与证据连接

1. 沿现有run_regression.py唯一入口和现有审计材料组织，先固定95个已映射节点，再增加6个现有高耗时代表：六来源完整产物两个参数、B03压缩冷恢复、B04十三步、超过20答案的连续会话、五计划原回执精确导出。不增加重复正常链，不更改节点或断言。节点清单已从本次JUnit精确生成，见[待执行责任包](../../tmp/tp02/proposed-packages.json)：A共101例，原逐例合计163.253秒（不含新进程/采样开销）；缺失/重复即拒绝测量。首轮只观察，不优化。
2. 保留cProfile，附现有pytest的setup/call/teardown duration，记录索引次数、消息文件读取次数、数据库构造/真实连接/迁移、快照重写/fsync与tokenizer调用。线程/子进程不能覆盖的部分明确列出，不把累计时间相加。每次新短run-dir、重定向现有31证据变量；记录冷/热状态、依赖/解释器、是否有竞争任务。前后各3次小样本，报告中位数及范围；不拿不同节点/失败早退做速度对照。
3. 扩充已有shared-owner-impact-review的明确边：共享质量门→保留的count_empty正常图链；生产者返回值→旧直接调用观察器；证据索引/候选→检索和提取事务；确认load→正常同步/流式待决与恢复。复用已有用例。之前整库发现的count图误拒、ToolResult旧观察器TypeError说明“选包遗漏”需要修，不能只缩短单次执行。
4. 拟将现有31证据变量的重定向归入现有运行入口的同一run-dir管理，拒绝指向历史材料；保留原变量名称和捕获机制，不另起账本。现状官方runner仅直接隔离workspace/sessions，靠外层wrapper保护其余证据；入口单独使用时的证据隔离应变得可核。此项属于待采用的测试执行组织调整。

**质量补链**：现有正常主业务链主要注入Response/ToolCall，LLMClient另有预算/超时/重试/finish_reason单测，真实辅助LLMClient也有正常链。所审材料尚不能证明“主LLMClient原始碎片响应→工具参数拼接→正常app→保存/导出”这一连接已由同一代表用例核定；这是具名未核点，不据静态搜索断言全库绝无覆盖或直接宣判产品缺陷。

先复用已有等价链；若不能对应，仅补少量代表：同步原始响应、流式分段工具参数、无效参数或缺终态拒绝、末端保存故障。只替换最底层传输为本地固定响应，让真实LLMClient、AgentLoop、工具、发布和持久化运行；数值/范围/调用次数/唯一AcceptedAnswer/失败状态由独立预期核。不得直接在模型替身内读取内部state来反向生成唯一oracle。Provider与远端MCP仍0；不新增模型审核层、浏览器框架或测试平台。

### 包B：减少原件索引与候选提取的一次调用内重复工作

责任仅限knowledge/evidence.py、knowledge/candidates.py与必要的现有存储上下文传递；不关闭history.save_session的索引、不延迟候选可见时机、不跨请求缓存原件或权限、不合并原来两个事务。

拟实施边界：

- 一次extract_for_session调用内按确切会话与实际文件集合读消息，用同一已核输入批量hydrate该会话的content_ref，避免每条记录重新读全文件。每条仍校验引用的session/index/path，保持原JSON＋JSONL拼接、坏行、空内容、排序、去重键、max_candidates和已有候选刷新语义。不能借此替换canonical history定义。
- 输入文件集合、实际身份与字节证明变化或不可核时，不使用批量复用；沿原逐条解析或原失败路径，绝不借旧缓存补缺。调用结束前还需核适用性；不得拿mtime/路径相同代替原内容证明。并发变化行为必须先由反例固定，不引入新的静默重试或默认许可。
- 同一index_session调用内部，允许探讨传递同一已核DB/Store上下文给候选提取，避免重复构造和PRAGMA初始化核验；各原事务、真实连接、BEGIN/commit/rollback、索引时机与权限检查保留。若无法在每个原事务前保持115要求的实际文件/schema核验，就只做批量消息读取，DB生命周期不动。连接池、跨线程共享连接及跨请求身份缓存不在本提案内。
- 不先做跨save的增量索引或跳过整个索引：当前DELETE/重建、created_at、ev_session_index身份及候选状态有对外行为，必须独立讨论，不能伪装成无语义变化的缓存。

验证复用test_evidence_store、test_evidence_auto_index、test_memory_candidate_auto_extract、test_memory_candidate_extractor、test_knowledge_database_initialization及storage正常链。保留短记录、JSONL、会话逃逸、引用错绑、记录删改、候选accepted/rejected状态、去重、限额、失败回滚、删库/换库/schema变化等全部原断言。新增只限本优化引入的文件集合变化、同长换字节、跨会话与批量读取故障反例。

收益目前未知；profile中索引父项15.725秒是含真实写入和其他必要工作的样本总成本，不能全部作为可节省预算。以减少重复读取和构造计数且原结果/事务等价为先决条件；没有稳定收益则撤回优化候选。

### 包C：确认快照同字节时不重复物化

责任仅限confirmation/store.py现有load与snapshot物化；这是**需要讨论的持久化生命周期取舍**，本次不实施。

拟边界：load仍每次读取、完整replay原events，校验重复event_id、跨会话、版本连续性、中段损坏和截尾；权威只来自原事件。生成与原逻辑完全相同的快照字节，再读取当前真实snapshot核字节一致；只有相同才省本次write/replace/fsync。不能只看mtime、event_count或内存缓存，也不以snapshot内容授予新状态。缺失、损坏、不一致或不能证明同字节则沿现有原子写入/fsync与原异常路径。append的事件和snapshot两次fsync保持，真实变化、恢复物化和故障测试仍走真实磁盘。

必须先核的反例：连续load不变化；删/坏/异会话snapshot重建；同字节长度改写；同一事件ID不同payload；中段损坏与截尾；append与load竞争；replace/fsync失败后冷恢复；同步/流式待决恢复与唯一终态。复用test_confirmation_store、runtime/service/session_api及既有并发正常链；不再为每种参数新加完整app链。

样本626次load触发约3.000秒快照重写，是定位证据；省写还要增加一次小文件核读，实际净收益需包A测量。不能承诺净省3秒，更不能换算为整库固定百分比。

## 5. 覆盖面与有效性如何保证

目标是：对冻结输入和明确合同，除模型生成内容之外的可控环节有实际执行与独立判据；剩余未知可定位。任何有限测试都不能证明所有输入、所有机器与所有外部故障正常。

| 层 | 离线必须实际运行并判断 | 后续配合与当前边界 |
| --- | --- | --- |
| 内核/77工具 | 原数值与方法、单位/分母/窗口、对象/版本/权限、反例拒绝及原件；保留当前公开模式 | 77表/200函数1163例是有限具名合同，不是全部分支覆盖；AST关联和passed数量不能替代行为证明 |
| 正常AgentLoop | 固定模型提议，真实计划、工具、发布、同步/流式、确认、失败与预算、持久化、冷恢复、精确导出 | 固定模型只证明给定提议的宿主行为；正确接受的正向值与拒绝负例都要有，不能只有fail-closed |
| 主LLMClient边界 | 原始本地传输响应经过真实解析/拼参/finish_reason/超时，再接同一正常链 | 不访问Provider；补前述具名连接即可，不复制全部业务矩阵 |
| Web后端及JS | 现有Flask test-client真实后端＋Node中实际app.js协议断言分别保留 | test-client不等于监听服务；Node伪DOM/fetch不等于浏览器。真实HTTP分块/断连/并发及浏览器DOM连接必须有后续同源证据 |
| 浏览器/自然 | 本次不执行 | S4按原AGENTS健康服务和控制路线核图/文字/确认/刷新/下载/console；S5新freeze及新授权核自然分类、构造、解释/审核，沿同一原数据与oracle，不从本地passed升级 |

验收文档的E2/E3-HTTP含义按实际观测解释：当前大量Flask test-client正常链属于app-path离线集成证据，不能单凭文件名或“HTTP”命名升级为真实HTTP/浏览器批。

另外需要改进的质量点：

- shared-owner变更的选择闭包必须包括旧直接调用方；包A沿现有影响清单修复，不重开105组。
- 248条warnings包含退化统计警告与JUnit record_property格式警告。仅把预期退化在对应用例中显式断言并核未知值；未知警告继续可见。不全局静默，也不通过更改日期解析或数值算法提速。JUnit属性警告按所需报告格式单独核，不为了消警告改全套语义。
- 本批2跳过逐项保留：live smoke因Provider禁用；symlink因Windows权限。前者到S5精确授权后核；后者不能当通过，后续在具备能力的既有环境核符号链接路径隔离。不能为了绿色去掉环境检查。
- 当前没有本批运行的分支覆盖率或突变有效性度量，不能把77/106枚举及静态映射写成100%覆盖。优化变更只对受影响责任做少量oracle挑战：错一个预期数值、错绑一个原件或模拟一次真实保存失败，确认既有断言能阻断；优先用现有故障参数，不新建全库mutation框架。

## 6. 实施与最终回归门（待采用）

先A，再B/C；B与C分别按责任包核反例和代表正常链，收敛后一起冻结一次完整full-offline。所有7932既有节点/参数必须保留，AST断言及原独有业务oracle差异逐项审；新增只允许本优化或具名证据连接所需，不能把“文件变小”或“少测”计作收益。

有限样本性能前后同机器、同节点/输入/oracle、独立新目录、无并发整库；正常读写、索引、fsync、真实计算和错误路径全部保留。对比源码各自精确freeze，报告测量噪声，不设3—5分钟硬线。代码/作用域/权限/事务或保存一致性出现回归即回退该候选，不靠放松断言留住速度。

最终冻结后一次官方full-offline必须仍完整、无失败；比较总时长、慢文件、计数及材料体积，跳过分别解释。局部前后对照不能代签整库。若出现已知失败，按已有用户批准的具体早停边界保全并记录未完成，不自动扩成所有验收批的fail-fast政策。

本轮不建议直接全库并行：cfg、workspace/context、task_manager、注册表和若干全局monkeypatch依赖当前隔离方式；首先核隔离才能谈进程分片，不在同进程并发fixture或共享数据库。也不建议关闭fsync/索引、会话级共享可变engine、mock掉数值工具、减少fit方法、缩短超时来换速度。

若A证明B/C不是当前主要热点或收益不稳定，先提交测量结果调整方案；不自动扩至连接池、增量索引、跨请求缓存、算法更换或测试删减。这些均需新的讨论。

## 7. 本次产物与保全

[分析基线](../../tmp/tp02/preflight.json)、[输入材料SHA](../../tmp/tp02/input-digests.json)、[95例当前映射](../../tmp/tp02/historic-sample-mapping.json)、[证据连接审核](../../tmp/tp02/coverage-seam-review.json)。派生脚本tmp/tp02-analyze.py保留；首次节点归一化未处理JUnit测试类的方法，已在新目录修正并逐节点对齐，tmp/tp01原诊断保留。

本次只形成可审附件和唯一计划/验收/交接的当前链接，生产/测试源码变化0，新测试运行0，材料删除0，105审核重开0。全部历史原件、失败/RED、full/full2/full3、性能profile及具名缺口保留；没有开启Provider、远端MCP、服务或S4/S5。
