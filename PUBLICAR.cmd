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
if %errorlevel%==0 goto :sin_cambios
git commit -m "%MSG%"
if errorlevel 1 (
  echo No se pudo guardar el commit.
  goto :fin
)
goto :remoto

:sin_cambios
echo No hay cambios nuevos para guardar.

:remoto
git remote get-url origin >nul 2>&1
if not errorlevel 1 goto :subir

echo.
echo No hay remoto configurado.
set "URL="
set /p "URL=Pega la URL del repo privado (Enter = solo guardar local): "
if not defined URL goto :sin_remoto
git remote add origin "%URL%"
if errorlevel 1 (
  echo No se pudo agregar el remoto.
  goto :fin
)

:subir
echo.
echo Subiendo a GitHub...
git push -u origin main
if errorlevel 1 (
  echo No se pudo subir. Revisa la URL, la conexion o si el repo ya tiene commits.
) else (
  echo Listo: subido a GitHub.
)
goto :fin

:sin_remoto
echo Guardado LOCAL. Falta configurar el remoto para subir a GitHub.

:fin
echo.
