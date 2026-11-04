param(
    [string]$Python = "python",
    [string]$Configuration = "Release",
    [switch]$SkipBackend
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$Project = Join-Path $Root "intrashop-server/IntraShop.ServerManager/IntraShop.ServerManager.csproj"
$Release = Join-Path $Root "intrashop-server/release"
$BackendDist = Join-Path $Root "dist/pos_server"
$BuildBackend = Join-Path $PSScriptRoot "build-backend.ps1"

if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    throw "No se encontró dotnet. Instalá .NET 10 SDK."
}
if (-not $SkipBackend) {
    & $BuildBackend -Python $Python
    if ($LASTEXITCODE -ne 0) { throw "Falló el empaquetado del backend Python." }
}
if (-not (Test-Path (Join-Path $BackendDist "pos_server.exe"))) {
    throw "No existe el backend empaquetado en $BackendDist. Ejecutá sin -SkipBackend."
}
if (Test-Path $Release) { Remove-Item $Release -Recurse -Force }
New-Item -ItemType Directory -Path $Release -Force | Out-Null
& dotnet publish $Project -c $Configuration -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o $Release
if ($LASTEXITCODE -ne 0) { throw "Falló dotnet publish." }
Copy-Item $BackendDist (Join-Path $Release "backend") -Recurse -Force
$manager = Join-Path $Release "IntraShop.ServerManager.exe"
$backend = Join-Path $Release "backend/pos_server.exe"
if (!(Test-Path $manager) -or !(Test-Path $backend)) {
    throw "Publicación incompleta: falta el administrador .NET o el backend."
}
$bytes = (Get-ChildItem $Release -Recurse -File | Measure-Object Length -Sum).Sum
Write-Host ""
Write-Host "Distribución combinada creada: $Release"
Write-Host ("Tamaño total: {0:N1} MB" -f ($bytes / 1MB))
Write-Host "Iniciá: $manager"
Write-Host "Backend interno: $backend"
