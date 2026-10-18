# 可信发布宿主语义绑定实施收据

日期：2026-10-01。当前执行安排只在[唯一总计划](../superpowers/plans/2026-09-22-analysis-agent-trust-reset-plan.md)维护；本文记录本轮改动、失败与证据，不是第二份计划。

## 1. 源码身份与权限

实施树 `C:\Users\duguy\.codex\worktrees\trust-rebuild\data-agent`，分支 `codex/trust-rebuild-20260927`，HEAD `71e23d0ac26091365508ae1b50fa7dd88b238591`；供体 `D:\Project\Daily\data-agent@b181646ff66ea9ea3b0e6a38ffcd3d16b6687312` 只读。已核 worktree、树内 AGENTS、唯一计划、VP/IC/CP、PRD 与设计。全部原 dirty/untracked 保留；没有暂存、提交、服务启动、正式配置变更、外部 Git 或真实 Provider 调用。语义试验环境变量和 PYTHONPATH 未设置；所有测试通过既有 Provider 禁用 regression 入口执行。

本轮向既有在途 `agent/publication/` 核心补齐局部语义责任，尚无 app 调用者。旧运行协议仍在应用中运行；没有增加产品双路径、开关或 wrapper。不能把未接入包的通过记为新 app 通过。

## 2. 实施内容和事实边界

- `requirements.py` 使用既有 `AnalysisSessionState.answer_requirements / requirement_revision`，不建第二清单。新增/替换/撤回必须绑定摘要匹配的 `CanonicalHistorySnapshot` 内唯一真实用户消息和精确原文范围；批量校验通过才更新，重复新增幂等。保留九项需求，不截为六项。模型的 answered 等额外字段被拒绝；缺少交付为具体 not_computed。单条原文来源失效转 evidence_insufficient 并撤去该条全部交付绑定，独立有效需求保留；规范历史本身损坏仍全局拒绝。
- `facts.py` 将既有唯一严格 reader 提取为 `load_receipt_result`，原字段解析和新语义适配共同使用：当前 session、唯一 receipt、原文件 byte SHA、结构摘要、实际读取范围、当前数据版本与 fingerprint；失败工具结果不产生 checked claim。没有新增 fallback reader 或绕过范围权限。
- `native.py` 从实际 `describe_dataset / compare_periods` 结果建立封闭 claim。记录数、日期端点和含首尾天数、原两期值/差值/相对变化均有精确路径及范围。两工具同时交付，不靠顺序 builder 抢占。未知单位继续未知；百分比是工具明确计算的相对百分比，不能授予百分点、币种、因果或推断强度。分组比较等未承接形状明确拒绝，不自动提升所有数值字段。
- 显示精度与计算精度分开：nongrouped `compare_periods` 在同一原结果新增 `exact_aggregates`，保留原浮点测量，原显示字段仍按工具既定舍入输出。新适配器要求这些原精度字段，核对原差值、显示舍入和零分母/负基数百分比；不从舍入后零值恢复分母，不兼容旧回执缺失精度字段。公开事实值绑定原精度字段，原始百分比路径单独绑定。没有重写统计算法。
- 假设状态重新使用既有 `receipt_verified_hypothesis_measurements / receipt_verified_descriptive_directions / update_hypotheses_from_evidence`。候选必须匹配当前真实计划 ID、当前状态唯一注册的假设集 ID 与产物 byte SHA、原 JSON；`persist_hypothesis_set` 在既有 artifact ref 加 byte SHA，不建新存储。真实测量决定 supported/refuted/contested，公开 renderer 按结构状态显示中文；旧数据、错指标、无原绑定、无据因果、重复回执只留下相关缺口。模型缓存 status 不授予公开强度。
- 业务确认读取现有 ConfirmationStore 的真实 durable events，对照新鲜宿主 ConfirmationRequest 的 session/key/data_version/spec_version/action/params/options；resolved 与有效稳定选项值才产生决定引用，skip/pending/corrupt/stale 拒绝。此引用没有 numeric value 或 claim_ids，不能当成本计算结果。
- `contracts.py / renderer.py` 承接日期/假设派生来源与已核状态、百分比显示；开放审核职责和一次调用预算保持设计值，没有添加散文关键词、正则或同义词补丁。

## 3. 行为验收与未改写失败

`tests/test_trusted_publication_semantics.py` 36 个用例。数据经实际注册工具 `registry.execute` 和既有 AgentLoop receipt producer，未用手写“成功工具回执”替代实际入口。原数据为 12 行、两期各 6 日，amount 前期 60、后期 120、差值 60；这是局部行为 fixture，不冒充原 M01/M06 冻结输入。另有正/负/零/很小非零基数、当前 time-series 真测量、真实持久确认事件。

| 新目录 | 结果 | 含义 |
| --- | --- | --- |
| `tmp/tpub-sem-red-1001-r1` | 28 failed | 新语义模块缺失的需求 RED，不是历史自然收据重放 |
| `tmp/tpub-sem-green-1001-r1` | 81 passed / 11 failed / 1 skipped | 实际工具 fixture 未 discover_tools，unknown tool；仅修正测试初始化，未修改 oracle |
| `tmp/tpub-sem-green-1001-r2` | 92 passed / 1 skipped | 新 semantics + 原 pipeline/facts 核心联合 |
| `tmp/tpub-hyp-origin-red-1001-r1` | 30 passed / 1 failed | 未注册候选假设集被接受，随后补注册身份与原产物摘要核验 |
| `tmp/tpub-sem-green-1001-r3` | 131 passed / 1 skipped，15.99 秒 | 上述三个核心套件 + 既有 hypotheses/confirmation_store/canonical_history_compaction |
| `tmp/tpub-precision-red-1001-r1` | 33 passed / 3 failed | 真实很小非零基数被拒、原精度被显示舍入覆盖、单条来源失效中断独立需求 |

所有 RED 原目录保留，未把失败项补测拼为完整批次。符号链接负例因 OS 无创建权限仍 skipped，不能计通过。现有自然批次原目录在两个指定树下缺失，未重放；本轮 fixture 和脚本决定不能升级为自然语义、表达质量、M01—M06 联合或视觉证据。

## 4. 代码规模与尚缺的承接

新包 912 行：contracts 258、facts 99、native 142、renderer 63、requirements 137、audit 44、service 168、init 1；比上一收据 609 行增加 303。旧 synthesis 5417 + audit 903 + loop 4647 = 10967 行未修改，旧三文件 + 新包 = 11879。相对旧基线的共享替代 helper 增量另计：既有 result_reference 3 行说明、hypotheses 2 行、eda 2 行，共 7；合并增量 919 行。R5 删除/净收缩没有满足，不把文件拆分或新模块局部通过说成债务清理完成。

尚未闭合：真实意图到需求操作的语义接受、需求与事实目标/窗口/单位的完整宿主绑定、其余原生统计/聚合/曲线/Python 族、实际 app 计划来源与假设全谱关系、当前确认请求的相关数据版本派生及只恢复一次、需求历史随规范压缩保留、同步/流式/确认统一终局、保存 revision 原子检查、工作台/导出同身份、旧会话只读与旧权威删除。

当前原文引用沿既有 msg 内容摘要格式；重复相同用户文本无法证明唯一消息身份时拒绝新增，不能猜用另一个 turn。规范 snapshot 参数须由宿主正常历史入口取得；类型/摘要校验本身不能证明调用方已接入真实历史。需求原文定位不证明模型新增/撤回/配对的语言含义，相关整链验收仍待完成。

## 5. 完整离线签收

完整入口 `.venv\Scripts\python.exe scripts\testing\run_regression.py full-offline --run-dir tmp/tpub-e2-1001-r1`，exec session `27774` exit 1：**3090 passed / 1 failed / 2 skipped / 16 warnings、215.09 秒**。唯一失败是新增独立数值 oracle 的 `(b-a)*6` 与浮点求和后相减相差约一个机器精度单位，测试 abs=1e-16 误拒；校准为 rel=1e-14、abs=0，仍不能把很小非零值舍入为零，未改业务预期或放宽产品算术、显示舍入/百分比门。同时删除新适配器未使用的 Decimal 转换。r1 原 JUnit 收据保留：tests=3093、failures=1、errors=0、skipped=2、time=215.067，SHA-256 `87363aaa3ff3a72acbb7cd49e2fb4271bf5536f68f1f78f83ad81f3590ae8894`。

完整新目录 `tmp/tpub-e2-1001-r2`，exec session `80851` exit 0：**3091 passed / 2 skipped / 16 warnings、227.28 秒、Provider initiated 0**。JUnit tests=3093、failures=0、errors=0、skipped=2、time=227.263，SHA-256 `23e0ed7ad3909ed230f0b38f9c8422e7b47be4cabbf6e6425a5f4548a54e4e61`。三套新核心共 101 例，其中 100 passed / 1 skipped；semantics 36 例全通过。r2 完整重跑，未继承或拼接 r1。

两项 skip 为既有 live smoke 与无创建权限的符号链接负例；16 项警告是既有退化统计样本和 JUnit record_property 配置。没有因离线通过而消除其边界。文档链接/围栏、合并代码行数及 git diff --check 已核。完整离线覆盖当前未接入新核心及仍在运行的旧应用，不能签收新 app 切换、自然审核质量、R5 收缩或最终自然测试。HEAD/供体保持第 1 节身份，原 dirty/untracked 保留，未执行 Provider、提交、部署或外部 Git。
