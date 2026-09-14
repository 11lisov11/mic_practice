param(
    [string]$Python = "",
    [ValidateSet("auto", "cpu", "cuda")][string]$Device = "auto"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $ProjectRoot ".venv-research-gpu\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Research Python not found: $Python"
}

function Invoke-ResearchStep {
    param([string[]]$Arguments)
    & $Python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Research step failed with exit code $LASTEXITCODE"
    }
}

Push-Location $ProjectRoot
try {
    $Source = "research/mic_ai_theory/snh_pwm/source"
    Invoke-ResearchStep @("-m", "pytest", "-q", "$Source/tests/test_air56b2_measured_loss_fit.py", "$Source/tests/test_air56b2_measurement_adaptation.py")
    Invoke-ResearchStep @("$Source/tools/run_air56b2_measurement_adaptation.py", "--device", $Device)
    Invoke-ResearchStep @("$Source/tools/audit_air56b2_loss_balance.py")
    Invoke-ResearchStep @("tools/build_air56b2_measurement_report.py")
    Invoke-ResearchStep @("tools/build_air56b2_measurement_report.py", "--verify-only")
}
finally {
    Pop-Location
}
