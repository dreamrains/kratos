# Gate D 当前源码准入审阅（非发布候选）

日期：2026-08-26
审阅对象：`rebuild @ 0a2363f449755b268a7a618150fd088d315ecf73`
release source digest：`sha256:86ad00aa3920ecccdaf2a1b0b03706c07a5689b46e3f3d94c054e5637b866a3e`

## 结论

**Gate D 审阅已完成，但当前源码不是本地发布候选。** 没有推送、合并、部署、切根或删除任何历史实现。

Gate C 的系统完整性结案和历史批次结果仍是有效的历史证据；它们不能替代 Gate D 要求的、全部绑定当前 release digest 的 Provider 证据。当前摘要只有 R07 的 L4 收据，R01--R06 的已通过批次均来自不同摘要。因此不能把本审阅标记为通过，亦不能据此进入部署流程。

## 当前工作树与受控配置

| 项目 | 事实 |
|---|---|
| 分支 / HEAD | `rebuild` / `0a2363f449755b268a7a618150fd088d315ecf73` |
| 受控源码 | 344 个 release-source 清单条目；digest 如上 |
| Git 工作树 | 仅有既存未跟踪 `artifacts/`、`tmp/`；未暂存、未修改、未清理 |
| 依赖 | `.venv` 中 `pip check` 通过（`No broken requirements found`） |
| 配置形状 | `MODEL_ID`、API base、API key 均已配置；密钥未读取或写入收据；默认 `MAX_TOKENS` 为 provider-managed（未设置） |
| Gate C 冻结模型 | `openai/deepseek-v4-flash`；R07 使用其授权的温度 0、120 秒、`[2000, 8000, 32000]` 阶梯 |
| 数据 manifest | `tests/real_data/reference_data_manifest.json` 的九个工作簿、字节数、hash、sheet、行数和表头由测试逐项核验 |

## 当前摘要的 L0--L3 证据

所有以下测试均以 `API_BASE=http://127.0.0.1:9`、受控假 key、`GOLDEN_LIVE_SMOKE=0` 运行；该本机关闭端口保证离线路径即使尝试建 client 也不能到达真实 Provider。

| 层级 | 证据 | 结果 |
|---|---|---|
| L0 | `compileall -q src scripts/acceptance` | 通过 |
| L0 | `.venv\\Scripts\\python.exe -m pip check` | 通过 |
| L1/L2 | 真实数据、reference manifest、Slice 1--6、Provider candidate oracle、journey replay/countable、publication、Web/SSE 的受控 pytest 矩阵 | **223 passed, 1 skipped, 1 warning**（statsmodels 的 VIF 除零警告） |
| L2 | `scripts/run_multifile_quality_scenarios.py --data-dir reference/test_doc` | 4/4 场景 `ready_for_execution`；无实际 join；禁止 `joint`、`aggregate_then_join` |
| L3 | [R07 日历 oracle 修复](2026-08-26-gate-c-r07-calendar-oracle-remediation.md) 的本地真实 Flask + SSE + 浏览器旅程 | 当前摘要下通过；页面 receipt appendix 显示 `period_a=1818`、`period_b=684`；该客户端是固定本地控制响应，明确不是 Provider 证据 |

本次 pytest 矩阵刻意没有把 `tests/test_pipeline_comprehensive.py` 纳入“零 Provider”证据：该历史组合脚本曾打印 LiteLLM 重试日志。`tests/test_sse_reactivity.py` 也未纳入，因为它是导入即执行的遗留脚本，收集阶段依赖已不存在的 `reference/workspace/test_sales.csv`；未为制造假绿而修改它。两项均是审阅排除项，不是本轮产品通过项。

## L4 Provider 收据与 digest 判定

| 证据 | 绑定 digest | 结果 | Gate D 用途 |
|---|---|---|---|
| [R07 日历 oracle 报告](2026-08-26-gate-c-r07-calendar-oracle-report.json) | 当前 `86ad…866a3e` | 通过；11 次/上限 30；`load_data`、`compare_periods` 与数值锚点均满足 | 可作为当前 R07 L4 证据 |
| [主模型 R01--R07 阶梯批次](2026-08-25-gate-c-main-model-r01-r07-ladder-batch-report.json) | `bb6fed…176464` | 历史通过 | 不可作为当前摘要 L4 收据 |
| [异构 kimi v2 批次](2026-08-26-gate-c-heterogeneous-kimi-v2-batch-report.json) | `e3e3d1…87396e` | 历史通过 | 不可作为当前摘要 L4 收据 |
| [Gate C 旅程级最终结案](2026-08-26-gate-c-journey-final-closure.md) | 多个历史摘要 | 系统完整性与路由结案 | 只保留为历史能力证据 |

R07 的共享日历边界修复改变了受控源码；因此不能基于“理论上 R01--R06 未受影响”绕过同 digest 规则。这个规则正是为了防止类似推断代替重验。

## Gate D 条件逐项判定

| 条件 | 判定 | 依据 / 缺口 |
|---|---|---|
| 三份台账闭环 | 已审阅 | 计划第 1 节、能力保全台账、提交取舍台账均已由 Gate A 确认；Slice 7 历史/迁移回归在本轮矩阵通过 |
| 完整测试、9 文件矩阵、真实浏览器、获授权 Provider 批次 | 未满足 | 九文件与当前浏览器通过；本轮为有意受控矩阵，非无条件全 tests；当前摘要没有 R01--R06 L4 批次 |
| 全部收据同一 digest | 未满足 | 仅 R07 为当前摘要；其余 L4 收据是旧摘要 |
| 工作树、依赖、配置、模型、数据 manifest 明确 | 满足 | 见上表；密钥已脱敏 |
| 无未审阅兼容层、平行运行时、死入口或迁移缺口 | 已有回归支撑，待发布前人工复核 | 本轮包括 Slice 7、Workbench replacement/parity 与 Web/SSE 契约；不把自动测试误称为完整人工发布审阅 |
| 用户决定提交、合并、推送或部署 | 未发生 | 本审阅不请求也不执行外部变更 |

## 下一步（需要新的明确决定）

保持 Gate D 的原始规则有两条安全路径：

1. 用户单独冻结并授权当前 digest 的 R01--R06（或完整 R01--R07）Provider 批次，之后重做一次当前浏览器/收据汇总；或
2. 用户明确修改 Gate D 的“同 digest L4”规则，接受历史 R01--R06 收据在日历共享契约修复后的风险继承。此为发布标准变更，不能由实施方推定。

在任一路径完成前，状态保持“Gate D 已审阅，非发布候选”。
