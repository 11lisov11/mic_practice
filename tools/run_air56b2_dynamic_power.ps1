param(
    [int]$Models = 2,
    [int]$Workers = 4
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv-research-gpu/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Research Python environment missing' }
Push-Location $root
try {
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Research tests failed' }
    & $python -m pytest -q research/mic_ai_foc_ppo/tests
    if ($LASTEXITCODE -ne 0) { throw 'FOC PPO tests failed' }
    $runner = 'research/mic_ai_theory/snh_pwm/source/tools/run_air56b2_dynamic_power.py'
    & $python $runner --out artifacts/dynamic_power_adaptation_20260908 --models $Models --duration 6 --plant-substeps 2 --workers $Workers
    if ($LASTEXITCODE -ne 0) { throw 'Dynamic study failed' }
    & $python $runner --out artifacts/dynamic_power_dt50us --models 1 --smoke --duration 6 --dt 0.00005 --speeds 0.7 --workers $Workers
    if ($LASTEXITCODE -ne 0) { throw '50 us check failed' }
    & $python $runner --out artifacts/dynamic_power_dt25us --models 1 --smoke --duration 6 --dt 0.000025 --speeds 0.7 --workers $Workers
    if ($LASTEXITCODE -ne 0) { throw '25 us check failed' }
    & $python $runner --out artifacts/dynamic_power_plant_sub2 --models 1 --smoke --duration 6 --plant-substeps 2 --speeds 0.7 --workers $Workers
    if ($LASTEXITCODE -ne 0) { throw 'Plant-only 50 us check failed' }
    & $python $runner --out artifacts/dynamic_power_plant_sub4 --models 1 --smoke --duration 6 --plant-substeps 4 --speeds 0.7 --workers $Workers
    if ($LASTEXITCODE -ne 0) { throw 'Plant-only 25 us check failed' }
    & $python $runner --out artifacts/dynamic_power_plant_sub8 --models 1 --smoke --duration 6 --plant-substeps 8 --speeds 0.7 --workers $Workers
    if ($LASTEXITCODE -ne 0) { throw 'Plant-only 12.5 us check failed' }
    & $python tools/build_air56b2_dynamic_power_report.py
    if ($LASTEXITCODE -ne 0) { throw 'Report generation failed' }
    & $python tools/mic_theory_snapshot_check.py
    if ($LASTEXITCODE -ne 0) { throw 'Theory source snapshot mismatch' }
}
finally { Pop-Location }
