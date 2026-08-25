# Slice 3 统计方法完整性冻结收据（Provider 除外）

日期：2026-08-25

## 源码与边界

- 基线提交：`46866b5cbe1b656434b7aaa7d1d965aa8bae57bd`。
- 当前受控源码摘要：`sha256:dbec018126c82fca686530af20d7598f6c322c2a28eda02a5e4c151227b117f2`（317 条；`src`、`scripts`、`tests`、入口和依赖清单）。
- 没有真实 Provider 调用；没有推送、合并、部署、切根或清理 `artifacts/`、`tmp/`。

## 交付

1. 新增共享 `analysis_method_result.v1` 契约：数据版本 identity、有效样本、方法参数、状态/原因、限制和 claim ceiling 由确定性工具输出，不建第二个 planner/store/workbench。
2. 新增 `curve_fitting`：幂律、指数、对数三族在原始尺度比较 SSE/R²；输出零值排除数，明确为描述性结果，不外推、不作因果断言。
3. 既有 `forecast` 保留名称和 JSON 返回兼容性，改为有序留出回测，在 naive-last-value 与 linear-trend 基线之间选取，并输出短期区间、验证窗口和时间缺口失败原因；不再把样本内拟合当验证。
4. 既有 `attribution_analysis` 保留名称和 JSON 返回兼容性，接入恒等式/共线性检查、HC3 稳健估计、Holm 校正，以及无稳定因素时的双变量描述性降级。
5. 分类/回归所训练模型记录当前数据 identity、特征和模型类型；SHAP 与 predict 模拟拒绝使用不同数据版本或隐式自动训练的模型。解释和模拟均受 associational 边界约束。

## D09 真实数据 oracle

- 数据：`reference/test_doc/游戏B留存.xlsx`，manifest SHA256 `63f72f645b34f2ca5456871fabd2a2785d2cf14c5a8ae147d344e85d2f5cbbe0`，62 行、日期 2020-07-01 至 2020-08-31。
- 宽表留存曲线的 10 个有效 horizon 中，30 天列排除 6 个零值并披露。
- 幂律为最佳族：`a=0.18800129`、`b=-0.71667274`、原始尺度 `R²=0.98240474`；这只是当前观察范围内的描述性曲线。

## 验证

- `pytest tests/test_slice3_method_integrity.py tests/test_tool_recovery.py tests/test_slice2_workspace_versions.py tests/test_pipeline_comprehensive.py tests/test_phase_comprehensive.py::TestPhase2ToolParameterUpgrade tests/test_web_overhaul.py -q`：`220 passed`。
- `python tests/test_tools_comprehensive.py`：`104 PASS, 0 FAIL`。
- `compileall`、模块导入与 `git diff --check` 通过。
- 真实本地 Flask 进程 + 浏览器：在隔离的 `tmp/slice3-browser-5133` 运行目录打开当前源码，上传真实 D09；DOM 显示 `游戏B留存.xlsx` 与 `1 个文件已附加`，console error 为 0。未发送提问，因此未调用 Provider；此证据只证明真实 Web 上传入口，不冒充 Provider 或模型质量验证。

## 未计入通过的项

- 完整 `pytest -q` 两次在约 9% 后无 CPU 进展且未返回退出码；已停止本轮启动的挂起进程，故不将其表述为完整回归通过。
- Gate C 的真实 Provider 场景、真实模型路由质量与最终发布候选仍未完成，均需独立精确授权。
