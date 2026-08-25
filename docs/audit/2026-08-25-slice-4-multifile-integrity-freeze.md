# Slice 4 多文件完整性冻结收据（Provider 除外）

日期：2026-08-25

## 源码与边界

- 基线提交：`3003030f6aaed7b06352397c6fce9a844821ee7a`。
- 当前受控源码摘要：`sha256:23c5692c93a50674ff253ae99f3a37ce872c3c7a9910bd7859ee47a7c745d77b`（319 条）。
- 未调用真实 Provider；未触碰 `artifacts/`、`tmp/`。

## 交付

1. Workspace 增加 `derive_multi`：派生版本记录全部父版本 ID 与多源表达式，不创建平行数据 store。
2. 新增 `synthesize_time_series`：只有明确列出的数据集、日期列和指标才能按日期聚合/并列对齐；输出每源 identity、覆盖区间、有效行数和对齐缺失数。
3. 工具不推断实体级业务 join；many-to-many、缺键或时间不可比关系继续由既有 relationship validation 拒绝或诊断，不能成为 material claim 的依据。
4. 新能力进入现有 EDA 工具组和 capability registry，provider-neutral 路由可达。

## 真实数据 oracle

- R04：D06 `游戏A激励视频汇总数据报表.xlsx`、D07 `游戏A内购数据.xlsx`、D08 `游戏Abanner汇总数据.xlsx` 各有 248 个日期。按 `日期` 聚合 `视频广告收入`、`内购收入`、`BN_广告收入` 后，对齐结果为 248 行，三列均无对齐缺失，派生版本有 3 个父版本 ID。
- R05 风险 oracle：`省钱卡订单.xlsx` 与 D01 的 `user_id` 关系为 many-to-many，保持 rejected 与 `many_to_many_join_explosion`，不物化 join。

## 验证

- `pytest tests/test_slice4_multifile_integrity.py tests/real_data/test_multifile_analysis_quality.py tests/real_data/test_multifile_real_data_scenarios.py tests/test_multifile_regressions.py tests/test_slice3_method_integrity.py tests/test_slice2_workspace_versions.py tests/test_web_overhaul.py -q`：`138 passed`。
- 未将 fixture、test_client 或离线契约冒充真实 Web/Provider 验证；Slice 4 的真实 Web 多文件旅程留待 Workbench 收口的五条浏览器旅程一并验证。
