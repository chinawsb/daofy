@echo off
setlocal EnableDelayedExpansion

:: UTF-8 encoding for pip and script output
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo:
echo ============================================================
echo   Daofy Installer
echo ============================================================
echo:

set "SD=%~dp0"
if "%SD:~-1%"=="\" set "SD=%SD:~0,-1%"

set "PY="

:: ============================================================
:: Step 1: Venv Python
:: ============================================================
if exist "%SD%\venv\Scripts\python.exe" (
    set "PY=%SD%\venv\Scripts\python.exe"
    echo [INFO] Found venv Python
    goto :VERIFY
)

:: ============================================================
:: Step 2: System Python (from PATH)
:: ============================================================
echo [INFO] Checking system Python...
where python >nul 2>&1
if not errorlevel 1 call :FIND_SYS_PY
if defined PY goto :VERIFY

:: ============================================================
:: Step 3: Common install paths
:: ============================================================
echo [INFO] Checking install paths...
call :FIND_INSTALL_PY
if defined PY goto :VERIFY

:: ============================================================
:: Step 4: Download and install Python
:: ============================================================
echo [WARNING] Python not found. Attempting download...
echo:
call :DOWNLOAD_PY

:: If download succeeded, install it
if defined PI (
    call :INSTALL_PY
)
if defined PY goto :VERIFY

:: Fallback: re-check existing Python
call :FIND_FALLBACK_PY
if defined PY goto :VERIFY

:: ============================================================
:: Error: No Python
:: ============================================================
echo [ERROR] Python 3.10+ not found.
echo         Please install manually: https://www.python.org/downloads/
echo:
pause
exit /b 1

:: ============================================================
:: Subroutines
:: ============================================================

:: ----------------------------------------------------------
:: Find system Python from PATH
:: ----------------------------------------------------------
:FIND_SYS_PY
for /f "delims=" %%p in ('where python 2^>nul') do (
    if not defined PY (
        echo "%%p" | findstr /I "WindowsApps" >nul 2>&1
        if errorlevel 1 (
            "%%p" -c "import sys;v=sys.version_info;sys.exit(0 if v.major==3 and v.minor>=10 else 1)" 2>nul
            if not errorlevel 1 set "PY=%%p"
        )
    )
)
goto :eof

:: ----------------------------------------------------------
:: Find Python from common local install paths
:: ----------------------------------------------------------
:FIND_INSTALL_PY
for %%d in (
    "Python314" "Python313" "Python312" "Python311" "Python310"
) do (
    if not defined PY (
        if exist "%LOCALAPPDATA%\Programs\Python\%%~d\python.exe" (
            set "PY=%LOCALAPPDATA%\Programs\Python\%%~d\python.exe"
        )
    )
)
goto :eof

:: ----------------------------------------------------------
:: Try to find Python after download failure (broader search)
:: ----------------------------------------------------------
:FIND_FALLBACK_PY
where python >nul 2>&1
if errorlevel 1 goto :eof

for /f "delims=" %%p in ('where python 2^>nul') do (
    if not defined PY (
        echo "%%p" | findstr /I "WindowsApps" >nul 2>&1
        if errorlevel 1 (
            "%%p" -c "import sys;v=sys.version_info;sys.exit(0 if v.major==3 and v.minor>=10 else 1)" 2>nul
            if not errorlevel 1 (
                set "PY=%%p"
                echo [WARNING] Using existing Python: %%p
            )
        )
    )
)
goto :eof

:: ============================================================
:: Download Python 3.14
:: Uses flat per-version sequential mirror checks
:: Each subroutine has at most 1 level of for/if nesting
:: ============================================================

:DOWNLOAD_PY
set "PI="
set "PV="

for %%v in (
    3.14.0  3.14.0rc2  3.14.0rc1  3.14.0b3  3.14.0b2  3.14.0b1
    3.14.0a7  3.14.0a6  3.14.0a5  3.14.0a4
) do (
    if not defined PI call :DL_CHECK_VER %%v
)
if not defined PI (
    echo [ERROR] Failed to download any Python 3.14 version.
)
goto :eof

:: ----------------------------------------------------------
:: Try to download a specific version from all mirrors
:: ----------------------------------------------------------
:DL_CHECK_VER
set "VER=%~1"
set "TF=%TEMP%\python-%VER%-amd64.exe"

call :DL_URL "https://mirrors.tuna.tsinghua.edu.cn/python/%VER%/python-%VER%-amd64.exe" "%TF%"
if defined PI goto :eof

call :DL_URL "https://mirrors.aliyun.com/python/%VER%/python-%VER%-amd64.exe" "%TF%"
if defined PI goto :eof

call :DL_URL "https://mirrors.ustc.edu.cn/python/%VER%/python-%VER%-amd64.exe" "%TF%"
if defined PI goto :eof

call :DL_URL "https://www.python.org/ftp/python/%VER%/python-%VER%-amd64.exe" "%TF%"
if defined PI goto :eof

goto :eof

:: ----------------------------------------------------------
:: Download a single URL to a destination file
:: Try curl first, fall back to PowerShell
:: ----------------------------------------------------------
:DL_URL
set "URL=%~1"
set "DST=%~2"

echo [INFO] Trying %URL%

where curl >nul 2>&1
if errorlevel 1 (
    powershell -NoProfile -Command "try { $wc = New-Object System.Net.WebClient; $wc.DownloadFile('%URL%', '%DST%') } catch {}"
) else (
    curl -L --connect-timeout 10 -s -o "%DST%" "%URL%"
)

:: Validate: file exists and is >= 20MB
if exist "%DST%" call :CHECK_SIZE "%DST%"
if not defined PI if exist "%DST%" del "%DST%" 2>nul
goto :eof

:: ----------------------------------------------------------
:: Check if downloaded file is valid (>= 20MB)
:: ----------------------------------------------------------
:CHECK_SIZE
set "FP=%~1"
for %%f in ("%FP%") do if %%~zf geq 20000000 (
    set "PI=%FP%"
    set "PV=%VER%"
    echo [SUCCESS] Downloaded Python %VER%
)
goto :eof

:: ============================================================
:: Install downloaded Python installer
:: ============================================================
:INSTALL_PY
echo [INFO] Installing Python %PV% ...
echo        Please wait...

"%PI%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=0
if errorlevel 1 (
    echo [ERROR] Python installation failed.
    del "%PI%" 2>nul
    exit /b 1
)
del "%PI%" 2>nul

:: Re-detect Python after installation
set "PY="
if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
) else (
    where python >nul 2>&1
    if not errorlevel 1 for /f "delims=" %%p in ('where python 2^>nul') do (
        if not defined PY (
            echo "%%p" | findstr /I "WindowsApps" >nul 2>&1
            if errorlevel 1 set "PY=%%p"
        )
    )
)
if not defined PY (
    echo [ERROR] Python not found after installation. Restart terminal and retry.
    pause
    exit /b 1
)
echo [SUCCESS] Python installed: %PY%
goto :eof

:: ============================================================
:: Verify Python version
:: ============================================================
:VERIFY
if not defined PY (
    echo [ERROR] Python path not found.
    pause
    exit /b 1
)

echo [INFO] Python: !PY!

"!PY!" -c "import sys;v=sys.version_info;sys.exit(0 if v.major==3 and v.minor>=10 else 1)" 2>nul
if errorlevel 1 (
    echo [ERROR] Python 3.10+ required.
    pause
    exit /b 1
)
echo [INFO] Python version OK.

:: ============================================================
:: Download install_mcp.py if missing
:: ============================================================
:ENSURE_SCRIPT
if exist "%SD%\install_mcp.py" goto :RUN_INSTALL

echo [INFO] Downloading install_mcp.py...

for %%s in (
    "https://raw.githubusercontent.com/chinawsb/daofy/main/install_mcp.py"
    "https://gitee.com/zuoyouruanjian/daofy/raw/main/install_mcp.py"
    "https://ghproxy.net/https://raw.githubusercontent.com/chinawsb/daofy/main/install_mcp.py"
) do (
    if not exist "%SD%\install_mcp.py" (
        echo        %%~s
        where curl >nul 2>&1
        if errorlevel 1 (
            powershell -NoProfile -Command "try { $wc = New-Object System.Net.WebClient; $wc.DownloadFile('%%~s', '%SD%\\install_mcp.py') } catch {}"
        ) else (
            curl -L --connect-timeout 10 -s -o "%SD%\install_mcp.py" "%%~s"
        )
        if exist "%SD%\install_mcp.py" (
            for %%f in ("%SD%\install_mcp.py") do if %%~zf lss 100 del "%SD%\install_mcp.py" 2>nul
        )
    )
)
if not exist "%SD%\install_mcp.py" (
    echo [ERROR] Failed to download install_mcp.py.
    echo         https://github.com/chinawsb/daofy
    pause
    exit /b 1
)
echo [SUCCESS] install_mcp.py downloaded.

:: ============================================================
:: Run installation
:: ============================================================
:RUN_INSTALL
echo [INFO] Starting Daofy installation...
echo:

"!PY!" "%SD%\install_mcp.py" %*
if %errorlevel%==0 goto :RUN_OK
if %errorlevel%==1 goto :RUN_FAIL
if %errorlevel%==2 goto :RUN_CANCEL
echo:
echo [WARNING] Operation completed with exit code %errorlevel%
pause
exit /b %errorlevel%

:RUN_OK
echo:
echo [SUCCESS] Daofy installed successfully!
pause
exit /b 0

:RUN_FAIL
echo:
echo [ERROR] Installation failed.
pause
exit /b 1

:RUN_CANCEL
echo:
echo [INFO] Installation cancelled.
pause
exit /b 2


