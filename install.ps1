#Requires -Version 5.1
<#
.SYNOPSIS
    Delphi MCP Server 安装脚本 - 自动检测并配置 AI Agent

.DESCRIPTION
    此脚本用于检测用户已安装的 AI Agent，并检查是否已配置本 MCP Server。
    如果未配置，则自动将 MCP Server 添加到相应的 AI Agent 配置中。

    支持的 AI Agent:
    - Claude Desktop
    - Trae
    - CodeArts Agent
    - Cursor
    - OpenCode
    - Windsurf
    - Cline
    - Roo Code
    - 通义灵码 (Tongyi Lingma)
    - 豆包 (Doubao)
    - Kimi
    - DeepSeek
    - 智谱清言 (ChatGLM)

.EXAMPLE
    .\install.ps1
    运行安装脚本，自动检测并配置所有已安装的 AI Agent

.EXAMPLE
    .\install.ps1 -Agent "Claude"
    仅配置指定的 AI Agent

.EXAMPLE
    .\install.ps1 -Force
    强制重新配置，即使已存在配置

.PARAMETER Agent
    指定要配置的 AI Agent 名称，可选值: Claude, Trae, CodeArts, Cursor, OpenCode, Windsurf, Cline, Roo, Tongyi, Doubao, Kimi, DeepSeek, ChatGLM, All
    默认值为 All

.PARAMETER Force
    强制重新配置，即使已存在配置

.PARAMETER PythonPath
    指定 Python 解释器路径，默认自动检测

.PARAMETER ProjectDir
    指定项目目录路径（CodeArts Agent 使用）。MCP Server 将在该目录下运行，
    从而使知识库和编译功能针对该项目的 Delphi 代码。

.NOTES
    Author: Delphi MCP Server Team
    Version: 1.0.0
#>

param(
    [Parameter(Mandatory=$false)]
    [ValidateSet("Claude", "Trae", "CodeArts", "Cursor", "OpenCode", "Windsurf", "Cline", "Roo", "Tongyi", "Doubao", "Kimi", "DeepSeek", "ChatGLM", "All")]
    [string]$Agent = "All",

    [Parameter(Mandatory=$false)]
    [switch]$Force,

    [Parameter(Mandatory=$false)]
    [string]$PythonPath = "",

    [Parameter(Mandatory=$false)]
    [string]$ProjectDir = ""
)

# ============================================================
# 全局变量和配置
# ============================================================

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$McpServerName = "delphi-compiler"
$McpServerScript = Join-Path $ScriptDir "src\server.py"

# 颜色输出函数
function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Write-Success {
    param([string]$Message)
    Write-ColorOutput "[SUCCESS] $Message" "Green"
}

function Write-Info {
    param([string]$Message)
    Write-ColorOutput "[INFO] $Message" "Cyan"
}

function Write-Warning {
    param([string]$Message)
    Write-ColorOutput "[WARNING] $Message" "Yellow"
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-ColorOutput "[ERROR] $Message" "Red"
}

function Write-Separator {
    param([string]$Title = "")
    $line = "=" * 60
    if ($Title) {
        Write-ColorOutput $line "Cyan"
        Write-ColorOutput "  $Title" "Cyan"
        Write-ColorOutput $line "Cyan"
    } else {
        Write-ColorOutput $line "Cyan"
    }
}

# ============================================================
# 检测 Python 环境
# ============================================================

function Get-PythonExecutable {
    param([string]$PreferredPath)

    if ($PreferredPath -and (Test-Path $PreferredPath)) {
        return $PreferredPath
    }

    # 优先检查虚拟环境
    $venvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        Write-Info "使用虚拟环境 Python: $venvPython"
        return $venvPython
    }

    # 检查系统 Python
    $systemPython = Get-Command python -ErrorAction SilentlyContinue
    if ($systemPython) {
        Write-Info "使用系统 Python: $($systemPython.Source)"
        return $systemPython.Source
    }

    # 检查常见安装路径
    $commonPaths = @(
        "${env:LOCALAPPDATA}\Programs\Python\Python3*\python.exe",
        "${env:LOCALAPPDATA}\Programs\Python\Python*\python.exe",
        "C:\Python3*\python.exe",
        "C:\Python*\python.exe"
    )

    foreach ($pattern in $commonPaths) {
        $found = Get-Item $pattern -ErrorAction SilentlyContinue | 
                 Sort-Object { $_.FullName } -Descending | 
                 Select-Object -First 1
        if ($found) {
            Write-Info "使用 Python: $($found.FullName)"
            return $found.FullName
        }
    }

    return $null
}

function Test-PythonVersion {
    param([string]$PythonExe)

    try {
        $version = & $PythonExe --version 2>&1
        if ($version -match "Python (\d+)\.(\d+)") {
            $major = [int]$matches[1]
            $minor = [int]$matches[2]
            if ($major -eq 3 -and $minor -ge 10) {
                return $true
            }
            Write-Warning "Python 版本过低: $version，需要 3.10+"
            return $false
        }
    }
    catch {
        Write-ErrorMsg "无法检测 Python 版本: $_"
        return $false
    }
    return $false
}

# ============================================================
# 检查依赖项
# ============================================================

function Test-GitInstalled {
    try {
        $git = Get-Command git -ErrorAction SilentlyContinue
        if ($git) {
            $version = & git --version 2>&1
            Write-Info "Git 已安装: $version"
            return $true
        }
        
        # 检查常见安装路径
        $gitPaths = @(
            "${env:ProgramFiles}\Git\bin\git.exe",
            "${env:ProgramFiles(x86)}\Git\bin\git.exe",
            "${env:LOCALAPPDATA}\Programs\Git\bin\git.exe"
        )
        
        foreach ($path in $gitPaths) {
            if (Test-Path $path) {
                $version = & $path --version 2>&1
                Write-Info "Git 已安装: $version"
                return $true
            }
        }
        
        return $false
    }
    catch {
        return $false
    }
}

function Test-SevenZipInstalled {
    try {
        $7z = Get-Command 7z -ErrorAction SilentlyContinue
        if ($7z) {
            Write-Info "7-Zip 已安装"
            return $true
        }
        
        # 检查常见安装路径
        $7zPaths = @(
            "${env:ProgramFiles}\7-Zip\7z.exe",
            "${env:ProgramFiles(x86)}\7-Zip\7z.exe"
        )
        
        foreach ($path in $7zPaths) {
            if (Test-Path $path) {
                Write-Info "7-Zip 已安装: $path"
                return $true
            }
        }
        
        return $false
    }
    catch {
        return $false
    }
}

function Test-PythonPackages {
    param(
        [string]$PythonExe,
        [string]$RequirementsFile
    )
    
    $missingPackages = @()
    $installedPackages = @()
    
    # 读取 requirements.txt
    if (-not (Test-Path $RequirementsFile)) {
        Write-Warning "未找到 requirements.txt: $RequirementsFile"
        return @{ Success = $false; Missing = @(); Installed = @() }
    }
    
    $requirements = Get-Content $RequirementsFile | Where-Object { 
        $_ -and $_ -notmatch "^\s*#" -and $_ -notmatch "^\s*$"
    }
    
    foreach ($req in $requirements) {
        # 解析包名（去掉版本要求）
        if ($req -match "^([a-zA-Z0-9_-]+)") {
            $packageName = $matches[1]
            
            # 检查包是否已安装（用pip show避免import副作用）
            $checkResult = & $PythonExe -m pip show $packageName --quiet 2>&1
            $found = ($LASTEXITCODE -eq 0)
            
            if ($found) {
                $installedPackages += $packageName
            }
            else {
                $missingPackages += $packageName
            }
        }
    }
    
    return @{
        Success = ($missingPackages.Count -eq 0)
        Missing = $missingPackages
        Installed = $installedPackages
    }
}

function Install-PythonPackages {
    param(
        [string]$PythonExe,
        [string]$RequirementsFile
    )
    
    Write-Info "正在安装 Python 依赖包..."
    
    # 使用国内镜像源加速
    $mirrors = @(
        "https://pypi.tuna.tsinghua.edu.cn/simple",
        "https://mirrors.aliyun.com/pypi/simple/",
        "https://pypi.mirrors.ustc.edu.cn/simple/"
    )
    
    $installed = $false
    foreach ($mirror in $mirrors) {
        try {
            Write-Info "尝试使用镜像: $mirror"
            & $PythonExe -m pip install -r $RequirementsFile -i $mirror --quiet 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Success "依赖包安装成功"
                $installed = $true
                break
            }
        }
        catch {
            Write-Warning "镜像 $mirror 安装失败，尝试下一个..."
        }
    }
    
    if (-not $installed) {
        # 尝试不使用镜像
        try {
            Write-Info "尝试使用默认源安装..."
            & $PythonExe -m pip install -r $RequirementsFile --quiet 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Success "依赖包安装成功"
                $installed = $true
            }
        }
        catch {
            Write-ErrorMsg "依赖包安装失败: $_"
        }
    }
    
    return $installed
}

function Test-VirtualEnvironment {
    param([string]$ScriptDir)
    
    $venvPath = Join-Path $ScriptDir "venv"
    $venvPython = Join-Path $venvPath "Scripts\python.exe"
    $venvPip = Join-Path $venvPath "Scripts\pip.exe"
    
    if ((Test-Path $venvPython) -and (Test-Path $venvPip)) {
        return @{
            Exists = $true
            PythonPath = $venvPython
            PipPath = $venvPip
        }
    }
    
    return @{
        Exists = $false
        PythonPath = $null
        PipPath = $null
    }
}

function New-VirtualEnvironment {
    param(
        [string]$PythonExe,
        [string]$ScriptDir
    )
    
    $venvPath = Join-Path $ScriptDir "venv"
    
    Write-Info "正在创建虚拟环境..."
    
    try {
        & $PythonExe -m venv $venvPath 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $venvPython = Join-Path $venvPath "Scripts\python.exe"
            Write-Success "虚拟环境创建成功: $venvPython"
            return $venvPython
        }
    }
    catch {
        Write-ErrorMsg "虚拟环境创建失败: $_"
    }
    
    return $null
}

# ============================================================
# AI Agent 检测函数
# ============================================================

function Test-ClaudeDesktop {
    # 检查 Claude Desktop 是否安装
    $claudePaths = @(
        "${env:LOCALAPPDATA}\Programs\Claude\Claude.exe",
        "${env:ProgramFiles}\Claude\Claude.exe",
        "${env:ProgramFiles(x86)}\Claude\Claude.exe"
    )

    foreach ($path in $claudePaths) {
        if (Test-Path $path) {
            return @{
                Installed = $true
                Path = $path
                ConfigPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
                Name = "Claude Desktop"
                ConfigType = "Standard"
            }
        }
    }

    # 即使未找到可执行文件，也检查配置文件是否存在
    $configPath = Join-Path $env:APPDATA "Claude\claude_desktop_config.json"
    if (Test-Path $configPath) {
        return @{
            Installed = $true
            Path = "Unknown"
            ConfigPath = $configPath
            Name = "Claude Desktop"
            ConfigType = "Standard"
        }
    }

    return @{
        Installed = $false
        Path = $null
        ConfigPath = $configPath
        Name = "Claude Desktop"
        ConfigType = "Standard"
    }
}

function Test-Trae {
    # 检查 Trae 是否安装
    $traePaths = @(
        "${env:LOCALAPPDATA}\Programs\Trae\Trae.exe",
        "${env:ProgramFiles}\Trae\Trae.exe"
    )

    foreach ($path in $traePaths) {
        if (Test-Path $path) {
            return @{
                Installed = $true
                Path = $path
                ConfigPath = Join-Path $env:USERPROFILE ".trae-cn\mcp_config.json"
                Name = "Trae"
                ConfigType = "Standard"
            }
        }
    }

    # 检查配置文件
    $configPath = Join-Path $env:USERPROFILE ".trae-cn\mcp_config.json"
    if (Test-Path $configPath) {
        return @{
            Installed = $true
            Path = "Unknown"
            ConfigPath = $configPath
            Name = "Trae"
            ConfigType = "Standard"
        }
    }

    return @{
        Installed = $false
        Path = $null
        ConfigPath = $configPath
        Name = "Trae"
        ConfigType = "Standard"
    }
}

function Test-CodeArtsAgent {
    # 检查 CodeArts Agent 是否安装
    # 1. 检查可执行文件
    $codeartsPaths = @(
        "${env:LOCALAPPDATA}\Programs\CodeArts\CodeArts.exe",
        "${env:ProgramFiles}\CodeArts\CodeArts.exe"
    )

    foreach ($path in $codeartsPaths) {
        if (Test-Path $path) {
            return @{
                Installed = $true
                Path = $path
                ConfigPath = Join-Path $env:USERPROFILE ".codeartsdoer\mcp\mcp_settings.json"
                Name = "CodeArts Agent"
                ConfigType = "Standard"
            }
        }
    }

    # 2. 检查 AppData\Roaming\codearts-agent (实际安装位置)
    $codeartsRoaming = Join-Path $env:APPDATA "codearts-agent"
    if (Test-Path $codeartsRoaming) {
        return @{
            Installed = $true
            Path = $codeartsRoaming
            ConfigPath = Join-Path $env:USERPROFILE ".codeartsdoer\mcp\mcp_settings.json"
            Name = "CodeArts Agent"
            ConfigType = "Standard"
        }
    }

    # 检查配置文件
    $configPath = Join-Path $env:USERPROFILE ".codeartsdoer\mcp\mcp_settings.json"
    if (Test-Path $configPath) {
        return @{
            Installed = $true
            Path = "Unknown"
            ConfigPath = $configPath
            Name = "CodeArts Agent"
            ConfigType = "Standard"
        }
    }

    return @{
        Installed = $false
        Path = $null
        ConfigPath = $configPath
        Name = "CodeArts Agent"
        ConfigType = "Standard"
    }
}

function Test-Cursor {
    # 检查 Cursor 是否安装
    $cursorPaths = @(
        "${env:LOCALAPPDATA}\Programs\Cursor\Cursor.exe",
        "${env:ProgramFiles}\Cursor\Cursor.exe"
    )

    foreach ($path in $cursorPaths) {
        if (Test-Path $path) {
            return @{
                Installed = $true
                Path = $path
                ConfigPath = Join-Path $env:USERPROFILE ".cursor\mcp.json"
                Name = "Cursor"
                ConfigType = "Standard"
            }
        }
    }

    # 检查 AppData 目录
    $cursorRoaming = Join-Path $env:APPDATA "Cursor"
    if (Test-Path $cursorRoaming) {
        return @{
            Installed = $true
            Path = $cursorRoaming
            ConfigPath = Join-Path $env:USERPROFILE ".cursor\mcp.json"
            Name = "Cursor"
            ConfigType = "Standard"
        }
    }

    # 检查配置文件
    $configPath = Join-Path $env:USERPROFILE ".cursor\mcp.json"
    if (Test-Path $configPath) {
        return @{
            Installed = $true
            Path = "Unknown"
            ConfigPath = $configPath
            Name = "Cursor"
            ConfigType = "Standard"
        }
    }

    return @{
        Installed = $false
        Path = $null
        ConfigPath = $configPath
        Name = "Cursor"
        ConfigType = "Standard"
    }
}

function Test-OpenCode {
    # OpenCode 配置文件在项目目录下
    $configPath = Join-Path $ScriptDir "opencode.json"
    
    # 检查 OpenCode 是否安装（多种方式）
    # 1. npm 全局安装
    $opencodeNpm = Get-Command opencode -ErrorAction SilentlyContinue
    # 2. AppData\Local 安装
    $opencodeLocal = Join-Path $env:LOCALAPPDATA "opencode\OpenCode.exe"
    $opencodeCli = Join-Path $env:LOCALAPPDATA "opencode\opencode-cli.exe"
    # 3. AppData\Roaming 安装
    $opencodeRoaming = Join-Path $env:APPDATA "opencode"
    # 4. ai.opencode.desktop (桌面版)
    $aiOpenencodeRoaming = Join-Path $env:APPDATA "ai.opencode.desktop"
    $aiOpenencodeLocal = Join-Path $env:LOCALAPPDATA "ai.opencode.desktop"
    
    $opencodeInstalled = $opencodeNpm -or 
                         (Test-Path $opencodeLocal) -or 
                         (Test-Path $opencodeCli) -or 
                         (Test-Path $opencodeRoaming) -or
                         (Test-Path $aiOpenencodeRoaming) -or
                         (Test-Path $aiOpenencodeLocal)
    
    # 确定安装路径
    $installPath = if ($opencodeNpm) { $opencodeNpm.Source } 
                   elseif (Test-Path $opencodeLocal) { $opencodeLocal }
                   elseif (Test-Path $opencodeCli) { $opencodeCli }
                   elseif (Test-Path $aiOpenencodeRoaming) { $aiOpenencodeRoaming }
                   elseif (Test-Path $aiOpenencodeLocal) { $aiOpenencodeLocal }
                   else { "OpenCode CLI" }
    
    if (Test-Path $configPath) {
        return @{
            Installed = $true
            Path = $installPath
            ConfigPath = $configPath
            Name = "OpenCode"
            ConfigType = "OpenCode"
        }
    }
    
    # 即使没有配置文件，如果 OpenCode 已安装也返回
    if ($opencodeInstalled) {
        return @{
            Installed = $true
            Path = $installPath
            ConfigPath = $configPath
            Name = "OpenCode"
            ConfigType = "OpenCode"
        }
    }

    return @{
        Installed = $false
        Path = $null
        ConfigPath = $configPath
        Name = "OpenCode"
        ConfigType = "OpenCode"
    }
}

function Test-Windsurf {
    # 检查 Windsurf 是否安装
    $windsurfPaths = @(
        "${env:LOCALAPPDATA}\Programs\Windsurf\Windsurf.exe",
        "${env:ProgramFiles}\Windsurf\Windsurf.exe"
    )

    foreach ($path in $windsurfPaths) {
        if (Test-Path $path) {
            return @{
                Installed = $true
                Path = $path
                ConfigPath = Join-Path $env:USERPROFILE ".windsurf\mcp.json"
                Name = "Windsurf"
                ConfigType = "Standard"
            }
        }
    }

    # 检查 AppData 目录
    $windsurfRoaming = Join-Path $env:APPDATA "Windsurf"
    if (Test-Path $windsurfRoaming) {
        return @{
            Installed = $true
            Path = $windsurfRoaming
            ConfigPath = Join-Path $env:USERPROFILE ".windsurf\mcp.json"
            Name = "Windsurf"
            ConfigType = "Standard"
        }
    }

    # 检查配置文件
    $configPath = Join-Path $env:USERPROFILE ".windsurf\mcp.json"
    if (Test-Path $configPath) {
        return @{
            Installed = $true
            Path = "Unknown"
            ConfigPath = $configPath
            Name = "Windsurf"
            ConfigType = "Standard"
        }
    }

    return @{
        Installed = $false
        Path = $null
        ConfigPath = $configPath
        Name = "Windsurf"
        ConfigType = "Standard"
    }
}

function Test-Cline {
    # Cline 是 VS Code 扩展，检查 VS Code 扩展目录
    $vscodeExtensions = Join-Path $env:USERPROFILE ".vscode\extensions"
    $clineExtension = Get-ChildItem $vscodeExtensions -ErrorAction SilentlyContinue | 
                      Where-Object { $_.Name -like "*saoudrizwan.claude-dev*" } | 
                      Select-Object -First 1

    $configPath = Join-Path $env:USERPROFILE ".cline\mcp.json"

    if ($clineExtension) {
        return @{
            Installed = $true
            Path = $clineExtension.FullName
            ConfigPath = $configPath
            Name = "Cline"
            ConfigType = "Standard"
        }
    }

    # 检查配置文件
    if (Test-Path $configPath) {
        return @{
            Installed = $true
            Path = "Unknown"
            ConfigPath = $configPath
            Name = "Cline"
            ConfigType = "Standard"
        }
    }

    return @{
        Installed = $false
        Path = $null
        ConfigPath = $configPath
        Name = "Cline"
        ConfigType = "Standard"
    }
}

function Test-RooCode {
    # Roo Code 是 VS Code 扩展，检查 VS Code 扩展目录
    $vscodeExtensions = Join-Path $env:USERPROFILE ".vscode\extensions"
    $rooExtension = Get-ChildItem $vscodeExtensions -ErrorAction SilentlyContinue | 
                    Where-Object { $_.Name -like "*rooveterinaryinc.roo-cline*" } | 
                    Select-Object -First 1

    $configPath = Join-Path $env:USERPROFILE ".roo\mcp.json"

    if ($rooExtension) {
        return @{
            Installed = $true
            Path = $rooExtension.FullName
            ConfigPath = $configPath
            Name = "Roo Code"
            ConfigType = "Standard"
        }
    }

    # 检查配置文件
    if (Test-Path $configPath) {
        return @{
            Installed = $true
            Path = "Unknown"
            ConfigPath = $configPath
            Name = "Roo Code"
            ConfigType = "Standard"
        }
    }

    return @{
        Installed = $false
        Path = $null
        ConfigPath = $configPath
        Name = "Roo Code"
        ConfigType = "Standard"
    }
}

# ============================================================
# 国内 AI Agent 检测函数
# ============================================================

function Test-TongyiLingma {
    # 通义灵码 - 阿里云 AI 编程助手
    # VS Code 扩展形式
    $vscodeExtensions = Join-Path $env:USERPROFILE ".vscode\extensions"
    $tongyiExtension = Get-ChildItem $vscodeExtensions -ErrorAction SilentlyContinue | 
                       Where-Object { $_.Name -like "*alibaba-cloud.tongyi-lingma*" -or $_.Name -like "*tongyi*" } | 
                       Select-Object -First 1

    # JetBrains 插件形式
    $jetbrainsDir = Join-Path $env:APPDATA "JetBrains"
    $tongyiJetbrains = Get-ChildItem $jetbrainsDir -Directory -ErrorAction SilentlyContinue | 
                       Where-Object { $_.Name -like "*tongyi*" } | 
                       Select-Object -First 1

    # AppData 目录
    $tongyiRoaming = Join-Path $env:APPDATA "tongyi"
    $tongyiLocal = Join-Path $env:LOCALAPPDATA "tongyi"

    $configPath = Join-Path $env:USERPROFILE ".tongyi\mcp.json"

    if ($tongyiExtension) {
        return @{
            Installed = $true
            Path = $tongyiExtension.FullName
            ConfigPath = $configPath
            Name = "通义灵码"
            ConfigType = "Standard"
        }
    }

    if ($tongyiJetbrains) {
        return @{
            Installed = $true
            Path = $tongyiJetbrains.FullName
            ConfigPath = $configPath
            Name = "通义灵码"
            ConfigType = "Standard"
        }
    }

    if ((Test-Path $tongyiRoaming) -or (Test-Path $tongyiLocal)) {
        return @{
            Installed = $true
            Path = if (Test-Path $tongyiRoaming) { $tongyiRoaming } else { $tongyiLocal }
            ConfigPath = $configPath
            Name = "通义灵码"
            ConfigType = "Standard"
        }
    }

    # 检查配置文件
    if (Test-Path $configPath) {
        return @{
            Installed = $true
            Path = "Unknown"
            ConfigPath = $configPath
            Name = "通义灵码"
            ConfigType = "Standard"
        }
    }

    return @{
        Installed = $false
        Path = $null
        ConfigPath = $configPath
        Name = "通义灵码"
        ConfigType = "Standard"
    }
}

function Test-Doubao {
    # 豆包 - 字节跳动 AI 助手
    $doubaoPaths = @(
        "${env:LOCALAPPDATA}\Programs\Doubao\Doubao.exe",
        "${env:ProgramFiles}\Doubao\Doubao.exe",
        "${env:LOCALAPPDATA}\Doubao\Doubao.exe"
    )

    foreach ($path in $doubaoPaths) {
        if (Test-Path $path) {
            return @{
                Installed = $true
                Path = $path
                ConfigPath = Join-Path $env:USERPROFILE ".doubao\mcp.json"
                Name = "豆包"
                ConfigType = "Standard"
            }
        }
    }

    # 检查配置文件
    $configPath = Join-Path $env:USERPROFILE ".doubao\mcp.json"
    if (Test-Path $configPath) {
        return @{
            Installed = $true
            Path = "Unknown"
            ConfigPath = $configPath
            Name = "豆包"
            ConfigType = "Standard"
        }
    }

    return @{
        Installed = $false
        Path = $null
        ConfigPath = $configPath
        Name = "豆包"
        ConfigType = "Standard"
    }
}

function Test-Kimi {
    # Kimi - 月之暗面 AI 助手
    $kimiPaths = @(
        "${env:LOCALAPPDATA}\Programs\Kimi\Kimi.exe",
        "${env:ProgramFiles}\Kimi\Kimi.exe",
        "${env:LOCALAPPDATA}\Kimi\Kimi.exe"
    )

    foreach ($path in $kimiPaths) {
        if (Test-Path $path) {
            return @{
                Installed = $true
                Path = $path
                ConfigPath = Join-Path $env:USERPROFILE ".kimi\mcp.json"
                Name = "Kimi"
                ConfigType = "Standard"
            }
        }
    }

    # 检查配置文件
    $configPath = Join-Path $env:USERPROFILE ".kimi\mcp.json"
    if (Test-Path $configPath) {
        return @{
            Installed = $true
            Path = "Unknown"
            ConfigPath = $configPath
            Name = "Kimi"
            ConfigType = "Standard"
        }
    }

    return @{
        Installed = $false
        Path = $null
        ConfigPath = $configPath
        Name = "Kimi"
        ConfigType = "Standard"
    }
}

function Test-DeepSeek {
    # DeepSeek - 深度求索 AI 助手
    $deepseekPaths = @(
        "${env:LOCALAPPDATA}\Programs\DeepSeek\DeepSeek.exe",
        "${env:ProgramFiles}\DeepSeek\DeepSeek.exe"
    )

    foreach ($path in $deepseekPaths) {
        if (Test-Path $path) {
            return @{
                Installed = $true
                Path = $path
                ConfigPath = Join-Path $env:USERPROFILE ".deepseek\mcp.json"
                Name = "DeepSeek"
                ConfigType = "Standard"
            }
        }
    }

    # 检查配置文件
    $configPath = Join-Path $env:USERPROFILE ".deepseek\mcp.json"
    if (Test-Path $configPath) {
        return @{
            Installed = $true
            Path = "Unknown"
            ConfigPath = $configPath
            Name = "DeepSeek"
            ConfigType = "Standard"
        }
    }

    return @{
        Installed = $false
        Path = $null
        ConfigPath = $configPath
        Name = "DeepSeek"
        ConfigType = "Standard"
    }
}

function Test-ChatGLM {
    # 智谱清言 - 智谱 AI 助手
    $chatglmPaths = @(
        "${env:LOCALAPPDATA}\Programs\ChatGLM\ChatGLM.exe",
        "${env:ProgramFiles}\ChatGLM\ChatGLM.exe",
        "${env:LOCALAPPDATA}\Programs\智谱清言\智谱清言.exe"
    )

    foreach ($path in $chatglmPaths) {
        if (Test-Path $path) {
            return @{
                Installed = $true
                Path = $path
                ConfigPath = Join-Path $env:USERPROFILE ".chatglm\mcp.json"
                Name = "智谱清言"
                ConfigType = "Standard"
            }
        }
    }

    # 检查配置文件
    $configPath = Join-Path $env:USERPROFILE ".chatglm\mcp.json"
    if (Test-Path $configPath) {
        return @{
            Installed = $true
            Path = "Unknown"
            ConfigPath = $configPath
            Name = "智谱清言"
            ConfigType = "Standard"
        }
    }

    return @{
        Installed = $false
        Path = $null
        ConfigPath = $configPath
        Name = "智谱清言"
        ConfigType = "Standard"
    }
}

# ============================================================
# 配置管理函数
# ============================================================

function Get-McpConfig {
    param(
        [string]$PythonExe,
        [string]$ConfigType = "Standard",
        [string]$ProjectDir = ""
    )

    # 根据是否使用虚拟环境决定配置方式
    $venvPython = Join-Path $ScriptDir "venv\Scripts\python.exe"
    
    if ($ConfigType -eq "OpenCode") {
        # OpenCode 使用特殊配置格式
        if ($PythonExe -eq $venvPython) {
            return @{
                type = "local"
                command = @($PythonExe, $McpServerScript)
                environment = @{
                    PYTHONIOENCODING = "utf-8"
                    PYTHONUNBUFFERED = "1"
                    PYTHONUTF8 = "1"
                }
            }
        }
        else {
            return @{
                type = "local"
                command = @("python", "src\server.py")
                environment = @{
                    PYTHONIOENCODING = "utf-8"
                    PYTHONUNBUFFERED = "1"
                    PYTHONUTF8 = "1"
                }
            }
        }
    }
    else {
        # 标准 MCP 配置格式
        if ($PythonExe -eq $venvPython) {
            # 使用虚拟环境，使用绝对路径
            return @{
                command = $PythonExe
                args = @($McpServerScript)
                env = @{
                    PYTHONUNBUFFERED = "1"
                    PYTHONIOENCODING = "utf-8"
                    PYTHONUTF8 = "1"
                }
            }
        }
        else {
            # 使用系统 Python，使用 cwd 方式
            $cwdPath = if ($ProjectDir -and (Test-Path $ProjectDir)) { $ProjectDir } else { $ScriptDir }
            return @{
                command = "python"
                args = @("src\server.py")
                cwd = $cwdPath
                env = @{
                    PYTHONUNBUFFERED = "1"
                    PYTHONIOENCODING = "utf-8"
                    PYTHONUTF8 = "1"
                }
            }
        }
    }
}

# 将 PSCustomObject 转换为 Hashtable（兼容 PowerShell 5.1）
function ConvertTo-Hashtable {
    param([Parameter(ValueFromPipeline)] $InputObject)

    if ($null -eq $InputObject) {
        return $null
    }

    if ($InputObject -is [System.Collections.IEnumerable] -and $InputObject -isnot [string]) {
        $collection = @()
        foreach ($item in $InputObject) {
            $collection += ConvertTo-Hashtable $item
        }
        return $collection
    }
    elseif ($InputObject -is [PSCustomObject]) {
        $hash = @{}
        foreach ($property in $InputObject.PSObject.Properties) {
            $hash[$property.Name] = ConvertTo-Hashtable $property.Value
        }
        return $hash
    }
    else {
        return $InputObject
    }
}

function Test-McpConfigured {
    param(
        [string]$ConfigPath,
        [string]$ServerName,
        [string]$ConfigType = "Standard"
    )

    if (-not (Test-Path $ConfigPath)) {
        return $false
    }

    try {
        $config = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        
        if ($ConfigType -eq "OpenCode") {
            # OpenCode 使用 mcp 节点
            if ($config.mcp -and $config.mcp.$ServerName) {
                return $true
            }
        }
        else {
            # 标准格式使用 mcpServers 节点
            if ($config.mcpServers -and $config.mcpServers.$ServerName) {
                return $true
            }
        }
    }
    catch {
        Write-Warning "无法解析配置文件: $ConfigPath"
    }

    return $false
}

function Add-McpConfig {
    param(
        [string]$ConfigPath,
        [string]$ServerName,
        [hashtable]$McpConfig,
        [string]$ConfigType = "Standard"
    )

    # 确保配置目录存在
    $configDir = Split-Path $ConfigPath -Parent
    if ($configDir -and -not (Test-Path $configDir)) {
        New-Item -ItemType Directory -Path $configDir -Force | Out-Null
        Write-Info "创建配置目录: $configDir"
    }

    # 读取现有配置或创建新配置
    $config = @{}
    if (Test-Path $ConfigPath) {
        try {
            $json = Get-Content $ConfigPath -Raw | ConvertFrom-Json
            $config = ConvertTo-Hashtable $json
        }
        catch {
            Write-Warning "无法解析现有配置文件，将创建新配置"
            $config = @{}
        }
    }

    if ($ConfigType -eq "OpenCode") {
        # OpenCode 使用 mcp 节点
        if (-not $config.ContainsKey("mcp")) {
            $config["mcp"] = @{}
        }
        $config["mcp"][$ServerName] = $McpConfig
    }
    else {
        # 标准格式使用 mcpServers 节点
        if (-not $config.ContainsKey("mcpServers")) {
            $config["mcpServers"] = @{}
        }
        $config["mcpServers"][$ServerName] = $McpConfig
    }

    # 保存配置
    $json = $config | ConvertTo-Json -Depth 10
    $json | Out-File -FilePath $ConfigPath -Encoding UTF8 -Force

    Write-Success "已配置 MCP Server 到: $ConfigPath"
}

function Remove-McpConfig {
    param(
        [string]$ConfigPath,
        [string]$ServerName,
        [string]$ConfigType = "Standard"
    )

    if (-not (Test-Path $ConfigPath)) {
        return
    }

    try {
        $json = Get-Content $ConfigPath -Raw | ConvertFrom-Json
        $config = ConvertTo-Hashtable $json
        
        if ($ConfigType -eq "OpenCode") {
            if ($config.mcp -and $config.mcp.ContainsKey($ServerName)) {
                $config.mcp.Remove($ServerName)
                $json = $config | ConvertTo-Json -Depth 10
                $json | Out-File -FilePath $ConfigPath -Encoding UTF8 -Force
                Write-Info "已移除旧配置: $ServerName"
            }
        }
        else {
            if ($config.mcpServers -and $config.mcpServers.ContainsKey($ServerName)) {
                $config.mcpServers.Remove($ServerName)
                $json = $config | ConvertTo-Json -Depth 10
                $json | Out-File -FilePath $ConfigPath -Encoding UTF8 -Force
                Write-Info "已移除旧配置: $ServerName"
            }
        }
    }
    catch {
        Write-Warning "无法移除旧配置: $_"
    }
}

# ============================================================
# 主安装逻辑
# ============================================================

function Install-McpServer {
    param(
        [hashtable]$AgentInfo,
        [string]$PythonExe,
        [string]$ProjectDir = ""
    )

    Write-Info "正在配置 $($AgentInfo.Name)..."
    Write-Info "配置文件: $($AgentInfo.ConfigPath)"

    $configType = if ($AgentInfo.ConfigType) { $AgentInfo.ConfigType } else { "Standard" }

    # CodeArts Agent 需要项目目录
    $effectiveProjectDir = $ProjectDir
    if ($AgentInfo.Name -eq "CodeArts Agent" -and -not $effectiveProjectDir) {
        Write-Info ""
        Write-Info "CodeArts Agent 使用项目级 MCP 配置，需要指定项目目录。"
        Write-Info "项目目录是您的 Delphi 项目所在目录，MCP Server 将在该目录下运行。"
        Write-Info ""
        $inputDir = Read-Host "请输入项目目录路径（留空则使用当前目录）"
        if ($inputDir) {
            if (Test-Path $inputDir) {
                $effectiveProjectDir = $inputDir
            }
            else {
                Write-Warning "路径不存在: $inputDir，将使用默认目录"
            }
        }
    }

    # 检查是否已配置
    $alreadyConfigured = Test-McpConfigured -ConfigPath $AgentInfo.ConfigPath -ServerName $McpServerName -ConfigType $configType

    if ($alreadyConfigured -and -not $Force) {
        Write-Info "$($AgentInfo.Name) 已配置 MCP Server，跳过（使用 -Force 强制重新配置）"
        return $true
    }

    # 如果强制重新配置，先移除旧配置
    if ($Force -and $alreadyConfigured) {
        Remove-McpConfig -ConfigPath $AgentInfo.ConfigPath -ServerName $McpServerName -ConfigType $configType
    }

    # 生成 MCP 配置
    $mcpConfig = Get-McpConfig -PythonExe $PythonExe -ConfigType $configType -ProjectDir $effectiveProjectDir

    # 添加配置
    try {
        Add-McpConfig -ConfigPath $AgentInfo.ConfigPath -ServerName $McpServerName -McpConfig $mcpConfig -ConfigType $configType
        return $true
    }
    catch {
        Write-ErrorMsg "配置失败: $_"
        return $false
    }
}

function Main {
    Write-Separator "Delphi MCP Server 安装脚本"

    # 检查 MCP Server 脚本是否存在
    if (-not (Test-Path $McpServerScript)) {
        Write-ErrorMsg "MCP Server 脚本不存在: $McpServerScript"
        Write-ErrorMsg "请确保在项目根目录运行此脚本"
        exit 1
    }

    Write-Info "MCP Server 路径: $McpServerScript"

    # ============================================================
    # 检查依赖项
    # ============================================================
    Write-Separator "检查依赖项"

    $depsOk = $true

    # 检查 Git
    Write-Info "检查 Git..."
    if (-not (Test-GitInstalled)) {
        Write-Warning "Git 未安装"
        Write-Info "  下载地址: https://git-scm.com/download/win"
        Write-Info "  或使用: winget install Git.Git"
        $depsOk = $false
    }

    # 检查 7-Zip（可选）
    Write-Info "检查 7-Zip (可选)..."
    if (-not (Test-SevenZipInstalled)) {
        Write-Warning "7-Zip 未安装（可选，用于解压 CHM 帮助文件）"
        Write-Info "  下载地址: https://www.7-zip.org/download.html"
        Write-Info "  或使用: winget install 7zip.7zip"
    }

    # 检测 Python
    Write-Info "检查 Python..."
    $pythonExe = Get-PythonExecutable -PreferredPath $PythonPath
    if (-not $pythonExe) {
        Write-ErrorMsg "未找到 Python，请安装 Python 3.10+ 或使用 -PythonPath 参数指定路径"
        Write-Info "  下载地址: https://www.python.org/downloads/"
        Write-Info "  或使用: winget install Python.Python.3.12"
        exit 1
    }

    if (-not (Test-PythonVersion -PythonExe $pythonExe)) {
        Write-ErrorMsg "Python 版本不满足要求，需要 3.10+"
        exit 1
    }

    Write-Success "Python 检测通过: $pythonExe"

    # 检查虚拟环境
    Write-Info "检查虚拟环境..."
    $venv = Test-VirtualEnvironment -ScriptDir $ScriptDir
    
    if (-not $venv.Exists) {
        Write-Warning "虚拟环境不存在，正在创建..."
        $venvPython = New-VirtualEnvironment -PythonExe $pythonExe -ScriptDir $ScriptDir
        if ($venvPython) {
            $pythonExe = $venvPython
        }
        else {
            Write-ErrorMsg "虚拟环境创建失败"
            exit 1
        }
    }
    else {
        Write-Success "虚拟环境已存在: $($venv.PythonPath)"
        $pythonExe = $venv.PythonPath
    }

    # 检查 Python 依赖包
    Write-Info "检查 Python 依赖包..."
    $requirementsFile = Join-Path $ScriptDir "requirements.txt"
    $packages = Test-PythonPackages -PythonExe $pythonExe -RequirementsFile $requirementsFile
    
    if ($packages.Installed.Count -gt 0) {
        Write-Info "已安装的包: $($packages.Installed -join ', ')"
    }
    
    if ($packages.Missing.Count -gt 0) {
        Write-Warning "缺少依赖包: $($packages.Missing -join ', ')"
        Write-Info "正在安装缺少的依赖包..."
        
        $installResult = Install-PythonPackages -PythonExe $pythonExe -RequirementsFile $requirementsFile
        if (-not $installResult) {
            Write-ErrorMsg "依赖包安装失败，请手动执行: pip install -r requirements.txt"
            exit 1
        }
    }
    else {
        Write-Success "所有依赖包已安装"
    }

    # 依赖检查完成
    Write-Separator "依赖检查完成"
    if (-not $depsOk) {
        Write-Warning "部分依赖项未安装，可能影响部分功能"
        Write-Info "建议安装上述缺失的依赖项"
    }

    # 检测 AI Agent
    Write-Info "正在检测已安装的 AI Agent..."

    $agents = @()

    if ($Agent -eq "All" -or $Agent -eq "Claude") {
        $agents += Test-ClaudeDesktop
    }
    if ($Agent -eq "All" -or $Agent -eq "Trae") {
        $agents += Test-Trae
    }
    if ($Agent -eq "All" -or $Agent -eq "CodeArts") {
        $agents += Test-CodeArtsAgent
    }
    if ($Agent -eq "All" -or $Agent -eq "Cursor") {
        $agents += Test-Cursor
    }
    if ($Agent -eq "All" -or $Agent -eq "OpenCode") {
        $agents += Test-OpenCode
    }
    if ($Agent -eq "All" -or $Agent -eq "Windsurf") {
        $agents += Test-Windsurf
    }
    if ($Agent -eq "All" -or $Agent -eq "Cline") {
        $agents += Test-Cline
    }
    if ($Agent -eq "All" -or $Agent -eq "Roo") {
        $agents += Test-RooCode
    }
    # 国内 AI Agent
    if ($Agent -eq "All" -or $Agent -eq "Tongyi") {
        $agents += Test-TongyiLingma
    }
    if ($Agent -eq "All" -or $Agent -eq "Doubao") {
        $agents += Test-Doubao
    }
    if ($Agent -eq "All" -or $Agent -eq "Kimi") {
        $agents += Test-Kimi
    }
    if ($Agent -eq "All" -or $Agent -eq "DeepSeek") {
        $agents += Test-DeepSeek
    }
    if ($Agent -eq "All" -or $Agent -eq "ChatGLM") {
        $agents += Test-ChatGLM
    }

    # 显示检测结果
    Write-Separator "AI Agent 检测结果"

    $installedAgents = $agents | Where-Object { $_.Installed }
    $notInstalledAgents = $agents | Where-Object { -not $_.Installed }

    if ($installedAgents) {
        Write-Info "已安装的 AI Agent:"
        foreach ($a in $installedAgents) {
            Write-Host "  - $($a.Name)" -ForegroundColor Green
            if ($a.Path -and $a.Path -ne "Unknown") {
                Write-Host "    路径: $($a.Path)" -ForegroundColor Gray
            }
            Write-Host "    配置: $($a.ConfigPath)" -ForegroundColor Gray
        }
    }

    if ($notInstalledAgents) {
        Write-Info "未安装的 AI Agent:"
        foreach ($a in $notInstalledAgents) {
            Write-Host "  - $($a.Name)" -ForegroundColor Yellow
        }
    }

    if (-not $installedAgents) {
        Write-Warning "未检测到任何已安装的 AI Agent"
        Write-Info "支持的 AI Agent:"
        Write-Info "  国际: Claude Desktop, Trae, CodeArts Agent, Cursor, OpenCode, Windsurf, Cline, Roo Code"
        Write-Info "  国内: 通义灵码, 豆包, Kimi, DeepSeek, 智谱清言"
        exit 0
    }

    # 配置 MCP Server
    Write-Separator "配置 MCP Server"

    $successCount = 0
    $failCount = 0

    foreach ($agentInfo in $installedAgents) {
        $result = Install-McpServer -AgentInfo $agentInfo -PythonExe $pythonExe -ProjectDir $ProjectDir
        if ($result) {
            $successCount++
        }
        else {
            $failCount++
        }
    }

    # 显示结果摘要
    Write-Separator "安装结果"

    Write-Info "成功配置: $successCount 个 AI Agent"
    if ($failCount -gt 0) {
        Write-Warning "配置失败: $failCount 个 AI Agent"
    }

    if ($successCount -gt 0) {
        Write-Success "MCP Server 安装完成！"
        Write-Info "请重启相应的 AI Agent 使配置生效"
        Write-Info ""
        Write-Info "使用方法:"
        Write-Host "  在 AI Agent 中直接使用 MCP 工具，例如:" -ForegroundColor White
        Write-Host "  - compile_project: 编译 Delphi 项目" -ForegroundColor Gray
        Write-Host "  - search_knowledge: 搜索 Delphi 知识库" -ForegroundColor Gray
        Write-Host "  - check_environment: 检查编译环境" -ForegroundColor Gray
    }

    exit 0
}

# 运行主函数
Main
