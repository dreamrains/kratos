# Data Agent V2 Slice 5B1：统一分析入口

- **日期**：2026-08-13
- **状态**：Complete（未切换主入口）
- **基线提交**：`88824f4`（`feat(v2): add layered release readiness contract`）
- **分支**：`codex/data-agent-v2`
- **上位设计**：[`2026-08-13-data-agent-v2-architecture-design.md`](../specs/2026-08-13-data-agent-v2-architecture-design.md)

## 1. 目标

把已经验收的八类 V2 纵向切片放入一个统一 Workbench：用户只上传一次文件，显式选择分析类型并填写相应方法参数；服务端薄路由将请求确定性映射到现有 runtime。页面统一呈现语义 SSE、答案块、邻接图表、日期语义确认与刷新恢复。

本切片建立 `/v2-workbench`，不替换 `/`。显式分析类型是当前无 provider 阶段的诚实边界；本切片不使用关键词猜测或 LLM 自动选择方法。

## 2. 单一职责

- `AnalysisRouter`：校验公共 envelope 和方法参数，选择一个现有 runtime；
- 方法 runtime：继续拥有 Commitment、Execution Event、Finding 和答案块生产；
- `V2FactStore`：继续拥有恢复事实；
- Workbench：只渲染事件和持久化块，不推断完成状态。

路由层不得写 Finding、设置任务完成或拼接自由 Markdown。

## 3. 支持的分析类型

1. `descriptive`
2. `factor_relationship`
3. `date_transformation`
4. `group_comparison`
5. `time_trend`
6. `forecast`
7. `multi_finding_synthesis`
8. `exploratory_python`

## 4. 交互边界

- 分析类型切换只显示相关字段，不丢失已填写内容；
- question 输入框在运行中保持可编辑，为后续 steer 协议预留；
- 活动列表默认收起，以固定 overlay 展示，不压缩正文；
- 图表按 `chart_refs` 邻接，未消费图表进入补充区；
- 日期语义歧义在同页显示绑定选项并调用现有 resolve API；
- 刷新从 session/turn URL 恢复分析类型、参数、块和图表；
- 失败后输入保留且可再次运行。

## 5. 停止边界

本切片不提供伪停止按钮。真正停止必须追加 `USER_INTERRUPTED` 事实、关闭当前 generator、阻止后续持久化并提供恢复语义；该协议进入 Slice 5B2。前端仅中断网络连接不足以满足该要求。

## 6. 本切片不做

- 切换 `/`；
- 删除旧页面或旧运行时；
- provider/LLM 自动路由；
- 运行中 steer；
- 声称 `unified_analysis_entry` 矩阵已经全层 PASS；
- 生成 real-provider 或人工语义 receipt。

## 7. 验收

- 八类路由均有参数契约；未知类型和错误枚举在启动线程前返回 400；
- 至少描述、综合、转换确认三条统一 API 旅程有测试；
- 同一页面完成上传、SSE、图表邻接、确认及刷新恢复；
- question 在运行中不 disabled；活动 overlay 默认关闭且不参与正文布局；
- 浏览器失败重试不刷新页面、不丢输入；
- 全量 V2 回归通过；不调用真实 provider。

## 8. 实施结果（2026-08-13）

- 新增确定性的 `AnalysisRouter` 和统一 `POST /api/v2/analyze`；八类方法继续复用各自 runtime，路由层不写 Finding、不判定完成；
- 新增 `/v2-workbench`，统一完成上传、方法参数、语义 SSE、答案块、邻接/补充图表、日期确认与刷新恢复；
- 描述分析补齐持久化 `analysis_kind`，保证统一页面刷新后可恢复方法类型；
- 活动列表为默认关闭的固定 overlay；question 在运行中保持 enabled，当前轮继续使用点击运行时的请求快照；
- 没有添加伪停止按钮。真实停止和 steer 仍属于 Slice 5B2；
- 没有替换 `/`、删除旧 canary、生成 provider receipt 或宣称产品发布就绪。

## 9. 验证记录

### 自动化

- 统一路由/API/页面专项：`11 passed`；
- 全部 `test_v2*.py`：`159 passed`；
- JavaScript 语法检查、Python compileall、`git diff --check`：通过；
- 全仓 `tests` 在明确设置 `GOLDEN_LIVE_SMOKE=0` 后运行，180 秒上限时执行至 24%，当时无失败；该结果不是全仓 PASS，不能作为发布凭据。

### 本地真实浏览器旅程

- 初始和运行期间活动 overlay 均保持关闭，question 在 SSE 运行期间可编辑；
- 综合分析完成后形成 4 个结构化答案块和 2 个邻接图表，2 个 Plotly iframe 均完成加载；
- 刷新后恢复 `multi_finding_synthesis`、原问题、4 个答案块和 2 个图表；
- 歧义日期在同页展示“日/月/年”和“月/日/年”，刷新仍保持待确认状态；选择“日/月/年”后发布 2 个答案块；
- 故意提交不存在的指标后，错误可见、问题不丢失、运行按钮恢复；改正指标后无需重新上传即可原位成功；
- 浏览器控制台无 error/warn；本地服务和临时 QA 文件已清理。

以上仅证明 Slice 5B1 的离线统一工作台验收通过，不代表 real-provider 分析质量、旧主入口切换或产品级发布完成。
