@echo off
cd /d "%~dp0"
echo Cerrando instancias anteriores de app.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*.exe' -and $_.CommandLine -like '*app.py*' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force } catch {} }"
REM Por si quedo el puerto 5000 ocupado por otro proceso:
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
timeout /t 1 /nobreak >nul
REM Copia de respaldo con fecha en Codex\respaldos (ej: Codex\respaldos\DisenioHumano - para prueba OpenCode - 9-9-2026 11.45):
set "DH_ORIGEN=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ts = Get-Date -Format 'd-M-yyyy H.mm'; $src = $env:DH_ORIGEN.TrimEnd('\'); $resp = (Split-Path $src -Parent) + '\respaldos'; New-Item -ItemType Directory -Force -Path $resp | Out-Null; $dst = $resp + '\' + (Split-Path $src -Leaf) + ' - ' + $ts; robocopy $src $dst /E /XD __pycache__ .git /NFL /NDL /NJH /NJS > $null; echo ('Copia creada: ' + $dst)"
python preparar_datos.py
start "" python app.py
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:5000