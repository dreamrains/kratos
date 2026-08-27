# Gate C 发布综合契约修复（离线）

日期：2026-08-26
受控源码摘要：`sha256:d8a30eaa838611836447df7b932a1c1e830efa0b5e5270f3a26c35e655f33b8b`

## 触发事实

R07 与 R09 的最新真实收据均已执行所需工具，却仍未满足最终数值锚点。此前的 `tools=None`、DSML 正文拒绝和一次纠正轮分别解决了工具循环与伪工具标记，不能保证模型从长工具历史重建已验证数值。

## 本次共享契约

本修复不引入 V2/planner/store/workbench。它扩展既有 `AnalysisSessionState` 与工具 receipt：

1. 成功工具的结构化 `ToolResult.data` 被压缩为有限 `publication_facts`，与原 receipt 的 hash、工具名和预览一起保存。旧 JSON 字符串工具在共享 `ToolResult` 边界解析为 `data`，不要求为每个旧工具另建返回通道。
2. 收尾前只从**本 turn**的成功实质工具收据构建 `publication_synthesis.v1` 包；旧 turn 的 receipt 不得混入。
3. 最终化模型仍可推理和撰写解释，但接收的是受限、标为不可信指令的已验证证据包；工具 schema 仍关闭。
4. 每个已执行实质工具的终端回答都走该发布边界，不依赖到达 `WRAP_UP_ROUND`；发布时将模型解释与由 receipt 渲染的“已验证计算结果”合并，并把合并后的正文持久化后才发送 SSE；模型漏写数字不能抹去计算结果。
5. 无成功实质 receipt 时包为 `incomplete`，维持既有不强制发布行为；不会用模型文本伪造证据。

该契约把“工具成功”与“可发布证据”分开：解释仍由模型完成，事实、数值和来源由程序传递与展示。

## 离线门禁

- `tests/test_publication_synthesis.py`：曲线参数/拟合度/样本量、期间比较数值、跨 turn 隔离、状态往返持久化、流式发布正文、非强制收尾的终端发布、结构化 JSON 摘要不泄露原始数组。
- `tests/test_analysis_quality.py`：增加注册表执行 `compare_periods` 的回归；发现并修复原装饰器误绑到 `_recommend_statistical_test` helper 的上游缺陷。
- `tests/test_route_a_journey_countable.py` 与 `tests/test_route_a_journey_replay.py`：现有最终化、DSML 纠正、有界轮次和可数旅程不回退。
- 组合回归：`157 passed, 8 skipped`；`compileall src` 与本地验收启动器编译通过。

## 真实本地浏览器门禁

通过真实运行的 localhost Flask 进程和浏览器完成一次本地桩旅程：输入问题 → SSE → `load_data` → 真实 `compare_periods` → 持久化 → 页面渲染。桩仅决定三轮工具/终端响应，真实工具、会话、SSE 和 Workbench 均为产品代码；未传输用户文件，也未调用 Provider。

页面确认模型的因果边界解释旁出现“已验证计算结果”，并从 `compare_periods` receipt 显示 `metrics.售价.period_a=1773`、`metrics.售价.period_b=639`、`diff=-1134`、`change_pct=-63.96`；JSON 日期数组未进入最终正文。

### R07 oracle 差异（阻止新的 Provider 授权）

该浏览器旅程使用 R07 同一受控工作簿 hash `9475ab...23d4d3` 和相同的两个 15 天边界。真实 `compare_periods` 输出为 `1773/639/-1134`，而冻结 R07 candidate 仍要求 `1818/684/71/30`；两个期间各相差 `45`。历史 countable replay 仅让脚本化模型文本写入旧锚点，并未将真实工具 JSON 与 candidate oracle 对账，故不能证明旧锚点是当前工具口径。

这不是可以由模型推理、温度或 token 预算解决的问题。下一步须由用户确认采用哪一个可审计口径（修正 candidate 为真实工具结果，或修正工具/数据后重新计算）并重新冻结数据、prompt 和 source digest；在此之前不得发起新的 R07 Provider 授权。

本次 Provider 调用：`0`。这是当前源码的真实本地浏览器/本地桩证据，不是真实 Provider 通过声明。

## 后续边界

下一步先处理上述 R07 oracle 决策；R09 的 oracle 也应使用同一“真实工具结果对账”门禁复核。两者重新冻结后，才可冻结一次 Provider 最终化传输 canary；canary 成功后才能为 R07/R09 重新申请精确旅程授权。
