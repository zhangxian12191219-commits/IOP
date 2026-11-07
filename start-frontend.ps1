# 启动前端开发服务器（Windows PowerShell）
# 用法: .\start-frontend.ps1  [后端端口，默认8000]

param([int]$BackendPort = 8000)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Join-Path $root "frontend")

$env:VITE_API_TARGET = "http://localhost:$BackendPort"
Write-Host "后端代理目标: $env:VITE_API_TARGET" -ForegroundColor Cyan
Write-Host "前端地址: http://localhost:5173" -ForegroundColor Green

npm run dev
