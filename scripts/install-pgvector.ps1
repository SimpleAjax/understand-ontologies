# Run in Administrator PowerShell after building pgvector in artifacts/.
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path $PSScriptRoot -Parent
$taskBuild = Join-Path $taskRoot 'artifacts/pgvector-v0.8.7'
$taskPostgres = 'C:\Program Files\PostgreSQL\18'
$taskIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
$taskPrincipal = [Security.Principal.WindowsPrincipal]::new($taskIdentity)
if (-not $taskPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Open PowerShell as Administrator and run this script again.'
}
if (-not (Test-Path -LiteralPath "$taskBuild/vector.dll")) {
    throw 'Compiled vector.dll is missing from artifacts/pgvector-v0.8.7.'
}
Copy-Item -LiteralPath "$taskBuild/vector.dll" -Destination "$taskPostgres/lib/vector.dll"
Copy-Item -LiteralPath "$taskBuild/vector.control" -Destination "$taskPostgres/share/extension/vector.control"
Get-ChildItem -LiteralPath "$taskBuild/sql" -Filter 'vector--*.sql' | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination "$taskPostgres/share/extension/$($_.Name)"
}
Write-Host 'pgvector 0.8.7 installed. Initializing project database...'
& "$taskRoot/.venv/Scripts/python.exe" "$PSScriptRoot/pipeline.py" init-db
if ($LASTEXITCODE -ne 0) { throw 'Files installed, but database initialization failed.' }
