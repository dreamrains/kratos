#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "============================================"
echo "  观澜 Data Agent - 启动中..."
echo "============================================"
echo ""

# Check Python 3.11+
if command -v python3 &>/dev/null; then
    PY=python3
elif command -v python &>/dev/null; then
    PY=python
else
    echo "[错误] 未检测到 Python。"
    echo "请安装 Python 3.11 或更高版本：https://www.python.org/downloads/"
    exit 1
fi

if ! $PY -c "import sys; assert sys.version_info >= (3, 11)" 2>/dev/null; then
    echo "[错误] Python 版本过低，需要 3.11 或更高。"
    echo "请访问 https://www.python.org/downloads/ 下载最新版本。"
    exit 1
fi

# Create virtual environment if missing
if [ ! -f ".venv/bin/activate" ]; then
    echo "[1/2] 正在创建虚拟环境并安装依赖，首次运行需要几分钟..."
    echo ""
    $PY -m venv .venv
    source .venv/bin/activate
    pip install -e .
    echo ""
    echo "[2/2] 安装完成！"
    echo ""
else
    source .venv/bin/activate
fi

export LITELLM_LOCAL_MODEL_COST_MAP=True
echo "正在启动服务，浏览器将自动打开..."
echo "按 Ctrl+C 停止服务。"
echo ""
python -m data_agent.web.entry
