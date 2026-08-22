# Data Agent V2 Slice 3：数据转换与语义确认

- **日期**：2026-08-13
- **状态**：Implemented; focused acceptance passed
- **基线提交**：`6083b14`（`feat(v2): add structured factor analysis slice`）
- **分支**：`codex/data-agent-v2`
- **上位设计**：[`2026-08-13-data-agent-v2-architecture-design.md`](../specs/2026-08-13-data-agent-v2-architecture-design.md)

## 1. 目标

建立一条日期字段转换纵向路径，证明系统只在用户掌握独占语义时询问，而不是把普通分析方法或无损转换变成许可门。

```text
RawDatasetVersion
→ 服务端日期语义诊断
→ 无歧义则自动生成 AnalysisDatasetVersion
→ 有歧义则生成 CandidateDatasetVersions + 敏感性比较
→ 结构化 user_input_required
→ 用户选择后校验父版本与指纹
→ 提升为新的 AnalysisDatasetVersion
→ Transformation Finding + 只读 Outcome
→ 可读血缘答案块、SSE 与刷新恢复
```

## 2. 硬边界

1. raw 版本不可修改；任何转换都生成新版本。
2. ISO 日期或只有一种格式能完整解析时自动执行，不询问用户。
3. 同一原始文本在 DMY 与 MDY 下都能完整解析、但结果不同时，属于用户独占语义，必须确认。
4. 确认绑定 `proposal_id + parent_version_id + parent_content_fingerprint + option_key`。
5. 候选父版本不再是调用方声明的当前父版本时，拒绝陈旧确认；不得静默套用到新数据。
6. Candidate 和敏感性比较是事实，不是完成状态；只有提升后的 analysis version 与 Transformation Finding 才能形成 supported Outcome。
7. 确认状态由不可变 Proposal 与 Decision 投影，不引入可任意改写的 `confirmed=true` 权威。
8. 本切片不读取或兼容旧 ConfirmationService、task、requirement、evidence 或 audit schema。

## 3. 日期决策规则

### 自动安全转换

- 非空值全部符合 ISO 8601；或
- DMY/MDY 中只有一种能完整解析；或
- 多种解析策略得到完全相同的时间值；
- 不新增缺失值，不删除行，不覆盖原始版本。

### 需要语义确认

- 两种日期顺序都能完整解析；
- 至少一个非空值在两种顺序下产生不同日期；
- 系统没有可靠业务元数据决定日期制式。

确认选项必须展示格式标签、成功解析数、新增缺失数、时间范围和与其他候选不同的值数。

### 本切片暂不自动处理

- 部分不可解析且会新增缺失值；
- 时区补全；
- Excel serial date；
- 跨字段日期拼接；
- 删除、覆盖或向外部系统写入。

这些情况发布具体 `limited` 诊断，后续再扩展转换策略。

## 4. 事实模型

### TransformationProposal

```text
proposal_id
turn_id / run_id / commitment_id
parent_version_id
parent_content_fingerprint
column
target_type
reason_code
options[]: option_key / label / candidate_version_id / sensitivity
```

### TransformationDecision

```text
decision_id
proposal_id
option_key
expected_parent_version_id
expected_parent_content_fingerprint
```

Proposal 与 Decision 都只追加且 ID 幂等。选择冲突或父版本变化必须报错。

## 5. 验收重点

- ISO 日期自动转换，不出现 `user_input_required`；
- `01/02/2026` 一类双解释日期产生结构化 DMY/MDY 选择；
- raw frame 保持字符串，candidate/analysis frame 才是 datetime；
- 每个候选展示新增缺失、解析率、时间范围和候选差异；
- 错误 option、错误父版本或错误父指纹不能完成确认；
- 确认后生成新的 analysis version、Transformation Finding 和 supported Outcome；
- 等待输入状态可刷新恢复，确认后最终答案与血缘可刷新恢复；
- 普通方法执行不请求许可，本切片不调用真实 provider。

## 6. 非完成声明

Slice 3 canary 通过只证明日期转换与语义确认这一条 V2 纵切。它不代表旧主页面、多文件关系、其他清洗操作、Gate E/F 或产品整体已经恢复。

## 7. 验收记录

- ISO 日期通过真实浏览器上传后自动转换，没有出现确认面板，并可刷新恢复；
- DMY/MDY 歧义样本展示两个候选的解析数、新增缺失、范围和差异值数量；
- 待确认状态关闭 SSE 后保持 `needs_input`，刷新仍恢复相同候选；
- 用户选择绑定父版本和内容指纹，随后候选提升为 analysis version，最终答案可刷新恢复；
- stale 父版本、未知选项和冲突决策不能被接受；相同语义重试保持幂等；
- 浏览器验收发现并移除了最终正文中的 Proposal 与 Dataset 内部 ID；
- 本切片没有调用真实 provider，也没有生成 Gate E/F 产品完成凭证。
