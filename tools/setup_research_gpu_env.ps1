param(
    [string]$EnvironmentPath = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($EnvironmentPath)) {
    $EnvironmentPath = Join-Path $Root ".venv-research-gpu"
}

if (-not (Test-Path -LiteralPath $EnvironmentPath)) {
    & py -3.12 -m venv $EnvironmentPath
    if ($LASTEXITCODE -ne 0) {
        throw "Unable to create Python 3.12 environment at $EnvironmentPath"
    }
}

$Python = Join-Path $EnvironmentPath "Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Environment Python not found: $Python"
}

& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "pip upgrade failed"
}
& $Python -m pip install -r (Join-Path $Root "research\requirements-host.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Host research dependency installation failed"
}
& $Python -m pip install torch==2.11.0 --index-url https://download.pytorch.org/whl/cu128
if ($LASTEXITCODE -ne 0) {
    throw "CUDA PyTorch installation failed"
}
& $Python (Join-Path $Root "tools\gpu_research_preflight.py") `
    --require-gpu `
    --json-output (Join-Path $Root "artifacts\gpu_research_preflight.json")
if ($LASTEXITCODE -ne 0) {
    throw "GPU research preflight failed"
}

Write-Host "Research GPU environment is ready: $EnvironmentPath"
