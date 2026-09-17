$Web = Join-Path $PSScriptRoot "..\web"
Set-Location $Web
Write-Host "Edge Web -> $Web"
npm run dev
