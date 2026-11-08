@echo off
REM Panel de actividad de Alma (usuarios, matches, mensajes, bloqueos, reportes).
REM Usa la misma base Neon que Render: los datos son los reales, no una copia.
REM Abre solo el panel; si el servidor no esta corriendo, lo levanta en esta PC.
cd /d "%~dp0"
set "PANEL=http://127.0.0.1:5000/admin/dh-9f3a7c1e5b2d4f6a8c0e/panel"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=New-Object Net.Sockets.TcpClient; try{$c.Connect('127.0.0.1',5000);$c.Close();exit 0}catch{exit 1}"
if not errorlevel 1 (
  echo Servidor ya iniciado. Abriendo el panel...
  start "" "%PANEL%"
  exit /b 0
)

echo Levantando app.py...
start "RAVE (panel)" cmd /k "python app.py"
echo Esperando al servidor...
set /a intentos=0
:bucle
timeout /t 1 /nobreak >nul
set /a intentos+=1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$c=New-Object Net.Sockets.TcpClient; try{$c.Connect('127.0.0.1',5000);$c.Close();exit 0}catch{exit 1}"
if not errorlevel 1 goto abrir
if %intentos% lss 40 goto bucle
echo No respondio el servidor. Revisa la ventana "RAVE (panel)".
pause
exit /b 1

:abrir
start "" "%PANEL%"
exit /b 0
