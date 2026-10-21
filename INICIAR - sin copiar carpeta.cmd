@echo off
cd /d "%~dp0"
echo Cerrando instancias anteriores de app.py...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*.exe' -and $_.CommandLine -like '*app.py*' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force } catch {} }"
REM Por si quedo el puerto 5000 ocupado por otro proceso:
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :5000 ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
timeout /t 1 /nobreak >nul
start "" python app.py
echo Esperando a que la app responda...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ok=$false; for($i=0;$i -lt 90;$i++){ try { $c=New-Object Net.Sockets.TcpClient('127.0.0.1',5000); $c.Close(); $ok=$true; break } catch { Start-Sleep -Seconds 1 } }; if($ok){ Start-Process 'http://127.0.0.1:5000/' } else { Write-Host 'La app no respondio en 90 segundos.' }"
