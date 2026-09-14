$Core = if ($env:YOLO_CORE) { $env:YOLO_CORE } else { Join-Path $PSScriptRoot "..\..\yolo-demo" }
$Web = Join-Path (Resolve-Path $Core).Path "yolo-client"
Set-Location $Web
npm run dev:edge
