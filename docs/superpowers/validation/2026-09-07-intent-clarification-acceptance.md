# 需求对齐与必要澄清：验收矩阵

日期：2026-09-09｜版本：1.1｜状态：**IC0—IC3 已完成本地实现与 E1/E2 回归；IC4 的 E3 浏览器矩阵及 IC5/E4 真实 Provider 未执行**。

关联：[计划](../plans/2026-09-07-intent-clarification-plan.md)｜[设计](../specs/2026-09-07-intent-clarification-design.md)｜[诊断](../../audit/2026-09-07-intent-clarification-diagnosis.md)。诊断里的历史观察/模拟不计入下表通过数量。

## 1. 证据层级与测试原则

- E0：源码和原始会话只读核对，仅支持原因分析。
- E1：Provider 禁用的纯函数/合成夹具/模拟语义返回，证明宿主策略和边界。
- E2：隔离会话、真实 AgentLoop/工具/HTTP/SSE/持久化，模型使用脚本连接；证明应用集成，不证明真实模型自主路由质量。
- E3：真实本地浏览器操作 E2 应用，检查卡片、完成、刷新、恢复；仍不是真实 Provider 验收。
- E4：另行授权后的真实 Provider；精确冻结、串行记账、停止策略独立管理，本次不安排或消耗。

成功标准不能只是“未弹窗”。必须核对正确任务继续、具体语义得到处理、无错用历史回答、无错误结论升级。失败用例不要以 skip/xfail、删除反例或改成只断言非空来掩盖。

## 2. 可移植最小夹具

| 夹具 | 内容 | 判定所需差异 |
|---|---|---|
| F1 省钱卡综合请求 | 原始九指标和连续付费/影响目标；四张小合成表：购卡记录、券使用、前后订单、全期支付 | 有/无成本定义；有/无明确前后窗口；有/无对照；正常复购分母与续购分母 |
| F2 聚合留存 | day/retention 或按 cohort 的日龄留存矩阵，已知观测范围 | 明确 0 为真实值；明确 0 为未成熟；0 含义未知且会改变结果；有/无 cohort 人数权重 |
| F3 文件范围 | 两个同名有效文件，带不同 file_id/dataset/version | 点名歧义、明确选择、无关文件新增、已选文件替换 |
| F4 历史决定 | 同 session 的具体口径 resolved/open/skipped/cancelled/expired 记录 | 同义改写、否定/数值变化、跨 session、相关/无关版本变化 |
| F5 旧确认 | 旧 method_playbook 通用模板；旧具体窗口确认；未知来源确认；对应 event/task/checkpoint | 退役、保留/转换、不盲目批准、迁移幂等和历史可读 |
| F6 语义连接 | LLM 合法主方法+空 supporting；合法完整返回；超时；异常；空/坏 JSON/未知 ID | 路径可观测、最多既有调用预算、无隐式重试、空 supporting 的规则补充 |

原始会话和上传文件可能仅存在于本机，不作为 CI 或新分支验收的唯一依赖。测试中仅保留任务文本与合成数据，不复制真实明细、模型内部推理或敏感凭据进入 Git。

## 3. 必要提问与各入口 Q

| ID | 输入/触发 | 必须观察到的结果 | 最低证据/测试归属 |
|---|---|---|---|
| Q01 | F2，仅要求拟合观测内留存公式，口径已明确 | 无通用方法暂停；进入拟合计划 | E1，method_playbooks / question_need_detector |
| Q02 | F1，要求九项指标 | 不因指标多强迫只选一个；保留九项需求 | E1，question_need_detector / analysis_entry |
| Q03 | 要求描述性复购率，分母/窗口已明确 | 直接执行，不以 retention 类别审批 | E1，analysis_flow_controller |
| Q04 | 需要净收益但两种成本定义均合理、未提供答案 | 问具体成本边界及影响，不问是否采用某方法 | E1，策略及 interaction |
| Q05 | 同 Q04，但当前请求已给出成本边界 | 不重复问；实际采用明确边界 | E1，策略 |
| Q06 | F3 指代不唯一且影响范围 | 提供可区分文件选项；未选前不访问错误数据 | E1，multi_file_scope / analysis_entry |
| Q07 | 预测/因果/分类计算，已授权分析且必要输入明确 | 不因能力名称审批；数据/方法检查仍执行 | E1，controller / execution_control |
| Q08 | 技术工具失败，已有合法恢复方法 | 走现有恢复预算；不把“是否换工具”当必要业务确认 | E1，registry / tool_recovery |
| Q09 | 模型主动 ask：是否按留存方法继续 | 不产生 suspended；原 tool_call_id 获一次可理解响应；继续任务 | E2，interaction / loop / confirmation_runtime |
| Q10 | 模型主动 ask：真实未决分母 | 和自动候选采用同一判定；有效暂停、答案应用准确 | E2，confirmation_runtime |
| Q11 | 一次多问题：已有答案+方法审批+真实窗口缺口 | 前两项复用/降级，只询问真实缺口；每项答案归属明确 | E2，interaction / runtime |
| Q12 | 模型伪造 safe_default、dataset_ref 或“所有操作受阻” | 不信任自报字段；越界拒绝，真实缺口不得因此自动放行 | E1/E2，policy / runtime / scope |
| Q13 | D1—D7 留存数据；请求“解释 D7，并判断能否预测 D30；若不能说明缺失证据” | 直接发布 D7 的数据内描述和 D30 的证据边界；不得因 `forecast`、`D30` 或方法名产生确认 | E1/E2，method_playbooks / question_need_detector / analysis_entry |
| Q14 | 已明确“提出并检验至少两种竞争性假设”的数据分析请求 | 自动选择满足请求的内部路线；不得把 `trend`、`period_compare` 等技术路线选择交给用户；未决解释仍按证据状态输出 | E1/E2，method_playbooks / analysis_entry / loop |

## 4. 复用与恢复 R

| ID | 变化 | 预期 |
|---|---|---|
| R01 | 同一业务决定换措辞、换显示文案 | 复用有效答案；无新暂停 |
| R02 | 消息数量变化，业务范围不变 | 不因 messages:N 变化重复问 |
| R03 | 同方法但复购改为到期续购 | 不复用原分母；若新请求仍未定义则问具体差异 |
| R04 | 窗口 30 天改 7 天，或“包含成本”改“不包含成本” | 保留否定和数值差异；更新范围，不能沿用冲突答案 |
| R05 | 相关数据版本变化 vs 无关文件变化 | 前者重新验证适用性；后者不失效；不等于每次变化必问 |
| R06 | 相同文本来自另一 session | 不跨会话自动复用 |
| R07 | 重复提交同一 resume / 过期 version | 一次应用、一致终态；旧版本冲突受控 |
| R08 | resolved / skipped / cancelled / expired 的同类记录 | 仅合法 resolved 可复用；其他状态不批准计算口径 |
| R09 | 同时到达等价 open candidate | 复用同一个有效 open 记录，不产生重复任务/弹窗 |
| R10 | advisory/reused/rejected、正常暂停分别经过同步/流式/恢复入口 | 无 record 时不抛通用异常；无工具响应缺口、重复执行、空终态或死循环 |

最低 E1；R06—R10 必须提升到 E2。归属：`tests/test_confirmation_policy.py`、`test_confirmation_service.py`、`test_confirmation_runtime.py`、`test_confirmation_continuation.py`、`test_confirmation_session_api.py`；新覆盖文件名由 IC0 冻结。

## 5. 旧记录与投影 L

| ID | 场景 | 预期 |
|---|---|---|
| L01 | 恢复 F5 纯模板审批 | 审计可见地退役，不模拟用户批准；允许重新评估后继续 |
| L02 | 恢复真正的旧窗口/字段决定 | 保留或转换为等价候选；不因 type=method_confirmation 丢失 |
| L03 | 未识别来源/范围的旧记录 | 不盲目批准或删除；重新确认是否存在实质依赖 |
| L04 | 连续加载、刷新、重启 | 迁移幂等；pending、event、checkpoint、task、UI 一致 |
| L05 | 已有历史结果和确认事件 | 原结果/历史答案保留；不重写原始 event log |
| L06 | 新元数据由兼容旧代码读取，或代码回滚 | round-trip 无丢失；不支持版本时明确失败，不覆盖新事件 |

最低 E2；L04 包含 E3。归属：store/models/actions/runtime/continuation 与 Web 生命周期测试。所有操作作用于隔离夹具，禁止迁移两个原始会话。

## 6. 主目标、方法与计划覆盖 M

| ID | 请求 | 预期 |
|---|---|---|
| M01 | 原始省钱卡九指标+连续付费/影响目标 | 主线覆盖功能/效果与行为；九项各有步骤或具体缺口；不要求主方法只能是一个固定 ID |
| M02 | M01 改变“复购率”在列表中的位置 | 整体任务和覆盖不随词出现顺序改变 |
| M03 | “不要分析留存，只分析省钱卡收益” | 不被被否定的留存词接管 |
| M04 | “仅计算复购率，口径如下……” | 留存/复购方法仍可正确使用；不因修复 M01 禁用它 |
| M05 | 原始聚合留存公式拟合请求 | 实际拟合步骤、参数、误差、观测范围；不默认要求用户级事件或流失标签 |
| M06 | “拟合当前曲线，不预测 D30” | 否定外推被保留；不创建预测审批或输出 D30 数字 |
| M07 | “预测后续留存”，数据/验证条件充足与不充足两组 | 前者计算并按验证范围输出；后者说明缺口，用户同意不能填补证据 |
| M08 | 收益、趋势、纯咨询、数据操作、问候+分析等对照 | 原有合法意图仍可达；不把所有任务改成效果分析 |
| M09 | F1 缺少成本/对照，但描述性支付指标完整 | 完成可支持指标，对缺项精确说明；不把全部需求降为“数据不足” |
| M10 | F2 含 0/未成熟 cohort/权重歧义 | 明确已知时正确计算；未知且实质影响结果时具体澄清或标注可区分探索结果，不静默把 0 当缺失 |

最低 E1；M01、M05、M09、M10 至少一组 E2 真实工具数据计算。覆盖既有 method_playbooks、intent、intent_refinement、analysis_entry、analysis_flow_tools 测试；不得通过强制 mock 最终选择/最终计划来掩盖实际选择和计划构建错误。

## 7. 可观测性 O 与可信度 S

| ID | 场景 | 预期 |
|---|---|---|
| O01 | 合法 LLM 主方法、空 supporting | 主来源=LLM，辅助来源=规则；日志不声称超时/失败 |
| O02 | F6 各失败模式 | 有真实可区分原因与回退来源，不增加调用/重试或泄露凭据 |
| O03 | 必要/无关/复用/失效四种候选 | producer、disposition、范围摘要、reason、是否 suspended 一致 |
| O04 | 固定验收集统计 | 报告必要提问命中、不必要暂停、重复询问、覆盖遗漏；不外推生产频率 |
| S01 | 无对照的购卡前后变化 | 可描述差异，不升级为卡功能造成提升；确认不能放行因果结论 |
| S02 | 只观测 D1—D7 的描述性拟合 | 可给公式/误差，不能凭同意发布无依据 D30 数值；明确边界允许发布 |
| S03 | 跨 dataset/version/plan 的旧答案或证据 | 不错绑、不扩大访问范围、不升级当前验证状态 |
| S04 | 工具失败/无真实收据/未执行计划 | 不自报完成或已验证；取消审批不会取消执行/发布核对 |
| S05 | 所有 E1—E3 运行 | 真实 Provider initiated calls=0；辅助连接调用符合现有预算；任何越界调用立即失败 |
| S06 | 必要语义仍未解决但用户 skip/cancel 或模型反复问通用许可 | 无捏造答案；独立安全结果保留；现有预算约束终止重复循环 |

O 最低 E1；S 最低 E2。优先复用当前有效的 publication_synthesis、execution_control、artifact_publication_contracts、作用域、P7 安全反例；目标分支缺少时记录兼容用例，不静默引入整个其他专项。

## 8. 浏览器用例 B

| ID | 操作 | 页面和持久化 oracle |
|---|---|---|
| B01 | 上传 F2，提交拟合请求 | 无通用审批；拟合结果与真实工具相符，刷新后保留范围和误差 |
| B02 | 上传 F1，提交完整需求 | 无主方法许可卡片；明确九项覆盖/缺口，未把连续付费相关性写成因果 |
| B03 | 提交真正有成本/窗口歧义的请求，回答具体选项 | 一个相关问题；确认后使用正确口径；重复 resume 无副作用 |
| B04 | 将 B03 换措辞继续，再实质改变口径 | 前者复用；后者更新并在必要时问差异；不永久放行整个方法 |
| B05 | 恢复 F5，刷新/重启，再跳过真实语义问题 | 通用旧审批退役可追溯；真实问题不丢失；skip 不算批准 |
| B06 | 脚本模型发无关方法 ask 与真实语义 ask 两种调用 | 前者继续且工具响应闭合；后者正常悬挂；SSE 与刷新终态一致 |

E3 必须使用真实页面、实际 HTTP/SSE 和隔离会话，不用截图 mock 代替。B01/B02 的脚本连接不能当作真实 LLM 语义正确的证据；选择质量由 E1 的实际解析/回退和后续可选 E4 分别证明。

## 9. 执行命令与结果记录

以下为后续在合并后 `main` 上继续使用的入口。整合阶段已使用两个新的隔离 run-dir 执行定向集合；完整离线也使用新目录，未复用历史产物。

```powershell
.venv\Scripts\python.exe scripts/testing/run_regression.py full-offline tests/test_method_playbooks.py tests/test_question_need_detector.py tests/test_analysis_entry.py tests/test_confirmation_policy.py tests/test_confirmation_runtime.py tests/test_confirmation_continuation.py
.venv\Scripts\python.exe scripts/testing/run_regression.py full-offline
```

第一条只是起始定向集合，不替代矩阵中其他受影响模块和新增用例。全量必须明确收集 `tests`，不使用根目录裸 pytest 误收集 tmp。浏览器可复用 `scripts/testing/run_p7_browser_rehearsal.py` 的隔离/网络禁止模式；IC0 先核查目标分支是否存在，不复制其其他专项 oracle 或伪造本专题已通过。

每次执行记录：HEAD、相关源哈希、分支/dirty、用例 ID、fixture/脚本连接版本、E 等级、命令、开始/结束、结果、JUnit/trace/截图路径和哈希、Provider initiated 数量、已知局限。产物保存到新的受控 tmp/artifacts 子目录；需要提交哪些报告届时按授权指定。

| 阶段 | 状态 | 证据 |
|---|---|---|
| 本文规格检查 | completed | 文档状态已按实际实现和整合证据更新 |
| E1 / E2（IC0—IC3） | passed_local | `tmp/integration-20260909-target-intent`：301 passed；`vp-analysis-value@d6e4780` 的既有专项完整离线为 2569 tests、0 failures、1 skipped |
| 整合相关内容定向 | passed_local | `tmp/integration-20260909-target-content`：129 passed |
| 整合 full-offline | accepted_for_merge_with_environment_exception | 首次 2492 passed、56 failed、62 skipped：缺 Git 忽略夹具及 Windows 长路径；缩短路径并补齐夹具后为 2608 passed、1 failed、1 skipped，唯一失败为多复制清单外 `游戏C改版.xlsx`；用户接受当前结果并要求合入 `main`，本项不记作全绿 |
| E3 / IC4 | not_run | B01—B06 尚未在合并后源码上执行；后续在 `main` 继续 |
| E4 / IC5 | not_authorized / not_run | 未冻结或调用真实 Provider |

强制退出：矩阵全部通过或每个非适用项有基于范围的明确理由；不得用“没有弹窗”掩盖结果缺失。出现调用记账、数据归属、事件完整性或错误证据升级失败时，按计划停止依赖路径，离线修复后重新验证。
