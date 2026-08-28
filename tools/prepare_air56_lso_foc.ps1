[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$MotorProfile,
    [Parameter(Mandatory = $true)]
    [string]$OutputProject,
    [string]$Workspace,
    [switch]$AllowWorkbenchNonZero
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$source = Join-Path $repoRoot "mcsdk_reference\AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"
$output = [System.IO.Path]::GetFullPath($OutputProject)
$profile = (Resolve-Path -LiteralPath $MotorProfile).Path
$lsoTemplate = "C:\Program Files (x86)\STMicroelectronics\MC_SDK_6.4.2\Utilities\PC_Software\STMCWB\assets\examples\ACIM-NUCLEOG431RB-IPM15B-LSO_FOC.ioc"
if (-not (Test-Path -LiteralPath $lsoTemplate -PathType Leaf)) {
    throw "Official MCSDK 6.4.2 LSO-FOC template is missing: $lsoTemplate"
}
$tmpRoot = Join-Path $repoRoot "tmp"
New-Item -ItemType Directory -Force -Path $tmpRoot | Out-Null
$seed = Join-Path $tmpRoot ("mcsdk_lso_seed_" + [guid]::NewGuid().ToString("N"))

if (Test-Path -LiteralPath $output) {
    throw "Output project already exists: $output"
}
if ([string]::IsNullOrWhiteSpace($Workspace)) {
    $Workspace = Join-Path $repoRoot "_cubeide_ws_air56b2_lso_foc"
}

try {
    Copy-Item -LiteralPath $source -Destination $seed -Recurse
    $seedResolved = (Resolve-Path -LiteralPath $seed).Path
    if (-not $seedResolved.StartsWith($tmpRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Temporary seed escaped repository tmp: $seedResolved"
    }
    $debug = Join-Path $seedResolved "STM32CubeIDE\Debug"
    if (Test-Path -LiteralPath $debug) {
        Remove-Item -LiteralPath $debug -Recurse -Force
    }

    & py -3 (Join-Path $PSScriptRoot "prepare_air56_lso_profile.py") `
        --project $seedResolved `
        --motor-profile $profile `
        --lso-template $lsoTemplate
    if ($LASTEXITCODE -ne 0) { throw "Measured AIR56B2 profile was rejected." }

    $regenArgs = @{
        SourceProject = $seedResolved
        OutputProject = $output
        Workspace = $Workspace
    }
    if ($AllowWorkbenchNonZero) { $regenArgs.AllowWorkbenchNonZero = $true }
    & (Join-Path $PSScriptRoot "regenerate_mcsdk_project.ps1") @regenArgs
    if ($LASTEXITCODE -ne 0) { throw "LSO-FOC generation failed." }

    & py -3 (Join-Path $PSScriptRoot "mcsdk_release_preflight.py") `
        --project $output `
        --motor-profile $profile `
        --artifacts (Join-Path $output "STM32CubeIDE\Debug") `
        --output (Join-Path $output "STM32CubeIDE\Debug\mcsdk_release_preflight.json")
    if ($LASTEXITCODE -ne 0) {
        throw "Generated LSO-FOC project failed release checks; inspect its preflight report."
    }
    Write-Host "Measured AIR56B2 LSO-FOC project: $output"
} finally {
    if (Test-Path -LiteralPath $seed) {
        $resolved = (Resolve-Path -LiteralPath $seed).Path
        if ($resolved.StartsWith($tmpRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
            Remove-Item -LiteralPath $resolved -Recurse -Force
        }
    }
}
