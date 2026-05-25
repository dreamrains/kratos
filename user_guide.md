# 观澜 Data Agent 用户手册

## 目录

- [简介](#简介)
- [环境准备](#环境准备)
- [安装与启动](#安装与启动)
- [首次配置](#首次配置)
- [Web 界面导览](#web-界面导览)
- [常见工作流](#常见工作流)
- [环境变量参考](#环境变量参考)
- [常见问题](#常见问题)

---

## 简介

观澜 Data Agent 是一个专业级 AI 数据分析智能体。你只需要用自然语言描述分析需求，它会自动完成数据加载、探索分析、统计检验、机器学习建模、可视化等全流程。

**核心能力**：

- 数据加载与清洗（CSV、Excel、JSON、Parquet、SQL 数据库）
- 探索性数据分析（分布、相关性、趋势、漏斗、同期群等）
- 统计分析（A/B 测试、因果推断、归因分析）
- 机器学习（回归、分类、预测、特征重要性分析）
- 数据可视化（折线图、柱状图、散点图、热力图等）
- 任务管理与多阶段分析流程

---

## 环境准备

### 1. 安装 Python

访问 [Python 官网](https://www.python.org/downloads/) 下载并安装 **3.11 或更高版本**。

**Windows 用户注意**：安装时务必勾选底部的 **"Add Python to PATH"** 选项。

### 2. 验证安装

打开终端（Windows 按 `Win+R` 输入 `cmd`，Mac 打开"终端"应用），输入：

```
python --version
```

应显示 `Python 3.11.x` 或更高版本。（Mac 用户可能需要输入 `python3 --version`。）

### 3. 网络要求

- 安装依赖时需要访问 PyPI（Python 包仓库）
- 运行时需要访问 LLM API 服务（如 OpenAI、DeepSeek 等）

---

## 安装与启动

### Windows

1. 将项目文件夹解压或克隆到本地
2. **双击 `start.bat`**
3. 首次运行会自动创建虚拟环境并安装依赖，等待几分钟
4. 安装完成后浏览器自动打开 `http://127.0.0.1:5001`
5. 如浏览器未自动打开，手动访问上述地址

启动后保持命令行窗口打开，关闭窗口即停止服务。

### macOS / Linux

1. 将项目文件夹解压或克隆到本地
2. 打开终端，进入项目目录
3. 执行以下命令：

```bash
chmod +x start.sh
./start.sh
```

4. 首次运行会自动创建虚拟环境并安装依赖
5. 浏览器自动打开

按 `Ctrl+C` 停止服务。

### 手动启动（开发者）

如果已安装 `uv`：

```bash
uv sync
uv run python -m data_agent.web.entry
```

或使用 pip：

```bash
python -m venv .venv
source .venv/bin/activate   # Mac/Linux
.venv\Scripts\activate      # Windows
pip install -e .
python -m data_agent.web.entry
```

---

## 首次配置

首次打开 Web 界面后，需要配置 LLM（大语言模型）接口才能开始使用。

### 步骤

1. 在 Web 界面左上角，点击 **齿轮图标**（"LLM 配置"）
2. 在弹出的配置窗口中填写以下信息：

#### 模型名称

填写你要使用的模型标识。常见示例：

| 提供商 | 模型名称 |
|--------|----------|
| OpenAI | `gpt-4o`、`gpt-4o-mini` |
| Anthropic | `claude-sonnet-4-6`、`claude-opus-4-7` |
| DeepSeek | `openai/deepseek-chat` |
| Kimi（月之暗面） | `openai/kimi-k2.6` |
| 其他 OpenAI 兼容服务 | 加前缀 `openai/`，如 `openai/your-model-name` |

> **注意**：使用第三方 OpenAI 兼容接口时，模型名称前需加 `openai/` 前缀。

#### API 地址

填写模型提供商的 API 端点：

| 提供商 | API 地址 |
|--------|----------|
| OpenAI | `https://api.openai.com/v1`（留空默认） |
| Anthropic | `https://api.anthropic.com` |
| DeepSeek | `https://api.deepseek.com` |
| Kimi | `https://api.moonshot.cn/v1` |
| 其他 | 填写对应的 Base URL，通常以 `/v1` 结尾 |

#### API 密钥

填写你从模型提供商获取的 API Key。

- OpenAI：[https://platform.openai.com/api-keys](https://platform.openai.com/api-keys)
- Anthropic：[https://console.anthropic.com/](https://console.anthropic.com/)
- DeepSeek：[https://platform.deepseek.com/](https://platform.deepseek.com/)
- Kimi：[https://platform.moonshot.cn/](https://platform.moonshot.cn/)

3. 点击 **保存**
4. 配置会自动持久化到 `.env` 文件，重启后无需重新配置

---

## Web 界面导览

### 整体布局

界面分为三个区域：

- **左侧边栏**：项目管理与会话列表
- **中间主区域**：对话交互区
- **右侧面板**：产出物与导出（宽屏下显示）

### 左侧边栏

#### 顶部操作

- **齿轮图标**：打开 LLM 配置窗口
- **加号图标**：新建会话

#### 搜索框

输入关键词搜索已有会话。

#### 项目区

- 点击 **加号** 创建新项目（用于归类分析会话）
- 点击项目名称展开/折叠该项目下的会话
- 点击会话可切换到该会话
- 点击会话右侧的 **三点图标** 可进行：移出项目、移动到其他项目、查看产出物、导出、删除

#### 会话区

显示未归类到项目的独立会话，操作同上。

### 中间对话区

#### 顶部工具栏

- **汉堡菜单**：折叠/展开侧边栏
- **压缩按钮**：压缩上下文以释放空间（长对话时使用）
- **回退按钮**：选择历史轮次进行编辑重发
- **上下文用量**：圆形指示器，显示当前上下文使用比例

#### 对话区

- 用户消息显示在右侧
- AI 回复显示在左侧，实时流式输出
- AI 回复下方有 **复制** 和 **导出** 操作按钮

#### 确认对话框

当 AI 需要向你确认信息时，会弹出交互卡片：
- 选择预设选项或输入自定义回答
- 点击 **提交** 继续，或 **跳过** / **取消**

#### 任务面板

当分析涉及多步骤任务时，对话区上方会出现任务面板，显示任务进度。

#### 输入区

- 在输入框中输入自然语言分析需求
- 按 `Enter` 发送，`Shift+Enter` 换行
- 点击 **附件图标** 上传数据文件
- 分析进行中可点击 **暂停按钮** 中断

### 右侧面板

宽屏下自动显示（窄屏隐藏）：

- **导出对话**：将当前会话导出为 HTML 或 Markdown 文件
- **产出物**：展示分析过程中生成的图表和数据文件，点击可查看

---

## 常见工作流

### 1. 上传数据并探索

```
你：[上传 CSV 文件] 帮我了解这份数据的基本情况
```

AI 会自动加载数据并执行探索性分析，包括数据概览、字段类型、缺失值、基本统计等。

### 2. 趋势分析

```
你：分析销售金额的月度趋势
```

AI 会进行时间序列分析，生成趋势图表并解读变化模式。

### 3. 统计检验

```
你：对比 A 组和 B 组的转化率差异是否显著
```

AI 会执行 A/B 测试分析，给出统计显著性结论。

### 4. 机器学习建模

```
你：用历史数据预测下个月的销量
```

AI 会选择合适的模型进行训练和预测，展示预测结果和模型评估。

### 5. 多维度分析

```
你：分析用户流失的影响因素，找出关键驱动因子
```

AI 会综合运用相关性分析、归因分析、特征重要性等方法，给出结构化的分析结论。

### 6. 导出结果

- 点击 AI 回复下方的 **导出** 按钮，导出单条回复为 HTML 或 Markdown
- 在右侧面板点击 **HTML** 或 **MD** 按钮，导出完整对话

---

## 环境变量参考

可通过项目根目录 `.env` 文件或环境变量配置：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `MODEL_ID` | `gpt-4o` | LLM 模型标识 |
| `API_BASE` | 无 | API 地址 |
| `API_KEY` | 无 | API 密钥 |
| `PROJECT_DIR` | `./project` | 项目数据目录 |
| `SESSIONS_DIR` | `./sessions` | 会话存储目录 |
| `MAX_TOKENS` | `8000` | 单次回复最大 token 数 |
| `TOKEN_THRESHOLD` | `100000` | 上下文压缩阈值 |
| `SIGNIFICANCE_LEVEL` | `0.05` | 统计显著性水平 |
| `LOG_LEVEL` | `INFO` | 日志级别 |
| `DATA_AGENT_WEB_HOST` | `127.0.0.1` | Web 服务监听地址 |
| `DATA_AGENT_WEB_PORT` | `5001` | Web 服务端口 |
| `DATA_AGENT_NO_BROWSER` | 无 | 设置为 `1` 禁止自动打开浏览器 |
| `MCP_ENABLED` | `True` | 是否启用 MCP 工具 |
| `SKILL_AUTO_DISCOVER` | `True` | 是否自动发现技能模板 |

---

## 常见问题

### 启动相关

**Q：双击 start.bat 后闪退**

安装 Python 时未勾选 "Add Python to PATH"。重新运行 Python 安装程序，勾选该选项。

**Q：提示 "Python 版本过低"**

需要 Python 3.11 或更高。访问 [python.org](https://www.python.org/downloads/) 下载最新版。

**Q：pip install 报错 / 安装很慢**

网络问题。可配置国内镜像：

```bash
pip install -e . -i https://pypi.tuna.tsinghua.edu.cn/simple
```

或修改 `start.bat` 中的 `pip install` 行添加 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。

**Q：首次启动时报 plotly.js 下载失败**

首次启动会尝试下载可视化库。如果网络受限，图表功能可能降级为 CDN 加载模式，不影响核心分析功能。

### 配置相关

**Q：配置保存后重启丢失**

确保启动时工作目录是项目根目录（双击 `start.bat` 会自动处理）。`.env` 文件在项目根目录下。

**Q：模型名称该怎么填**

参考 [首次配置](#首次配置) 部分的表格。关键是第三方 OpenAI 兼容接口要加 `openai/` 前缀。

**Q：API 地址和 API 密钥从哪里获取**

在对应模型提供商的开发者平台注册并创建 API Key。详见 [首次配置](#首次配置) 中的链接。

### 使用相关

**Q：对话过程中报错 "context window exceeded"**

对话过长超出模型上下文限制。点击顶部工具栏的 **压缩按钮** 压缩上下文。

**Q：图表显示不了**

可能是 plotly.js 未成功下载。检查网络连接，重启服务会重新尝试下载。

**Q：如何更换分析的数据集**

在新的对话中上传新文件即可，或在当前对话中说明"请分析另一份数据"并上传。

**Q：如何停止正在进行的分析**

点击输入框旁的红色 **暂停按钮**。

**Q：如何修改端口号**

在 `.env` 文件中添加 `DATA_AGENT_WEB_PORT=8080`（改成你想要的端口），或设置环境变量后启动。

---

## 高级功能

### MCP 工具扩展

可通过 MCP（Model Context Protocol）连接外部工具服务。在 `project/mcp_servers.yaml` 中配置 MCP 服务器。

### 技能模板

项目支持分析技能模板，放置在 `~/.data-agent/skills/`（全局）或 `project/skills/`（项目级）。技能会根据用户意图自动激活。

### 领域知识

支持电商、游戏等领域的专业知识注入，在对话中可切换：

```
你：切换到电商领域知识
```

### 项目管理

- **项目**：用于归类分析会话，每个项目可以有独立的领域知识
- **会话**：一次完整的分析对话，支持跨项目移动
- 在侧边栏创建项目，将相关会话归入同一项目进行管理
