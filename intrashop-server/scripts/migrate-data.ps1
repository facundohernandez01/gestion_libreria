param(
    [Parameter(Mandatory=$true)][string]$SourceDirectory,
    [string]$DestinationDirectory = (Join-Path $env:ProgramData "Kiosmico\IntraShop"),
    [switch]$ConfirmMigration
)
$ErrorActionPreference = "Stop"
if (-not $ConfirmMigration) { throw "Migración no ejecutada. Cerrá POS/servidor y repetí con -ConfirmMigration." }
$src = (Resolve-Path $SourceDirectory).Path
$dst = [IO.Path]::GetFullPath($DestinationDirectory)
if ($src.TrimEnd('\') -eq $dst.TrimEnd('\')) { throw "Origen y destino coinciden." }
if (!(Test-Path (Join-Path $src "libreria.db"))) { throw "No existe libreria.db en origen." }
if (Get-Process -Name "pos_server","IntraShop.ServerManager" -ErrorAction SilentlyContinue) {
    throw "Cerrá pos_server y el administrador antes de migrar."
}
$files = @("libreria.db", "libreria.db-wal", "libreria.db-shm", ".mp-oauth-local.key", ".env")
$present = @($files | Where-Object { Test-Path -LiteralPath (Join-Path $src $_) })
if (!(Test-Path $dst)) { New-Item -ItemType Directory -Path $dst -Force | Out-Null }
$conflicts = @($present | Where-Object { Test-Path -LiteralPath (Join-Path $dst $_) })
if ($conflicts.Count -gt 0) { throw "El destino ya contiene: $($conflicts -join ', '). No se sobrescribe nada." }
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$backup = Join-Path $src ("backup-before-intrashop-migration-" + $stamp)
New-Item -ItemType Directory -Path $backup -ErrorAction Stop | Out-Null
foreach ($name in $present) { Copy-Item -LiteralPath (Join-Path $src $name) -Destination (Join-Path $backup $name) -ErrorAction Stop }
foreach ($name in $present) { Copy-Item -LiteralPath (Join-Path $src $name) -Destination (Join-Path $dst $name) -ErrorAction Stop }
foreach ($name in $present) {
    $a = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $src $name)).Hash
    $b = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $dst $name)).Hash
    if ($a -ne $b) { throw "Verificación SHA256 falló para $name. Conservá los originales." }
}
Write-Host "Migración por copia verificada. Origen intacto: $src"
Write-Host "Copia de respaldo: $backup"
Write-Host "Datos nuevos: $dst"
Write-Host "Configurá DB_PATH=$dst\libreria.db para usar esta copia. No arranques ambos servidores simultáneamente."
