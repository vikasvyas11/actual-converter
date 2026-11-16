@echo off
setlocal
cd /d "%~dp0"
where pyw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pyw.exe -3 "%~dp0actual converter.pyw" %*
    exit /b 0
)
where pythonw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pythonw.exe "%~dp0actual converter.pyw" %*
    exit /b 0
)
echo Run Set up.cmd to install Python and the conversion engines.
pause
exit /b 1
