[CmdletBinding()]
param(
    [string]$ProjectRoot,
    [string]$Workspace,
    [ValidateSet("Debug", "Release")]
    [string]$Configuration = "Debug",
    [string]$MotorProfile,
    [switch]$RunReleaseGate
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Join-Path $scriptRoot "..\mcsdk_reference\AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"
}
if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = Join-Path $scriptRoot "..\_cubeide_ws_air56b2_vf_nameplate"
}

$cubeIde = "C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE\stm32cubeidec.exe"
$objcopy = "C:\ST\STM32CubeIDE_2.2.0\STM32CubeIDE\plugins\com.st.stm32cube.ide.mcu.externaltools.gnu-tools-for-stm32.14.3.rel1.win32_1.0.100.202602081740\tools\bin\arm-none-eabi-objcopy.exe"

$projectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path
# Keep the artifact manifest tied to the motor actually selected in this project,
# rather than to the original ST reference project used as a starting point.
$iocFiles = @(Get-ChildItem -LiteralPath $projectRoot -Filter "*.ioc" -File)
$iocText = if ($iocFiles.Count -eq 1) { Get-Content -LiteralPath $iocFiles[0].FullName -Raw } else { "" }
function Get-MotorControlIocValue([string]$Key) {
    $match = [regex]::Match(
        $iocText,
        "(?m)^MotorControl\." + [regex]::Escape($Key) + "=(.+?)\s*$"
    )
    if ($match.Success) {
        return $match.Groups[1].Value.Trim()
    }
    return $null
}
function Get-IocValue([string]$Key) {
    $match = [regex]::Match(
        $iocText,
        "(?m)^" + [regex]::Escape($Key) + "=(.+?)\s*$"
    )
    if ($match.Success) {
        return $match.Groups[1].Value.Trim()
    }
    return $null
}

$projectName = Get-IocValue "ProjectManager.ProjectName"
if ([string]::IsNullOrWhiteSpace($projectName)) {
    throw "ProjectManager.ProjectName is missing from the single IOC file."
}
$ideProject = Join-Path $projectRoot "STM32CubeIDE"
$buildDir = Join-Path $ideProject $Configuration
$elf = Join-Path $buildDir "$projectName.elf"
$bin = Join-Path $buildDir "$projectName.bin"
$hex = Join-Path $buildDir "$projectName.hex"

$selectedMotorName = Get-MotorControlIocValue "M1_MOTOR_NAME"
$selectedNominalPhaseVoltage = Get-MotorControlIocValue "NOMINAL_PHASE_VOLTAGE"
$selectedNominalCurrent = Get-MotorControlIocValue "ACIM_NOMINAL_CURRENT"
$selectedPolePairs = Get-MotorControlIocValue "ACIM_POLE_PAIR_NUM"
$selectedControlConfig = Get-MotorControlIocValue "ACIM_CONFIG"
$isAir56B2 = $selectedMotorName -match "(?i)AIR56B2"
$controlMode = if ($selectedControlConfig -eq "LSO_FOC") { "ACIM LSO-FOC sensorless" } else { "ACIM V/F open loop" }

$manifestMotor = "Siemens (official ST reference; not AIR-56)"
$manifestMotorStatus = "NOT APPROVED FOR AIR-56: add verified nameplate/measured values before flashing a motor"
$manifestProfileStatus = "st_reference_not_air56"
if ($isAir56B2) {
    $manifestMotor = "IEK AIR56B2 0.25 kW 220/380 V Delta/Y"
    $manifestMotorStatus = "AIR56B2 CANDIDATE ONLY: target-motor provenance, measured model, and external soft-start HIL must match this generated project"
    $manifestProfileStatus = "catalog_operator_confirmed_vf_candidate_pending_instance_provenance_and_identification"
}

foreach ($path in @($cubeIde, $objcopy, $ideProject)) {
    if (-not (Test-Path -LiteralPath $path)) {
        throw "Required build path is missing: $path"
    }
}

New-Item -ItemType Directory -Force -Path $Workspace | Out-Null
New-Item -ItemType Directory -Force -Path $buildDir | Out-Null
$buildLog = Join-Path $buildDir "$projectName.build.log"

& $cubeIde `
    -nosplash `
    -application org.eclipse.cdt.managedbuilder.core.headlessbuild `
    -data $Workspace `
    -import $ideProject `
    -cleanBuild "$projectName/$Configuration" 2>&1 | Tee-Object -FilePath $buildLog
$buildExitCode = $LASTEXITCODE
if ($buildExitCode -ne 0) {
    throw "STM32CubeIDE build failed with exit code $buildExitCode. See $buildLog"
}

if (-not (Test-Path -LiteralPath $elf)) {
    throw "CubeIDE reported success, but ELF is missing: $elf"
}

& $objcopy -O binary $elf $bin
if ($LASTEXITCODE -ne 0) {
    throw "Could not create BIN from ELF (exit code $LASTEXITCODE)."
}

& $objcopy -O ihex $elf $hex
if ($LASTEXITCODE -ne 0) {
    throw "Could not create HEX from ELF (exit code $LASTEXITCODE)."
}

$artifacts = @($elf, $bin, $hex) | ForEach-Object {
    $item = Get-Item -LiteralPath $_
    [ordered]@{
        file = $item.Name
        bytes = $item.Length
        sha256 = (Get-FileHash -LiteralPath $_ -Algorithm SHA256).Hash
    }
}

$buildErrors = $null
$buildWarnings = $null
$buildSummaryMatch = [regex]::Matches(
    (Get-Content -LiteralPath $buildLog -Raw),
    "(?im)(\d+)\s+errors?\s*,\s*(\d+)\s+warnings?"
) | Select-Object -Last 1
if ($null -ne $buildSummaryMatch) {
    $buildErrors = [int]$buildSummaryMatch.Groups[1].Value
    $buildWarnings = [int]$buildSummaryMatch.Groups[2].Value
}

$manifest = [ordered]@{
    schema = "mic_ai.mcsdk.acim_reference_build.v1"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    project = $projectName
    configuration = $Configuration
    target = "NUCLEO-G431RB + X-NUCLEO-IHM09M2 + STEVAL-IPM15B"
    control_mode = $controlMode
    mcsdk_acim_config = $selectedControlConfig
    reference_motor = $manifestMotor
    motor_status = $manifestMotorStatus
    motor_profile_status = $manifestProfileStatus
    ioc_motor_name = $selectedMotorName
    ioc_nominal_phase_voltage_v = $selectedNominalPhaseVoltage
    ioc_nominal_current_a = $selectedNominalCurrent
    ioc_pole_pairs = $selectedPolePairs
    build_log = (Split-Path -Leaf $buildLog)
    build_exit_code = $buildExitCode
    build_errors = $buildErrors
    build_warnings = $buildWarnings
    artifacts = $artifacts
}
$manifestPath = Join-Path $buildDir "$projectName.build-manifest.json"
$manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding utf8
$releaseGateReport = Join-Path $buildDir "mcsdk_release_preflight.json"

Write-Host "Build artifacts: $buildDir"
Write-Host "Manifest: $manifestPath"

$reportProfile = $MotorProfile
if ([string]::IsNullOrWhiteSpace($reportProfile)) {
    $reportProfile = Join-Path $scriptRoot "..\docs\mcsdk_acim_motor_profile.iek_air56b2_catalog_operator_confirmed_vf_candidate.json"
}
if (-not (Test-Path -LiteralPath $reportProfile -PathType Leaf)) {
    throw "Motor profile for the build preflight report is missing: $reportProfile"
}

$gate = Join-Path $scriptRoot "mcsdk_release_preflight.py"
$python = (Get-Command python -ErrorAction Stop).Source
& $python $gate `
    --project $projectRoot `
    --motor-profile $reportProfile `
    --artifacts $buildDir `
    --output $releaseGateReport
$gateExitCode = $LASTEXITCODE
if ($RunReleaseGate -and $gateExitCode -ne 0) {
    throw "Release gate rejected the package. Read mcsdk_release_preflight.json."
}
if (-not $RunReleaseGate) {
    Write-Host "Updated non-gating preflight report (exit $gateExitCode). It is not an HV release approval."
}
