@echo off
setlocal EnableExtensions
cd /d "%~dp0"

rem  run.bat                 run the built exe if there is one, otherwise run from source (dev mode)
rem  run.bat --dev           always run from source:  python main.py
rem  run.bat --debug         run the debug build (console window with logs)
rem  Anything else is passed on to the app, e.g.  run.bat "C:\scans\invoice.pdf"

set "MODE=auto"
if /i "%~1"=="--dev"   ( set "MODE=dev"   & shift )
if /i "%~1"=="--debug" ( set "MODE=debug" & shift )

rem  %* ignores SHIFT, so collect the remaining arguments by hand
set "ARGS="
:collect
if "%~1"=="" goto collected
set ARGS=%ARGS% "%~1"
shift
goto collect
:collected

if "%MODE%"=="dev" goto dev
if "%MODE%"=="debug" goto debug

if exist "dist\OcuRead\OcuRead.exe" (
    start "" "dist\OcuRead\OcuRead.exe" %ARGS%
    goto end
)
if exist "dist\OcuRead.exe" (
    start "" "dist\OcuRead.exe" %ARGS%
    goto end
)
echo No built executable found - running from source (dev mode).
goto dev

:debug
if exist "dist\OcuRead-debug\OcuRead-debug.exe" (
    "dist\OcuRead-debug\OcuRead-debug.exe" %ARGS%
    goto end
)
if exist "dist\OcuRead-debug.exe" (
    "dist\OcuRead-debug.exe" %ARGS%
    goto end
)
echo No debug build found. Run:  build.bat --debug
exit /b 1

:dev
if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"
python main.py %ARGS%

:end
endlocal
