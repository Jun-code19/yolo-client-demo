$Core = if ($env:YOLO_CORE) { $env:YOLO_CORE } else { Join-Path $PSScriptRoot "..\..\yolo-demo" }
$Core = (Resolve-Path $Core).Path
$env:DEPLOY_MODE = "edge"
Set-Location $Core
python .\base_data_server.py
