# 已有能力承接清单

当前接续：[S4交接](2026-10-18-s4-handoff.md)；以下保留原合同及证据状态，S4尚未执行。

当前候选424文件437f271efb906fafa9dcf422279aa888bafbba3efa6593a6fef3485ddb46d93f；128已实施并包含于最终整库。S3按127四包本地出口签收，官方full3 7930通过/0失败/2跳过；原180仍118完整/62局部/0待审，不是完成率。自然/视觉/历史缺口保留，105不重开、runtime536，Provider/远端MCP0，S4/S5未开始。

77入口/62能力元数据/22族；28个顶层枚举字段/106个值。当前有限合同逐行核原断言和共享owner，并与一次同源完整JUnit对应；静态if/名称关联不算执行证明，不声称任意输入全组合、自然语义、最终视觉或远端服务执行。

| 入口 | 当前owner | 公开模式 | 有限原合同 | 当前执行证据 |
| --- | --- | --- | --- | --- |
| ab_test | [statistics.py](../../src/data_agent/tools/statistics.py) | method=auto/ttest/mannwhitneyu/chi2；unit_aggregation=sum/mean | A/B四方法及分析单位sum/mean/配对；DID四格原估计和独立方差；SHAP模型前提及版本/完整类别；随机分配/因果假设未验证仍保持。 | 5函数/18实例通过 |
| add_mcp_server | [mcp_tools.py](../../src/data_agent/tools/mcp_tools.py) | transport=stdio/sse/streamable-http | 本地三transport配置必需字段、保存/读回/失败保旧；缓存目录与动态schema；隔离Session stub原isError/返回内容透传及错误，不启动任何远端连接。 | 4函数/33实例通过 |
| analyze_time_series | [eda.py](../../src/data_agent/tools/eda.py) | 按当前公开参数及具名条件 | 分布线性分位数/ddof0/退化未知；相关三方法及全矩阵；漏斗三原算法与auto；cohort日历/月龄；分解sum/mean与时序有效范围；全部按原字段、范围及方法绑定。 | 3函数/9实例通过 |
| apply_type_conversion | [data_clean.py](../../src/data_agent/tools/data_clean.py) | target_type=/datetime/numeric/percentage_to_float/bool/category/date_int_to_datetime/numeric_with_suffix | 七转换及auto、六缺失策略、三IQR、去重后真实行数/新增缺失和独立子对象；坏值/全空未知、失败原子保旧。 | 3函数/30实例通过 |
| ask_user_question | [interaction.py](../../src/data_agent/tools/interaction.py) | 按当前公开参数及具名条件 | 单卡多题逐题归属、仅真实业务歧义暂停、原决定显式引用精确复用/过期/skip；同步流式及原请求竞争唯一终局。 | 2函数/15实例通过 |
| assess_readiness | [data_understand.py](../../src/data_agent/tools/data_understand.py) | 按当前公开参数及具名条件 | 描述/预览/类型建议/质量/就绪/解释/派生原列与实际记录；诊断未知不授方法就绪，真实读表权限和版本不变。 | 2函数/13实例通过 |
| attribution_analysis | [ml.py](../../src/data_agent/tools/ml.py) | 按当前公开参数及具名条件 | 分类三方法/回归四方法及实际holdout/CV独立oracle、原标签/混淆矩阵；forecast auto/backtest原候选及有序留出；SHAP逐类别与当前精确模型/目标/版本。 | 2函数/23实例通过 |
| call_mcp_tool | [mcp_tools.py](../../src/data_agent/tools/mcp_tools.py) | 按当前公开参数及具名条件 | 本地三transport配置必需字段、保存/读回/失败保旧；缓存目录与动态schema；隔离Session stub原isError/返回内容透传及错误，不启动任何远端连接。 | 1函数/4实例通过 |
| causal_analysis | [statistics.py](../../src/data_agent/tools/statistics.py) | method=did | A/B四方法及分析单位sum/mean/配对；DID四格原估计和独立方差；SHAP模型前提及版本/完整类别；随机分配/因果假设未验证仍保持。 | 5函数/15实例通过 |
| classification | [ml.py](../../src/data_agent/tools/ml.py) | method=auto/logistic/rf | 分类三方法/回归四方法及实际holdout/CV独立oracle、原标签/混淆矩阵；forecast auto/backtest原候选及有序留出；SHAP逐类别与当前精确模型/目标/版本。 | 3函数/33实例通过 |
| clean_data | [data_clean.py](../../src/data_agent/tools/data_clean.py) | missing_strategy=keep/drop/fill_mean/fill_median/fill_mode/fill_constant；outlier_strategy=mark/cap/drop | 七转换及auto、六缺失策略、三IQR、去重后真实行数/新增缺失和独立子对象；坏值/全空未知、失败原子保旧。 | 4函数/36实例通过 |
| cohort_analysis | [eda.py](../../src/data_agent/tools/eda.py) | 按当前公开参数及具名条件 | 分布线性分位数/ddof0/退化未知；相关三方法及全矩阵；漏斗三原算法与auto；cohort日历/月龄；分解sum/mean与时序有效范围；全部按原字段、范围及方法绑定。 | 2函数/9实例通过 |
| compare_periods | [eda.py](../../src/data_agent/tools/eda.py) | 按当前公开参数及具名条件 | 分布线性分位数/ddof0/退化未知；相关三方法及全矩阵；漏斗三原算法与auto；cohort日历/月龄；分解sum/mean与时序有效范围；全部按原字段、范围及方法绑定。 | 3函数/4实例通过 |
| confirm_memory | [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | 按当前公开参数及具名条件 | 真实文件/SQLite记忆和候选状态；创建、检索、确认、提取、规则修改的前后原效果/事务/权限；注记不授数据事实。 | 3函数/10实例通过 |
| contribute_decomposition | [eda.py](../../src/data_agent/tools/eda.py) | agg_func=sum/mean | 分布线性分位数/ddof0/退化未知；相关三方法及全矩阵；漏斗三原算法与auto；cohort日历/月龄；分解sum/mean与时序有效范围；全部按原字段、范围及方法绑定。 | 4函数/28实例通过 |
| correlation_analysis | [eda.py](../../src/data_agent/tools/eda.py) | method=pearson/spearman/kendall | 分布线性分位数/ddof0/退化未知；相关三方法及全矩阵；漏斗三原算法与auto；cohort日历/月龄；分解sum/mean与时序有效范围；全部按原字段、范围及方法绑定。 | 5函数/24实例通过 |
| create_chart | [visualization.py](../../src/data_agent/tools/visualization.py) | chart_type=line/bar/stacked_bar/scatter/box/histogram/heatmap/pie/funnel；purpose=exploratory/evidence/insight；aggregation=/sum/mean/median/count；scale_mode=/raw/normalize/index100 | 九图种、三purpose、原aggregation/scale、单多指标/分组/组合标签、选择器与原数据/结果引用、真实HTML/metadata及故障；最终浏览器/PNG视觉保留S4。 | 11函数/151实例通过 |
| create_knowledge_item | [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | 按当前公开参数及具名条件 | 真实文件/SQLite记忆和候选状态；创建、检索、确认、提取、规则修改的前后原效果/事务/权限；注记不授数据事实。 | 3函数/16实例通过 |
| create_memory_candidate | [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | 按当前公开参数及具名条件 | 真实文件/SQLite记忆和候选状态；创建、检索、确认、提取、规则修改的前后原效果/事务/权限；注记不授数据事实。 | 3函数/10实例通过 |
| curve_fitting | [curve_fitting.py](../../src/data_agent/tools/curve_fitting.py) | zero_values=exclude/keep；value_scale=unknown/fraction/percentage_points | 长宽表、原power/exponential/logarithmic三族独立回归公式、零值/成熟度/人数权重/敏感性和同一交付；只在观测内拟合，不授已验证预测。 | 6函数/62实例通过 |
| delete_mcp_server | [mcp_tools.py](../../src/data_agent/tools/mcp_tools.py) | 按当前公开参数及具名条件 | 本地三transport配置必需字段、保存/读回/失败保旧；缓存目录与动态schema；隔离Session stub原isError/返回内容透传及错误，不启动任何远端连接。 | 2函数/15实例通过 |
| delete_skill | [skill_tools.py](../../src/data_agent/tools/skill_tools.py) | 按当前公开参数及具名条件 | 全局隔离目录发现/加载/卸载/启禁/删除实际效果，当前会话加载隔离及源失效；不增加调用或扩权限。 | 2函数/26实例通过 |
| derive_features | [derive_features.py](../../src/data_agent/tools/derive_features.py) | feature_type=time_features/lag_features/rolling_features/ratio_features/bin_features/onehot_encoding | 六feature_type、原排序/lag/窗口/分母零值/onehot类别和实际子列；坏JSON/列冲突原子拒绝、父源保留。 | 3函数/37实例通过 |
| derive_field | [data_understand.py](../../src/data_agent/tools/data_understand.py) | 按当前公开参数及具名条件 | 描述/预览/类型建议/质量/就绪/解释/派生原列与实际记录；诊断未知不授方法就绪，真实读表权限和版本不变。 | 1函数/21实例通过 |
| describe_dataset | [data_understand.py](../../src/data_agent/tools/data_understand.py) | 按当前公开参数及具名条件 | 描述/预览/类型建议/质量/就绪/解释/派生原列与实际记录；诊断未知不授方法就绪，真实读表权限和版本不变。 | 3函数/14实例通过 |
| detect_data_quality | [data_understand.py](../../src/data_agent/tools/data_understand.py) | 按当前公开参数及具名条件 | 描述/预览/类型建议/质量/就绪/解释/派生原列与实际记录；诊断未知不授方法就绪，真实读表权限和版本不变。 | 2函数/11实例通过 |
| disable_mcp_server | [mcp_tools.py](../../src/data_agent/tools/mcp_tools.py) | 按当前公开参数及具名条件 | 本地三transport配置必需字段、保存/读回/失败保旧；缓存目录与动态schema；隔离Session stub原isError/返回内容透传及错误，不启动任何远端连接。 | 2函数/15实例通过 |
| disable_skill | [skill_tools.py](../../src/data_agent/tools/skill_tools.py) | 按当前公开参数及具名条件 | 全局隔离目录发现/加载/卸载/启禁/删除实际效果，当前会话加载隔离及源失效；不增加调用或扩权限。 | 2函数/26实例通过 |
| distribution_analysis | [eda.py](../../src/data_agent/tools/eda.py) | 按当前公开参数及具名条件 | 分布线性分位数/ddof0/退化未知；相关三方法及全矩阵；漏斗三原算法与auto；cohort日历/月龄；分解sum/mean与时序有效范围；全部按原字段、范围及方法绑定。 | 3函数/10实例通过 |
| edit_file | [file_ops.py](../../src/data_agent/tools/file_ops.py) | 按当前公开参数及具名条件 | read/list真实分页及可见文件、write/edit原效果；路径隔离/失败保旧/元数据原件和完整输出；不能冒充上传源或事实。 | 2函数/10实例通过 |
| enable_mcp_server | [mcp_tools.py](../../src/data_agent/tools/mcp_tools.py) | 按当前公开参数及具名条件 | 本地三transport配置必需字段、保存/读回/失败保旧；缓存目录与动态schema；隔离Session stub原isError/返回内容透传及错误，不启动任何远端连接。 | 2函数/19实例通过 |
| enable_skill | [skill_tools.py](../../src/data_agent/tools/skill_tools.py) | 按当前公开参数及具名条件 | 全局隔离目录发现/加载/卸载/启禁/删除实际效果，当前会话加载隔离及源失效；不增加调用或扩权限。 | 2函数/26实例通过 |
| export_conversation | [report.py](../../src/data_agent/tools/report.py) | reply_target=conversation/current_answer | conversation及精确current_answer/reply_id，三格式/图链接/压缩原历史；保存唯一AcceptedAnswer后导出及失败回执，正文不重算。 | 3函数/15实例通过 |
| export_data | [data_io.py](../../src/data_agent/tools/data_io.py) | 按当前公开参数及具名条件 | CSV/Excel/JSON真实格式及SQL只读快照；换版/上传票据/时序精度/三格式导出原值；失败不造新对象或丢旧下载。 | 3函数/29实例通过 |
| export_output | [data_io.py](../../src/data_agent/tools/data_io.py) | output_type=data；fmt=csv/excel/json | CSV/Excel/JSON真实格式及SQL只读快照；换版/上传票据/时序精度/三格式导出原值；失败不造新对象或丢旧下载。 | 3函数/28实例通过 |
| extract_memory_candidates | [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | 按当前公开参数及具名条件 | 真实文件/SQLite记忆和候选状态；创建、检索、确认、提取、规则修改的前后原效果/事务/权限；注记不授数据事实。 | 1函数/3实例通过 |
| forecast | [ml.py](../../src/data_agent/tools/ml.py) | method=auto/backtest | 分类三方法/回归四方法及实际holdout/CV独立oracle、原标签/混淆矩阵；forecast auto/backtest原候选及有序留出；SHAP逐类别与当前精确模型/目标/版本。 | 4函数/8实例通过 |
| funnel_analysis | [eda.py](../../src/data_agent/tools/eda.py) | mode=auto/steps/aggregate/rates | 分布线性分位数/ddof0/退化未知；相关三方法及全矩阵；漏斗三原算法与auto；cohort日历/月龄；分解sum/mean与时序有效范围；全部按原字段、范围及方法绑定。 | 5函数/32实例通过 |
| get_analysis_summary | [analysis_flow.py](../../src/data_agent/tools/analysis_flow.py) | 按当前公开参数及具名条件 | 六入口原文/公开字段/原呈现、canonical原算式、精确目录和正式DAG；同一原件事务及旧协议只读；新事实仅原生回执授权。 | 9函数/43实例通过 |
| interpret_dataset | [data_understand.py](../../src/data_agent/tools/data_understand.py) | 按当前公开参数及具名条件 | 描述/预览/类型建议/质量/就绪/解释/派生原列与实际记录；诊断未知不授方法就绪，真实读表权限和版本不变。 | 3函数/16实例通过 |
| list_data | [data_io.py](../../src/data_agent/tools/data_io.py) | 按当前公开参数及具名条件 | CSV/Excel/JSON真实格式及SQL只读快照；换版/上传票据/时序精度/三格式导出原值；失败不造新对象或丢旧下载。 | 3函数/9实例通过 |
| list_files | [file_ops.py](../../src/data_agent/tools/file_ops.py) | 按当前公开参数及具名条件 | read/list真实分页及可见文件、write/edit原效果；路径隔离/失败保旧/元数据原件和完整输出；不能冒充上传源或事实。 | 3函数/12实例通过 |
| list_mcp_servers | [mcp_tools.py](../../src/data_agent/tools/mcp_tools.py) | 按当前公开参数及具名条件 | 本地三transport配置必需字段、保存/读回/失败保旧；缓存目录与动态schema；隔离Session stub原isError/返回内容透传及错误，不启动任何远端连接。 | 3函数/31实例通过 |
| list_memory_candidates | [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | 按当前公开参数及具名条件 | 真实文件/SQLite记忆和候选状态；创建、检索、确认、提取、规则修改的前后原效果/事务/权限；注记不授数据事实。 | 2函数/7实例通过 |
| list_skills | [skill_tools.py](../../src/data_agent/tools/skill_tools.py) | 按当前公开参数及具名条件 | 全局隔离目录发现/加载/卸载/启禁/删除实际效果，当前会话加载隔离及源失效；不增加调用或扩权限。 | 2函数/6实例通过 |
| load_data | [data_io.py](../../src/data_agent/tools/data_io.py) | 按当前公开参数及具名条件 | CSV/Excel/JSON真实格式及SQL只读快照；换版/上传票据/时序精度/三格式导出原值；失败不造新对象或丢旧下载。 | 3函数/5实例通过 |
| load_skill | [skill_tools.py](../../src/data_agent/tools/skill_tools.py) | 按当前公开参数及具名条件 | 全局隔离目录发现/加载/卸载/启禁/删除实际效果，当前会话加载隔离及源失效；不增加调用或扩权限。 | 2函数/6实例通过 |
| load_sql | [data_io.py](../../src/data_agent/tools/data_io.py) | 按当前公开参数及具名条件 | CSV/Excel/JSON真实格式及SQL只读快照；换版/上传票据/时序精度/三格式导出原值；失败不造新对象或丢旧下载。 | 3函数/14实例通过 |
| preview_data | [data_understand.py](../../src/data_agent/tools/data_understand.py) | 按当前公开参数及具名条件 | 描述/预览/类型建议/质量/就绪/解释/派生原列与实际记录；诊断未知不授方法就绪，真实读表权限和版本不变。 | 3函数/13实例通过 |
| quick_profile | [data_understand.py](../../src/data_agent/tools/data_understand.py) | 按当前公开参数及具名条件 | 描述/预览/类型建议/质量/就绪/解释/派生原列与实际记录；诊断未知不授方法就绪，真实读表权限和版本不变。 | 2函数/20实例通过 |
| read_file | [file_ops.py](../../src/data_agent/tools/file_ops.py) | 按当前公开参数及具名条件 | read/list真实分页及可见文件、write/edit原效果；路径隔离/失败保旧/元数据原件和完整输出；不能冒充上传源或事实。 | 3函数/19实例通过 |
| record_analysis_plan | [analysis_flow.py](../../src/data_agent/tools/analysis_flow.py) | 按当前公开参数及具名条件 | 六入口原文/公开字段/原呈现、canonical原算式、精确目录和正式DAG；同一原件事务及旧协议只读；新事实仅原生回执授权。 | 21函数/107实例通过 |
| record_analysis_spec | [analysis_flow.py](../../src/data_agent/tools/analysis_flow.py) | 按当前公开参数及具名条件 | 六入口原文/公开字段/原呈现、canonical原算式、精确目录和正式DAG；同一原件事务及旧协议只读；新事实仅原生回执授权。 | 7函数/30实例通过 |
| record_answer_targets | [analysis_flow.py](../../src/data_agent/tools/analysis_flow.py) | 按当前公开参数及具名条件 | 六入口原文/公开字段/原呈现、canonical原算式、精确目录和正式DAG；同一原件事务及旧协议只读；新事实仅原生回执授权。 | 9函数/32实例通过 |
| record_data_requirement | [analysis_flow.py](../../src/data_agent/tools/analysis_flow.py) | 按当前公开参数及具名条件 | 六入口原文/公开字段/原呈现、canonical原算式、精确目录和正式DAG；同一原件事务及旧协议只读；新事实仅原生回执授权。 | 7函数/30实例通过 |
| record_evidence_record | [analysis_flow.py](../../src/data_agent/tools/analysis_flow.py) | 按当前公开参数及具名条件 | 六入口原文/公开字段/原呈现、canonical原算式、精确目录和正式DAG；同一原件事务及旧协议只读；新事实仅原生回执授权。 | 16函数/72实例通过 |
| regression_analysis | [ml.py](../../src/data_agent/tools/ml.py) | method=auto/linear/rf/gbrt | 分类三方法/回归四方法及实际holdout/CV独立oracle、原标签/混淆矩阵；forecast auto/backtest原候选及有序留出；SHAP逐类别与当前精确模型/目标/版本。 | 4函数/41实例通过 |
| reload_data | [data_io.py](../../src/data_agent/tools/data_io.py) | 按当前公开参数及具名条件 | CSV/Excel/JSON真实格式及SQL只读快照；换版/上传票据/时序精度/三格式导出原值；失败不造新对象或丢旧下载。 | 2函数/20实例通过 |
| retrieve_knowledge_context | [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | 按当前公开参数及具名条件 | 真实文件/SQLite记忆和候选状态；创建、检索、确认、提取、规则修改的前后原效果/事务/权限；注记不授数据事实。 | 1函数/8实例通过 |
| run_python | [sandbox.py](../../src/data_agent/tools/sandbox.py) | 按当前公开参数及具名条件 | 当前权限/真实读取/显式参数与timeout先核；真实子进程/重放/结构result及完整stdout原件；预算/原件/恢复故障不授虚假数值。 | 3函数/8实例通过 |
| search_knowledge | [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | 按当前公开参数及具名条件 | 真实文件/SQLite记忆和候选状态；创建、检索、确认、提取、规则修改的前后原效果/事务/权限；注记不授数据事实。 | 2函数/11实例通过 |
| segmentation_analysis | [eda.py](../../src/data_agent/tools/eda.py) | 按当前公开参数及具名条件 | 分布线性分位数/ddof0/退化未知；相关三方法及全矩阵；漏斗三原算法与auto；cohort日历/月龄；分解sum/mean与时序有效范围；全部按原字段、范围及方法绑定。 | 2函数/22实例通过 |
| shap_analysis | [statistics.py](../../src/data_agent/tools/statistics.py) | model_kind=auto/regression/classification | A/B四方法及分析单位sum/mean/配对；DID四格原估计和独立方差；SHAP模型前提及版本/完整类别；随机分配/因果假设未验证仍保持。 | 4函数/30实例通过 |
| show_project_rules | [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | 按当前公开参数及具名条件 | 真实文件/SQLite记忆和候选状态；创建、检索、确认、提取、规则修改的前后原效果/事务/权限；注记不授数据事实。 | 2函数/11实例通过 |
| suggest_column_types | [data_clean.py](../../src/data_agent/tools/data_clean.py) | 按当前公开参数及具名条件 | 七转换及auto、六缺失策略、三IQR、去重后真实行数/新增缺失和独立子对象；坏值/全空未知、失败原子保旧。 | 2函数/18实例通过 |
| synthesize_time_series | [multifile.py](../../src/data_agent/tools/multifile.py) | 按当前公开参数及具名条件 | 当前多源自然日对齐与独立来源/版本，缺失和不可比明确；原实际读取/子对象持久化，synthesis不得回读原表。 | 3函数/11实例通过 |
| task_create | [task_tools.py](../../src/data_agent/tools/task_tools.py) | 按当前公开参数及具名条件 | 同会话/项目任务create/get/list/update、依赖及普通生命周期；跨源身份/额外字段/外部依赖原子拒绝；原证据产品仅解锁对应计算。 | 4函数/12实例通过 |
| task_get | [task_tools.py](../../src/data_agent/tools/task_tools.py) | 按当前公开参数及具名条件 | 同会话/项目任务create/get/list/update、依赖及普通生命周期；跨源身份/额外字段/外部依赖原子拒绝；原证据产品仅解锁对应计算。 | 2函数/8实例通过 |
| task_list | [task_tools.py](../../src/data_agent/tools/task_tools.py) | 按当前公开参数及具名条件 | 同会话/项目任务create/get/list/update、依赖及普通生命周期；跨源身份/额外字段/外部依赖原子拒绝；原证据产品仅解锁对应计算。 | 2函数/8实例通过 |
| task_update | [task_tools.py](../../src/data_agent/tools/task_tools.py) | 按当前公开参数及具名条件 | 同会话/项目任务create/get/list/update、依赖及普通生命周期；跨源身份/额外字段/外部依赖原子拒绝；原证据产品仅解锁对应计算。 | 4函数/11实例通过 |
| tool_search | [registry.py](../../src/data_agent/tools/registry.py) | 按当前公开参数及具名条件 | 公开schema/关键词匹配/发现全范围顺序、真实激活；未知名及错误/权限拒绝不扩大范围。 | 4函数/23实例通过 |
| top_n | [eda.py](../../src/data_agent/tools/eda.py) | 按当前公开参数及具名条件 | 分布线性分位数/ddof0/退化未知；相关三方法及全矩阵；漏斗三原算法与auto；cohort日历/月龄；分解sum/mean与时序有效范围；全部按原字段、范围及方法绑定。 | 3函数/7实例通过 |
| transform_data | [data_transform.py](../../src/data_agent/tools/data_transform.py) | operation=filter/select/rename/sort/group_aggregate/resample/pivot/merge；freq=D/W/ME/QE/YE；merge_how=inner/left/right/outer | 八operation、pivot宽长、全部原聚合和五频率/四merge方法；原父血缘、额外源、子快照/独立质量合同、参数优先级和失败回滚。 | 7函数/58实例通过 |
| unload_skill | [skill_tools.py](../../src/data_agent/tools/skill_tools.py) | 按当前公开参数及具名条件 | 全局隔离目录发现/加载/卸载/启禁/删除实际效果，当前会话加载隔离及源失效；不增加调用或扩权限。 | 2函数/26实例通过 |
| update_project_rules | [knowledge_tools.py](../../src/data_agent/tools/knowledge_tools.py) | 按当前公开参数及具名条件 | 真实文件/SQLite记忆和候选状态；创建、检索、确认、提取、规则修改的前后原效果/事务/权限；注记不授数据事实。 | 3函数/14实例通过 |
| what_if_simulation | [simulation.py](../../src/data_agent/tools/simulation.py) | mode=sensitivity/predict/optimize | sensitivity/predict/optimize三方法独立原算式/当前模型/约束和不适用；情景与分配不是干预收益事实。 | 5函数/44实例通过 |
| write_file | [file_ops.py](../../src/data_agent/tools/file_ops.py) | 按当前公开参数及具名条件 | read/list真实分页及可见文件、write/edit原效果；路径隔离/失败保旧/元数据原件和完整输出；不能冒充上传源或事实。 | 3函数/19实例通过 |

[具名原断言及当前JUnit](../../tmp/acu11-final/mode-contract-proof.json)、[实际旧责任引用](../../tmp/acu11-final/private-responsibility-review.json)。verified_topn_producer/_register_topn_contract/_positive_limit/_persist_planning_record无生产引用；原输入校验、同一子合同owner、只读协议及事务连接owner仍有实际职责，不因私有命名删除。

[历史指定切片原文](../../tmp/acu11-final/capability-history-before-final.md)只作保留材料，旧“剩余待核”不再作为当前待办。105组正常链退役审核和全部原断言/内核实例保留；没有重新开启退役审核。
