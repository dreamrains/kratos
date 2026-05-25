# 🌊 观澜

<img width="1920" height="819" alt="ig_01986cde80c65f24016a074f8746cc81918f9466a41ac8be4d" src="https://github.com/user-attachments/assets/ffb7b0ae-c74c-4ad3-ad6c-892f96f9ee62" />


> **观水有术，必观其澜** —— 《孟子·尽心上》

**观澜** 是一款专攻深度数据分析的智能体。它不满足于呈现静止的数据表面，而是主动从动态、复杂的数据浪潮中，捕捉关键的“波澜”——异常、趋势、拐点与归因。

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen)]()

---

## 🎯 核心定位

- **不是仪表盘**（你已经有足够多的仪表盘了）
- **不是报表工具**（报表只回答“发生了什么”）
- **是数据分析智能体**：自然语言交互 + 自动归因 + 基于数据概览给出分析方向 + 业务建议 + 专业分析

一句话：**从“看见数据”到“理解数据”**。

观澜适合谁？

- 如果你缺少数据分析知识和方向
- 如果你面对诸多数据无从下手
- 如果你苦于已知目标却不知要获取哪些数据进行分析
- 如果你想要了解数据分析知识
- 如果你想要提升分析效率而非所有环节都依赖自己动手

## ✨ 特性

- **自然语言驱动**：用中文描述分析需求，自动规划并执行分析流程
- **40+ 专业工具**：覆盖数据加载、EDA、统计检验、机器学习、可视化等全链路
- **多模型支持**：OpenAI、Anthropic、DeepSeek、Kimi 等 OpenAI 兼容接口
- **本地执行**：LLM 负责规划和解释，工具与数据在本地运行
- **知识积累**：领域知识、经验日志、项目规则持续沉淀
- **Web 图形界面**：基于浏览器的交互式分析界面，支持实时流式输出

## 🚀 快速开始

### 环境要求

- Python 3.11 或更高版本（[下载](https://www.python.org/downloads/)）
- Windows 安装时勾选 **"Add Python to PATH"**

### 启动

**Windows**：双击 `start.bat`

**macOS / Linux**：

```bash
chmod +x start.sh
./start.sh
```

首次运行会自动创建虚拟环境并安装依赖，需要几分钟。安装完成后浏览器自动打开。

### 配置 LLM

首次使用需要在 Web UI 中配置 LLM 接口：

<img width="2880" height="1580" alt="image" src="https://github.com/user-attachments/assets/7b04f053-ad72-4977-b5cf-7dbbe6c990fa" />


1. 点击左侧边栏顶部的齿轮图标
2. 填写模型名称（如 `gpt-4o`、`claude-sonnet-4-6`、`openai/deepseek-chat`）
3. 填写 API 地址（留空使用默认值）
4. 填写 API 密钥
5. 点击保存

常用配置示例：

| 提供商 | 模型名称 | API 地址 |
|--------|----------|----------|
| OpenAI | `gpt-4o` | 留空或 `https://api.openai.com/v1` |
| Anthropic | `claude-sonnet-4-6` | `https://api.anthropic.com` |
| DeepSeek | `openai/deepseek-chat` | `https://api.deepseek.com` |
| Kimi | `openai/kimi-k2.6` | `https://api.moonshot.cn/v1` |

配置保存后自动持久化，重启无需重新配置。

## 🛣️ 使用方式

1. **上传数据**：点击输入框旁的附件按钮，支持 CSV、Excel、JSON、Parquet 等格式
2. **描述任务**：用自然语言输入分析需求，如 "分析销售数据的趋势"
3. **查看结果**：分析结果实时流式展示，包含图表、统计数据和解读
4. **导出产出**：右侧面板可导出对话为 HTML 或 Markdown

详细操作说明请参阅 [用户手册](user_guide.md)。

## 🤖 安装与启动

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


## 📁 项目结构

```
project/          用户数据工作区
  data/           处理后的数据集
  inbox/          上传的原始文件
  knowledge/      领域知识、经验日志、项目规则
  objects/        按项目组织的分析对象
  skills/         项目级技能模板
sessions/         会话数据（分析记录、图表、知识）
src/data_agent/   源代码
```

## 🔍 名字的由来

> “观水有术，必观其澜。”

观水有一定的方法，一定要观赏它**壮阔的波澜**。真正的洞察，从来不在平静的水面，而在波澜之中。

**观澜** = 主动观察数据中的关键波动，不放过任何一个值得追问的变化。

**随波逐流者众，观澜知势者智。**

观澜不替你做决定，但让你在数据的惊涛骇浪中，看得更清楚。

## 📄 许可

MIT License

## 🤝 贡献

欢迎提交 Issue、PR 或讨论新特性。

如果你也对“从数据中观澜”这件事感兴趣，一起来吧。
