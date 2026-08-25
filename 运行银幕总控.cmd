@echo off
setlocal DisableDelayedExpansion
chcp 65001 >nul 2>&1
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONUTF8=1"
set "_SILVER_ENTRY=%~dp0scripts\runtime_launcher.py"

if not exist "%_SILVER_ENTRY%" goto launcher_missing

if not defined SILVER_PYTHON goto try_codex
set "_SILVER_CANDIDATE=%SILVER_PYTHON%"
call :probe_executable "%_SILVER_CANDIDATE%"
if errorlevel 1 goto explicit_invalid
set "_SILVER_PYTHON=%_SILVER_CANDIDATE%"
goto run

:try_codex
set "_SILVER_CANDIDATE=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
call :probe_executable "%_SILVER_CANDIDATE%"
if not errorlevel 1 set "_SILVER_PYTHON=%_SILVER_CANDIDATE%"
if defined _SILVER_PYTHON goto run

:try_workbuddy
set "_SILVER_WORKBUDDY_ROOT=%USERPROFILE%\.workbuddy\binaries\python\versions"
if not exist "%_SILVER_WORKBUDDY_ROOT%" goto try_path_py
for /d %%D in ("%_SILVER_WORKBUDDY_ROOT%\*") do if not defined _SILVER_PYTHON call :capture_executable "%%~fD\python.exe"
if defined _SILVER_PYTHON goto run

:try_path_py
call :find_path_executable py.exe
if defined _SILVER_PYTHON goto run
call :find_path_executable python3.exe
if defined _SILVER_PYTHON goto run
call :find_path_executable python.exe
if defined _SILVER_PYTHON goto run
goto python_missing

:capture_executable
call :probe_executable "%~1"
if not errorlevel 1 set "_SILVER_PYTHON=%~1"
exit /b 0

:find_path_executable
for /f "delims=" %%P in ('where.exe %~1 2^>nul') do if not defined _SILVER_PYTHON call :capture_executable "%%P"
exit /b 0

:probe_executable
if "%~1"=="" exit /b 1
if not exist "%~1" exit /b 1
"%~1" -B -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 91)" >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:run
"%_SILVER_PYTHON%" -B "%_SILVER_ENTRY%" %*
exit /b %errorlevel%

:launcher_missing
echo 银幕总控无法启动：运行入口文件缺失。请重新解压完整的 .skill 或 ZIP 包。 1>&2
exit /b 72

:explicit_invalid
echo 银幕总控无法启动：SILVER_PYTHON 指向的程序不是可用的 Python 3.10 或更高版本。 1>&2
echo 请修正这个路径，或清除 SILVER_PYTHON 后重试。 1>&2
exit /b 73

:python_missing
echo 银幕总控无法启动：没有找到可用的 Python 3.10 或更高版本。 1>&2
echo 已检查手动指定路径、Codex 自带环境、WorkBuddy 自带环境，以及 py、python3、python。 1>&2
echo Windows 应用商店的空入口不会被当成可用环境。 1>&2
exit /b 74
