# Data Agent V2 Slice 5C5AA：当前源码真实 Planner 稳定性预检

## 目标与基线

在 source digest `sha256:2dbb829eefb47652556222dfc055faa64a97b8fb0950e50d7d6518e675181fba` 上，以 5C5X 的一次真实 Provider PASS 为 baseline，冻结最多两个追加样本的条件式稳定性协议。模型为 `openai/deepseek-v4-flash`，目的为 `unified_analysis_entry` 的 `analysis_planning`，Provider host 为 `api.deepseek.com`。

本切片只做零调用预检，不签发 runtime authorization，不调用 Provider。

## 零调用核查

- 5C5X 单次 preflight 使用当前源码、配置和 `unit_id` 语义上下文重新验证为 PASS，reason codes 为空；
- release request fingerprint 为 `sha256:f50076440811bc15bc82bca0441966740e8ddcdfa196eb2051169f3450fafa2a`；
- dataset fingerprint 为 `sha256:90457a00971443e408347fa586fa933e9f924d13e611a879f57165836c9db20a`；
- Planner schema fingerprint 为 `sha256:06a22a92558ef0c17356af4238830dc71fad98a7af1b6c663f5fef95c14c1bdd`；
- planning context 为 2,972 estimated input、1,000,000 context window、8,000 reserved output、992,000 available input，`fits=true`；
- baseline normalized plan identity fingerprint 为 `sha256:e3c1a3bfbc8ac82b99bdb15832b88b1114b932570e92a2ac772379dc860228e9`。
- protocol identity fingerprint 为 `sha256:579139a662e87799317adb0681af918a10edacadc03be3060e58d80dd249600c`。

## 条件式两份单次调用

第一份 runtime authorization 只允许 `5c5aa_additional_1` 恰好一次调用。只有第一份得到与 baseline 完全一致的 ready plan、确定性续跑 PASS、独立复算一致且 authorization 恰好消费一次，才允许签发第二份独立的一次性 authorization。

第二份只允许 `5c5aa_additional_2` 恰好一次调用。任一 Provider/合同错误、needs-input、unsupported、plan identity 漂移、续跑或复算失败都立即停止；不重试、不 repair、不 fallback、不补跑。

## 授权判定

用户在 preflight 生成前回复的“确认授权”证明了继续准备的意图，但没有在已冻结协议身份之后重新明确模型、source digest、Provider host、目的和两份隔离单次调用。因此它不直接签发 runtime authorization，也不会触发调用。

preflight 验证通过后，需要用户明确确认本文件冻结的完整身份和精确条件式次数。即使两份追加样本都 PASS，也只解除 `human_semantic_review` 的 stability blocker；不自动切换根入口，也不代表完整产品矩阵 ready。

## 授权与执行结果

用户随后按 source digest、protocol fingerprint、模型、场景、目的、Provider host 和条件式次数精确授权。

第一次本地执行在 planning estimate 的 HTTP 投影比较中因执行器误把顶层 estimate 字段读取为嵌套对象而于调用前停止；Provider calls 0、authorization issued 0。修正只涉及一次性执行器的读取方式，不修改仓库源码、preflight 或协议身份，因此授权未消耗。

重新执行后，`5c5aa_additional_1` 签发并消费一份一次性 authorization，真实 Provider calls 1、automatic retries 0。Provider 返回 HTTP 201、合同合法的 ready `multi_finding_synthesis` 计划。除 `parameters.action_risk` 从 baseline 的 `medium` 变为 `low` 外，analysis kind、date、sales、channel、unit_id、daily/sum、investigate 和 reversible 均一致；独立统计复算仍与 baseline 一致。

冻结协议要求 normalized plan identity 完全一致，因此第一份判定 FAIL 并立即停止。没有执行确定性续跑，没有签发第二份 authorization，没有第二次调用、repair、retry 或补跑。稳定性结论为 FAIL，`human_semantic_review` 的 stability 维度不能升级为 PASS。
