@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

:: 1. venv Python
set "PYTHON="
if exist "%SCRIPT_DIR%\venv\Scripts\python.exe" (
    set "PYTHON=%SCRIPT_DIR%\venv\Scripts\python.exe"
    echo [INFO] 使用虚拟环境 Python: !PYTHON!
)

:: 2. 系统 Python（跳�?WindowsApps 占位，验证版�?>= 3.10�?if not defined PYTHON (
    where python >nul 2>&1
    if !ERRORLEVEL! equ 0 (
        for /f "delims=" %%p in ('where python 2^>nul') do if not defined PYTHON (
            echo "%%p" | findstr /I "WindowsApps" >nul 2>&1
            if !ERRORLEVEL! neq 0 (
                "%%p" -c "import sys; v=sys.version_info; sys.exit(0 if v.major==3 and v.minor>=10 else 1)" 2>nul
                if !ERRORLEVEL! equ 0 (
                    set "PYTHON=%%p"
                    echo [INFO] 使用系统 Python: %%p
                ) else (
                    echo [INFO] 系统 Python %%p 版本过低（需�?3.10+），继续搜索...
                )
            ) else (
                echo [INFO] 跳过 WindowsApps 中的 Python 占位: %%p
            )
        )
    )
)

:: 3. 常见安装路径
if not defined PYTHON (
    for %%d in (
        "%LOCALAPPDATA%\Programs\Python\Python314"
        "%LOCALAPPDATA%\Programs\Python\Python313"
        "%LOCALAPPDATA%\Programs\Python\Python312"
        "%LOCALAPPDATA%\Programs\Python\Python311"
        "%LOCALAPPDATA%\Programs\Python\Python310"
    ) do (
        if not defined PYTHON (
            if exist "%%~d\python.exe" (
                set "PYTHON=%%~d\python.exe"
                echo [INFO] 找到 Python: !PYTHON!
            )
        )
    )
)

if not defined PYTHON (
    echo [ERROR] Python 未找到，请先安装 Python 3.10+
    pause
    exit /b 1
)

echo [INFO] 使用 Python: !PYTHON!
echo:

"%PYTHON%" "%SCRIPT_DIR%\install_mcp.py" --uninstall %*
exit /b %ERRORLEVEL%


