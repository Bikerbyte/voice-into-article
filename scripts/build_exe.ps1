$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
  python -m venv .venv
}

.\.venv\Scripts\python -m pip install -e ".[build]"
.\.venv\Scripts\pyinstaller --clean --noconfirm NoteScribe.spec

Write-Host ""
Write-Host "Built: $root\dist\NoteScribe\NoteScribe.exe"
