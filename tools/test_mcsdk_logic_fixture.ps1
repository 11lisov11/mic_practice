[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$OutputDirectory,
    [switch]$ConfirmIsolatedZeroBus
)

$ErrorActionPreference = "Stop"
if (-not $ConfirmIsolatedZeroBus) {
    throw "This fixture requires physically disconnected J1, J4 and motor, and measured DC bus below 2 V."
}
$repo = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$out = [System.IO.Path]::GetFullPath($OutputDirectory)
if (-not $out.StartsWith($repo + [System.IO.Path]::DirectorySeparatorChar,
        [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Fixture artifacts must remain inside the repository."
}
if (Test-Path -LiteralPath $out) {
    throw "Use a new artifact directory; previous evidence is never overwritten."
}
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "Project Python environment is missing." }

Push-Location $repo
try {
    & $python (Join-Path $PSScriptRoot "mcsdk_logic_bench_selftest.py") --outdir (Join-Path $out "host")
    if ($LASTEXITCODE -ne 0) { throw "Fixture host validation failed; no hardware changes made." }
    & $python (Join-Path $PSScriptRoot "prepare_mcsdk_logic_bench.py") --outdir (Join-Path $out "fixture")
    if ($LASTEXITCODE -ne 0) { throw "Fixture preparation failed; no hardware changes made." }
    & (Join-Path $PSScriptRoot "build_acim_reference.ps1") `
        -ProjectRoot (Join-Path $out "fixture\project") `
        -Workspace (Join-Path $out "cube_workspace") *> (Join-Path $out "build.log")
    # Non-gating preflight deliberately returns 2 for open powered-HIL gates.
    # The build script throws on compiler failure; check its actual build manifest.
    $manifestPath = Join-Path $out "fixture\project\STM32CubeIDE\Debug\ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json"
    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    if ($manifest.build_exit_code -ne 0 -or $manifest.build_errors -ne 0 -or $manifest.firmware_build_id -ne 2026100699) {
        throw "Fixture build manifest rejected; see build.log."
    }
    & $python (Join-Path $PSScriptRoot "run_mcsdk_logic_bench.py") `
        --confirm-isolated-zero-bus --fixture (Join-Path $out "fixture") `
        --input-break-test --outdir (Join-Path $out "live")
    if ($LASTEXITCODE -ne 0) {
        throw "Fixture qualification failed. Check live/report.json, including production restoration."
    }
    & python (Join-Path $PSScriptRoot "analyze_mcsdk_modulation.py") `
        --source-report (Join-Path $out "live\report.json") --outdir (Join-Path $out "modulation")
    if ($LASTEXITCODE -ne 0) { throw "Captured V/f modulation qualification failed." }
} finally {
    Pop-Location
}
