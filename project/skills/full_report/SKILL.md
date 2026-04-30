---
name: full_report
description: "完整分析报告模板 — 7 阶段全自动分析流程"
version: "1.0"
trigger_keywords: "报告,完整分析,全面分析,出报告,全量分析"
tools_required:
  - describe_dataset
  - detect_data_quality
  - assess_readiness
  - clean_data
  - analyze_time_series
  - correlation_analysis
  - distribution_analysis
  - attribution_analysis
  - segmentation_analysis
  - generate_report
task_template:
  - id: T1
    tool: describe_dataset
    params: {name: main}
    depends_on: []
  - id: T2
    tool: detect_data_quality
    params: {name: main}
    depends_on: []
  - id: T3
    tool: assess_readiness
    params: {name: main}
    depends_on: ["T1", "T2"]
  - id: T4
    tool: analyze_time_series
    params: {name: main}
    depends_on: ["T3"]
  - id: T5
    tool: correlation_analysis
    params: {name: main}
    depends_on: ["T3"]
  - id: T6
    tool: distribution_analysis
    params: {name: main}
    depends_on: ["T3"]
  - id: T7
    tool: attribution_analysis
    params: {name: main}
    depends_on: ["T4", "T5"]
  - id: T8
    tool: segmentation_analysis
    params: {name: main, n_clusters: 3}
    depends_on: ["T3"]
  - id: T9
    tool: generate_report
    params: {name: main}
    depends_on: ["T4", "T5", "T6", "T7", "T8"]
---

# 完整分析报告模板

## 分析阶段

### 阶段 1：数据探索与质量评估（T1-T3）
- describe_dataset：理解表结构、字段类型、数据量
- detect_data_quality：缺失值、异常值、重复记录检测
- assess_readiness：数据就绪度综合评估，识别阻塞和警告项
- 如果 assess_readiness 发现 Block 级问题，必须用 ask_user_question 向用户确认后再继续

### 阶段 2：趋势与分布分析（T4-T6）
- analyze_time_series：关键指标的趋势、季节性、突变点
- correlation_analysis：指标间相关性，标记高相关对
- distribution_analysis：数值列的分布特征（偏度、峰度、分位数）

### 阶段 3：驱动分析与分群（T7-T8）
- attribution_analysis：识别目标变量的关键驱动因素
- segmentation_analysis：基于特征的用户/数据分群

### 阶段 4：报告生成（T9）
- generate_report：汇总所有分析结果，生成完整报告
- 默认使用 detailed 风格，如用户要求简洁则用 executive 风格

## 注意事项
- 每个阶段完成后用 task_update 标记为 completed
- 如果某工具报错，尝试用替代方法或 ask_user_question 请求指导
- 分析过程中发现的洞察需要遵循多假设竞争规则
