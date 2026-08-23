# 路线 A 分阶段实施计划（跨会话主计划）

> **本文件是路线 A 的唯一权威计划**。任何新会话从 §0 状态表恢复上下文；每完成一个任务更新状态表并提交。任务级细化（RED 测试/文件清单）在每阶段启动时以其小节为准。
>
> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development 或 superpowers:executing-plans 按任务实施；checkbox 跟踪。

- 日期：2026-08-23｜分支：`rebuild`（自 1d57061）｜上位设计：`docs/superpowers/specs/2026-08-23-route-a-top-architecture-design.md`
- 证据输入：`docs/audit/2026-08-23-v1-0713-base-real-data-test.md`（基座实测）、`docs/archive/v2/`（v2 与 7 月线全部参考文档）、`docs/audit/2026-08-23-v1-v2-parity-audit.md` 对齐审计
- 资产来源：v2 引擎在 `archive/v2-exploration` 分支 `src/data_agent/v2/`；7 月线修复在 `archive/july-recovery-m2c` 分支
- 质量标准：严谨（最高）+数据为本+方法合规+完整；旧会话仅为对比锚点

## §0 状态表（每任务完成即更新提交）

| 阶段 | 任务 | 状态 | 提交 |
|---|---|---|---|
| R0 | 基线测试套件跑通+缺陷确诊 | ☐ | |
| R1 | 数据底座：版本化副本+血缘（P1/P2） | ☐ | |
| R1 | 数值自愈进 load_data | ☐ | |
| R2 | 引擎工具化×9（含参数契约 P3/有界沙箱 P4） | ☐ | |
| R2 | 引擎选择引导（提示+意图层） | ☐ | |
| R3 | compile-verifier（标注式校验器） | ☐ | |
| R4 | 确认门 M1 化（非破坏自动放行） | ☐ | |
| R4 | 回合内完成度对账 | ☐ | |
| R5 | 产品面增量（结论先行工作台 P8-⑤ 等） | ☐ | |
| R6 | golden 重放固化 S1-S7+锚点 | ☐ | |
| — | v2 复盘文档（反面教材） | ☐ | |

## R0 基线复活与确诊（先行，~1 会话）

**目标**：确认基座健康，产出确诊清单供后续阶段校准。
1. 跑通 v1 测试套件（注意已知：全套件有顺序依赖的偶发失败，按模块跑）
2. 用 8/22+8/23 两轮实测已确认的缺陷清单为准（不必重测）：确认门过度触发/口径纪律/断言式完成/图表落盘对账
3. 摸底 LLMClient 在工具循环下的 token 配置（实测正常，记录参数）
**验收**：基线测试绿；缺陷清单入本文件 §R0-发现。

## R1 数据底座（7 月线 P1/P2 + v2 自愈）

**目标**：非破坏操作的物理前提 + 脏数据零障碍。
1. 从 `archive/july-recovery-m2c` 摘取 workspace 版本段（register_raw_snapshot/promote_analysis_copy/restore_analysis_version，session/workspace.py:144-343）+ 血缘（agent/data_lineage.py，纯函数）+ 两个测试文件
2. v2 的列角色探测（planner.py `_infer_column_role` 的 ≥95% 数值可转换逻辑）移植进 load_data 的类型推断，转换即派生版本（带 coerced 披露）
**验收**：卖量收入类脏列加载后可直接进工具；每次转换生成新版本且可恢复；测试含真实文件重放。

## R2 统计引擎工具化（核心价值件，最大批次）

**目标**：统计正确性下沉引擎，编排自由度留给 LLM。
1. 从 `archive/v2-exploration` 移植 9 引擎纯函数（group_comparison 含配对/聚合、curve_fitting、factor、time_series、forecasting、bivariate_fallback、group_ranking 即 >2 组排序）——**只取引擎函数，不取 slice/store/合同**
2. 每引擎包装为 `@registry.register` 工具：结构化输入 schema + ToolResult 带完整统计输出（系数/CI/p/诊断/局限），能力元数据声明问题类型与适用条件
3. 同批移植 P3（registry 参数契约校验）与 P4（有界沙箱）——引擎工具需要参数校验
4. 系统提示与意图层引导："统计检验/拟合/比较类问题优先调用对应引擎工具"；配对设计优先原则（同单位跨两组→paired_comparison）写入工具描述
5. 保留 run_python 于探索用途
**验收（golden 重放）**：S1 提示词→调 curve_fitting 工具→幂律参数与 0.1880/-0.7167/0.9824 一致；S4→调 paired_comparison→-1220.13/p=0.0186；S5→脏列自愈+group_ranking；引擎调用率纳入断言（LLM 不弃引擎手写代码）。

## R3 合成校验器（v2 compile 的标注式改造）

**目标**：口径纪律与数值诚实，不设门禁。
1. 从 v2 answer.py 取校验思想（数值一致性/claim 分级），实现为合成后校验器：答案数值与引擎输出抽查、estimand/口径披露检查、结论分级标注
2. 不合规→答案内联标注+尾部"校验摘要"，永不删除/阻断
**验收**：S4 重放答案含口径声明（总额/日均并列或说明选择）；注入一个数值不一致的合成（测试钩子）→被标注不消失。

## R4 确认门 M1 化 + 完成度对账

1. 按 M1 原则改 confirmation 触发：非破坏自动放行+血缘记录；仅删除/覆盖外部/导出确认。方法类高风险不再是确认理由（S5 类误触发清零）
2. 完成度对账：record_analysis_plan 的声明 × 回合内真实工具成功落盘对账；计划声明图表而无成功 create_chart→补跑或答案如实声明
**验收**：S5 重放 3 秒挂起不再发生；S2 重放"9 调 3 落"类差异要么消除要么在答案中如实披露。

## R5 产品面增量（按需，优先级最低）

结论先行工作台（P8-⑤ 已有实现可借鉴）、图表邻接/内联修复（P8-④/⑥）、任务列表真实推进（P8 替代项，采用"工具能力∈步骤能力"而非 7 月线的任意成功推进）。

## R6 测量固化

1. S1-S7 + 5/18、7/11 锚点提示词固化为 golden 重放（断言：工具序列/引擎调用/图表落盘/校验摘要；不断言旧会话内容为真值）
2. 人工评审 12 维口径文档化（10 维+信息量/可操作性）
3. 发布流程采纳 v2 的成组 provider 授权纪律（测试用）

## v2 复盘文档（随 R0 提交）

`docs/archive/v2-retrospective.md`：时间线/资产证明/病理四环节/可回收清单（已回收状态）/查阅指南（archive 分支+PR #1/#2）。

## 全局纪律

- 每任务：RED 先行→实现→全量回归→compileall→独立提交（源码与文档分开）
- 真实 provider 调用：测试场景按成组授权（v2 纪律）；每阶段验收的重放消耗计入阶段说明
- 不做清单：不引入 planner 单路由（B 方案）、不做阻断式发布门（C 方案）、不建跨回合全量事实日志——三者为实测否决路径
- 跨会话恢复：读本文件 §0 + 上位设计 §2 即可继续；细节问题查 docs/archive/v2/ 对应文档
