@echo off
chcp 65001 >nul
echo.
echo ╔═══════════════════════════════════════════════════════╗
echo ║       零度叙事多智能体小说系统 v0.2                     ║
echo ║   后端: http://localhost:8000  前端: http://localhost:5173 ║
echo ╚═══════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0backend"

echo [1/3] 检查 .env 配置...
if not exist .env (
    echo   ⚠  未找到 .env 文件，从模板复制...
    copy .env.example .env >nul
    echo   ✓  已创建 .env，请填写 API Key 后重启
    echo.
    pause
    exit /b 1
)
echo   ✓  .env 存在

echo.
echo [2/3] 后台启动后端 (port 8000)...
start "🖥 Backend - 零度叙事后端" cmd /k "chcp 65001 >nul && set PYTHONUTF8=1&& cd /d "%~dp0backend" && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

echo   等待后端初始化 (3秒)...
timeout /t 3 /nobreak >nul

echo.
echo [3/3] 启动前端开发服务器 (port 5173)...
cd /d "%~dp0frontend"
start "🌐 Frontend - 零度叙事前端" cmd /k "chcp 65001 >nul && npm run dev"

echo.
echo ✓  系统已启动！
echo.
echo   👉 打开浏览器访问: http://localhost:5173
echo.
echo  （关闭此窗口不影响服务，单独关闭各自终端窗口停止服务）
echo.
pause
