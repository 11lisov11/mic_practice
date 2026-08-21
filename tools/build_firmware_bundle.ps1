[CmdletBinding()]
param(
    [string]$MotorProfile,
    [switch]$RunReleaseGate,
    [string]$NucleoProjectRoot,
    [string]$NucleoWorkspace,
    [ValidateSet("Debug", "Release")]
    [string]$NucleoConfiguration = "Debug"
)

$ErrorActionPreference = "Stop"
$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

if ([string]::IsNullOrWhiteSpace($NucleoProjectRoot)) {
    $NucleoProjectRoot = Join-Path $scriptRoot "..\mcsdk_reference\AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"
}
if ([string]::IsNullOrWhiteSpace($NucleoWorkspace)) {
    $NucleoWorkspace = Join-Path $scriptRoot "..\_cubeide_ws_air56b2_vf_nameplate"
}
$NucleoProjectRoot = (Resolve-Path -LiteralPath $NucleoProjectRoot).Path

$nucleoIoc = @(Get-ChildItem -LiteralPath $NucleoProjectRoot -Filter "*.ioc" -File)
if ($nucleoIoc.Count -ne 1) {
    throw "Expected exactly one MCSDK .ioc file in $NucleoProjectRoot."
}
$polePairMatch = [regex]::Match(
    (Get-Content -LiteralPath $nucleoIoc[0].FullName -Raw),
    "(?m)^MotorControl\.ACIM_POLE_PAIR_NUM=(.+?)\s*$"
)
if (-not $polePairMatch.Success) {
    throw "ACIM_POLE_PAIR_NUM is missing from $($nucleoIoc[0].Name)."
}
$expectedPolePairs = $polePairMatch.Groups[1].Value.Trim()

if ($RunReleaseGate -and [string]::IsNullOrWhiteSpace($MotorProfile)) {
    throw "-RunReleaseGate requires -MotorProfile with actual nameplate and measurement data."
}

$python = (Get-Command python -ErrorAction Stop).Source
$nucleoAdapterSource = Join-Path $NucleoProjectRoot "Src\main.c"
& $python (Join-Path $scriptRoot "uno_nucleo_mcsdk_contract_check.py") `
    --nucleo $nucleoAdapterSource `
    --expected-pole-pairs $expectedPolePairs
if ($LASTEXITCODE -ne 0) {
    throw "UNO Q to Nucleo MCSDK protocol contract check failed."
}

$acimBuildArguments = @{
    ProjectRoot = $NucleoProjectRoot
    Workspace = $NucleoWorkspace
    Configuration = $NucleoConfiguration
}
if ($RunReleaseGate) {
    $acimBuildArguments["MotorProfile"] = $MotorProfile
    $acimBuildArguments["RunReleaseGate"] = $true
}

& (Join-Path $scriptRoot "build_acim_reference.ps1") @acimBuildArguments
& (Join-Path $scriptRoot "build_unoq_mcsdk_scalar.ps1")

$nucleoArtifacts = Join-Path (Join-Path $NucleoProjectRoot "STM32CubeIDE") $NucleoConfiguration
& $python (Join-Path $scriptRoot "air56b2_firmware_profile_check.py") `
    --project $NucleoProjectRoot `
    --artifacts $nucleoArtifacts
if ($LASTEXITCODE -ne 0) {
    throw "AIR56B2 firmware profile consistency check failed."
}
& $python (Join-Path $scriptRoot "verify_firmware_bundle.py") --nucleo-directory $nucleoArtifacts
if ($LASTEXITCODE -ne 0) {
    throw "Firmware bundle artifact verification failed."
}

if ($RunReleaseGate) {
    Write-Host "Firmware bundle build and motor-profile release gate completed."
} else {
    Write-Host "Firmware bundle build completed. It is not an approval to energize the DC bus or motor without -RunReleaseGate and hardware interlock validation."
}
