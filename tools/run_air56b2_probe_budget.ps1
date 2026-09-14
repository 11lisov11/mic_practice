param(
    [string]$Out = 'artifacts/probe_budget_pilot_20260909_reproduction',
    [int]$Models = 2,
    [int]$Workers = 8
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv-research-gpu/Scripts/python.exe'
Push-Location $root
try {
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Research tests failed' }
    & $python research/mic_ai_theory/snh_pwm/source/tools/run_air56b2_probe_budget.py --out $Out --models $Models --workers $Workers
    if ($LASTEXITCODE -ne 0) { throw 'Pilot failed' }
    & $python tools/check_air56b2_probe_budget_refinement.py --out ($Out + '_refinement') --workers $Workers
    if ($LASTEXITCODE -ne 0) { throw 'Plant refinement failed' }
    & $python tools/analyze_air56b2_probe_budget.py $Out --refinement ($Out + '_refinement')
    if ($LASTEXITCODE -ne 0) { throw 'Analysis failed' }
}
finally { Pop-Location }
