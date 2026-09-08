# 回复内容优化实施记录

日期：2026-09-08｜分支：`codex/answer-content-optimization`｜实施基线：`85f62794e24cfa95a864293d159e0208c8615a4b`

## 交付范围

本次实现处理诊断中可以由当前运行时可靠修复的四个根因：终局复用旧预览包、业务事实过早裁剪、明确子问题在正文中遗漏、可局部判定的数量级错误；同时解除普通分析默认 `light` 和固定 `2-4` 小节带来的表达压缩。实现沿用现有 `AgentLoop`、`AnalysisSessionState`、发布包、验证和一次修订链，没有增加 Provider 调用或第二套状态机。

## 实际变更

- 预览包标记为 `phase=preview` 且不持久化；终态在验证完成后必定按最后收据、证据、分析规格和验证报告重建 `phase=final` 包。
- 发布包升级为 `publication_synthesis.v2`，增加全内容 `snapshot_digest`；正式包增加 `answer_sha256`，同一包 id 继续由状态层幂等更新。
- 工具收据最多保留 500 个受控事实候选；最终 prompt 再按来源预算选择。Python stdout 按行保留，执行代码、hash、replay、risk label 等审计元数据不再挤占业务事实预算。
- 分组路径按自然数字顺序排序；明确“全部分组”请求可保留 12 组 `name/count/revenue` 的完整事实组。
- 对高置信度的编号需求和简短“请回答 A 和 B”请求生成 `requirements`；正文必须给结果或具体缺口。复杂自由文本保持未评估，避免虚假的 100% 覆盖率。
- 新增受限算术检查，仅检查正文显式写出的乘法或“基数 × 百分比 = 人数”关系，允许正常舍入并识别“万”单位；日期、版本号和未表达的运算不作自动结论。
- 普通分析深度改为 `standard`；明确简短模式仍由既有 terse 规则控制。回答结构按内容选择表格、列表和小节，不再限制为 2-4 节。

## 验证证据

### 定向回归 E1/E2

命令：

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
..\..\.venv\Scripts\python.exe -m pytest `
  tests/test_publication_synthesis.py tests/test_synthesis_policy.py `
  tests/test_sse_publication_order.py tests/test_artifact_publication_contracts.py `
  tests/test_compact_preservation.py tests/test_prompt_system.py `
  tests/test_prompt_injection_safety.py tests/test_p08_boundary_finalization.py `
  tests/test_p08_tool_message_integrity.py -q -p no:cacheprovider
```

结果：`226 passed`。

### 完整离线回归 E2

第一次运行使用自动生成的长目录，结果 `47 failed, 2445 passed, 62 skipped`。失败分类为：独立 worktree 没有 Git 忽略的 `reference/test_doc/*.xlsx` 夹具；Windows 长路径造成上传临时文件失败；一项旧测试仍期待普通分析为 `light`；以及上述夹具/旧断言引出的关联失败。该次结果不计为通过，也未归因于产品功能。

补入主工作树中相同的九个只读、Git 忽略夹具，更新深度策略断言，并使用短的新隔离目录后执行：

```powershell
..\..\.venv\Scripts\python.exe scripts/testing/run_regression.py full-offline --run-dir tmp/r2
```

结果：`2553 passed, 1 skipped, 16 warnings`，退出码 0，JUnit：`tmp/r2/junit.xml`。脚本设置 `DATA_AGENT_REAL_PROVIDER_NETWORK_ENABLED=0`、无效本地 `API_BASE` 并声明 `provider_calls=forbidden`；该结果不证明真实浏览器、真实 Provider、部署或生产环境通过。

## 变更后文件摘要

| 文件 | SHA-256 |
|---|---|
| `src/data_agent/agent/loop.py` | `1BBE8695225A8D878713C1723C313D110F47AB773449DFC4994547836A757FD9` |
| `src/data_agent/agent/publication_synthesis.py` | `BBE564A6A95420918414A8BFC8DCD5DEA28349AF67E5F6A2575919562F125755` |
| `src/data_agent/agent/synthesis_policy.py` | `3E39E69F0C5EC1F96884CFA91D6794AE6906360C592ABB27B6D95685A4A431E5` |
| `src/data_agent/agent/prompts.py` | `3A63A1B99A74885632B862A7C551655E537BF8983AD04CDFC72E71EB459107F1` |
| `tests/test_publication_synthesis.py` | `48FB91588FF154C7B9AAF8CAF32DA678BCD9ACF7B556B7F219B687D81275CE3C` |
| `tests/test_synthesis_policy.py` | `D351A3CCBA450DB65CDEC0844EE04CEE4162EDE5355B48EF63DE8E50D2B0872E` |
| `tests/test_execution_control.py` | `41CF425D0E18AE962BE07923E402EE0096CAAD30908E7DBCAAB5ECC6C1EFA213` |

## 尚未形成的证据

- 没有启动本地真实浏览器，因此移动端 Markdown、图文就近呈现和刷新/导出的 E3 证据仍为 `not_run`。
- 没有调用真实 Provider；五月与九月真实回答的自然语言丰富度改善仍需另行冻结输入、模型、源码和预算后验证。
- 自动需求覆盖只处理高置信度结构；复杂自由文本、同义改写与跨来源语义绑定仍为 `unassessed`，不会被伪装成已检查。
- 自动算术只覆盖显式、局部可解析的乘法和百分比人数换算；百分点、相对变化、币种与跨版本绑定仍依赖现有来源边界和后续专门契约。

## 合并说明

此分支基于 `85f62794e24cfa95a864293d159e0208c8615a4b` 创建。当前分支不要直接覆盖主工作树中并行修改的 `loop.py`；合并时按函数块解决冲突，保留主分支后续的确认策略与 P08 终局改动，再运行同一完整离线命令。Git 忽略的 `reference/test_doc` 与 `tmp/r2` 只用于本地验证，不进入提交。
