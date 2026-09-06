# Slice 0 工程基线收据

- 日期：2026-08-25
- 结论：Slice 0 PASS；只代表工程基线、工具面、真实数据前置、依赖声明和本地 Web smoke 可复算，不代表分析质量、真实 Provider、staging 或 production 已通过
- 分支：`rebuild`
- HEAD：`6ae6abe0a49d5c0d42b559645127b14a5ea7f9a2`
- HEAD tree：`fbbe3df020692f5bb2955f2285c211177233d0aa`
- 7/13 底座：当前 `HEAD:src` 与 `1d57061:src` 均为 `f3769ad16f903e644995ab8810031cec03f7e10b`
- 当前源码摘要：`sha256:f604620595eec095e472623463d5cc3cecbc719877bb6eae2256ad9e549fd471`
- 摘要范围：`src`、`scripts`、`tests`、`main.py`、`pyproject.toml`、`uv.lock`、`start.bat`、`start.sh`，当前 307 个存在的受控源码条目
- 真实 Provider 调用：0
- Git 动作：未提交、未合并、未推送、未部署

## 1. 已完成的 Slice 0 内容

### 1.1 唯一真实数据清单

- 唯一根目录固定为仓库内 `reference/test_doc`；用户最初给出的 `reference/test/_doc` 当前不存在，不建立别名或兼容目录。
- `tests/real_data/reference_data_manifest.json` 固定 9 个实际 Excel 文件的相对路径、SHA256、字节数、sheet、行数、必需列和用途。
- `scripts/acceptance/real_data_manifest.py` 严格校验文件集合、内容指纹、sheet、行数和表头；缺失与漂移显式失败。
- 旧文件名、仓库外 `D:/Project/Daily/备用/...` 绝对路径和“文件不存在即静默跳过”已从受影响测试中移除。
- 原计划列出的 8 个陈旧测试及同根因的其他真实数据/自定义 runner 均改用同一 manifest。

### 1.2 可移植源码身份

- `scripts/acceptance/release_source.py` 使用 Git clean filter 后的 blob identity，避免 checkout 路径和 LF/CRLF 差异改变摘要。
- 摘要覆盖已跟踪与未跟踪的当前源码，排除缓存和生成收据。
- 新增“已跟踪文件在工作树删除”场景；删除的旧报告测试不再让摘要器尝试哈希不存在路径。

### 1.3 工具面和 deprecated 报告收口

- Gate A 时 76 项模型工具按确认台账收口为 73 项正式工具。
- 删除 `generate_report`、`generate_analysis_brief`、`generate_formal_report` 的 registry、prompt、实现、旧 `/api/sessions/<id>/report` 路由和专属测试；不保留别名或兼容入口。
- 保留主对话完整合成和 `export_conversation` HTML/Markdown 产出；旧 `/report` 路由契约为 404。
- 删除 `record_insight_record` 在 registry、prompt、execution control、evidence 等处的死引用，不新造替代工具。
- 当时的验收工具清单已随旧矩阵退役；当前工具注册完整性由默认离线 pytest 中的确定性测试覆盖。

### 1.4 依赖和格式声明

- `src/data_agent/file_formats.py` 作为当前输入格式单一事实源：CSV、TSV、XLSX、JSON、JSONL。
- TSV 与 JSONL 有真实加载实现；未知后缀明确失败，不再错误回退为 CSV。
- 当前环境和锁文件均无 `pyarrow`/`fastparquet`，因此 Web、上传和意图层不再宣称 Parquet/Feather 可用。
- 这不是永久放弃列式格式；后续如引入，必须同时交付依赖声明、启动预检、真实上传和数据版本收益证据。

### 1.5 故障索引

- 当时的故障验收索引已随旧矩阵退役；未来验收体系的重建边界见 `docs/testing/retired-browser-provider-matrix.md`。
- Slice 0 只将 F26（工具死引用/报告漂移）、F27（虚假格式依赖声明）、F28（真实数据路径漂移）置为 `contract_guard`。
- F01–F25、F29–F33 仍为后续切片的 `characterized` 项；完整回归通过不等于这些事故已解决。

## 2. 当前源码验证

| 验证 | 结果 |
|---|---|
| 完整测试 `pytest tests -q --disable-warnings --maxfail=1` | `2181 passed, 11 skipped, 55 warnings`，392.21 秒 |
| `pytest tests/test_release_source.py` | `5 passed` |
| Python 编译 `python -m compileall -q src scripts` | PASS |
| 前端语法 `node --check src/data_agent/web/static/js/app.js` | PASS |
| 真实数据 manifest CLI | PASS；9 文件集合和内容一致 |
| dependency preflight CLI | PASS；核心依赖全部可导入；Parquet/Feather 未安装且未宣称支持 |
| `git diff --check` | PASS；仅有工作区既有换行策略的 LF→CRLF 提示，无 whitespace error |

11 个 skip 均来自测试自身已有条件；本次没有用 skip、复制旧文件或外部绝对路径制造假绿。LiteLLM 在一个预期错误路径测试中打印帮助提示，但测试断言通过，不是 Provider 调用。

## 3. 本地真实 Web 进程与浏览器证据

### 3.1 执行边界

- 使用当前源码启动独立 Flask 进程：`127.0.0.1:5127`。
- 使用专用临时目录 `tmp/slice0-browser-5127/workspace` 和 `tmp/slice0-browser-5127/sessions`，不读取或覆盖用户正式会话。
- MCP 与 Skill 自动发现关闭；进程启动日志注册 73 项原生工具。
- 验收结束后 Web 与离线协议桩进程均已停止，5127/5128 无监听者。

### 3.2 页面、vendor 与格式

- 应用内真实浏览器打开首页得到 HTTP 200，标题为 `Data Agent`。
- 页面 12 个脚本/样式资源全部来自 `http://127.0.0.1:5127`，外部资源数为 0。
- 文件输入 `accept` 精确为 `.csv,.tsv,.xlsx,.json,.jsonl`。
- 页面完整加载，控制台 error/warning 为 0；“当前分析”与“产出与导出”切换正常。
- 当前分析仍显示“仍不确定、建议下一步、完整叙述”等待删内容，这是已知现状，按计划在 Slice 6 前后端一致删除；Slice 0 未偷跑产品面重构。

### 3.3 会话恢复、产出与下载

- 使用离线预置会话验证列表刷新、会话恢复、主回答渲染和导出按钮恢复可用。
- 浏览器点击会话级 Markdown 导出后，产出列表出现唯一 `Conversation Export` 链接。
- 真实服务日志记录导出 API HTTP 200，随后文件服务 HTTP 200/304；导出文件名含微秒和 UUID 片段，避免同秒覆盖。
- 单条回复的 Blob 下载动作执行后页面菜单关闭且控制台无错误；应用内浏览器未返回 download event，因此不以该事件作为唯一证明，以上会话级文件服务 200 为下载 smoke 的正式依据。

### 3.4 离线 SSE

- 为保证真实 Provider 调用为 0，在 `127.0.0.1:5128` 启动仅供本次验收的临时 OpenAI 协议桩；桩文件和日志只位于专用 `tmp` 子目录，不进入源码摘要。
- 浏览器通过真实 `/api/chat` 发送离线 smoke 消息；Web 返回 HTTP 200 的 SSE 流。
- 页面出现 `Slice 0 离线 SSE smoke 已完成。`，`思考中...` 消失，输入框恢复可用，控制台 error/warning 为 0。
- 协议桩记录 6 次本地 `/v1/chat/completions` 请求，反映 Agent 内部回合；这些请求全部发往本机桩，不是 Provider 调用，也不作为分析质量证据。

## 4. 明确未解决和未授权的内容

1. Slice 0 没有证明数据分析质量提升，只恢复了后续质量改造可相信的测量底座。
2. R01–R09 的真实数据纵向分析、方法 oracle、verified conclusion 和图表一致性仍按 Slice 1–5 执行。
3. Workbench 只保留已验证结论、产出和导出的用户要求仍在 Slice 6；当前页面不能作为目标体验。
4. 未执行真实数据浏览器上传+分析旅程，未执行真实 Provider L4，未验证 staging/production L5。
5. 未执行历史会话迁移、根入口切换、提交、合并、推送、部署或既有资产清理。

## 5. 放行结论

Slice 0 可以关闭，下一步建议进入 Slice 1 的方案冻结：以 D03 冻结小样建立单文件可信分析黄金链路，先定义同一条旅程的数值 oracle、完成条件、verified/publication 契约和浏览器验收，再修改分析策略。未经用户确认，不自动开始 Slice 1。
