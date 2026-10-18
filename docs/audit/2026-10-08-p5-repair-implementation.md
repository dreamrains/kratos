# P5批后修复实施与当前本地复验

日期：2026-10-08启动，2026-10-09继续。唯一计划仍为可信发布重建总计划。工作树C trust-rebuild，分支`codex/trust-rebuild-20260927`，HEAD `882df1c4c217e71320fdc43336d537851a3d721a`，实施保留dirty。供体b181646只读；不提交正式默认、部署或外部Git。

## 1. 当前状态

原真实批次executed_failed/not_accepted保持，133物理调用及791文件封存未改。本轮Provider调用0。新自然M01—M06需要重新精确冻结和授权。本收据的固定模型合同不证明自然质量；HTTP picker、可见图文、浏览器刷新与console未评估。

本轮已删除提示层重复分类责任，数据加载复用同一意图；原文需求保留，目标登记只完善真实工具/字段/版本。咨询与数据续问按宿主上下文权限分开；短继续只执行已登记未完成目标；风格退役范围明确。上传对象/版本沿Workspace事务、既有确认与原业务公式链实施；局部审核看完整答案只读事实背景，错误裁决不吞独立事实。导出文本只规范行尾，字节摘要仍精确。

## 2. 责任与规模审查

| 唯一责任 | 当前模块 | 删除/禁止的重复责任 |
| --- | --- | --- |
| 回合语义决策与恢复 | intent/llm_intent、loop | 提示及加载后第二次分类；确认响应登记新用户需求 |
| 原文、目标与版本 | publication.requirements、analysis_flow | 最终草案自报覆盖；旧目标改成新数据或新指标 |
| 数据命名/血缘事务 | Workspace | adapter直接散落修改内部字典 |
| 上传身份和票据补偿 | uploads | 文件名推版本；失败留下半替换票据 |
| 业务确认和恢复 | 既有ConfirmationStore/action；models.continuation_context | 放宽semantic参数对照；新授权队列/账本 |
| 快照、事实与审核 | runtime/service/audit | 下发后修改宿主投影；复制proof给审核；散文词表门 |

用户取消净增400行上限。`tmp/p5-repair-source-20261008-r4/preservation-and-size.json`逐文件核算核心、publication及全部既有helpers和本轮替代职责：相对P4候选净增576行，统一重建口径仍净减4931行。loop净增192、uploads净增163；新增代码承担恢复、原子事务、精确对象选择及逐项确认，未拆文件隐去增长。此净减数字不替代职责与行为审查。测试/文档增长另计。

## 3. 测试身份与原失败

- 完整离线r1：3399 passed/11 failed/2 skipped/17 warnings，原目录保留。九项审核请求因重复proof超过64KB；另有咨询fixture分类和原76工具清单。只读六字段审核投影和明确fixture协议修订后复验。
- 完整离线r2：3416 passed/5 failed/2 skipped/17 warnings、439.22秒，原目录保留。四项旧审核视图断言和首次加载版本revision断言；完整宿主来源/数学/原自然语句及reject控制未放宽。
- 定向219 passed；多对象候选歧义负例1 passed。对象→公式→实际值及重启、所有映射逐项确认、上传原子补偿、发布实际下发摘要和加载后一次分类均在当前回归内。
- 完整离线r3：3422 passed/2 skipped/17 warnings、442.05秒，0 failed；401清单摘要均未变。目录：`tmp/p5-repair-full-20261008-r3`；源/测试清单401文件，SHA256 `44ae9eaf90d1a80c4493b3dfdd0fe199240b699192c8969a1afdfce5fac0b2bd`。
- HTTP r1已停止：冻结头继承旧head/source摘要；保留`local-app-r1-rejection.json`，不计部分绿灯。服务PID11148及exec12366、控制exec1155已关闭，端口8781不再监听。
- HTTP新r2准备：原控制及47组/90回合未改，369源集合；freeze SHA256 `69d3c17006d50566a08e88814a4120ce01c94c36a1fdac934d65696978dacd37`。r3完整门已通过后执行90回合；前46组评估完成，末组CONTENT-B07因已有knowledge selector首次加载版本登记触发过严拒绝，控制缺answer KeyError。整轮failed_not_accepted保留，服务exec40149/PID7304与控制exec80926均关闭，独立stdout/stderr保留。

## 4. 原材料与尚未评估边界

791原manifest文件全部摘要一致，原ledger SHA256 `b99b19e50730ad6b5916809f78043ebaf1c9537e621e5c75989e196601c159c2`不变。M04第66草案复制的摘要等于实际下发摘要，宿主拒绝却要求另一摘要；已修正宿主刷新顺序，具体旧状态差量仍无完整trace，不能宣称完全重建。

旧ddb9daa/71e23d0原重放保持unassessed；旧M01—M06全部失败与50条hard oracle保留。当前协议通过后才形成新候选和完整新冻结。正式默认/外部Git仍各需授权。


## 5. 正常app反例：已有知识说明的数据示例目标

r2最后一组原固定协议将“表格与公式”登记为knowledge但有明确run_python selector；图表另为result。原工具load_data成功后，自动绑定首次加载版本复用执行目标接口，接口一律拒knowledge；控制随后KeyError。此故障在本地单元全集中未被组合覆盖，原90.json与失败均保留。

架构裁决沿已确认PRD：纯知识不需要数据执行；知识说明若已明确登记具体数据示例则有数据引用权限并须事实绑定/审核。执行目标接口只允许原knowledge既有selector完全相同的版本登记，不允许新增/改变selector或交付用途；未登记的概念问题仍不能升级数据执行。实际数据上下文判定包含原已登记selector，knowledge标签不构成审核豁免。未添加正文解析或场景专属生产分支。

新增原表格/公式/图表实际工具链及既有/新增知识目标正反三项回归。初次测试只audit enum错写available，实际reviewed；值/图/覆盖均通过，修订为已有枚举。当前完整离线r4进行中，401文件SHA256 `e4e689ab20eba958527a081faaaf1cf20bd196378bc4d45fbed5346fefb5af80`；此前r3仅验证其原源，不能代签新变更。

新HTTP r3准备保留原47场景/fixture/数学oracle，只将CONTENT-B07缺接受答案记为失败oracle而非控制异常。controller SHA256 `99785095828fb9fb1b916fccd8552e20c0b65855e1dfeaf381495276d46b6e39`，freeze SHA256 `b478fe3accefcbec08d8e984950095553a649b2d109f7ae78b60f13eb028ec59`。r4完整离线门通过后再完整执行。Provider0，视觉/自然仍未评估。


## 6. 全来源首次版本登记（2026-10-09继续）

版本所有权复查发现，多来源目标原先以target_data_identities是否非空判断完成；已有一个来源、另一个后加载时，后者不会自动登记首个版本。现在统一按selector全部来源集合与已登记集合核对，待所有来源可读时通过原目标接口原子补齐；已经登记的来源仍须字节/版本身份相同，旧来源变动直接拒绝，不能沿用旧授权。

原实际load-once用例扩展为全未加载、部分已加载、部分已加载但旧来源改变三种情形，仍只一次意图和一份原文需求。相关6项实际链测试通过，包含表格/公式/图和知识数据示例权限。完整r4在源码冻结不变期间停止为interrupted_not_accepted，原目录/exec25520保留，不计通过。新完整r5进行中，source/test401摘要 `f3855760ab0868922cbf6503c27d2666ff8ea00acdf3c008da1989f2b24d47df`。

HTTP r3仅准备未启动；旧目录保持。最新HTTP r4采用r5源，controller及原47场景不变，等待完整r5出口通过。规模仍净增576行，无新增生产分支或确认路径。


完整r5为3425 passed/2 failed/2 skipped/17 warnings、437.90秒，原失败保留。两失败均是同一纯概念SSE/导出用例的固定意图夹具给“什么是回归分析”误加orders selector；按新边界它是有数据目标而客户端只给咨询草案。仅在纯知识变体去除该错误selector，已有orders、正文/SSE/持久/导出原断言和新数据示例正反例保留，生产校验不变。相关11项通过。当前完整r6进行中，source/test401摘要 `f279f9ff12f99765fdd2ab927bc063f14c758efd353c283af05b39673f3aeebd`；最新HTTP r5准备待此门通过。未启动r3/r4准备目录不构成测试通过或失败。


## 7. 当前完整复验出口（2026-10-09）

完整r6：3427 passed/2 skipped/17 warnings、421.79秒，0 failed。401 source/test摘要均未变，JUnit SHA256 `3cdb0c61be594ec728f128f7e7a2ec2438f85b4a060a84015fabbfb2fe96cd08`。两skip为未授权live smoke和Windows不允许symlink创建；不计入已评估正例。

HTTP r5完整47组/90回合完成，failed_case_checks=0、forbidden_provider_transport=0、Provider initiated=0；fixture/独立oracle、369源集合和全部401 source/test摘要未变。freeze SHA256 `c77466d47f558bbf56b22e96a04bb655ad9e54de692b51cecbc2522f9d3be9a0`，原47组/90回合、controller `99785095828fb9fb1b916fccd8552e20c0b65855e1dfeaf381495276d46b6e39`，369源不变。service exec17937/PID2084、control exec31830、port8781，独立stdout/stderr在准备目录；health ok且Provider禁用。完整reconciled.json已核对，90份回合记录全部检查通过；CONTENT-B07原表格、公式、图检查均通过。service exec17937/PID2084已停止，8781无监听，控制exec31830正常退出0。机器收据`tmp/p5-repair-source-20261008-r6/final-receipt.json`保留全部会话、源摘要、独立日志、旧失败及证据边界。尚无新自然调用。


当前本地修复出口已完成。工作树仍为882df1c+dirty、暂存区为空，所有在途文件保留；source/test清单401、原真实材料791均精确复核。统一规模净增576行，重建口径净减4931行。原P5六场景failed不改，新的自然行为验收及必要视觉仍未评估；下一步形成可审查新候选、完整M01—M06冻结与精确批次授权，不续跑旧133次账本或复用47次余量。
