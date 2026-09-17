# Start serve_unified — PowerShell from edge-ai-box root:
#   .\scripts\dev-unified.ps1

param(
    [string]$PyTag = "3.11"
)

function Invoke-EdgePython {
    param([object[]]$CommandArgs)
    if ($script:EdgePyLauncher.Count -ge 2) {
        & $script:EdgePyLauncher[0] $script:EdgePyLauncher[1] @CommandArgs
    } else {
        & python @CommandArgs
    }
}

if ($env:EDGE_PY_TAG) { $PyTag = $env:EDGE_PY_TAG }
if ($PyTag) {
    & py "-$PyTag" -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) { $script:EdgePyLauncher = @("py", "-$PyTag") }
}
if (-not $script:EdgePyLauncher) { $script:EdgePyLauncher = @("python") }

$Backend = Join-Path $PSScriptRoot "..\backend"
$Backend = (Resolve-Path $Backend).Path
$env:EDGE_PORT = if ($env:EDGE_PORT) { $env:EDGE_PORT } else { "8080" }
if (-not $env:EDGE_INFERENCE) { $env:EDGE_INFERENCE = "onnx" }
$env:DETECT_SERVER_URL = "http://127.0.0.1:$($env:EDGE_PORT)"
Set-Location $Backend

Invoke-EdgePython @("-c", "import apscheduler") 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Backend deps missing. Run:" -ForegroundColor Yellow
    Write-Host "  .\scripts\setup-backend.ps1 -Onnx -PyTag $PyTag" -ForegroundColor Yellow
    exit 1
}

Write-Host "Edge unified -> http://127.0.0.1:$($env:EDGE_PORT) (EDGE_INFERENCE=$env:EDGE_INFERENCE)"
Invoke-EdgePython @(".\serve_unified.py")
