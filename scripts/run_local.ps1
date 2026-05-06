$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$VenvActivate = Join-Path $ProjectRoot ".venv\Scripts\Activate.ps1"
if (-not (Test-Path $VenvActivate)) {
    throw "Virtual environment was not found at .venv\Scripts\Activate.ps1"
}

. $VenvActivate
uvicorn app.main:app --host 0.0.0.0 --port 8000
