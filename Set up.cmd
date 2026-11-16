@echo off
setlocal
cd /d "%~dp0"
echo Setting up actual converter for Windows.
where winget >nul 2>&1
if errorlevel 1 (
    echo Install App Installer from the Microsoft Store to enable Windows Package Manager.
    goto failed
)
py -3 -c "import tkinter, sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto engines
python -c "import tkinter, sys; sys.exit(sys.version_info < (3, 10))" >nul 2>&1
if not errorlevel 1 goto engines
winget install --id Python.Python.3.14 --exact --source winget --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto failed
:engines
call :engine magick ImageMagick.ImageMagick
if errorlevel 1 goto failed
call :engine ffmpeg Gyan.FFmpeg
if errorlevel 1 goto failed
echo Ready. Double-click actual converter.cmd to open the app.
pause
exit /b 0

:engine
where %1 >nul 2>&1
if not errorlevel 1 exit /b 0
winget list --id %2 --exact --source winget --accept-source-agreements >nul 2>&1
if not errorlevel 1 exit /b 0
winget install --id %2 --exact --source winget --accept-package-agreements --accept-source-agreements
exit /b %errorlevel%

:failed
echo Setup did not finish. Review the package manager message above.
pause
exit /b 1
