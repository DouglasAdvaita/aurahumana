@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "MSG="
set /p "MSG=Descripcion del cambio (Enter = fecha): "
if not defined MSG set "MSG=Cambios %date% %time%"
echo.
echo Guardando cambios...
git add -A
git diff --cached --quiet
if %errorlevel%==0 (
  echo No hay cambios para guardar.
  goto :fin
)
git commit -m "%MSG%"
if errorlevel 1 (
  echo No se pudo guardar el commit.
  goto :fin
)
git remote get-url origin >nul 2>&1
if errorlevel 1 (
  echo Guardado LOCAL. Aun no hay remoto de GitHub configurado.
) else (
  echo Subiendo a GitHub...
  git push -u origin main
)
:fin
echo.
pause
