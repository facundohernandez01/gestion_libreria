param([string]$Configuration = "Release")
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "../..")).Path
$Project = Join-Path $Root "intrashop-server/IntraShop.ServerManager/IntraShop.ServerManager.csproj"
$Output = Join-Path $Root "intrashop-server/release-dotnet"
& dotnet publish $Project -c $Configuration -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o $Output
if ($LASTEXITCODE -ne 0) { throw "Falló dotnet publish." }
Write-Host "Administrador .NET: $Output/IntraShop.ServerManager.exe"
