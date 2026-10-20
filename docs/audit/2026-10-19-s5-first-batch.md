# S5第一批自然验收：完整性停止

更新：2026-10-19，Asia/Shanghai。唯一实施计划仍为总计划§10；本页为本批收据及离线诊断，不另设实施计划。结论：第一批未完整执行且不通过，连续完整通过数为0。未启动第二批，未重试/续跑本批，未推送，未删除C。

## 精确候选、授权和路线

- 执行候选：D:/Project/Daily/data-agent，main@2b7349448f9de6fad47923f6c21c53cea08a2201。执行期间680项跟踪候选、426/407/431源码映射及.env原字节均核同；生产、测试、资产、输入、提示、oracle和配置未改。
- 批次：tmp/s5a01，端口8899；冻结SHA256为4ba461341feb4c9bcd2d5bc517fc73ff094ea6bf5f6ae3ad70e5b50052bb042d。13原CSV、20原提示、3恢复输入和独立判据保持。
- 用户直接授权本批完整M01—M06，共享最多400次物理调用，无金额上限；不重试、不回退、不续跑、不自动加额，第二批另行授权，远端MCP禁用。原文及授权映射保存在artifacts/mt10/authorization-granted.json。
- 用户允许单次输出提高到128K；该精确候选的既有launcher硬编码65536，提升需修改代码并改变候选。本批采用授权原清单的65536，未使用可选提升许可；能力配置仍为保守共享上下文1000000、模型输出能力393216。没有修改.env或通过运行时替换常量绕过冻结。
- 模型openai/deepseek-flash，端点https://api.deepseek.com；72个响应的model字段均为deepseek-flash。全部真实请求max_tokens=65536、num_retries=0；41个stop、31个tool_calls，length终结为0。提高输出上限不能由本批证据解释为修复这些失败的方法。
- 冻结控制路线为local_http_api，使用既有run_p08_real_matrix.py与run_p08_http_matrix.py，真实Provider、正常AgentLoop、上传票据、SSE、公开API和持久化均经正常应用路径。没有执行浏览器点击/显示/刷新；这些本批视觉项unassessed。原S4视觉收据按原身份保留，不能签成本批浏览器通过。本批没有重新核定当前浏览器可用性，不能以历史自动化限制宣称当前浏览器不可用。

普通沙箱只读访问本机端口曾被WinError10013拒绝；同一服务通过已批准的elevated exec只读核定，无服务重启、端口/路线更换或模型重试。该控制宿主限制不算产品或Provider故障。

## 实际执行与停止

服务exec-session 35951，服务PID15872、父wrapper PID29488；driver exec-session 27256，退出码1。stdout/stderr及进程收据均在artifacts/mt10。首个Provider请求为06:32:50，最后一个于06:48:58闭合；调用跨度967.600秒。driver约06:49:02完成停止记录。

| 场景/轮次 | 实际终态与判据 |
| --- | --- |
| M01/1 p值咨询 | completed；咨询正文可读，无数据工具或当前数据结论 |
| M01/2 留存方案咨询 | completed；字段、步骤、限制实际交付，无上传要求阻断咨询 |
| M01/3 销售订单 | completed，但内容硬门失败：12条/12天有交付，合计120未作为完整已验证事实交付；正文保留native_unsupported、内部claim/拒绝说明并加入8周、每组30条等原需求没有的强制行动阈值 |
| M01/4 七日窗口 | failed，通知为Repeated run_python failure。参数schema/scope拒绝后触发原execution_guard；模型在正常Loop内重复调用工具，不是SDK传输重试或场景重跑。完整金额/成本/净贡献/订单对比交付不足，用户原AND行动规则被添加条件、改动阈值；读取公开投影时触发既有driver全局停止 |
| M02—M06 | blocked_not_started，未启动；不是已运行失败，也不作自然能力推断 |

会话66053f8c290e，四个不同turn_id均各有一个turn_start和一个turn_end，终态依次为completed/completed/completed/failed，均与当时durable run state匹配。M01/3的普通正文问题出现后，driver确实继续了第四轮；并非发现第一个内容错误就停止整批。

随后_snapshot抛出public projection differs from accepted answer，driver按冻结实现将RuntimeError标为global_stop，并将M02—M06列为未启动。服务在核对PID、父PID和命令后关闭，8899无监听。没有续跑或补跑，剩余328次不能自动转为新批次额度。

“global_stop”是本批控制器的停止分类，不等于已经证明所有新会话或整服务都会失败。已证实的产品影响范围是M01同一会话的历史展开；既有driver把这类会话内投影不一致归为整批停止，范围是否过宽需在后续控制策略审核中明确，不能事后修改本批规则或将其拼成完整运行。

## 调用核算与原件

唯一Provider账本为tmp/s5a01/provider-calls.jsonl：started72、dispatched72、completed36、stream_exhausted36；failed/denied/stream_failed/gate_fault/在途均为0。所有72组原请求/原响应均核对账本绑定SHA。单次实际闭合最长98.654秒；没有触发120秒请求截止。远端MCP调用0。

72个响应均有usage，原响应报告合计prompt_tokens=4369469、completion_tokens=228472、total_tokens=4597941；这些是Provider报告值，不推算费用或另设金额上限。完整账本及usage核算见request-response-reconciliation.json。

停止现场362个文件、44128785字节已封存为artifacts/mt10/s5a01-evidence.zip，逐文件解压回读核SHA。归档SHA256：f57dc137235aba18302f14cdcb34dcb5e112d3a9fa821ed4d7260a4c4c3d9440。原freeze字节和13CSV另在freeze-original.json、original-fixtures；原tmp未删除、未改写。stopped-run-manifest.json与stopped-batch-result.json是完整清单和停止收据。

## 离线核验和证据边界

在网络及原批次写入拒绝下，直接运行既有public_messages读取已封存conversation/transcripts：47条压缩后canonical消息展开为749条公开消息，含31条user；第三轮同一answer_id出现5次，每份正文、content SHA和答案原件SHA均一致。第一、二、四轮答案各1次。原件没有被篡改，故障是公开历史重复，已离线复现native driver要求的唯一对应关系失败。第四轮失败GET响应体未被driver另存；offline-public-messages.json是明确标注的离线冷读复现，不冒称当时HTTP响应原字节。

初步责任定位为自动/重复压缩归档的重叠展开路径（session/public_messages.py::_expanded_public_history，当前以完整消息字典相等推断重叠）。重复现象已确认；具体哪一处消息/归档边界变化破坏重叠仍需离线RED定位，不能仅在显示末端按answer_id去重掩盖用户/工具历史重复。

既有p08_scenario_audit.py也原样运行并保留native-audit.json，返回failed。其中另有已核的观察器兼容问题：它将含整数turn的current_publication_snapshot也算成一次回合，误报前三轮各2条；旧scenario发现未识别这次咨询开头及压缩后的会话，sessions为空。真实SSE四轮各单终态的原证据仍成立；不能把该误报称为真实SSE重复，也不能把空sessions当成内容通过。没有修改该观察器或重开105组退役审核。

按验收§6对四份完整AcceptedAnswer正文单独评分（顺序为需求覆盖/口径方法/有效解释/边界准确/阅读层次）：

| 轮次 | 分数 | 判断依据 |
| --- | --- | --- |
| M01/1 | 2/2/2/2/2，10/10 | p值定义、误读、效应量/区间、假设/多重比较与示例边界清楚；条件性下一步不阻断当前咨询 |
| M01/2 | 2/2/2/2/2，10/10 | 字段、cohort分母/成熟度、分层/设计、方法及限制完整；无当前留存数值或已计算宣称 |
| M01/3 | 0/1/1/0/0，2/10 | 必答金额合计缺失；未授权阈值进入行动门；拒绝/内部标识和重复限制冲淡可读事实 |
| M01/4 | 0/1/1/0/0，2/10 | 完整四指标两窗口交付不足；原两条件规则被增加条件/改阈值；旧来源及内部拒绝说明混入正文 |

评分不能抵消硬门失败，亦不代表M01整组通过。四份正文可从accepted-answer-bodies直接查看，并与原答案content SHA核同；这些派生Markdown未作为新的浏览器或实际打开证据。

## 当前剩余事项

回到既有接口与生命周期设计关口：先用当前原件离线定位重复压缩/历史展开唯一性；核对窗口方法声明、公开工具参数、run_python业务scope、可发布测量适配与片段claim绑定；再审核正文的原需求覆盖、行动规则保留及driver/观察器对场景失败与整批停止的分级。当前没有修产品、改判据或自动放宽为普通失败继续。

若需要改变停止分级或采用浏览器/组合控制路线，先讨论并形成精确新清单；不能重启tmp/s5a01。源码修复后重验受影响正常app/保存/压缩/精确导出路径，并按S4出口跑当前候选完整离线回归；再冻结新自然候选与运行身份、重新申请授权。原第二批授权仍为空，不能用本批剩余额度自动运行。

S4本地有限签收和7953/0/2历史完整回归保持其原证据层级，不升级为自然通过。原180仍118完整/62局部/0待审；105关闭；F5原件、D历史清理缺口、65个未定位旧引用、Windows symlink和性能未核保持。A/B/C仍未批准未实施。C保全和原HEAD/索引/228项未在本轮操作。
