$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
  py -3.12 -m venv .venv
}

.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install pyinstaller

if (Test-Path "dist\TJR.exe") {
  Remove-Item "dist\TJR.exe" -Force
}

.\.venv\Scripts\pyinstaller.exe --clean --noconfirm TJR_windows.spec

Write-Host "[OK] EXE built: $(Resolve-Path .\dist\TJR.exe)"
