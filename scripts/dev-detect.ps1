# 本地开发：边缘 detect 服务（需已安装 yolo-demo 依赖）
$Core = if ($env:YOLO_CORE) { $env:YOLO_CORE } else { Join-Path $PSScriptRoot "..\..\yolo-demo" }
$Core = (Resolve-Path $Core).Path
$env:DEPLOY_MODE = "edge"
Set-Location $Core
Write-Host "DEPLOY_MODE=edge -> $Core"
python .\base_detect_server.py
