# 可信发布重置 Phase 2：跨批次证据与结构化切片开工审查

日期：2026-09-23。代码基线：`main@cdfcc1a`。本文件是设计/测试边界，不是 Phase 2 已完成证明；没有执行真实 Provider、浏览器矩阵或发布变更。

## 1. 证据不是单次 M02

| 历史证据 | 当时解决/验证了什么 | 仍未闭合什么 |
|---|---|---|
| 2026-08 Slice 0—7、8/28 本机验收 | 分析工具、会话与本地浏览器基本路径；2181→2342 量级的回归 | 自然模型措辞与生产级可信发布 |
| 9/6 full-offline 2393，9/8—20 2585/2569/2644/2713 等 | 运行时、确认与内容契约的大面积回归 | 历次后续 E4 仍失败，测试数不能替代语义/证据边界 |
| R7/R8/R10/R11/R14/R16 的 M02 | 多次正确给出 D7=10%、拒绝无证据 D30；发布门却分别把问句、否定、标题和边界说明误判为预测；修复提交逐步增加否定/标题识别 | 开放自然语言空间仍由散文正则担当硬审批 |
| `2dafc69` 与 R19/R20/R21 | 回执包络、数值先于族名的配对及不再要求披露词语；局部测试覆盖正确/错误数值；若干真实批次显示改进 | 配对仍依赖句内布局；后续 R4 证明未收敛 |
| R4 M02 `c3f4c190384c` | 两份回执支持的 D30 情景候选均因散文门误拒；同批存在被取消的误启动，不是完整验收批次 | 只能作失败轨迹，不能单独定义设计或宣称 E4 结果 |
| `bd42678` 的 `answer_bindings.v1` 与 R4 M03 | 已有模型可生成的 `blocks/exact_text/refs` 种子、宿主 parser 和数值绑定测试 | R4 M03 的 fence/digest 与宿主实际接纳须另证；现有绑定未承担情景 claim 渲染 |

历史记录见 `docs/audit/2026-09-09-answer-intent-integration-record.md`、三份原始计划及本任务 Phase 0 审计。这里区分旧 commit/旧模型/旧矩阵的证据，不把历史局部绿灯迁移为当前源码的通过。

## 2. 新确认的架构断层

1. `publication_synthesis.py::publication_contract()` 把 curve_fitting 的模型参数、R²、观测范围和 validation 状态放入 `publication_scope[*].scenario_extrapolation`；`build_publication_packet()` 将其置于 packet 的 `publication_scope`。
2. 同文件 `render_verified_appendix()` 却在 `packet["sources"]` 上寻找 `scenario_extrapolation`。当前 packet 构造的 source 不含此字段；生产 `src/` 内也没有该 renderer 的调用点。`2dafc69` 的宿主披露测试手工把 scenario 塞进 source，只证明孤立函数，未证明最终正文、刷新或导出会出现披露。
3. `answer_bindings.v1` 当前是可选协议，parser 校验唯一片段、packet digest、requirement/fact/derived refs；它尚不校验 curve receipt、模型族、时间点、claim 强度与单位状态。不能简单删除旧门并把可选绑定当成充分保护。
4. R4 M02 旧候选是未带 typed claim 的历史自然语言样本。若不解析自由散文（本计划禁止），宿主不能从它们自动恢复可信的族—数值绑定。因此“旧候选原字节直接通过”与“只认结构化 claim”不能同时作为硬验收条件；应要求**内容等价的结构化重放**保留结论，并把旧候选作为旧门误拒的对照样本。

## 3. Phase 2 不变量与最小垂直切片

- 仍使用现有 `answer_bindings.v1`；向后兼容一般事实绑定。对 `scenario_extrapolation` block 增加封闭字段：claim id/type/status、receipt ref、时间点、要求渲染的模型族、validation/unit 状态。引用必须在同一 packet/数据版本的 `publication_scope` 找到；不能接受模型自报的参数、R²、结果或验证状态作为权威。
- 模型在正文放唯一的情景占位片段并绑定它；宿主根据 curve_fitting receipt 重算族参数、R²、D30 数值和观测/验证状态，**在该片段位置**替换为表格与紧邻披露。不得只在答案末尾附免责声明；不得把负留存显示为可用预测。
- 结构化区以闭合的 receipt/claim 数值验证，不再经过族名/百分比散文配对。未绑定的其余正文仍按现有发布约束验证；迁移期间不一次性关闭其它旧门。正式候选若缺必需的情景绑定，只能定向修订或不发布该高风险 claim，不能把自由散文冒充已绑定数据。
- 正确/错误对必须共用同一 packet：R4 等价三族情景可发布；改错 D30 值、stale digest、外来 receipt、错数据版本、虚称 holdout/预测、缺 claim 绑定必须失败或结构化降级。验证还应覆盖语序/表格布局变形，证明结果不靠补关键词。
- 宿主披露必须沿真实最终化调用链进入用户可见正文，且刷新、Markdown 导出和持久化一致。单独调用 `render_verified_appendix()` 的单测不能作为完成证据。

## 4. 实施前 RED、旧门退役与停止条件

先在当前源码上固定以下 RED：真实 R4 候选触发 `unbound_time_point_claim`；手工 packet 的披露函数虽然输出文字，但生产 packet + finalization 不在正文输出；`answer_bindings.v1` 不校验情景 receipt/claim。再新增结构化等价重放及编造数值负例，运行定向测试、受影响完整文件、fresh full-offline，最后按既有入口做 Provider-disabled 浏览器完整矩阵。真实 Provider 一律等待新的精确冻结与显式授权。

仅退役结构化情景片段上 `_scenario_family_values` / `_range_envelope_ok` 这类布局门；其它未绑定散文的发布门保持，直到各自结构化替代物与全链路证据闭合。若实现需要从旧自然语言候选反推族值、靠末尾附录抵消正文、或为修一次失败再加词表，应停止并重新审查设计。

用户已于 2026-09-23 确认上述验收解释：历史 R4 候选作为误拒对照；其**内容等价的 typed-binding/宿主渲染版本**通过，不要求旧文本原字节绕过所有散文门。用户还确认：R4 curve 回执 `unit_status=not_confirmed` 时，宿主只渲染原始数值尺度并明确单位未确认；只有回执已有明确单位证据才换算成百分比。不得从 `retention` 列名或模型散文擅自提升单位状态。

## 5. 本地切片执行记录（尚非 Phase 2 验收）

- 实现前 HEAD 基线：`cdfcc1a5d4d4ab82cee85b722d9423a2c3036a99`；Phase 2 精确提交以 Git 记录为准。
- RED：新增聚焦测试在未修改产品代码时 `3 failed / 1 passed`。失败分别是现有 parser 丢弃 `claim_type`、外来回执未被拒绝、最终正文仍留 `[[claim:...]]`；旧的未绑定编造 D30 值被原有硬门拒绝。
- 最小实现：扩展原 `answer_bindings.v1` 的 scenario block，不建第二通道；宿主核对同一 packet 的 curve scope/receipt、全部模型族、时间点、验证与单位状态；不接受模型提供的参数或数值；在正文占位位置重算并渲染表格与紧邻披露。未绑定自由散文仍由现有门检查，结构化片段不做中文子句族值配对。
- 第二个 RED：生产 packet 的预览/最终 `snapshot_digest` 因 `phase` 不同而变化，旧 parser 只认最终 digest；新增 builder 回放先以缺少 `binding_digest` 失败。R4 M03 终稿使用普通 `json` fence 和 `snapshot_digest` 字段，也不符合宿主 parser 所需的 `answer-bindings` fence 与 `packet_digest`，不能称为已接纳的 binding。
- 协议修正：同一证据内容的预览/最终 packet 共享 `binding_digest`（只排除展示 `phase`），模型在现有 `answer_bindings.v1.packet_digest` 填此值；最终包仍有独立 `snapshot_digest`。需求 revision/迟到回执、scope 或版本变化会改变 binding digest，旧绑定继续 fail-closed。旧的直接引用当前 `snapshot_digest` 的本地调用保持兼容。
- GREEN：聚焦 10 passed；包含旧 scenario 包络、answer bindings/数值、发布合同、来源修订、P7 边界与输出渲染的跨历史组合 234 passed。fresh full-offline `tmp/trust-reset-phase2-full-offline-1`：2831 passed、1 skipped、16 warnings、0 failures，314.93s；JUnit 2832 tests、0 failures、0 errors、1 skipped，SHA-256 `BA462723F6363FBCB5BAC5C4F5D184BCEC1620D5E49907E8265BAB57C02C3890`。runner 设置 `provider_calls=forbidden`，并明确以 `PYTEST_ADDOPTS=--ignore=tests/test_p08_trust_restructure.py` 排除原有未跟踪、已否决设计的测试；不能宣称默认脏工作树无条件全绿。
- 生产调用链的测试已覆盖 `build_publication_packet` → `publication_packet_prompt`、`_render_finalized_publication` → 宿主表格、`_persist_accepted_answer` → 回复正文与 packet `answer_sha256` 一致。尚未证明刷新/Markdown 导出或 Provider-disabled 完整浏览器矩阵。
- 本地 E1/E2 收据已取得，E3 内置浏览器完整矩阵、真实 Provider、新冻结、staging/production 均未执行；Phase 2 尚不等于发布验收。旧未跟踪设计/测试文件仍保留且未收集。
