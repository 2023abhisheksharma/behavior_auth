$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root "python_engine\venv\Scripts\python.exe"

if (-not (Test-Path $Python)) {
    Write-Host "Python venv not found at $Python"
    Write-Host "Create and install dependencies first."
    exit 1
}

Set-Location (Join-Path $Root "python_engine")
& $Python "run_full_pipeline.py"
