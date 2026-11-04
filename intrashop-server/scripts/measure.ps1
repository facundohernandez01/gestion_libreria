param([string]$Backend = ".\dist\pos_server\pos_server.exe")
$ErrorActionPreference = "Stop"
if (!(Test-Path $Backend)) { throw "No existe $Backend" }
$exe = (Resolve-Path $Backend).Path
$folder = Split-Path $exe -Parent
$bytes = (Get-ChildItem $folder -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ("Tamaño backend onedir: {0:N1} MB" -f ($bytes / 1MB))
$p = Start-Process -FilePath $exe -ArgumentList "--headless", "--host", "127.0.0.1", "--port", "18080" -WorkingDirectory $folder -PassThru
try {
    Start-Sleep -Seconds 5
    $p.Refresh()
    if ($p.HasExited) { throw "Backend terminó con código $($p.ExitCode); revisar logs." }
    $health = Invoke-RestMethod "http://127.0.0.1:18080/health" -TimeoutSec 3
    if ($health.service -ne "pos-lan") { throw "Health inválido" }
    Write-Host ("Working set: {0:N1} MB" -f ($p.WorkingSet64 / 1MB))
    Write-Host ("Private memory: {0:N1} MB" -f ($p.PrivateMemorySize64 / 1MB))
} finally {
    if (!$p.HasExited) { Stop-Process -Id $p.Id -Force }
    $p.Dispose()
}
