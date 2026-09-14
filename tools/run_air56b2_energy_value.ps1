param(
    [string]$Out = 'artifacts/energy_value_reproduction',
    [int]$Workers = 14
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
    & $python -m pytest -q tests/test_air56b2_energy_value_publication_review.py
    if ($LASTEXITCODE -ne 0) { throw 'Publication tests failed' }
    & $python -m pytest -q tests/test_air56b2_light_load_design.py
    if ($LASTEXITCODE -ne 0) { throw 'Light-load design tests failed' }
    foreach ($stage in @('development','validation','stress','refinement')) {
        & $python research/mic_ai_theory/snh_pwm/source/tools/run_air56b2_energy_value.py --stage $stage --out ($Out + '_' + $stage) --workers $Workers
        if ($LASTEXITCODE -ne 0) { throw "Experiment failed: $stage" }
    }
    & $python tools/run_air56b2_accepted_refinement.py ($Out + '_validation') --out ($Out + '_accepted_refinement') --workers $Workers
    if ($LASTEXITCODE -ne 0) { throw 'Accepted-branch refinement failed' }
    $additional = @()
    if (Test-Path (Join-Path ($Out + '_accepted_refinement') 'study.json')) {
        $additional = @('--accepted-refinement', ($Out + '_accepted_refinement'))
    }
    foreach ($stage in @('light_load','light_load_refinement')) {
        & $python tools/run_air56b2_light_load.py --stage $stage --out ($Out + '_' + $stage) --workers $Workers
        if ($LASTEXITCODE -ne 0) { throw "Additional experiment failed: $stage" }
    }
    & $python tools/analyze_air56b2_energy_value.py ($Out + '_validation') --stress ($Out + '_stress') --refinement ($Out + '_refinement') --light-load ($Out + '_light_load') --light-load-refinement ($Out + '_light_load_refinement') @additional
    if ($LASTEXITCODE -ne 0) { throw 'Analysis failed' }
}
finally { Pop-Location }
