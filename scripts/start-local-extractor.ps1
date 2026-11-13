$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$ollamaPath = Join-Path $projectRoot 'artifacts/ollama/runtime/ollama.exe'
if (-not (Test-Path -LiteralPath $ollamaPath)) { throw 'Portable Ollama must be downloaded and extracted first.' }
$listener = Get-NetTCPConnection -LocalPort 18765 -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $serviceProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
    if ($serviceProcess.ExecutablePath -ne $ollamaPath) { throw 'Port 18765 is occupied by another service.' }
    Write-Output 'Project-local extraction server is already running.'
    exit 0
}
$env:OLLAMA_HOST = '127.0.0.1:18765'
$env:OLLAMA_MODELS = Join-Path $projectRoot 'artifacts/ollama/models'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_CONTEXT_LENGTH = '8192'
$env:OLLAMA_VULKAN = '0'
Start-Process -FilePath $ollamaPath -ArgumentList 'serve' -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $projectRoot 'artifacts/ollama/server.log') -RedirectStandardError (Join-Path $projectRoot 'artifacts/ollama/server-error.log')
Write-Output 'Started project-local Ollama on 127.0.0.1:18765. Models stay under artifacts/ollama/models.'
