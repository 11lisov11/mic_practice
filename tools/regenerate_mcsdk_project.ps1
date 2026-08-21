[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SourceProject,
    [Parameter(Mandatory = $true)]
    [string]$OutputProject,
    [string]$Workspace,
    [ValidateRange(30, 600)]
    [int]$CubeMxTimeoutSeconds = 180,
    [switch]$AllowWorkbenchNonZero
)

$ErrorActionPreference = "Stop"

$scriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$workbench = "C:\Program Files (x86)\STMicroelectronics\MC_SDK_6.4.2\Utilities\PC_Software\STMCWB\STMCWB_C.exe"
$python = (Get-Command python -ErrorAction Stop).Source
$source = (Resolve-Path -LiteralPath $SourceProject).Path
$output = [System.IO.Path]::GetFullPath($OutputProject)

if ($source.TrimEnd('\') -ieq $output.TrimEnd('\')) {
    throw "-OutputProject must be a new copy, not the source project."
}
if (Test-Path -LiteralPath $output) {
    throw "Output project already exists: $output. Choose a new empty path."
}
if (-not (Test-Path -LiteralPath $workbench)) {
    throw "MC Workbench CLI not found: $workbench"
}

$iocFiles = @(Get-ChildItem -LiteralPath $source -Filter *.ioc -File)
if ($iocFiles.Count -ne 1) {
    throw "Expected exactly one .ioc in source project, found $($iocFiles.Count): $source"
}

if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = Join-Path (Split-Path -Parent $output) ("_cubeide_ws_" + (Split-Path -Leaf $output))
}

Write-Host "Copying source project to: $output"
Copy-Item -LiteralPath $source -Destination $output -Recurse
$ioc = Join-Path $output $iocFiles[0].Name
$started = Get-Date

Write-Host "Regenerating through MC Workbench and STM32CubeMX (no hardware access)."
$savedNativeErrorPreference = $PSNativeCommandUseErrorActionPreference
try {
    # CubeMX may report an updater/network failure only after completing code generation.
    # Capture that code and let the independent source/build checks decide what succeeded.
    $PSNativeCommandUseErrorActionPreference = $false
    & $workbench -wb2mx -Q -loadIoc -ioc $ioc -mx_timeout $CubeMxTimeoutSeconds
    $workbenchExitCode = $LASTEXITCODE
} finally {
    $PSNativeCommandUseErrorActionPreference = $savedNativeErrorPreference
}

$main = Join-Path $output "Src\main.c"
$cproject = Join-Path $output "STM32CubeIDE\.cproject"
foreach ($required in @($main, $cproject, (Join-Path $output ".mxproject"))) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Generation did not produce expected file: $required"
    }
}
if ((Get-Item -LiteralPath $main).LastWriteTime -lt $started) {
    throw "Src\main.c was not refreshed by regeneration."
}

& $python (Join-Path $scriptRoot "patch_cubeide_dsp_include.py") $cproject
if ($LASTEXITCODE -ne 0) {
    throw "Could not restore the CMSIS-DSP include path."
}

& $python (Join-Path $scriptRoot "uno_nucleo_mcsdk_contract_check.py") --nucleo $main
if ($LASTEXITCODE -ne 0) {
    throw "UNO Q to Nucleo adapter did not survive regeneration."
}

& (Join-Path $scriptRoot "build_acim_reference.ps1") -ProjectRoot $output -Workspace $Workspace

$report = [ordered]@{
    schema = "mic_ai.mcsdk.regeneration.v1"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    source_project = $source
    output_project = $output
    ioc = $ioc
    workbench_exit_code = $workbenchExitCode
    cubemx_timeout_seconds = $CubeMxTimeoutSeconds
    adapter_contract = "passed"
    cubeide_build = "passed"
    hardware_accessed = $false
    motor_release = "not approved: reference Siemens parameters and no precharge HIL gate"
}
$reportPath = Join-Path $output "mcsdk_regeneration_report.json"
$report | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $reportPath -Encoding utf8
Write-Host "Regeneration report: $reportPath"

if ($workbenchExitCode -ne 0 -and -not $AllowWorkbenchNonZero) {
    throw "MC Workbench exited with $workbenchExitCode after generation. The source and build checks passed, but do not treat the generator execution as clean. Inspect its log or rerun; use -AllowWorkbenchNonZero only after review."
}
if ($workbenchExitCode -ne 0) {
    Write-Warning "MC Workbench returned $workbenchExitCode. Source contract and CubeIDE build passed; this invocation is recorded as degraded in $reportPath."
}
