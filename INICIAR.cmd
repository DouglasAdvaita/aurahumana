@echo off
cd /d "%~dp0"
echo Cerrando instancias anteriores de app.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*.exe' -and $_.CommandLine -like '*app.py*' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force } catch {} }"
REM Por si quedo el puerto 5000 ocupado por otro proceso:
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
timeout /t 1 /nobreak >nul
REM Copia de respaldo con fecha en Codex\respaldos (ej: Codex\respaldos\DisenioHumano - para prueba OpenCode - 9-9-2026 11.45):
set "DH_ORIGEN=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ts = Get-Date -Format 'd-M-yyyy H.mm'; $src = $env:DH_ORIGEN.TrimEnd('\'); $resp = (Split-Path $src -Parent) + '\respaldos'; New-Item -ItemType Directory -Force -Path $resp | Out-Null; $dst = $resp + '\' + (Split-Path $src -Leaf) + ' - ' + $ts; $o = robocopy $src $dst /E /R:0 /W:0 /XD __pycache__ .git /NFL /NDL /NJH /NJS; $cod = $LASTEXITCODE; $omit = @($o | Where-Object { $_ -match '\S' }).Count; if ($cod -ge 8) { echo ('RESPALDO INCOMPLETO (robocopy codigo ' + $cod + '): ' + $dst) } elseif ($omit -gt 0) { echo ('Copia creada con ' + $omit + ' archivos omitidos: ' + $dst) } else { echo ('Copia creada: ' + $dst) }"
REM preparar_datos.py ya no se usa (movido a _viejos); se arranca con datos.csv
start "" python app.py
echo Esperando a que la app responda...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 90;$i++){ try { $c=New-Object Net.Sockets.TcpClient('127.0.0.1',5000); $c.Close(); $ok=$true; break } catch { Start-Sleep -Seconds 1 } }; if($ok){ Start-Process 'http://127.0.0.1:5000/' } else { Write-Host 'La app no respondio en 90 segundos.' }"