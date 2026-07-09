# 黄金最终答案质量测量设计

Date: 2026-07-09

## 1. 目的与范围

本设计定义一个**可复现的"最终答案质量"回归测量体系**：在真实数据场景上，
驱动 agent 回答黄金业务问题，对答案做两层质量评估（确定性 fatal 门 + LLM 裁判
soft 维度），给出当前 baseline 并能在每次改动后抓取质量回归。

这是续作计划 `2026-07-06-stage3c0b-realigned-continuation-plan.md` 中
**Phase 2「Quality Regression System And Golden Questions」**未落地的部分。
此前 Task 5 只完成了「真实数据回归 + soft 质量 rubric」（readiness 与结构校验），
**未实现"最终答案深度/有用性"的测量**——这正是验证报告点名的 Next Recommended
Task，也是用户当前最大痛点（"答案停在数值说明，缺严谨洞察、引导、方向拓展"）。

### 本设计做什么

- 黄金场景集（单文件深度 + 多文件综合 + 关系边界 + 防假 join），使用
  `reference/test_doc` 真实数据，含用户新增的 4 个省钱卡文件。
- 两层测量：fatal 确定性硬门（扩展 `analysis_quality_rubric`）+ soft LLM 裁判
  维度（绝对基线 + 配对 before/after）。
- Runner：真跑 agent 生成答案，抓取答案 + EvidenceRecord + verification，
  跑 fatal 门 + 裁判，落盘可审计产物。
- harness 自测（fixture 答案的确定性 meta-test）+ 决策入口（测量结果如何驱动后续）。

### 本设计不做什么（明确边界）

- **不**改运行期行为：不新增执行期硬契约、不新增运行期 claim 提取阶段、不改
  `synthesis_policy` 运行期逻辑。本设计是**测量层**，不约束运行期。
- **不**落地 Workbench 结论先行界面（后续 spec，由本测量的信号决定）。
- **不**启动 Stage 3C1A（join / DataOperationRecord）。若测量证明省钱卡洞察
  非连表不可得，则触发 3C1A 重开评估，但不在本设计实现。
- **不**给 soft 维度加总评分（与 evidence-synthesis 决策一致：不让广度补偿
  无证据结论）。

## 2. 背景与决策脉络

- **测量先行**：用户痛点是"结论深度不够 + 数据理解/建议方向不准"。但"深度/有用性"
  是主观维度，现有 `score_analysis_quality()` 只能做确定性硬检查（无证据结论、错误
  口径、错误关系）。在加任何新守卫（Phase 4）或重做 Workbench 界面之前，必须先有
  "最终答案质量"信号，否则是盲操作。
- **混合方法论**：fatal 用确定性（防住坏结论、可复现），soft 用 LLM 裁判（量化
  主观深度）。两层硬度：fatal 阻断"宣称可交付"；soft 只记 before/after 回归、不阻塞合并。
- **质量标尺（用户原话）**：好答案 = 用户能"反馈不存在问题的数据分析结果"。
  拆为两层：地基=严谨（可辩护、不夸大、口径对、局限清）；价值=严谨洞察 + 引导 +
  数据说明 + 拓展方向。停在数值说明=有地基但无用。

## 3. 设计原则

1. **测量层，非运行期契约**：所有新增工作要么是只读评估（rubric/judge）、要么是
   离线脚本（runner）。不进入 agent 运行期决策路径。
2. **复用优先**：扩展 `analysis_quality_rubric.py`、复用 `verification` /
   `evidence_contracts` / 现有 manifest 格式与产物目录结构。
3. **维度分离，无总评分**：每个 soft 维度独立打分/对比；fatal 门独立阻断。
4. **真跑 agent**：为抓真回归，runner 必须重新生成答案（方案 A），而非只裁判历史答案。
5. **相对判断优先**：配对 before/after 用相对判断（更好/持平/更差），比绝对打分稳定，
   免疫分数漂移。绝对基线仅一次性用于坐实"现在有多浅"。
6. **诚实边界即正向**：黄金场景奖励"承认数据不足以支持因果结论"，惩罚"自信的胡说"。

## 4. 黄金场景集

数据语料库 `reference/test_doc`。用户新增的 4 个省钱卡文件替换了旧的
`省钱卡用户最近流水_20260511` / `省钱卡订单_20260507`（现有
`tests/real_data/scenario_manifest.json` 中相关条目的旧文件名需在实现时同步更新）。

### 4.1 省钱卡 4 文件结构（实测）

| 文件 | 行数 | 关键列 | 业务含义 |
|---|---|---|---|
| 省钱卡订单.xlsx | 71 | user_id, 产品名称(月卡), 单价45, 起止时间 | 谁买了卡（71 名月卡用户，45 元/月） |
| 省钱卡0201到0510购卡用户付费数据.xlsx | 13757 | order_id, user_id, 项目名称, 下单数量, 实际金额, 支付时间 | 购卡用户全部付费明细 |
| 省钱卡代金券明细订单.xlsx | 1075 | 领券用户ID, 代金券名称, 面值, 状态, 实付, 发货用户ID | 代金券领取/使用（卡的核心权益） |
| 省钱卡购卡前后订单.xlsx | 7206 | user_id, 实际金额, 支付时间, 用户类型(1=购卡前30天, 2=购卡后30天) | 购卡前后对比（**自带前后标志位**） |

**决定性发现**：`省钱卡购卡前后订单` 自带 `用户类型 1/2` 前后标志位，
"购卡是否提升消费"只需单文件按 `用户类型` 分组聚合即可答，**不需要 join**。
因此省钱卡场景是测"数值说明 vs 洞察"的干净试纸：数据足够丰富、好分析师不 join
就能挖出深度；若 agent 仍停在数值说明，铁定是综合深度问题而非数据访问问题。
（4 文件均有 user_id 共享键、代金券含领券/发货双 ID——同时提供"诱人但不该自动
join"的真实素材。）

### 4.2 场景定义

| ID | 类型 | 数据 | 业务问题 | 核心测点 |
|---|---|---|---|---|
| S1 | 多文件综合（主痛点） | 省钱卡 4 文件 | "省钱卡业务整体表现如何？购卡前后消费变化？代金券有没有拉动消费？整体赚还是亏、值不值得继续推？" | 洞察深度 + 多文件综合 + 不被 user_id 诱惑假 join |
| S2 | 同游戏多指标综合 | 游戏A banner+内购+激励视频 | "综合判断哪种推广/付费方式效果最好？" | 多指标综合深度 |
| S3 | 单文件深度 | 游戏B留存 | "留存曲线特征/拐点/意味着什么？该如何改善？" | 单文件洞察深度 |
| S4 | 防假 join | 游戏B留存 + 省钱卡订单（无关文件） | "这两个文件能合起来分析吗？" | 正确拒绝错误关联 |

业务问题措辞以用户真实使用为准；S1 的措辞为设计提案，需用户在 spec review
阶段最终确认或替换为真实使用过的问法。

### 4.3 黄金 manifest（新增）

新增 `tests/real_data/golden_answer_manifest.json`，schema
`golden_answer_scenarios.v1`。每条：

```json
{
  "id": "savings_card_business_overview",
  "description": "...",
  "required_files": ["省钱卡订单.xlsx", "省钱卡0201到0510购卡用户付费数据.xlsx",
                     "省钱卡代金券明细订单.xlsx", "省钱卡购卡前后订单.xlsx"],
  "business_question": "省钱卡业务整体表现如何？购卡前后消费变化？代金券有没有拉动消费？整体赚还是亏、值不值得继续推？",
  "analysis_mode": "independent_then_synthesis",
  "soft_dimension_focus": ["insight_depth", "guidance", "direction_expansion"],
  "fatal_expectations": {
    "no_unsupported_material_claim": true,
    "no_invalid_relationship_use": true,
    "before_after_grain_must_match": true
  },
  "forbidden_auto_join_by": ["user_id"]
}
```

## 5. 测量模型

### 5.1 Fatal 门（确定性，阻断"宣称可交付"）

扩展 `analysis_quality_rubric.score_analysis_quality()`，新增针对黄金答案的输入：
从最终答案文本提取 claim，与 agent 产出的 EvidenceRecord / verification 比对。

> 注：这里的 claim 提取是**测量期评估**，不是运行期硬契约，与 evidence-synthesis
> 决策"暂不新增运行期 claim 提取阶段"不冲突。

Fatal 条件（任一命中 → `claim_delivery_ready=false` / `global_publish_gate=false`）：

- 关键结论无 EvidenceRecord 支撑；
- 用被拒 / 未确认 / 时间不兼容的关系支撑结论；
- 口径不一致的比较未标注（如购卡前 30 天 vs 后 40 天直接比、不同币种/单位比）；
-（S4）对无关文件给出基于同名字段的关联结论。

复用：`verification.verify_analysis_claims()`、`evidence_contracts`、现有
`score_analysis_quality` 的 blocker 机制。

### 5.2 Soft 维度（LLM 裁判，before/after 回归，不阻塞）

按用户价值命名，每个维度独立打分（绝对基线 1–5）或对比（配对 更好/持平/更差），
**无总评分**：

| 维度 key | 中文名 | 评什么 | 锚点示例 |
|---|---|---|---|
| `rigor` | 严谨与可信 | 结论可辩护、证据充分、不夸大、主动声明局限/口径 | 5=主动指出"前后对比不能排除自然增长/季节性"等陷阱 |
| `insight_depth` | 洞察深度 | 超越数值描述→业务含义/机制/对比 | 1=纯数值；5=机制假设+横向对比 |
| `guidance` | 引导与可行动性 | 明确建议、下一步、决策含义 | 能否直接拿去做决策 |
| `data_explanation` | 数据说明清晰度 | 数值/口径/图表解释到位 | 讲清数的含义，而非堆数 |
| `direction_expansion` | 分析方向拓展 | 主动提出可深挖方向 | 直击"建议方向不准"痛点：要准且能拓展 |

`synthesis`（多文件综合性）作为 S1/S2 的附加维度；S3/S4 不评。

## 6. 裁判机制

- **模型**：config 新增 `quality_judge_model`，默认用**与被测 agent 不同**的强模型，
  降低"自评偏好"。中文领域需能力强的模型。
- **稳定性**：temperature=0、结构化 JSON 输出、固定 prompt；可选在样本上双跑测
  自一致性并报告方差。
- **裁判输入**：用户问题 + 数据 brief（**不喂原始行**，避免泄漏/成本）+ 答案 +
  各维度中文锚点。配对模式给两份答案（baseline / new）。
- **输出 schema**（版本化，schema `golden_quality_results.v1`）：

```json
{
  "schema_version": "golden_quality_results.v1",
  "run": { "mode": "generate|evaluate", "model": "...", "judge_model": "...",
           "timestamp": "...", "baseline_ref": "..." },
  "scenarios": [
    {
      "id": "savings_card_business_overview",
      "fatal": { "claim_delivery_ready": true, "global_publish_gate": true,
                 "blockers": [] },
      "soft": {
        "absolute": { "insight_depth": {"score": 2, "rationale": "..."}, ... },
        "pairwise": { "insight_depth": {"verdict": "worse", "rationale": "..."}, ... }
      }
    }
  ]
}
```

- **配对语义**：`verdict` ∈ {`better`, `same`, `worse`}，相对 pinned baseline。
  任何 `worse` + 其 rationale 即回归信号。

## 7. Runner 设计

新增 `scripts/run_golden_answer_quality.py`。比现有
`run_multifile_quality_scenarios.py`（只校验 manifest 就绪、不跑 agent）**重**：
必须真跑 agent 生成答案。

### 7.1 流程（generate 模式）

1. 读 `golden_answer_manifest.json`；
2. 每个场景：搭临时 session/workspace，加载 `required_files`（走 `load_data`，
   产出 `DataUnderstandingBundle`）；
3. 以 `business_question` 作为用户轮驱动 agent（`AgentRunner` / `AgentLoop`），
   抓取 `FinalResponse`（答案文本）+ 该轮 EvidenceRecord / verification 结果；
4. 跑 fatal 门（§5.1）；
5. 跑 LLM 裁判（§6）：generate 模式产 absolute 评分；若存在 pinned baseline
   答案，同时跑 pairwise；
6. 落盘 `artifacts/golden-quality/<timestamp>/results.json` + 可读摘要
   （每场景 fatal pass/fail + soft 维度评分/delta + top rationale）。

### 7.2 模式

- `generate`：重新生成答案（用于回归、baseline 更新）。产物 = 生成答案 + 评估。
- `evaluate`：只裁判**已存答案**（不跑 agent，可复现、零生成成本）。

### 7.3 Baseline 管理

- `artifacts/golden-quality/baseline/`：pin 一组"已知答案 + 评估"作为配对锚点。
- 回归流程：改代码 → `generate` 跑全场景 → 与 `baseline/` 配对 → 任何 `worse`
  即需排查。
- 当改动**有意**改善答案：人工确认后 `generate --update-baseline` 刷新锚点。

### 7.4 驱动 agent 的实现约束

- 复用 `AgentRunner`（`agent/runner.py`）在后台线程跑一轮；捕获 `FinalResponse`。
- EvidenceRecord / verification 通过 `AnalysisSessionState` / `trust_workflow_runtime`
  既有产物读取，不新造抓取路径。
- 实现细节（如何最小化搭 session、如何注入黄金问题）留给实现计划。

## 8. 非确定性与成本控制

- 生成本身非确定：temp=0 + 固定 judge 模型 + 配对相对判断（抗绝对漂移）；产物记录
  model / timestamp 供追溯。
- 成本：场景 4 个（可扩到 6），每场景 1 次生成 + 维度数 × 裁判调用；量级可控。
- runner 默认**不进 pytest 自动跑**（需 LLM、有成本）；确定性部分（fatal 门 on
  fixture、rubric 结构、manifest 校验）进 pytest。

## 9. harness 自测（meta-tests，确定性，进 pytest）

用 fixture 答案（不调 LLM）验证测量层本身正确：

- 已知"纯数值描述"答案 → `insight_depth` 评分低（fixture 预置期望档）；
- 已知"严谨+洞察+边界"答案 → 各维度高；
- 无证据结论答案 → fatal `claim_delivery_ready=false`；
- S4 对无关文件下关联结论 → fatal 命中；
- 配对：同一答案 vs 其裁剪浅化版 → `worse`。
- manifest 校验：所有 `required_files` 存在；新省钱卡文件名替换旧名后无悬空引用。

## 10. 测量结果如何驱动后续决策（闭环）

本设计是测量先行；其结果显式触发后续 spec，不在本设计实现：

| 测量结果 | 触发的后续工作 |
|---|---|
| absolute 显示全面偏浅（insight_depth/guidance 普遍 ≤2） | 优先调 `synthesis_policy` prompt（证据补齐已有，强化"洞察+引导+拓展"指令） |
| 配对显示某次改动致 `worse` | 阻断该改动宣称完成，先修复 |
| 单文件 vs 多文件深度差异大 | 定位深度丢失在综合层 → 综合策略专项 |
| S1 在"允许的综合路径"下仍给不出省钱卡洞察，且洞察**本质上需连表** | 触发 Stage 3C1A 重开评估（满足此前推迟决策的重开条件） |
| `direction_expansion` 普遍低/不准 | 建议方向准确性专项（`route_capabilities` / `multi_file_scope`） |
| 测量稳定、baseline 建立 | 启动 Workbench 结论先行界面 spec（行动看板骨架天然映射五维度） |

## 11. 复用清单

| 能力 | 现有实现 | 本设计如何用 |
|---|---|---|
| 质量 rubric | `agent/analysis_quality_rubric.py` | 扩展 fatal 门输入（claim 提取 + 比对） |
| 验证 | `agent/verification.py` `verify_analysis_claims()` | 复用，喂 EvidenceRecord |
| 证据契约 | `agent/evidence_contracts.py` | 复用 |
| 数据理解 | `agent/data_understanding.py` | 为裁判生成数据 brief |
| agent 驱动 | `agent/runner.py` / `agent/loop.py` | runner 用其生成答案 |
| 场景产物目录 | `artifacts/multifile-quality/` 模式 | 新增 `artifacts/golden-quality/` |
| manifest 格式 | `tests/real_data/scenario_manifest.json` | 新增并行 golden manifest |

## 12. 非目标

- 不改 agent 运行期行为（synthesis_policy 运行期逻辑、新增运行期 claim 提取）。
- 不落地 Workbench 结论先行界面（后续 spec）。
- 不启动 Stage 3C1A（join / DataOperationRecord）。
- 不给 soft 维度加总评分。
- 不让 runner 默认进 CI 自动跑。
- 不自动 join 省钱卡 4 文件。

## 13. 验收门

- 黄金 manifest 4 场景，`required_files` 全部存在（含新省钱卡文件）。
- fatal 门：fixture 无证据结论 / 无关文件关联 → 正确阻断（meta-test 绿）。
- soft 维度：fixture 浅答案低分、深答案高分、配对裁剪版 `worse`（meta-test 绿）。
- runner `generate` 模式：能在 ≥1 真实场景上端到端跑通，产出
  `artifacts/golden-quality/<ts>/results.json`（schema `golden_quality_results.v1`）
  + 可读摘要。
- absolute baseline 建立：坐实"当前答案在洞察/引导/拓展上偏浅"（或证伪）。
- 非越界自检：新增 src 未进入 agent 运行期决策路径（rubric/judge 为只读评估，
  runner 为离线脚本）。
- 旧 manifest 悬空旧文件名已修正。
