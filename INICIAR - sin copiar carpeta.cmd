@echo off
cd /d "%~dp0"
echo Cerrando instancias anteriores de app.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*.exe' -and $_.CommandLine -like '*app.py*' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force } catch {} }"
REM Por si quedo el puerto 5000 ocupado por otro proceso:
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
timeout /t 1 /nobreak >nul
start "" python app.py
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:5000