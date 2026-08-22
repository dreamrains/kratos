# Data Agent V2 Slice 5C6：验收合同重置与发布加速

- **日期**：2026-08-22
- **状态**：Proposed；供新会话核查后实施
- **分支**：`codex/data-agent-v2`
- **当前 HEAD**：`f184dfd3cc3e7ef2b9a66fe687dd05a9abb7a179`
- **当前 source digest**：`sha256:2dbb829eefb47652556222dfc055faa64a97b8fb0950e50d7d6518e675181fba`
- **上位设计**：`docs/superpowers/specs/2026-08-13-data-agent-v2-architecture-design.md`
- **直接前序**：5C5X、5C5Y、5C5Z、5C5AA

## 1. 目标

停止用真实 Provider 逐次发现验收合同，建立一个有限、可执行、可烧尽的发布路径，使 V2 尽快成为可替换旧入口的发布候选。

本切片不是“放宽测试让当前结果通过”。它修复四个共享根因：

1. 把 Provider 输出逐字段一致错误地当成产品稳定性；
2. 把技术稳定性错误地放进人工语义评审；
3. 开发诊断证据与正式 source-bound release receipt 混用；
4. 历史 canary 路径、共享运行时能力和用户场景被展开为重复的七层验收，缺少面向根入口替换的有限 burn-down。

最终交付不是自动切换 `/`。本切片必须产生 `ready_for_root_cutover_decision` 或明确的有限缺口；根入口切换、提交、push、merge、部署和旧代码删除仍需用户分别授权。

## 2. 当前事实

### 2.1 已经成立

当前 `unified_analysis_entry` 在冻结合成 fixture 上已经具有：

- owner contract、incident replay、SSE、浏览器交互、刷新持久化和真实 Provider journey 六层 PASS；
- 上传、estimate、一次性 authorization、恰好一次 planning、确定性续跑和独立统计复算；
- Stop、Steer、刷新恢复和会话隔离；
- 人工语义评审 10 个业务维度 PASS；
- `/v2-workbench` 可作为隔离的统一入口。

### 2.2 当前唯一 unified non-pass 的真实含义

5C5AA 的 current-source baseline 与追加样本都返回合同合法的 ready `multi_finding_synthesis`。除 `parameters.action_risk` 从 `medium` 变为 `low` 外，方法、数据列、分析单位、时间频率、聚合方式和独立统计复算一致。

旧协议要求 normalized `analysis_kind + parameters` 完全相同，因此判定 stability FAIL。该结果应作为旧协议下的真实失败永久保留，但不能在没有新的共享合同和 RED 回归时继续补跑或手工改成 PASS。

### 2.3 尚未成立

- `reference/test_doc` 尚未通过 V2 正常用户旅程；
- 旧的快速真实数据测试引用两个不存在的文件名，当前离线实测为 `2 failed, 28 passed, 1 skipped`；
- 其他方法场景尚未全部通过统一入口的场景语义验证；
- `/` 仍指向旧入口；
- 没有 root cutover、push、merge、部署或旧代码删除授权。

## 3. 发布目标分层

### R1：Unified Technical Candidate

统一入口的共享运行时和所有受支持 Planner schema 通过确定性合同；材料性稳定性合同取代 exact plan identity；状态和证据可由工具重新生成。

### R2：Real-Data Limited Release Candidate

至少一个当前 `reference/test_doc` 单文件场景通过：

`upload -> schema/data-scope -> semantic preflight -> plan -> deterministic analysis -> answer/chart -> refresh`

所有数值和业务语义由独立离线 oracle 复核。若当前 V2 不支持目标文件或问题，必须明确记录产品缺口，不得以旧 Agent loop 代跑。

### R3：Root Cutover Candidate

统一入口覆盖拟发布的方法族；共享运行时层只验证一次但必须证明所有场景走同一 owner/runtime 路径；场景特有的统计、数据和语义 oracle 分别通过。生成一个有限 burn-down，所有 root-cutover 必需项均 PASS。

达到 R3 只允许请求人工切换决定，不自动修改 `/`。

### R4：显式根入口切换

用户明确授权后才把 `/` 指向 V2。旧入口先保留为显式 rollback 路径；删除旧系统是稳定观察后的独立切片，不能与首次切换同时发生。

## 4. 验收模型重构

### 4.1 稳定性拆分

新增三个不同概念，禁止继续共用一个 `plan_identity_fingerprint` 代表全部稳定性：

1. `provider_response_repeatability`
   - 记录规范化 Provider 输出是否完全相同；
   - 仅作诊断，不单独阻断发布。
2. `planning_semantic_stability`
   - 比较 status、analysis kind、数据范围、必需绑定、analysis unit、aggregation、frequency 和会改变确定性执行路线的参数；
   - 是机器执行的技术 gate。
3. `outcome_stability`
   - 比较核心数值容差、方向、区间/显著性、claim class、主要限制和 recommendation safety mode；
   - 是机器执行的技术 gate。

必须先用历史事实写 RED：

- `medium -> low` 且行为路径、执行路线和结果相同时，不得因 exact fingerprint 单独失败；
- `low/medium -> high`、`reversible true -> false` 或 recommendation mode 改变时必须作为材料性安全差异；
- 必需列、分析单位、aggregation、frequency、analysis kind 或数据范围变化必须失败；
- 完整语义上下文下 `ready -> needs_input` 必须失败；
- 数值、方向、claim class 或主要限制越过预定义容差必须失败。

容差和等价规则必须写入版本化共享合同，不能在看到下一次 Provider 输出后临时解释。

### 4.2 Planner 与 recommendation 职责

Planner 只拥有方法选择和数据绑定。不得让模型仅凭 schema 猜测真实业务行动风险。

实施前用 RED 固定以下原则：

- 没有明确行动上下文时，只允许 investigative recommendation；
- `recommendation_intent`、风险和可逆性不能作为统计执行身份的可选噪声；
- action risk/reversibility 若影响 operational policy，必须来自明确的用户/业务上下文或安全的 unknown/fail-closed 状态；
- 不得用 `finding_kind + claim class` 假装确定真实业务行动风险；
- 不增加旧 Agent loop、repair、隐式重试或第二套 recommendation policy。

是否从 Planner schema 移除这些字段，必须由调用点和 RED 回归决定；不得只为让 5C5AA 变绿而忽略字段。

### 4.3 技术稳定性与人工评审分离

- 从 `HUMAN_REVIEW_DIMENSIONS` 中移出技术稳定性；
- 新增独立、机器校验的 stability receipt 或等价技术层；
- 人工语义评审只评价问题理解、数据范围、方法、统计、结论、替代解释、表达、图表、建议和旅程；
- 人工 receipt 可以引用技术 stability receipt，但不能替代或覆盖它。

### 4.4 共享运行时层与场景语义层分离

现有 9 × 7 矩阵是有限的，但把历史 canary 入口与用户产品入口混在了一起。V2 发布候选应以 `/v2-workbench` 为产品入口：

- owner、SSE、浏览器交互、Stop/Steer、刷新和 session isolation 等共享运行时层，只在能够证明相同代码路径时复用一次 current-source PASS；
- 方法 schema、统计 oracle、数据边界、图表策略和语义质量按场景分别验证；
- 不允许一个 unified happy path 冒充所有场景语义 PASS；
- 不要求每个历史 canary 页面重复证明同一个共享 SSE/刷新实现；
- release matrix 必须输出总项数、PASS/FAIL/BLOCKED/NOT_RUN、首个失败阶段和 root-cutover 必需缺口。

## 5. Evidence 生命周期

建立不可变事实与可重建状态的边界：

- Provider attempt、authorization consumption 和浏览器 observation 为 append-only evidence；
- 历史 5C5AA FAIL 不修改、不删除；
- receipt 由 validator 从 evidence 生成；
- current release status 是可重建投影，不手工维护；
- 开发阶段生成 `diagnostic` 证据，不签发正式 release PASS；
- 所有源码、测试、runner 和 validator 完成后只冻结一次 release candidate digest；
- 最终 candidate 的 source-bound receipt 仍必须严格匹配 digest；不得复用 stale receipt。

这不是取消 source digest，而是停止在每次开发改动后重走正式发布仪式。

## 6. 实施顺序

### Phase 0：证据检查点与基线

1. 核对 branch、HEAD、tracked/modified/untracked、source digest；
2. 审查当前未提交的 5C5AA evidence/status diff，确认只反映已发生事实；
3. 不改写历史 attempt；
4. 经用户明确要求后，才单独提交当前证据检查点；
5. 本阶段 Provider calls = 0。

### Phase 1：稳定性共享合同 RED

新增 provider-neutral fixtures，至少覆盖：

- current baseline `medium`；
- 5C5AA `low`；
- 历史合法 `needs_input`；
- analysis unit、metric/group/time field、aggregation/frequency 漂移；
- high-risk、irreversible 和 recommendation mode 漂移；
- outcome 数值容差内与容差外。

RED 必须先证明旧 exact-identity 判定会误杀行为等价计划，同时证明安全相关变化仍 fail closed。

### Phase 2：合同实现与 evidence 自动化

1. 实现版本化 semantic comparator；
2. 修复 Planner/recommendation 字段所有权；
3. 分离 technical stability 与 human review；
4. 实现 append-only evidence -> receipt -> current status 投影；
5. 更新 release matrix/evaluator 和设计文档；
6. 不调用 Provider，不签 current-source real-provider PASS。

### Phase 3：真实数据确定性 canary

1. 统一 `reference/test_doc` manifest 和实际文件名；
2. 禁止目录存在但关键文件缺失时静默 skip；
3. 选择当前 V2 真正支持的最小代表文件；
4. 明确业务问题、时间范围、行粒度、分析单位和允许发送的 metadata；
5. 完成不调用 Provider的 upload、preflight、确定性分析、复算、浏览器和刷新验证；
6. 若失败，修共享合同并完成全部离线回归，再统一冻结 source；不得边改边申请 Provider。

### Phase 4：一次冻结与成组真实验证

仅当 Phase 1–3 全绿：

1. 运行 V2/config、真实数据离线 suite、compileall、前端语法、`git diff --check`；
2. 计算一次候选 source digest；
3. 生成一份绑定模型、Provider host、目的、fixture/data metadata、protocol fingerprint 和精确条件式次数的 preflight；
4. 向用户请求一次成组授权；目标为有限的 2–3 个风险代表调用，而不是每修一个问题申请一次；
5. 任一失败按预定义协议停止，不重试、不 repair、不补跑；
6. 不得在调用后为迎合输出修改 comparator。

Phase 4 的精确调用次数必须由完成后的 preflight 明确；本计划本身不构成授权。

### Phase 5：统一入口发布候选

1. 在 `/v2-workbench` 上运行 root-cutover burn-down 中所有共享交互和场景语义验收；
2. 至少完成一个真实数据用户旅程和独立人工语义评审；
3. 生成 `ready_for_root_cutover_decision` 或有限缺口报告；
4. 用户明确授权后另开切片切换 `/`；
5. 首次切换保留显式 legacy rollback route；
6. 观察稳定后再单独审计、删除旧代码；删除不得与首次切换捆绑。

## 7. 最小验证集合

每个 source-changing phase 至少执行：

- 新增 stability/materiality RED/green tests；
- Planner、recommendation、release evaluator focused tests；
- authorization、planning HTTP、plan ledger tests；
- V2/config 全量确定性测试；
- `tests/test_mvp_real_data_fixtures.py` 和相关 `tests/real_data/` 离线测试；
- `python -m compileall src scripts tests`；
- JavaScript syntax checks（若相关文件变化）；
- `git diff --check`；
- source digest 重算。

测试报告必须分别列出 passed、failed、skipped。不得用 `test_v2*.py` 的结果代替真实数据 suite。

## 8. 明确禁止

- 在 Phase 4 精确授权前调用真实 Provider；
- 继续补跑或复用 5C5AA authorization；
- 添加自动 repair、隐式 retry 或旧 Agent loop；
- 删除或覆盖 `artifacts/`、`docs/audit/`、`tmp/`；
- 手工把历史 FAIL 改成 PASS；
- 用当前 frozen synthetic fixture 宣称真实数据或完整产品 ready；
- 未经授权 commit、merge、push、部署、切换 `/` 或删除旧系统；
- 为追求快速发布而取消 source-bound receipt、授权绑定或 fail-closed 安全边界。

## 9. 完成定义

本计划只有在以下结果全部产生时才算完成：

1. 材料性 planning/outcome stability 合同和 RED/green 回归；
2. technical stability 与 human review 分离；
3. evidence/status 可由工具重建；
4. 当前真实数据 manifest 和离线 canary 通过；
5. 统一入口的有限 root-cutover burn-down；
6. 冻结 source 上完成经授权的有限真实验证；
7. 至少一个真实数据旅程完成独立语义评审；
8. 输出 `ready_for_root_cutover_decision` 或一个有限、可执行的剩余缺口清单。

根入口切换和旧代码删除不属于本计划的自动完成动作。
