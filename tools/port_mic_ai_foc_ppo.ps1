param(
    [string]$SourceRoot = "C:\mic_theory",
    [string]$DestinationRoot = ""
)

$ErrorActionPreference = "Stop"
$RepositoryRoot = Split-Path -Parent $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($DestinationRoot)) {
    $DestinationRoot = Join-Path $RepositoryRoot "research\mic_ai_foc_ppo"
}

$SourceRoot = [System.IO.Path]::GetFullPath($SourceRoot)
$DestinationRoot = [System.IO.Path]::GetFullPath($DestinationRoot)
if (-not (Test-Path -LiteralPath $SourceRoot -PathType Container)) {
    throw "Source repository not found: $SourceRoot"
}
if (Test-Path -LiteralPath $DestinationRoot) {
    throw "Destination already exists; refusing to overwrite: $DestinationRoot"
}

$Files = @(
    "requirements.txt",
    "config\__init__.py",
    "config\env.py",
    "config\env_demo_true_motor1.py",
    "config\env_demo_true_motor1_physical.py",
    "config\env_air56b2_iek_025kw_delta.py",
    "control\__init__.py",
    "control\aff_foc.py",
    "control\ebs_foc.py",
    "control\esc_foc.py",
    "control\lmc_foc.py",
    "control\load_map_foc.py",
    "control\vector_foc.py",
    "control\scalar_vf.py",
    "control\v3_ternary.py",
    "control\hybrid_v3_foc.py",
    "control\id_ref_lut.py",
    "models\__init__.py",
    "models\induction_motor.py",
    "models\inverter_ideal.py",
    "models\transformations.py",
    "simulation\__init__.py",
    "simulation\gym_env.py",
    "simulation\scenarios.py",
    "mic_ai\__init__.py",
    "mic_ai\core\__init__.py",
    "mic_ai\core\env.py",
    "mic_ai\ident\motor_params.py",
    "mic_ai\analysis\__init__.py",
    "mic_ai\analysis\metrics.py",
    "mic_ai\ai\__init__.py",
    "mic_ai\ai\simple_agent.py",
    "mic_ai\ai\ai_agent_ai_only.py",
    "mic_ai\ai\plots_ai.py",
    "mic_ai\ai\agents\ppo_voltage.py",
    "mic_ai\ai\ai_env.py",
    "mic_ai\ai\ai_voltage_config.py",
    "mic_ai\ai\id_ref_supervisor.py",
    "mic_ai\ai\scenario_randomization.py",
    "mic_ai\ai\curiosity.py",
    "mic_ai\ai\world_model\__init__.py",
    "mic_ai\ai\train_ai_id_ref.py",
    "mic_ai\ai\distill_voltage.py",
    "mic_ai\tools\checkpoint_adaptation.py",
    "mic_ai\tools\scenario_compare.py",
    "mic_ai\tools\plot_style.py",
    "mic_ai\tools\id_ref_lut.py",
    "mic_ai\tools\export_id_ref_lut_c.py",
    "outputs\__init__.py",
    "outputs\styles.py",
    "tests\test_motor_model.py",
    "tests\test_control.py",
    "tests\test_sim_env.py",
    "tests\test_ai_env.py",
    "tests\test_ai_env_reward_gate.py",
    "tests\test_ppo_voltage_anchor.py",
    "tests\test_scenario_compare.py",
    "tests\test_id_ref_lut.py",
    "tests\test_export_id_ref_lut_c.py",
    "tests\test_distill.py",
    "tests\test_air56b2_iek_profile.py"
)

$Missing = @($Files | Where-Object { -not (Test-Path -LiteralPath (Join-Path $SourceRoot $_) -PathType Leaf) })
if ($Missing.Count -gt 0) {
    throw "Required source files are missing: $($Missing -join ', ')"
}

New-Item -ItemType Directory -Path $DestinationRoot | Out-Null
$Records = @()
foreach ($RelativePath in $Files) {
    $SourcePath = Join-Path $SourceRoot $RelativePath
    $DestinationPath = Join-Path $DestinationRoot $RelativePath
    $DestinationDirectory = Split-Path -Parent $DestinationPath
    New-Item -ItemType Directory -Force -Path $DestinationDirectory | Out-Null
    Copy-Item -LiteralPath $SourcePath -Destination $DestinationPath
    $SourceHash = (Get-FileHash -LiteralPath $SourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
    $DestinationHash = (Get-FileHash -LiteralPath $DestinationPath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($SourceHash -ne $DestinationHash) {
        throw "Hash mismatch after copy: $RelativePath"
    }
    $SourceStatus = (& git -C $SourceRoot status --short -- $RelativePath) -join "`n"
    $Records += [ordered]@{
        path = $RelativePath.Replace("\", "/")
        bytes = (Get-Item -LiteralPath $SourcePath).Length
        source_sha256 = $SourceHash
        destination_sha256 = $DestinationHash
        source_git_status = $SourceStatus
    }
}

$GeneratedIdentInit = Join-Path $DestinationRoot "mic_ai\ident\__init__.py"
$GeneratedIdentDirectory = Split-Path -Parent $GeneratedIdentInit
New-Item -ItemType Directory -Force -Path $GeneratedIdentDirectory | Out-Null
@'
"""Minimal identification types required by the isolated FOC+PPO port."""

from .motor_params import MotorParamsEstimated, MotorParamsTrue

__all__ = ["MotorParamsEstimated", "MotorParamsTrue"]
'@ | Set-Content -LiteralPath $GeneratedIdentInit -Encoding utf8
$GeneratedIdentHash = (Get-FileHash -LiteralPath $GeneratedIdentInit -Algorithm SHA256).Hash.ToLowerInvariant()
$Records += [ordered]@{
    path = "mic_ai/ident/__init__.py"
    bytes = (Get-Item -LiteralPath $GeneratedIdentInit).Length
    source_sha256 = $null
    destination_sha256 = $GeneratedIdentHash
    source_git_status = "generated_minimal_namespace"
}

$Head = (& git -C $SourceRoot rev-parse HEAD).Trim()
$FullStatus = (& git -C $SourceRoot status --short) -join "`n"
$StatusBytes = [System.Text.Encoding]::UTF8.GetBytes($FullStatus)
$StatusHasher = [System.Security.Cryptography.SHA256]::Create()
$StatusDigest = ([System.BitConverter]::ToString($StatusHasher.ComputeHash($StatusBytes))).Replace("-", "").ToLowerInvariant()
$StatusHasher.Dispose()
$Manifest = [ordered]@{
    schema = "mic-ai-foc-ppo-source-port-v1"
    source_root = $SourceRoot
    source_git_head = $Head
    source_worktree_dirty = -not [string]::IsNullOrWhiteSpace($FullStatus)
    source_status_sha256 = $StatusDigest
    destination_root = $DestinationRoot
    copied_file_count = $Records.Count
    old_checkpoints_copied = $false
    old_results_copied = $false
    hardware_claim = $false
    files = $Records
}
$ManifestPath = Join-Path $DestinationRoot "SOURCE_PORT_MANIFEST.json"
$Manifest | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $ManifestPath -Encoding utf8

Write-Host "FOC+PPO source port created: $DestinationRoot"
Write-Host "Copied files: $($Records.Count)"
Write-Host "Source HEAD: $Head"
Write-Host "Source dirty: $($Manifest.source_worktree_dirty)"
