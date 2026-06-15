$sshDir = Join-Path $HOME ".ssh"
New-Item -ItemType Directory -Path $sshDir -Force | Out-Null

# 生成 ed25519 密钥（空密码）
$keyFile = Join-Path $sshDir "id_ed25519"
Write-Output "Generating SSH key: $keyFile"
& ssh-keygen.exe -t ed25519 -C "daofy-push-key" -f $keyFile -N "" -q
Write-Output "Key generated!"

# 启动 ssh-agent 并添加密钥
Write-Output "Starting ssh-agent..."
& ssh-agent.exe -s | Out-String -Stream | ForEach-Object {
    if ($_ -match 'SET ([^=]+)=(.+)') {
        [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "User")
        Set-Item -Path "env:$($matches[1])" -Value $matches[2]
    }
}

Write-Output "Adding key to agent..."
& ssh-add.exe $keyFile -q
Write-Output "Key added!"

# 显示公钥
$pubKey = Get-Content "$keyFile.pub" -Raw
Write-Output "`nYour public key (add to GitHub → Settings → SSH keys):"
Write-Output "===== START PUBLIC KEY ====="
Write-Output $pubKey.Trim()
Write-Output "===== END PUBLIC KEY ====="
