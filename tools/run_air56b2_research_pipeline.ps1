param(
    [switch]$Full,
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($Python)) {
    $Python = Join-Path $Root ".venv-research-gpu\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $Python)) {
    throw "Research Python not found: $Python"
}

function Invoke-Checked {
    param(
        [string]$Label,
        [string]$WorkingDirectory,
        [string[]]$Arguments
    )
    Write-Host "[$Label]"
    Push-Location $WorkingDirectory
    try {
        & $Python @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "$Label failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

$Source = Join-Path $Root "research\mic_ai_theory\snh_pwm\source"
$FocPpoSource = Join-Path $Root "research\mic_ai_foc_ppo"
$Artifacts = Join-Path $Root "artifacts"
$Manifest = Join-Path $Artifacts "air56b2_research_manifest.json"
New-Item -ItemType Directory -Force -Path $Artifacts | Out-Null
if (Test-Path -LiteralPath $Manifest) {
    Remove-Item -LiteralPath $Manifest -Force
}

Invoke-Checked "GPU preflight" $Root @(
    "tools\gpu_research_preflight.py",
    "--require-gpu",
    "--json-output", "artifacts\gpu_research_preflight.json"
)
Invoke-Checked "Research consistency" $Root @(
    "tools\research_result_consistency.py",
    "--strict",
    "--json-out", "artifacts\research_result_consistency.json"
)
Invoke-Checked "AIR56B2 preregistered experiment package" $Root @(
    "tools\validate_air56b2_experiment_package.py"
)
Invoke-Checked "AIR56B2 tests" $Source @(
    "-m", "pytest", "-q"
)
Invoke-Checked "FOC PPO port tests" $FocPpoSource @(
    "-m", "pytest", "-q"
)
Invoke-Checked "Motor identification tests" $Root @(
    "-m", "pytest", "-q",
    "research\mic_ai_theory\model_identification\source\tests"
)
Invoke-Checked "AIR56B2 ensemble" $Source @(
    "tools\build_air56b2_nameplate_ensemble.py",
    "--count", "256",
    "--seed", "560225",
    "--output", (Join-Path $Artifacts "air56b2_nameplate_ensemble.json")
)
Invoke-Checked "AIR56B2 F1/F1S/F2/F3 fidelity bundle" $Source @(
    "tools\build_air56b2_fidelity_bundle.py",
    "--count", "256",
    "--seed", "560225",
    "--output", (Join-Path $Artifacts "air56b2_fidelity_bundle.json")
)
Invoke-Checked "AIR56B2 loss and thermal optimization study" $Source @(
    "tools\run_air56b2_loss_optimization_study.py",
    "--input", (Join-Path $Artifacts "air56b2_fidelity_bundle.json"),
    "--output", (Join-Path $Artifacts "air56b2_loss_optimization_study.json")
)
Invoke-Checked "AIR56B2 sensorless independent-plant study" $Source @(
    "tools\run_air56b2_sensorless_independent_plant_study.py",
    "--input", (Join-Path $Artifacts "air56b2_fidelity_bundle.json"),
    "--output", (Join-Path $Artifacts "air56b2_sensorless_independent_plant_study.json")
)
Invoke-Checked "AIR56B2 disjoint policy benchmark and LUT export" $Source @(
    "tools\run_air56b2_policy_benchmark.py",
    "--input", (Join-Path $Artifacts "air56b2_fidelity_bundle.json"),
    "--output", (Join-Path $Artifacts "air56b2_policy_benchmark.json"),
    "--checkpoint", (Join-Path $Artifacts "air56b2_id_policy_actor.pt"),
    "--bundle", (Join-Path $Artifacts "air56b2_id_policy_bundle.json"),
    "--lut-json", (Join-Path $Artifacts "air56b2_id_ref_lut.json"),
    "--lut-header", (Join-Path $Artifacts "air56b2_id_ref_lut.h"),
    "--device", "auto"
)
Invoke-Checked "AIR56B2 common paired control benchmark" $Source @(
    "tools\run_air56b2_common_control_benchmark.py",
    "--fidelity", (Join-Path $Artifacts "air56b2_fidelity_bundle.json"),
    "--policy", (Join-Path $Artifacts "air56b2_policy_benchmark.json"),
    "--lut", (Join-Path $Artifacts "air56b2_id_ref_lut.json"),
    "--output", (Join-Path $Artifacts "air56b2_common_control_benchmark.json")
)
Invoke-Checked "AIR56B2 sensorless V/f fidelity study" $Source @(
    "tools\run_air56b2_vf_fidelity_study.py",
    "--count", "24",
    "--steps", "4000",
    "--master-seed", "560225",
    "--frequency-hz", "15",
    "--ramp-hz-per-s", "100",
    "--load-fraction", "0.5",
    "--output", (Join-Path $Artifacts "air56b2_vf_fidelity_study.json")
)
Invoke-Checked "AIR56B2 scalar V/f operating matrix" $Source @(
    "tools\run_air56b2_vf_operating_matrix.py",
    "--count", "12",
    "--master-seed", "560225",
    "--output", (Join-Path $Artifacts "air56b2_vf_operating_matrix.json")
)
Invoke-Checked "AIR56B2 protection fault matrix" $Source @(
    "tools\run_air56b2_protection_fault_matrix.py",
    "--count", "24",
    "--master-seed", "560225",
    "--output", (Join-Path $Artifacts "air56b2_protection_fault_matrix.json")
)

if ($Full) {
    $Tuning = Join-Path $Artifacts "air56b2_foc_matched_tuning.json"
    Invoke-Checked "FOC train and validation" $Source @(
        "tools\tune_air56b2_foc_ensemble.py",
        "--candidates", "16",
        "--train-count", "6",
        "--validation-count", "10",
        "--train-steps", "2400",
        "--validation-steps", "3000",
        "--top-k", "6",
        "--master-seed", "560225",
        "--controller-model-mode", "matched_plant",
        "--output", $Tuning
    )
    Invoke-Checked "FOC blind holdout" $Source @(
        "tools\validate_air56b2_foc_holdout.py",
        "--tuning", $Tuning,
        "--count", "30",
        "--steps", "5000",
        "--output", (Join-Path $Artifacts "air56b2_foc_blind_holdout.json")
    )
}

$CanonicalTuning = Join-Path $Artifacts "air56b2_foc_matched_tuning.json"
$CanonicalHoldout = Join-Path $Artifacts "air56b2_foc_blind_holdout.json"
$EncoderTuning = Join-Path $Artifacts "air56b2_encoder_foc_tuning.json"
$EncoderValidation = Join-Path $Artifacts "air56b2_encoder_foc_fidelity_study.json"
if (Test-Path -LiteralPath $CanonicalTuning) {
    if ($Full -or -not (Test-Path -LiteralPath $EncoderTuning)) {
        Invoke-Checked "Encoder-observer FOC train and validation" $Source @(
            "tools\tune_air56b2_encoder_foc_fidelity.py",
            "--oracle-tuning", $CanonicalTuning,
            "--master-seed", "560225",
            "--candidate-limit", "16",
            "--train-count", "3",
            "--validation-count", "6",
            "--train-steps", "6000",
            "--validation-steps", "10000",
            "--top-k", "4",
            "--target-speed-fraction", "0.30",
            "--speed-ramp-s", "0.20",
            "--load-fraction", "0.50",
            "--output", $EncoderTuning
        )
    }
    Invoke-Checked "Encoder-observer FOC fidelity study" $Source @(
        "tools\run_air56b2_encoder_foc_fidelity_study.py",
        "--tuning", $EncoderTuning,
        "--count", "24",
        "--steps", "10000",
        "--master-seed", "560225",
        "--target-speed-fraction", "0.30",
        "--speed-ramp-s", "0.20",
        "--load-fraction", "0.50",
        "--output", $EncoderValidation
    )
}

if (
    (Test-Path -LiteralPath $CanonicalTuning) -and
    (Test-Path -LiteralPath $CanonicalHoldout) -and
    (Test-Path -LiteralPath $EncoderTuning) -and
    (Test-Path -LiteralPath $EncoderValidation)
) {
    Invoke-Checked "Canonical research manifest" $Root @(
        "tools\build_air56b2_research_manifest.py",
        "--artifacts", $Artifacts,
        "--output", $Manifest
    )
}

Write-Host "AIR56B2 research pipeline completed. Full=$Full"
