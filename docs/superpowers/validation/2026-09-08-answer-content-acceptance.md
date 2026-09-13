# 回复内容优化：验收矩阵与执行记录模板

日期：2026-09-14｜状态：AC01—AC39 已合入 `main`；最新 AC40/E4 已在 `main@fe83160` 完整执行，M01/M03/M05/M06 通过，M02/M04 失败，AC40 仍为 `executed_failed / not_accepted`；对应最小修复已提交为 `main@bed3b15` 并通过本地验收，新的 E4 尚未执行。

关联：[计划](../plans/2026-09-08-answer-content-optimization-plan.md)｜[设计](../specs/2026-09-08-answer-content-design.md)｜[表达规范](../specs/2026-09-08-answer-presentation-contract.md)｜[实施记录](../../audit/2026-09-08-answer-content-implementation-record.md)。历史 159 项绿灯仅为诊断背景；本次实际结果单独记录。

## 1. 用例与独立预期

下表为新增或扩展测试的具体输入/行为要求。CP0 将表中合成输入固化为版本化 fixture 与独立 expected；真实用户会话只读。不得从修复函数自己的输出生成 oracle。所有用例含正例和危险相邻负例；snapshot/source id 使用合成值。

### CP1：发布快照

| ID | 操作/输入 | 必须断言 | 建议测试落点 |
|---|---|---|---|
| AC01 | 第8轮预览只有 early，后追加 late 结果与 evidence，再终局 | 最终包含符合范围的 late、指纹变化；正文不能绑定旧包 | test_publication_synthesis.py |
| AC02 | 同 receipt id 修改 result hash/数值；另测只改限制或验证状态 | 各语义变更均改变 snapshot digest，不沿用旧 artifact | 同上 |
| AC03 | 原数据 v1 已验证，切换 v2，夹入其他会话同名数据 | 旧证据不为新版本背书；无跨会话引用 | 同上/现有 scope 测试 |
| AC04 | 同一最终候选重复回调、刷新、导出 | 唯一发布绑定，无重复来源说明，正文/hash/packet 对应 | test_artifact_publication_contracts.py |
| AC05 | 终局来源文件写失败或 save 失败 | 不发完整成功；已有独立结果/明确失败边界可恢复，不能无痕放行 | 同上 |
| AC06 | 同步与流式各走正常/修订/断流路径 | 校验前候选不作为正式答案发出；持久化早于正式 delta；终态恰好一次 | test_sse_publication_order.py |
| AC07 | P08 Python fallback 已算描述结果；无依据 D30；有效/孤立工具消息 | 保留合规结果和 D30 边界，仍拒无依据数值和孤立消息 | test_p08_boundary_finalization.py / test_p08_tool_message_integrity.py |

### CP2：内容提取与恢复

| ID | 操作/输入 | 必须断言 | 建议测试落点 |
|---|---|---|---|
| AC08 | Python stdout 前180字符是概览，尾部 `weighted_delta=0.00277` | 尾部可受控恢复、准确送入需要它的综合；不能只验证文件存在 | test_compact_preservation.py |
| AC09 | result 有收益/人数，replay 有代码/hash/timeout | 业务事实优先，执行元数据不占正文事实预算，审计仍保留 | test_publication_synthesis.py |
| AC10 | 12组，每组 name/count/revenue，要求全部分组 | 12组在完整可访问结果中逐一存在，组名不脱离数值；显式要求正文则正文全部覆盖 | 同上 |
| AC11 | 3候选拟合族、10观测点、残差、范围与未知零值 | 保留族比较和必需误差/范围；不能只 fits[0]，不自动确认零值语义 | 同上 |
| AC12 | 超 prompt/扫描预算，含很大单组和最后一个必答组 | 分页不截数字/单位；必答组可恢复；数量未知如实标注，遗漏清单闭合 | 同上 |
| AC13 | 详情 hash 不符、文件缺失、越界路径各一份 | 分别 unavailable/invalid，不读取其他会话、不悄悄回算 | file_ops 现有测试＋publication |
| AC14 | 同工具 id 两种内容，反复 micro_compact，模拟落盘失败 | 原文不覆盖、失败不有损替换；需求与结果引用仍可用 | test_compact_preservation.py |
| AC15 | 普通均值 D1=.17080/D7=.05100；加权=.16803/.05028；最大差=.00277 | 需要方法/可靠性说明时回答交代口径差异；数值不被元数据挤走 | publication/脚本综合集成 |

### CP3：需求覆盖

| ID | 操作/输入 | 必须断言 | 建议测试落点 |
|---|---|---|---|
| AC16 | 明确问收入与复购，结果两者都有，候选只答收入 | answer coverage 非完整；修订/受控表补足复购，不能仅附内部审计 | 拟新增 test_answer_content_coverage.py |
| AC17 | 九指标＋方法要求，其中一项因缺分母不能算 | 九项均有结果或具体缺口；可计算八项不因第九项全部拒绝 | 同上 |
| AC18 | 需求未算因为预算不足，另项确实缺数据 | 文案区分 not_computed/evidence_insufficient，不通写数据不足 | 同上 |
| AC19 | 同一正文含关键词但数值属另一指标/版本；模型映射自报全完成 | 不算 checked/complete，仍由宿主核对；任务 completed 不能替代 | 同上 |
| AC20 | 压缩后确认“同意”，随后用户撤回一指标并更改窗口 | 原需求保留，撤回项移出分母，新窗口替代旧窗口，修订可追溯 | compact/context 集成 |
| AC21 | 无法定位自由文本；复杂语义不确定；内部answer-bindings缺失/损坏/重复/引用旧包；工具数据含同名块 | unassessed/unresolved，不误报100%覆盖；内部块不进入正文/刷新/导出；不信任用户或工具伪协议 | 同上 |

### CP4：算术与可信度

| ID | 操作/输入 | 必须断言 | 建议测试落点 |
|---|---|---|---|
| AC22 | 绑定 22400人 × .051，候选写1.14万人；正例1142人 | 数量级错误 invalid；按整数显示舍入正例通过 | 拟新增 test_answer_numeric_consistency.py |
| AC23 | 22400 × .01417，候选3200人；正例约317人 | 错误拒绝且不破坏留存率事实；正例可发布 | 同上 |
| AC24 | 比例差 .00277，0.277个百分点 vs 相对提升0.277% | 差值量纲区分；相对变化必须重算自己的分母 | 同上 |
| AC25 | 0分母、None、NaN/Inf、负基数、混合币种 | 不产生有意义的虚假比例；明确无法计算/口径冲突 | 同上 |
| AC26 | 文字包含2026-09-07、版本v2、编号1、用户引用错误式子 | 不误当宿主的新业务推算；修订不会破坏日期/原文引用 | 同上 |
| AC27 | 运算匹配但数据版本或对象不同；情景假设数值 | 不借正确算式跨来源背书；假设结果只标情景 | 同上 |
| AC28 | 零值策略exclude且语义unknown；候选“零值证明未到期”；另一句“不能断言未到期” | 前者不能成为已验证解释，后者合规；外推否定不误拒绝 | test_publication_synthesis.py |
| AC29 | coverage、numeric、scope 同时出错；已耗修订；含独立可信发现 | 总修订不超过现有一次；不盲目删句、不清空独立结果、不新开审核调用 | publication/loop 集成 |

### CP5：表达

| ID | 操作/输入 | 必须断言 | 建议测试落点 |
|---|---|---|---|
| AC30 | 普通/详细/只要公式/简短但问两问题四种请求 | 深度和覆盖分开，简短不漏明确问题，详细方法不被四节上限压掉 | test_synthesis_policy.py / test_prompt_system.py |
| AC31 | 同证据切换业务、分析师、管理者；明确不要建议/图标 | 事实与边界一致，遵守显式偏好，不按身份猜事实 | 同上＋人工内容评分 |
| AC32 | 有待验证解释、无因果识别；要求建议 | 保留条件建议与区分证据；无行业评级/干预收益杜撰 | 同上＋publication 负例 |
| AC33 | 正确chart ref、全角wrapper、未知hash、歧义引用、其他会话图 | 正确引用就近呈现；明确识别的wrapper修复不删邻近内容；非法引用不嵌入 | 现有web/chart测试 |
| AC34 | 表格/公式/图在1440px电脑端页面；键盘操作详情 | 可读、不整体溢出、入口可达；图标不能是唯一状态语义 | 脚本模型真实浏览器；移动端另行规划 |
| AC35 | 图生成失败或不可用于当前结论 | 用同口径可信表或具体缺口，不捏造Mermaid备用图 | chart/publication 集成 |

### CP6：集成与证据

| ID | 操作/输入 | 必须断言 | 建议测试落点 |
|---|---|---|---|
| AC36 | 旧v1会话读取、新格式保存再载入、历史包>20、当前引用旧结果 | 旧正文不重写，新绑定round-trip完整，正文引用包可恢复，跨版本不借用 | state/report 集成 |
| AC37 | 答案→刷新→Markdown及当前支持的其他导出→实际打开文件 | 同一正文与来源绑定，图的静态替代/链接明确；不能只测按钮点击 | 脚本模型真实浏览器 |
| AC38 | 固定合成小中大结果，已有上下文预算，记录调用数 | 正常路径新增Provider调用为0，超限走详情；无无界扫描/整库复制 | 离线性能与调用守卫 |
| AC39 | CP1—CP5改完，当前full-offline及全部40项记录 | 当前检出检查通过，skip逐项解释；不以159项历史通过替代 | run_regression.py full-offline |
| AC40 | 授权后新真实批次：P08 M01—M06＋冻结内容样本 | 账本/身份闭合，原文和截图可查，批次内不修不重跑，内容独立评分 | 本次真实 Provider 批次已执行，状态 `executed_failed` |

## 2. 内容质量指标与门槛

| 指标 | 分母/定义 | 门槛 |
|---|---|---|
| 必答项响应覆盖率 | fixture独立列出的有效用户要求；结果或具体缺口计入 | 全部指定验收样本100%，并分报answered与缺口 |
| 必保事实保留率 | 独立标注为解释必需的事实组；正文或明确允许的完整可访问表中存在 | 100%；文件存在但入口不可达不计 |
| 省略可追溯率 | 未被选择的候选组，含扫描不完整 | 所有已知项可定位；未知数量必须披露，不虚报100%全量扫描 |
| 核心数字一致性 | 样本中所有核心数字人工标注，再核对机器绑定范围 | 零已知错误；checked/unassessed单列，不把未知算通过 |
| 无依据主张 | 行业评级、因果、预测、零值解释、错误显著性 | 指定负例不发布为确定结论 |
| 图文及导出一致性 | 正文图表引用、刷新、实际导出文件 | 相同来源/版本，正确可达 |

每份内容样本另按0/1/2评分：需求覆盖、口径方法、有效解释、边界准确、阅读层次。0=缺失/错误；1=有但不够明确；2=完整清楚。任何核心事实错误或必答遗漏直接不通过，不能用排版高分抵消；所有维度至少1，覆盖和边界须2，总分至少8/10。评分需附定位与理由，不能只给总分。

字符数/标题数/emoji数只做对照统计。禁止要求达到5月回答长度、恢复未经支持的建议或按短回答自动扣分。

## 3. 三类对照样本

1. 合成固定结果：用于上述数值、覆盖与渲染断言，适合离线脚本模型，不涉及用户数据。
2. 保存会话只读评审：`9959216b6a4a`、`9810fe7bacf6`、`c9cd1b4ce78f`及诊断中的5月样本。仅比较原文并提取问题，不启动/恢复真实会话，不把旧数值全当oracle。
3. 新真实质量验证：重新核对输入文件哈希和完整提示、确认回答、模型/配置/源码/启动进程身份；不同零值或窗口政策必须单独标明。相同文件名不能证明完全可比。先完成零调用准备，待明确授权再执行。

## 4. 证据等级与运行方式

- E1：纯函数、合成数据、单元反例。
- E2：完整离线与集成，真实 Provider 被禁止；脚本模型只证明编排。
- E3：本地真实浏览器＋脚本模型，验证页面/SSE/刷新/导出，不能证明自然分析质量。
- E4：真实浏览器＋真实 Provider，独立冻结与授权，账本完整；不能推断生产/部署通过。

开发时先运行本阶段命名测试。全部源码完成后使用现有 `.venv\Scripts\python.exe scripts\testing\run_regression.py full-offline`；按现有脚本隔离目录和禁网机制执行，不能写入真实 sessions/workspace。代码/依赖/fixture改变使结果失效时才重跑对应范围。

真实调用延用P08矩阵规则：一次冻结全部场景，普通单项失败记录后继续，只有系统性全局异常停止；不能在批次内修代码、换模型、增预算或隐式重试。历史授权与未用额度不继承。

## 5. 阶段执行记录模板

每阶段追加记录，历史结果不覆盖。总状态只在计划的CP表维护。

```text
阶段/日期：
目标checkout、branch、HEAD、dirty及相关源hash：
新增/变更文件（逐项）：
AC编号、独立fixture/oracle路径与hash：
RED反例与预期失败：
实现决策及与本设计差异：
实际命令、退出码、passed/failed/skipped：
问题状态：planned/passed/failed/blocked/not_run：
证据等级E1/E2/E3/E4及文件路径：
旧会话/并行工作保护核对：
已知限制、未评估项、未满足的退出门槛：
Provider授权引用、计数或明确0调用：
是否可进入下一阶段、回退范围：
```

## 6. 本次实施验收记录

状态含义：`passed_local` 表示对应行为已有 E1/E2 自动化或 E3 本地真实浏览器证据；`passed_compatible` 表示本次实现与既有专项回归共同证明；`not_run_authorization_required` 表示实现已准备但外部验证未获授权。它们都不等于生产部署通过。

| AC | 状态 | 当前证据 |
|---|---|---|
| AC01 | passed_local | 最终包在晚到 receipt/evidence 后重建，preview/final 快照分离 |
| AC02 | passed_local | 值、限制、数据版本、验证状态改变均改变语义 digest |
| AC03 | passed_local | packet 绑定当前 session、dataset contract 与版本，不跨会话查找 |
| AC04 | passed_local | 同快照同正文幂等；修订正文生成新 binding/supersedes；消息投影保留精确绑定 |
| AC05 | passed_local | artifact 写失败不提交 packet；回复前保存失败返回明确未完成状态 |
| AC06 | passed_local | 质量门前候选不进入公开投影，流式正式 delta 在持久化之后 |
| AC07 | passed_compatible | P08 边界终局、有效工具消息与孤立消息回归随 full-offline 通过 |
| AC08 | passed_local | stdout 尾部业务事实保留，detail_ref 与 compact 引用可恢复 |
| AC09 | passed_local | 业务事实优先于 replay/hash 等审计元数据，完整详情仍持久化 |
| AC10 | passed_local | 12 组保持完整和自然顺序；六来源浏览器场景每来源公平保留 7 个事实组 |
| AC11 | passed_local | 曲线族、实际/拟合序列、残差与范围以完整 FactGroup 保留；零值语义仍受既有边界门约束 |
| AC12 | passed_local | 扫描上限、未知数量、整组省略和必答大组 detail_required 均显式披露 |
| AC13 | passed_local | 同会话路径、扩展名与 SHA-256 校验；缺失、越界、hash 不符失败关闭 |
| AC14 | passed_local | publication/detail 引用进入 compact 附录；既有有损压缩失败保护通过 |
| AC15 | passed_local | 普通/加权/最大差业务行优先保留，方法说明可从同一详情恢复 |
| AC16 | passed_local | 两个明确指标不能由一个数值伪覆盖 |
| AC17 | passed_local | 九项需求允许八项 answered 与一项具体缺口并存 |
| AC18 | passed_local | `not_computed` 与 `evidence_insufficient` 分开呈现 |
| AC19 | passed_local | unknown fact、错误来源/版本及模型自报不能取得宿主 checked 状态 |
| AC20 | passed_local | 需求原句、撤回和窗口替换持久化并递增 revision；compact 保留引用 |
| AC21 | passed_local | terminal `answer-bindings.v1` 受限解析；损坏、重复、旧 digest、未知引用均不受信，内部块不进入正文 |
| AC22 | passed_local | 22400×5.1% 的十倍错误被拒，约 1142 人通过 |
| AC23 | passed_local | 22400×1.417% 的 3200 错误被拒，约 317 人通过 |
| AC24 | passed_local | percentage point 与 relative percent 使用不同运算和单位 |
| AC25 | passed_local | 零分母、None、NaN/Inf、负基数、混合单位失败关闭 |
| AC26 | passed_local | 日期、版本、编号与明确纠错引文不被误认作新计算 |
| AC27 | passed_local | 跨来源/版本操作数被拒；情景量值必须带 scenario |
| AC28 | passed_compatible | 未知零值语义不能支持“未到期”断言，合规否定与边界回归通过 |
| AC29 | passed_local | coverage/numeric/scope 问题合并返回并共用既有一次修订机会 |
| AC30 | passed_local | 简短/标准/详细策略与需求覆盖分离；明确多问题不因 briefness 丢失 |
| AC31 | passed_compatible | 显式呈现偏好进入 prompt；既有多受众事实边界回归随 full-offline 通过 |
| AC32 | passed_compatible | 条件建议、无因果边界及禁止无依据主张的既有回归通过 |
| AC33 | passed_local | 全角 wrapper 仅定向修复；歧义、缺失、异会话图表不嵌入；内嵌图不重复列入补充图表 |
| AC34 | passed_local | E3 场景 B07：1440×900 下表格、KaTeX、单个 Plotly 图与备用链接可见，文档宽度=视口宽度，无整页横向溢出；刷新后保持 |
| AC35 | passed_compatible | 数据 Mermaid 失败回退被阻止；既有 chart/report 降级与可信表路径回归通过 |
| AC36 | passed_local | 新字段 round-trip、旧状态缺省读取、历史回复按其 binding/artifact 恢复 |
| AC37 | passed_local | E3 场景 B03：刷新保留正文，实际 MD 导出包含同一 packet/snapshot/answer hash 与六来源 |
| AC38 | passed_local | 固定小中大 fixture，prompt 小于 65k；正常路径新增 Provider 调用 0，超限转 detail_ref |
| AC39 | passed_local | `tmp/r6`：`2585 passed, 1 skipped, 16 warnings`，退出码 0 |
| AC40 | executed_failed / not_accepted | 最新 `tmp/p08-real-provider-20260914-ae8a5f4-r1` 完整复验：74 started / 74 dispatched。M01/M03 通过；M02 边界标题误拒，M04 计划启动死锁，M05 总额缺失、CV 算术和无依据来源解释失败，M06 的确认与结果分类通过但仍有无依据来源/总体波动表述。完整内容门槛未通过。 |

AC40 失败项在 `main@13c129a` 完成本地修复：可恢复 fallback 继续进入下一模型轮且 SSE 工具事件保持配对；纯表达回合只在当前数据身份与已接受快照一致时复用发布绑定；未知金额单位不能被身份表达改写成币种，混合已发生/未来日期不能笼统称为未来；非有限数在 SSE 中转为严格 JSON `null`；空图表引用显示明确缺失提示。隔离回归为内容/Web 208 passed、最终聚焦 173 passed；修复后的 E3 结果见下文。这些证据不把 AC40 的真实 Provider 批次改为通过。

定向命令覆盖新增四个 AC 测试文件及关键发布、导出、渲染、质量门和预算回归，结果 `129 passed`。完整离线命令为：

```powershell
..\..\.venv\Scripts\python.exe scripts/testing/run_regression.py full-offline --run-dir tmp/r6
```

唯一 skip 是需要 `GOLDEN_LIVE_SMOKE=1` 的真实 Provider agent smoke；本次故意保持 Provider 禁用。E3 使用普通 Flask/SSE/AgentLoop/工具/持久化路径，只替换模型传输；B03 会话 `b2306f8ccffb`、B07 会话 `944d1f86cbce`，各自 `runtime.jsonl` 均为 0 条 `forbidden_provider_transport`，说明没有尝试越过禁用边界。

合并后追加 E3 证据：`main@be5ee9a` 的隔离目录 `tmp/main-ic4-browser-20260909-be5ee9a`。CONTENT-B03 会话 `c2c77b29d01e` 保留 `src_1`—`src_6` 及全部金额事实，实际生成 9380 字节的 Markdown 对话导出和 9150 字节的同快照发布报告；CONTENT-B07 会话 `a5ccf75b6f20` 在 1440×900 下显示真实表格、KaTeX 公式、Plotly 图表及备用链接，无可见整页横向溢出。同批 `runtime.jsonl` 记录 `provider_enabled=false`、`forbidden_provider_transport=0`，因此真实 Provider initiated calls=0。

追加 E4 证据：`main@1516337`、冻结 SHA-256 `c0bd787f64e2c7b8f05b2026db0a73ffa1336c9cb3b6d6f44ff2caca16a6c46`，模型 `openai/deepseek-v4-flash`。AC40 内容样本对应 M03/M05/M06：M03 的六来源两日金额、绝对/相对变化和记录数在正文及 4914 字节 Markdown 中完整，但 run_state 为 failed、fallback 未收敛且 Workbench 无 verified；M05 的 12 笔/120 在六类身份中保留，但“大白话”把未声明币种升级为“块钱”，核心单位一致性失败；M06 将 answered、not_computed、evidence_insufficient 分开，但页面显示原始 `[[chart:]]`。因此 AC40 不能通过。账本与会话原文保存在该隔离目录；证据只到本地真实浏览器＋真实 Provider，不代表生产。

修复后追加 E4 证据（2026-09-12）：`main@3873ff99301f47023e6da422f97316bbf345684a`、冻结 SHA-256 `7156c9e115f9f6451249396bdb28e7dd970e1d81d2f5c78a15a45777a8827f44`、模型 `openai/deepseek-v4-flash`、账本 80 started / 80 dispatched。M03 会话 `2fc39f5f2a14` 的六来源正文、刷新、14994 字节 Markdown 和发布报告全部保留逐来源金额/变化/记录数，证明内容裁剪问题已关闭；但压缩上下文在 `_auto_save()` 处因 `workspace_scope=None` 返回 500，完整场景仍失败。M05 会话 `76e0f71fa8ff` 六种表达均保持 12/120、范围、限制、未知单位和证据等级，9377 字节 Markdown 与刷新一致，单位漂移已关闭。M06 会话 `3c9b81654363` 将总金额 120、未计算净收益和证据不足明确分开，刷新与 16608 字节 Markdown 一致，原始 chart 标记未再出现。批次新增暴露：M02 的合规 D7/D30 边界被发布门拒绝；M04 正文虽正确标记 v1 关系失效，Workbench 却仍把 v1 旧结论列为 verified。因此 AC40 仍不能通过；详细错误、会话与账本见整合记录第 9 节。

R8 失败项本地修复证据（2026-09-12）：`main@d9164fa`。相关回归 135 passed；full-offline 为 2620 passed、1 skipped、16 warnings。Provider-disabled 内置浏览器目录 `tmp/repair-browser-20260912-r9` 中，M02 边界回答刷新保持，M03 六来源回答后压缩保存返回 200；对真实 M04 会话 `29e4536464f3` 的持久化状态只读重放后，Workbench 当前 verified 仅保留 4 条 v2 结论，v1 假设为 stale 历史。真实 Provider initiated calls=0；这些证据说明三个已知实现缺口在本地关闭，但不把 AC40/E4 改写为通过。

R10 E4 证据（2026-09-13）：`main@dc44382f873c2842d77307d7c8075bbd1e5f6233`、冻结 SHA-256 `087974003fdb023e64fc86aec4f4c39a8431d89ecdbcb70832c039ea4c79e451`、模型 `openai/deepseek-v4-flash`、账本 78 started / 78 dispatched。M03 会话 `082344612717` 的六来源正文、刷新、5877 字节 Markdown、2668 字节发布报告及压缩后内容均完整，但将 2026-09-01→09-02 错误描述为“同比”；M02 的无数值 D30 假设边界被误拒；M06 的成本范围被误标为方法确认，确认 records 为空。M01/M04/M05 通过不能覆盖这些硬失败，AC40 仍不通过。

对应本地修复证据（2026-09-13）：`main@16d2257`。发布门允许无数值的非预测假设边界、继续拒绝未观测率；显式相邻日期的“同比”进入一次修订；宿主恢复被误标的成本/时间/分母业务口径且不扩大到真正的方法许可。隔离回归 152 passed 与 126 passed；full-offline 为 2626 passed、1 skipped、0 failures。Provider-disabled 内置浏览器 `tmp/repair-browser-20260913-r10` 中，B02 负例单次修订后 completed；CONTENT-B03 的刷新、压缩和 9380 字节 Markdown 保留六来源金额/变化/日期/记录数；成本口径一次暂停恢复，方法许可不暂停；Provider initiated calls=0。该证据不把 AC40/E4 改写为通过。

R11 E4 证据（2026-09-13）：`main@fe831601b7adef52a831317adaf93c2aeba760ba`、冻结 SHA-256 `c41c6064dac6887339512874705097e9f8d90087b0c73886c565e9b60309d7e0`、模型 `openai/deepseek-v4-flash`、账本 89 started / 89 dispatched。M03 的六来源 10→11 至 60→66、合计 210→231、记录数、`日环比`、刷新、压缩和 5523 字节 Markdown 一致；M05 六种表达保持 12/120、日期、未知单位与证据等级；M06 将总额 120、未计算促销增量/成本/净收益和证据不足分开。M02 仍误拒无数值 D30 边界；M04 虽正确叙述 v1/v2，但持久化结构化证据和竞争假设为空。因此 AC40 仍不通过。

R11 失败项本地修复证据（2026-09-14 收口）：`main@bed3b15`。相关隔离回归为 131 passed 与 80 passed；full-offline 为 2630 passed、1 skipped、16 warnings。Provider-disabled 内置浏览器目录 `tmp/repair-browser-20260913-r11` 中，B02/B02-NEG 完成且仍拒绝无依据 5% 预测；B04 形成 3 条 evidence records、4 个 plan-scoped hypothesis sets、8 条 receipts，版本变化后旧证据进入 exclusions。`runtime.jsonl` 为 `provider_enabled=false`、`forbidden_provider_transport=0`，真实 Provider initiated calls=0。该证据不把 AC40/E4 改写为通过。

R14 E4 证据（2026-09-14）：`main@ae8a5f40f6c7bf9fa5572bdcea2d92cf1ed59cfc`、冻结 SHA-256 `b4826cb582abd868f5db90418932c5674ea49790d668821e137a77e5fe5a0cce`、模型 `openai/deepseek-v4-flash`、账本 74 started / 74 dispatched。M03 六来源内容、总计与压缩/刷新/导出完整；M05 六轮保留 12 条、日期、未知单位与证据等级，但均未给出总额 120，并出现 `mean=10` 却称 CV 分母为 0、以及样例/账本来源推断；M06 确认和结果分类正确，但含无依据来源/总体波动解释。M02/M04 另有确定性运行时失败，AC40 仍不通过。M05 首轮提示未明确要求求和，与“六轮总额 120”硬 oracle 不完全对齐，下一冻结应明确请求订单数和总额，不能降低 oracle 或把本轮算通过。

R14 失败项本地修复证据：`main@6d6f7e0fc2e1090df9e64b1b052b466e6060e7a9`。发布门修复边界标题、CV 分母和恒定样本语义；Stage3C0B 计划投影后启动唯一 ready 任务、证据完成后推进、全部终态后释放 scope。隔离回归 324 passed 与 80 passed；full-offline 2637 passed、1 skipped；提交后内置浏览器 `tmp/repair-browser-20260914-r15` 的 B02/B04 completed，控制台 0 error/warning，Provider initiated calls=0。新的 AC40/E4 尚未冻结或授权。

## 7. 本次文档校验记录

2026-09-08：本文件仍定义 40 个唯一 AC 编号；实现记录、差距关闭审计、设计、呈现规范与交接已按最终代码和用户确认的电脑端范围同步。AC01—AC39 的本地结论与 AC40 的外部授权边界分开记录，不以离线或脚本模型结果冒充真实 Provider 内容质量。

2026-09-10：`tmp/repair-browser-20260910-r2` 的页面与 API 返回 200；当时把通用 Playwright 模块加载失败误记为内置驱动不可用。改用已安装 Browser 插件的内置客户端后，在 `main@176f5f2`、`tmp/repair-browser-20260910-r3` 完成联合 E3：CONTENT-B03 会话 `2cc0a85c9d1f` 的刷新正文、9380 字节 Markdown 和 9150 字节发布报告均保留 `src_1`—`src_6`、金额与来源；CONTENT-B07 会话 `51fe66986d44` 渲染表格、KaTeX、Plotly 和备用链接，741×805 视口无整页横向溢出。B01 的五种表达保留 120/12、范围和证据等级；浏览器控制台无 JSON 解析错误。`runtime.jsonl` 为 `provider_enabled=false`、`forbidden_provider_transport=0`，真实 Provider initiated calls=0。本次只补齐 E3，不代表 AC40/E4、生产或部署通过。

2026-09-14：最新真实批次和修复后 E3 已分别记入上文；文件继续保留 AC01—AC40 的既有编号，没有增加新的验收框架、探针、模型审核调用或重复账本。新的 AC40/E4 仍须单独冻结和授权。
