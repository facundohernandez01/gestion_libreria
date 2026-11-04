param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
Push-Location $Root
try {
    if (-not (Get-Command pnpm -ErrorAction SilentlyContinue)) { throw "Falta pnpm. Instalá Node.js y pnpm para compilar Astro." }
    Push-Location (Join-Path $Root "intrashop")
    try {
        & pnpm install --frozen-lockfile
        if ($LASTEXITCODE -ne 0) { throw "Falló pnpm install." }
        & pnpm build
        if ($LASTEXITCODE -ne 0) { throw "Falló pnpm build." }
    } finally { Pop-Location }
    if (!(Test-Path (Join-Path $Root "intrashop/dist/index.html"))) { throw "Astro no generó dist/index.html." }
    & $Python -m pip install -r "intrashop-server/backend/requirements-server.txt" pyinstaller
    if ($LASTEXITCODE -ne 0) { throw "Falló instalación de dependencias" }
    & $Python -m PyInstaller --noconfirm --clean "intrashop-server/backend/pos_server.spec"
    if ($LASTEXITCODE -ne 0) { throw "Falló PyInstaller" }
    Write-Host "Backend: $Root/dist/pos_server/pos_server.exe"
} finally { Pop-Location }
