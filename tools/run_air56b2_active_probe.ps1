param(
    [string]$Out = 'artifacts/active_probe_reproduction',
    [int]$Models = 2,
    [int]$Workers = 8
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv-research-gpu/Scripts/python.exe'
Push-Location $root
try {
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
    & $python -m pytest -q research/mic_ai_foc_ppo/tests
    if ($LASTEXITCODE -ne 0) { throw 'FOC tests failed' }
    & $python research/mic_ai_theory/snh_pwm/source/tools/run_air56b2_active_probe.py --out $Out --models $Models --workers $Workers
    if ($LASTEXITCODE -ne 0) { throw 'Pilot failed' }
    & $python research/mic_ai_theory/snh_pwm/source/tools/run_air56b2_active_probe.py --out ($Out + '_refinement') --models $Models --workers $Workers --refinement
    if ($LASTEXITCODE -ne 0) { throw 'Refinement failed' }
    & $python tools/analyze_air56b2_active_probe.py $Out --refinement ($Out + '_refinement')
    if ($LASTEXITCODE -ne 0) { throw 'Analysis failed' }
}
finally { Pop-Location }
