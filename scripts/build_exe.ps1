$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  python -m venv .venv
}

.\.venv\Scripts\python -m pip install -e ".[build]"
.\.venv\Scripts\pyinstaller --clean --noconfirm ExamScribe.spec

Write-Host ""
Write-Host "Built: $root\dist\ExamScribe\ExamScribe.exe"
