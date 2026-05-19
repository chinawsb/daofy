@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

echo:
echo ============================================================
echo   Daofy Installer
echo ============================================================
echo:

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

:: 1. venv Python
set "PYTHON="
if exist "%SCRIPT_DIR%\venv\Scripts\python.exe" (
    set "PYTHON=%SCRIPT_DIR%\venv\Scripts\python.exe"
    echo [INFO] 使用虚拟环境 Python: !PYTHON!
)

:: 2. 系统 Python
if not defined PYTHON (
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
                    echo [INFO] 系统 Python %%p 版本过低（需要 3.10+），继续搜索...
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

:: 4. 下载安装 Python 3.14
if not defined PYTHON (
    echo [WARNING] 未找到 Python，将自动下载并安装 Python 3.14
    echo:

    set "PY_INSTALLER=%TEMP%\python-3.14.0-amd64.exe"

    :: 国内镜像源优先，下载更快
    set "PY_URLS="
    set "PY_URLS=https://mirrors.tuna.tsinghua.edu.cn/python/3.14.0/python-3.14.0-amd64.exe"
    set "PY_URLS=!PY_URLS! https://mirrors.aliyun.com/python/3.14.0/python-3.14.0-amd64.exe"
    set "PY_URLS=!PY_URLS! https://mirrors.ustc.edu.cn/python/3.14.0/python-3.14.0-amd64.exe"
    set "PY_URLS=!PY_URLS! https://www.python.org/ftp/python/3.14.0/python-3.14.0-amd64.exe"

    for %%u in (!PY_URLS!) do (
        if not exist "!PY_INSTALLER!" (
            echo [INFO] 正在下载 Python 3.14.0 ...
            echo        %%u

            where curl >nul 2>&1
            if !ERRORLEVEL! equ 0 (
                curl -L --connect-timeout 10 --progress-bar -o "!PY_INSTALLER!" "%%u"
                echo:
            ) else (
                echo [INFO] 使用 PowerShell 下载（显示进度条）...
                powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%%u' -OutFile '!PY_INSTALLER!' -TimeoutSec 120 -ErrorAction Stop } catch {}"
            )

            :: 验证下载的文件是否完整
            set "DL_VALID=1"
            if not exist "!PY_INSTALLER!" set "DL_VALID=0"
            if exist "!PY_INSTALLER!" for %%f in ("!PY_INSTALLER!") do if %%~zf LSS 20000000 set "DL_VALID=0"
            if exist "!PY_INSTALLER!" (
                findstr /M "MZ" "!PY_INSTALLER!" >nul 2>&1
                if !ERRORLEVEL! neq 0 set "DL_VALID=0"
            )
            if !DL_VALID! equ 0 (
                echo [WARNING] 文件下载不完整，尝试下一个镜像源 ...
                del "!PY_INSTALLER!" 2>nul
            )
        )
    )

    if not exist "!PY_INSTALLER!" (
        echo [ERROR] Python 下载失败，请尝试手动安装:
        echo        winget install Python.Python.3.14
        echo        或访问: https://www.python.org/downloads/
        pause
        exit /b 1
    )

    echo [INFO] 正在安装 Python 3.14.0 ^(InstallAllUsers=0, PrependPath=1^) ...
    echo        请等待安装完成 ...
    echo:

    "!PY_INSTALLER!" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=0

    if !ERRORLEVEL! neq 0 (
        echo [ERROR] Python 安装失败，请手动安装: https://www.python.org/downloads/
        del "!PY_INSTALLER!" 2>nul
        pause
        exit /b 1
    )

    del "!PY_INSTALLER!" 2>nul

    :: 重新检测
    set "PYTHON="
    for %%d in (
        "%LOCALAPPDATA%\Programs\Python\Python314"
    ) do (
        if not defined PYTHON (
            if exist "%%~d\python.exe" (
                set "PYTHON=%%~d\python.exe"
            )
        )
    )
    if not defined PYTHON (
        where python >nul 2>&1
        if !ERRORLEVEL! equ 0 (
            for /f "delims=" %%p in ('where python 2^>nul') do if not defined PYTHON (
                echo "%%p" | findstr /I "WindowsApps" >nul 2>&1
                if !ERRORLEVEL! neq 0 (
                    "%%p" -c "import sys; v=sys.version_info; sys.exit(0 if v.major==3 and v.minor>=10 else 1)" 2>nul
                    if !ERRORLEVEL! equ 0 set "PYTHON=%%p"
                )
            )
        )
    )

    if not defined PYTHON (
        echo [ERROR] Python 安装后仍未找到，请重启终端后重试
        pause
        exit /b 1
    )

    echo [SUCCESS] Python 3.14.0 安装成功: !PYTHON!
    echo:
)

:: 验证 Python 版本
"%PYTHON%" -c "import sys; v=sys.version_info; sys.exit(0 if v.major==3 and v.minor>=10 else 1)" 2>nul
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Python 版本过低，需要 3.10+
    pause
    exit /b 1
)

:: 如果 install_mcp.py 不存在，先从 GitHub release 下载引导（多镜像回退）
if not exist "%SCRIPT_DIR%\install_mcp.py" (
    echo [INFO] install_mcp.py 不存在，正在从 GitHub 下载引导脚本...

    :: GitHub raw 内容 URL 列表（原始源 + 国内代理，自动回退）
    set "GH_URLS="
    set "GH_URLS=https://raw.githubusercontent.com/chinawsb/daofy/main/install_mcp.py"
    set "GH_URLS=!GH_URLS! https://ghproxy.net/https://raw.githubusercontent.com/chinawsb/daofy/main/install_mcp.py"

    for %%s in (!GH_URLS!) do (
        if not exist "%SCRIPT_DIR%\install_mcp.py" (
            echo [INFO] 正在下载引导脚本...
            echo        %%s

            where curl >nul 2>&1
            if !ERRORLEVEL! equ 0 (
                curl -L --connect-timeout 10 --progress-bar -o "%SCRIPT_DIR%\install_mcp.py" "%%s"
                echo:
            ) else (
                echo [INFO] 使用 PowerShell 下载...
                powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%%s' -OutFile '%SCRIPT_DIR%\install_mcp.py' -TimeoutSec 30 -ErrorAction Stop } catch {}"
            )

            :: 验证下载文件是否正常（存在且 > 100 字节）
            set "DL_VALID=1"
            if not exist "%SCRIPT_DIR%\install_mcp.py" set "DL_VALID=0"
            if exist "%SCRIPT_DIR%\install_mcp.py" for %%f in ("%SCRIPT_DIR%\install_mcp.py") do if %%~zf LSS 100 set "DL_VALID=0"
            if !DL_VALID! equ 0 (
                echo [WARNING] 文件下载不完整，尝试下一个镜像源 ...
                if exist "%SCRIPT_DIR%\install_mcp.py" del "%SCRIPT_DIR%\install_mcp.py" 2>nul
            )
        )
    )

    if not exist "%SCRIPT_DIR%\install_mcp.py" (
        echo [ERROR] 无法下载 install_mcp.py，请手动下载完整包
        echo         https://github.com/chinawsb/daofy
        pause
        exit /b 1
    )
    echo [SUCCESS] 引导脚本下载成功
)

echo [INFO] 使用 Python: %PYTHON%
echo:

"%PYTHON%" "%SCRIPT_DIR%\install_mcp.py" %*

if %ERRORLEVEL% neq 0 (
    echo:
    echo [ERROR] 安装失败
    pause
    exit /b 1
)

echo:
pause
exit /b 0
