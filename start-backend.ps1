# 启动后端（Windows PowerShell）
# 用法: .\start-backend.ps1  [端口，默认8000]

param([int]$Port = 8000)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$python = $env:PYTHON_BIN
if (-not $python) { $python = "python" }

Write-Host "使用 Python: $python" -ForegroundColor Cyan
& $python "run_backend.py" $Port
