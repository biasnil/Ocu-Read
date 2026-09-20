@echo off
setlocal EnableExtensions
set "BUILD_VERSION=1.0.0"
cd /d "%~dp0"

rem ---------------------------------------------------------------------------
rem  OcuRead build script
rem    build.bat                normal build  -> dist\OcuRead\OcuRead.exe
rem    build.bat --debug        console window on, no UPX -> dist\OcuRead-debug\OcuRead-debug.exe
rem    build.bat --clean        delete build\ and dist\ first
rem    build.bat --onefile      single OcuRead.exe instead of a folder (slower to start)
rem  Flags can be combined.
rem ---------------------------------------------------------------------------

set "OCUREAD_DEBUG=0"
set "OCUREAD_ONEFILE=0"
set "DO_CLEAN=0"
set "LAST_ERROR="

:parse_args
if "%~1"=="" goto args_done
if /i "%~1"=="--debug"   ( set "OCUREAD_DEBUG=1"   & shift & goto parse_args )
if /i "%~1"=="--onefile" ( set "OCUREAD_ONEFILE=1" & shift & goto parse_args )
if /i "%~1"=="--clean"   ( set "DO_CLEAN=1"        & shift & goto parse_args )
if /i "%~1"=="--help"    goto usage
echo Unknown option: %~1
goto usage

:args_done
echo ==========================================================
echo   OcuRead build script  v%BUILD_VERSION%
echo ==========================================================
if "%OCUREAD_DEBUG%"=="1"   echo   Mode: DEBUG (console window on)
if "%OCUREAD_ONEFILE%"=="1" echo   Mode: ONE-FILE
if exist build_log.txt del build_log.txt

rem ---- 1. Python ---------------------------------------------------------
echo.
echo [1/6] Checking Python...
where python >nul 2>&1
if errorlevel 1 (
    set "LAST_ERROR=Python was not found on PATH. Install Python 3.12 from python.org and tick Add python.exe to PATH."
    goto fail
)
for /f "delims=" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo       Found: %PYVER%
echo %PYVER% | findstr /b /c:"Python 3" >nul
if errorlevel 1 (
    set "LAST_ERROR=python on PATH is not a working Python 3 - it may be the Microsoft Store stub. Install Python 3.12 from python.org."
    goto fail
)
python -c "import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,12) else 1)"
if errorlevel 1 echo       WARNING: Python 3.10 to 3.12 is recommended - PaddlePaddle and PyTorch wheels may be missing for this version.

rem ---- 2. Virtual environment ----------------------------------------------
echo.
echo [2/6] Virtual environment...
if defined VIRTUAL_ENV goto venv_ready
if not exist "venv\Scripts\activate.bat" (
    echo       Creating venv - preferring Python 3.12
    py -3.12 -m venv venv >nul 2>&1
    if errorlevel 1 python -m venv venv
)
if not exist "venv\Scripts\activate.bat" (
    set "LAST_ERROR=Could not create the virtual environment in .\venv"
    goto fail
)
call "venv\Scripts\activate.bat"
:venv_ready
echo       Using: %VIRTUAL_ENV%
for /f "delims=" %%v in ('python --version 2^>^&1') do echo       Python in venv: %%v

rem ---- 3. Dependencies -------------------------------------------------------
echo.
echo [3/6] Installing dependencies - the first run downloads several GB, please be patient...
python -m pip install --upgrade pip
if errorlevel 1 (
    set "LAST_ERROR=pip could not be upgraded - check your internet connection."
    goto fail
)
python -m pip install -r requirements.txt
if errorlevel 1 (
    set "LAST_ERROR=pip install -r requirements.txt failed - see the pip output above."
    goto fail
)

rem ---- 4. PyInstaller --------------------------------------------------------
echo.
echo [4/6] Checking PyInstaller...
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo       Not found - installing
    python -m pip install pyinstaller
    if errorlevel 1 (
        set "LAST_ERROR=Could not install PyInstaller."
        goto fail
    )
)
for /f "delims=" %%v in ('python -m PyInstaller --version') do echo       PyInstaller %%v

rem ---- 5. Icons + clean ------------------------------------------------------
echo.
echo [5/6] Preparing icon files...
python tools\make_icon.py
if not exist "assets\icon.ico" (
    set "LAST_ERROR=assets\icon.ico is missing and could not be generated."
    goto fail
)
if "%DO_CLEAN%"=="1" (
    echo       Cleaning build\ and dist\
    if exist build rmdir /s /q build
    if exist dist rmdir /s /q dist
)

rem ---- 6. Build --------------------------------------------------------------
echo.
echo [6/6] Building with PyInstaller - this takes several minutes. Full log: build_log.txt
python -m PyInstaller --clean --noconfirm ocuread.spec > build_log.txt 2>&1
if errorlevel 1 (
    set "LAST_ERROR=PyInstaller reported an error."
    goto fail
)

set "APP_NAME=OcuRead"
if "%OCUREAD_DEBUG%"=="1" set "APP_NAME=OcuRead-debug"
if "%OCUREAD_ONEFILE%"=="1" (
    set "OUT=dist\%APP_NAME%.exe"
) else (
    set "OUT=dist\%APP_NAME%\%APP_NAME%.exe"
)
if not exist "%OUT%" (
    set "LAST_ERROR=The build finished but %OUT% was not created."
    goto fail
)

echo.
echo ==========================================================
echo   BUILD SUCCESSFUL
echo   Output: %CD%\%OUT%
echo   Run it with run.bat
echo   Warnings, if any, are in build_log.txt
echo ==========================================================
goto done

:usage
echo.
echo Usage: build.bat [--debug] [--clean] [--onefile]
echo   --debug     console window on, no UPX, output named OcuRead-debug
echo   --clean     delete build\ and dist\ before building
echo   --onefile   build a single exe instead of a folder
exit /b 1

:fail
echo.
echo ================== BUILD FAILED ==================
echo   %LAST_ERROR%
if exist build_log.txt (
    echo   Last lines of build_log.txt:
    echo   --------------------------------------------------
    powershell -NoProfile -Command "Get-Content build_log.txt -Tail 25"
)
echo.
pause
endlocal
exit /b 1

:done
rem keep the window open only when the script was started by double-clicking
echo %cmdcmdline% | find /i "%~nx0" >nul
if not errorlevel 1 pause
endlocal
exit /b 0
