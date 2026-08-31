@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=D:\python\python.exe"

echo Starting CareerMatch backend...
start "CareerMatch Backend" cmd /k "cd /d "%ROOT%backend" && "%PYTHON%" -m uvicorn main:app --host 127.0.0.1 --port 8000"

echo Starting CareerMatch frontend...
start "CareerMatch Frontend" cmd /k "cd /d "%ROOT%frontend" && npm run dev"

echo Waiting for servers to start...
timeout /t 5 /nobreak >nul

start http://localhost:5173

endlocal
