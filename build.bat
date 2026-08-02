@echo off
setlocal
py -3.13 "%~dp0build.py"
set "BUILD_EXIT_CODE=%ERRORLEVEL%"
echo.
if not "%BUILD_EXIT_CODE%"=="0" echo Build failed with exit code %BUILD_EXIT_CODE%.
pause
exit /b %BUILD_EXIT_CODE%
