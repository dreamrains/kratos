@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ============================================
echo   观澜 Data Agent - 启动中...
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python。
    echo 请安装 Python 3.11 或更高版本：https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"。
    echo.
    pause
    exit /b 1
)

:: Check Python version >= 3.11
python -c "import sys; assert sys.version_info >= (3, 11), f'需要 Python 3.11+，当前 {sys.version}'" 2>nul
if errorlevel 1 (
    echo [错误] Python 版本过低，需要 3.11 或更高。
    echo 请访问 https://www.python.org/downloads/ 下载最新版本。
    echo.
    pause
    exit /b 1
)

:: Create virtual environment if missing
if not exist ".venv\Scripts\activate.bat" (
    echo [1/2] 正在创建虚拟环境并安装依赖，首次运行需要几分钟...
    echo.
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 创建虚拟环境失败。
        pause
        exit /b 1
    )
    call .venv\Scripts\activate.bat
    pip install -e . 2>&1
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络连接。
        pause
        exit /b 1
    )
    echo.
    echo [2/2] 安装完成！
    echo.
) else (
    call .venv\Scripts\activate.bat
)

:: Launch
set LITELLM_LOCAL_MODEL_COST_MAP=True
echo 正在启动服务，浏览器将自动打开...
echo 关闭此窗口即可停止服务。
echo.
python -m data_agent.web.entry
pause
