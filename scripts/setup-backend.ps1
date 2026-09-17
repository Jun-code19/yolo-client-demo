# Install backend deps — PowerShell from edge-ai-box root:
#   .\scripts\setup-backend.ps1 -Onnx
# NOT: py -3.11 .\scripts\setup-backend.ps1  (py runs Python; .ps1 is PowerShell)

param(
    [switch]$Onnx,
    [string]$PyTag = "3.11"
)

function Invoke-EdgePython {
    # Pass args as a single array so pip "-i" is not parsed as PowerShell -InformationAction/-InformationVariable
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
    if ($LASTEXITCODE -eq 0) {
        $script:EdgePyLauncher = @("py", "-$PyTag")
        Write-Host "Using py -$PyTag"
    }
}
if (-not $script:EdgePyLauncher) {
    $script:EdgePyLauncher = @("python")
    Write-Host "Using python (PATH); prefer -PyTag 3.11 if deps wrong version"
}

Invoke-EdgePython @("-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)") 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Need Python 3.10+. Run: py -0p" -ForegroundColor Red
    Write-Host "Then: .\scripts\setup-backend.ps1 -Onnx -PyTag 3.11" -ForegroundColor Yellow
    exit 1
}

$Backend = Join-Path $PSScriptRoot "..\backend"
Set-Location (Resolve-Path $Backend)

$req = if ($Onnx) { "requirements.rk3588.txt" } else { "requirements.txt" }
$ver = Invoke-EdgePython @("-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
Write-Host "Python $ver"
$pypi = "https://pypi.tuna.tsinghua.edu.cn/simple"
Write-Host "pip install -r $req -i $pypi"
Invoke-EdgePython @("-m", "pip", "install", "-r", $req, "-i", $pypi)
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed."
    exit 1
}
Write-Host "OK. Copy backend\.env.example to backend\.env and set DATABASE_URL."
Write-Host "Start: .\scripts\dev-unified.ps1 -PyTag $PyTag"
