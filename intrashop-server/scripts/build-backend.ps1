param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Push-Location $Root
try {
    & $Python -m pip install -r "intrashop-server/backend/requirements-server.txt" pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "Falló instalación de dependencias" }
    & $Python -m PyInstaller --noconfirm --clean "intrashop-server/backend/pos_server.spec"
    if ($LASTEXITCODE -ne 0) { throw "Falló PyInstaller" }
    Write-Host "Backend: $Root/dist/pos_server/pos_server.exe"
} finally { Pop-Location }
