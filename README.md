# 观澜 Data Agent

通过自然语言完成专业级数据分析的 AI 智能体。

## 特性

- **自然语言驱动**：用中文描述分析需求，自动规划并执行分析流程
- **40+ 专业工具**：覆盖数据加载、EDA、统计检验、机器学习、可视化等全链路
- **多模型支持**：OpenAI、Anthropic、DeepSeek、Kimi 等 OpenAI 兼容接口
- **本地执行**：LLM 负责规划和解释，工具与数据在本地运行
- **知识积累**：领域知识、经验日志、项目规则持续沉淀
- **Web 图形界面**：基于浏览器的交互式分析界面，支持实时流式输出

## 快速开始

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

## 使用方式

1. **上传数据**：点击输入框旁的附件按钮，支持 CSV、Excel、JSON、Parquet 等格式
2. **描述任务**：用自然语言输入分析需求，如 "分析销售数据的趋势"
3. **查看结果**：分析结果实时流式展示，包含图表、统计数据和解读
4. **导出产出**：右侧面板可导出对话为 HTML 或 Markdown

详细操作说明请参阅 [用户手册](user_guide.md)。

## 开发

```bash
# 安装（使用 uv）
uv sync

# 运行测试
uv run pytest tests/ -v

# CLI REPL 模式
python main.py
```

## 项目结构

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

## 许可

MIT License
