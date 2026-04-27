@echo off
setlocal EnableDelayedExpansion

chcp 65001 >nul 2>&1

echo:
echo ============================================================
echo   Delphi MCP Server Installer
echo ============================================================
echo:

where powershell >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [ERROR] PowerShell not found. Please install PowerShell 5.1+
    goto :fail
)

set "SCRIPT_DIR=%~dp0"

if not exist "%SCRIPT_DIR%install.ps1" (
    echo [ERROR] install.ps1 not found in %SCRIPT_DIR%
    goto :fail
)

echo Launching install script...
echo:

powershell -ExecutionPolicy Bypass -NoProfile -File "%SCRIPT_DIR%install.ps1" %*

if %ERRORLEVEL% neq 0 (
    goto :fail
)

goto :end

:fail
echo:
echo [ERROR] Installation failed.
pause
exit /b 1

:end
echo:
pause
exit /b 0
