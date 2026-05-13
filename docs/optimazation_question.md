一、如果我是一个缺少数据分析技能的用户

  我期望这个 agent 能帮我解决以下问题：

  核心诉求：我有一个业务问题，有数据，但不知道怎么从数据里找答案。

  1. "帮我看这份数据能告诉我什么" — 我可能连问题都提不出来，只是直觉数据里有价值但不会挖。我期望 agent
  主动告诉我"你的数据里值得关注的是 X"。
  2. "上个月收入为什么跌了" — 我有明确问题但不知道用哪个分析方法、怎么拆解。我期望 agent
  自己选择合适的分析方法，并把结论翻译成我能懂的语言（别说 p 值，告诉我"因为渠道 A 流量掉了 30%"）。
  3. "这波营销活动值不值" — 我需要做决策，我期望 agent 给出有信心的判断（"值/不值"），而不是含糊的"数据表明可能有效果"。
  4. "帮我生成一份数据报告给老板看" — 我期望输出是能直接发给别人的、结构清晰的报告，而不是一堆代码和技术输出。
  5. "预测下季度能做多少" — 我期望 agent 能做预测，但也会告诉我预测的可靠性限制。
  6. "这些用户的行为有什么规律" — 我期望 agent 能主动发现我没想到的洞察，而不是我问一句才动一下。

  ---
  二、从审视者角度的诊断分析

  以下按照你要求的维度，逐一分析缺陷和改进方向。按严重程度排序。

  1. 会话设计缺陷

  问题 A：意图分类过于依赖关键词匹配，鲁棒性不足

  intent.py 的 plan_turn_intent 完全基于关键词集合做硬匹配（_CHAT_KEYWORDS, _ANALYSIS_KEYWORDS
  等）。当用户说"我怀疑这个数据不太对"时，既不命中知识问答，也不命中分析关键词，最终走 LLM fallback
  或默认兜底。关键词方案有两个致命问题：
  - 用户语言是无限的，关键词集合永远覆盖不完
  - 关键词之间有优先级冲突——当前用 if-elif 链式判断，顺序调参困难，且后面的规则被前面的规则"吞掉"

  问题 B：conversation 模式不传任何工具，连数据查询都不能做

  prompts.py:311-321 conversation 模式只注入 rules，不注入 session_context（等等，实际注入了），但关键是 available
  tools: none。当用户在对话中说"上次分析的结论是什么"，agent 无法调用工具回顾
  evidence_records，只能靠上下文文本。上下文被 compact 后，这些信息可能丢失。

  问题 C：会话恢复不重建 analysis state 到 context

  loop.py:267-289 restore_object_context 恢复了 workspace 和 knowledge，但 analysis_state 的加载在 __init__ 里做（line
  222），restore_object_context 不重新加载。如果 session 恢复时 __init__ 先跑、restore_object_context 后跑，且
  project_name 变化了，analysis_state 可能用了错误的 project。

  2. 工具设计缺陷

  问题 A：工具参数大量使用 string 类型传递 JSON，增加出错率

  interaction.py 的 ask_user_question 工具中，options 参数是 string 类型，期望 LLM 传入 JSON 字符串如 [{"label": "A",
  "description": "..."}]。这在 LLM 实际调用中经常出问题——JSON 格式错误、引号转义、中文字符等。同样的问题出现在 questions
   参数。工具层面虽然有 json.loads 的 try-catch，但错误信息不友好，LLM 经常重试同样的格式错误。

  类似地，transform_data 的 group_aggregate 模式也依赖字符串格式约定（group_by: 列名, agg: 列A: [sum, mean]），这种"伪
  DSL"对 LLM 来说理解成本高且容易出错。

  问题 B：工具描述不够 LLM-friendly

  很多工具描述偏人类文档风格（"支持 CSV、Excel、JSON 格式"），缺乏对 LLM
  决策有用的结构化信息：什么情况下应该调用这个工具、什么情况下不应该、输入输出的精确格式。LLM
  需要的是决策规则，不是功能介绍。

  registry.py:315-343 的 _build_schema 从函数签名自动生成 JSON Schema，但生成的 schema 缺少 description 字段（除非用
  schema_overrides 手动指定）。LLM 看到的是 "source": {"type": "string"} 而不知道 source 是什么。

  问题 C：工具粒度不均匀

  run_python 是一个万能兜底工具，但缺乏有效的使用边界。prompt 里说"仅当结构化工具无法满足时"，但 LLM 经常走捷径直接调
  run_python，尤其在面对复杂需求时。同时，缺少一些高频需要的轻量工具：
  - 没有直接的数据概览/自动探索工具（需要连续调 quick_profile + interpret_dataset）
  - 没有数据对比工具（A/B 对比需要手动调 compare_periods + 配参数）
  - 缺少数据拼接/合并工具

  问题 D：ToolCapability 系统设计完善但未被充分利用

  registry.py 定义了详细的 ToolCapability（problem_types, input_contract, output_contract, dependencies,
  fallback_tools），但实际在 agent loop 中几乎没有使用这些信息做决策。_activate_capabilities_from_state 只在
  analysis_spec 有 method_plan 时才触发。工具选择完全依赖 LLM 自己判断，没有利用 capability metadata
  做工具推荐或工具链编排。

  3. 工具调用缺陷

  问题 A：错误恢复策略机械重复

  loop.py:1299-1311 每次工具错误都追加相同的 4 条恢复建议。连续错误时，LLM
  上下文被大量重复的"检查参数是否正确"占满，没有基于错误类型的差异化处理。比如 FileNotFoundError
  应该建议检查路径，KeyError 应该建议检查列名，TypeError 应该建议检查数据类型。

  问题 B：工具执行是串行的

  _loop_impl 的工具执行是 for 循环逐个执行（line 1229），即使同一轮 LLM 返回多个独立的工具调用也无法并行。对于数据加载 +
   描述统计这种独立操作，串行执行浪费时间。

  问题 C：工具分组激活过于保守

  analysis_flow_controller.py:165-197 的 activate_tool_groups 在 intent_negotiation 和 data_requirement 模式下只激活
  knowledge 和部分 eda。如果用户在协商阶段就问了"这数据有没有异常值"，agent 没有 detect_data_quality 工具（在 eda
  分组但被限制了）。

  4. 数据分析流程缺陷

  问题 A：Playbook 选择过于简化

  method_playbooks.py:463-486 的 _choose_primary 使用简单的关键词匹配选择 playbook。"预测"永远映射到
  forecast_decision_simulation，但用户可能是想预测用户流失（应该用
  retention_lifecycle）。关键词匹配无法理解用户意图的语义。

  问题 B：分析流程缺乏自适应反馈

  AnalysisSessionState 的 stage 单向推进（discover → scope → plan → execute →
  report），但缺乏基于分析结果回退的机制。比如 execute 阶段发现数据质量问题，应该回退到 scope
  重新定义分析范围，但当前设计中 stage 的变更主要由 intent 驱动而非分析结果驱动。

  问题 C：数据加载后的自动探索不够智能

  加载后只有 quick_profile + interpret_dataset，不会自动做数据质量评估（detect_data_quality
  需要单独调用）。对于非专业用户，他们不会想到要主动说"检查一下数据质量"，agent
  应该在数据加载后自动运行质量评估并报告问题。

  问题 D：分析结果缺乏"可信度校准"机制

  虽然 prompt 要求输出"置信度"，但没有机制校验 LLM 给出的置信度是否合理。agent 可能在样本量只有 10
  个的情况下给出"高置信度"结论。缺少基于统计量的自动置信度评估（如最小样本量检查、p-value 检查、effect size 检查）。

  5. 提示词设计缺陷

  问题 A：prompt 信息注入过多，信噪比低

  _get_system_prompt 最终拼出的 system prompt 可能包含：
  - 基础 prompt（~1000 tokens）
  - ANALYSIS_ENGINE（~500 tokens）
  - turn_intent prompt（~300 tokens）
  - project_rules + domain_knowledge + experience_log（可变）
  - session_context + analysis_state（可变）
  - skill instructions（可变）
  - execution_control hint（可变）
  - Mermaid reference（~100 tokens）

  对于简单操作（"汇总一下销售总额"），这些信息大部分是噪音，浪费 token 且干扰 LLM 的注意力。

  问题 B：ANALYSIS_ENGINE 和 AGENT_ANALYSIS 有信息重复

  AGENT_ANALYSIS 里写了"工具选择规则"和"分析流程5步"，AGENT_ANALYSIS_ENGINE
  又写了"分析策略表"和"多视角思考"。两者的信息有重叠且没有清晰的层次划分。LLM
  需要在两个区块之间交叉引用才能形成完整的决策图景。

  问题 C：缺少"用户画像"引导

  prompt 知道用户"通常缺少专业数据分析知识"（AGENT_ANALYSIS line
  110），但没有根据用户在会话中表现出的技术水平动态调整输出复杂度。第一个问题和第十个问题的回答应该有不同的详细程度，但
  prompt 没有这种自适应机制。

  6. Agent 能力缺陷

  问题 A：缺乏主动性和预判能力

  当前 agent 是完全被动的——用户问一句，agent 答一句。缺少：
  - 数据加载后主动给出洞察预览（"你的数据有几个值得关注的点：..."）
  - 分析完成后主动推荐下一步（不是等用户追问）
  - 检测到数据异常时主动提醒

  问题 B：缺乏跨会话学习能力

  experience_log 系统存在但需要用户主动确认（confirm_experience）。没有自动从历史分析中学习常见模式的机制。同一用户第 10
   次上传类似数据时，agent 仍然从零开始分析。

  问题 C：多数据集支持薄弱

  Workspace 支持多数据集（list_datasets 返回多个），但分析工具（analyze_time_series, correlation_analysis 等）只接受单个
   name 参数。缺少：
  - 多数据集关联分析
  - 数据集间的对比
  - JOIN/MERGE 操作的工具化支持

  问题 D：输出格式控制不足

  用户说"给我一个报告"，agent 调 generate_formal_report 生成 HTML/PDF，但用户可能只是想要一个简洁的 markdown
  摘要。输出格式（详细/简洁、技术/业务语言、图表/纯文本）缺少显式的用户偏好设置。