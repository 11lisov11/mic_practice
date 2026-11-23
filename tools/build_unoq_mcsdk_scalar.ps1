[CmdletBinding()]
param(
    [string]$Sketch = "",
    [string]$OutputDirectory = "",
    [string]$LibrariesDirectory = ""
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($Sketch)) {
    $Sketch = Join-Path $PSScriptRoot "..\UNOQ_MOTOR"
}
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $PSScriptRoot "..\firmware\unoq_mcsdk_scalar"
}

$arduinoCli = (Get-Command arduino-cli -ErrorAction Stop).Source
$sketchPath = (Resolve-Path -LiteralPath $Sketch).Path
$outputDirectoryPath = [System.IO.Path]::GetFullPath($OutputDirectory)
$sketchName = Split-Path -Leaf $sketchPath
$artifactPrefix = "$sketchName.ino"
$sketchSource = Get-Content -LiteralPath (Join-Path $sketchPath "$sketchName.ino") -Raw
$firmwareBuildMatch = [regex]::Match($sketchSource, "FW_BUILD_ID\s*=\s*(\d+)U")
$rpcSchemaMatch = [regex]::Match($sketchSource, "RPC_SCHEMA_VERSION\s*=\s*(\d+)U")
if (-not $firmwareBuildMatch.Success -or -not $rpcSchemaMatch.Success) {
    throw "UNO Q firmware identity or RPC schema is missing from the sketch."
}
$protocolVersionMatch = [regex]::Match($sketchSource, "BP_VER\s*=\s*0x([0-9a-fA-F]+)\s*;")
if ($protocolVersionMatch.Success) {
    $protocolVersion = [Convert]::ToInt32($protocolVersionMatch.Groups[1].Value, 16)
} elseif ($sketchSource -match "BP_VER\s*=\s*UV3_VERSION\s*;") {
    $protocolHeader = Get-Content -LiteralPath (Join-Path $sketchPath "uart_v3_transport.h") -Raw
    $protocolVersionMatch = [regex]::Match($protocolHeader, "UV3_VERSION\s*=\s*(\d+)\s*,")
    if (-not $protocolVersionMatch.Success) { throw "Missing UART v3 protocol identity." }
    $protocolVersion = [int]$protocolVersionMatch.Groups[1].Value
} else {
    throw "Unrecognized UART protocol version; refusing misleading build manifest."
}
$stagingDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ("mic_practice_unoq_" + [Guid]::NewGuid().ToString("N"))
$releaseArtifactNames = @(
    "$artifactPrefix.elf",
    "$artifactPrefix.hex",
    "$artifactPrefix.bin",
    "$artifactPrefix.elf-zsk.bin"
)

New-Item -ItemType Directory -Force -Path $outputDirectoryPath | Out-Null
New-Item -ItemType Directory -Force -Path $stagingDirectory | Out-Null

try {
    $libraryArgs = @()
    if (-not [string]::IsNullOrWhiteSpace($LibrariesDirectory)) {
        $libraryRoot = (Resolve-Path -LiteralPath $LibrariesDirectory).Path
        $libraryArgs = @("--libraries", $libraryRoot)
    }
    & $arduinoCli compile `
        --fqbn arduino:zephyr:unoq `
        --output-dir $stagingDirectory `
        @libraryArgs `
        $sketchPath
    if ($LASTEXITCODE -ne 0) {
        throw "Arduino UNO Q build failed with exit code $LASTEXITCODE."
    }

    & python (Join-Path $PSScriptRoot "unoq_llext_check.py") `
        --elf (Join-Path $stagingDirectory "$artifactPrefix.elf") `
        --report (Join-Path $outputDirectoryPath "llext-check.json")
    if ($LASTEXITCODE -ne 0) {
        throw "UNO Q dynamic-loader compatibility check failed; artifacts not exported."
    }

    $artifacts = foreach ($artifactName in $releaseArtifactNames) {
        $source = Join-Path $stagingDirectory $artifactName
        if (-not (Test-Path -LiteralPath $source -PathType Leaf)) {
            throw "Arduino UNO Q build is missing the required artifact: $artifactName"
        }
        $destination = Join-Path $outputDirectoryPath $artifactName
        Copy-Item -LiteralPath $source -Destination $destination -Force
        $item = Get-Item -LiteralPath $destination
        [ordered]@{
            file = $item.Name
            bytes = $item.Length
            sha256 = (Get-FileHash -LiteralPath $item.FullName -Algorithm SHA256).Hash
        }
    }

    # Arduino CLI leaves these compiler intermediates in --output-dir. They are
    # deliberately excluded from the release directory and its manifest.
    $obsoleteArtifactNames = @(
        "$artifactPrefix`_check.tmp",
        "$artifactPrefix`_debug.elf",
        "$artifactPrefix`_temp.elf",
        "$artifactPrefix`_temp.map",
        "$artifactPrefix.map",
        "$artifactPrefix.bin-zsk.bin"
    )
    foreach ($artifactName in $obsoleteArtifactNames) {
        $obsolete = Join-Path $outputDirectoryPath $artifactName
        if (Test-Path -LiteralPath $obsolete -PathType Leaf) {
            Remove-Item -LiteralPath $obsolete -Force
        }
    }

    $manifest = [ordered]@{
        schema = "mic_ai.unoq_mcsdk_scalar_build.v1"
        generated_at = (Get-Date).ToUniversalTime().ToString("o")
        fqbn = "arduino:zephyr:unoq"
        sketch = $sketchPath
        target = "Arduino UNO Q supervisory UART peer for NUCLEO-G431RB"
        transport = ("Serial1 / D0-D1, 115200 8N1, protocol v0x{0:X2}" -f $protocolVersion)
        control_mode = $(if ($sketchSource -match 'ma_wire_mode\(g_ma_algorithm\)') {
            "Native algorithm selection: V/F, sensorless FOC, FOC with adaptive PWM; stopped-only configuration; no raw DUTY/service outputs"
        } else {
            "Scalar V/F only; raw DUTY, FOC, MIC and service outputs are not sent to MCSDK"
        })
        flash_artifact = "$artifactPrefix.elf-zsk.bin"
        firmware_build_id = [uint32]$firmwareBuildMatch.Groups[1].Value
        rpc_schema_version = [uint32]$rpcSchemaMatch.Groups[1].Value
        artifacts = $artifacts
    }
    if ($libraryArgs.Count -gt 0) {
        $manifest.library_override_root = $libraryRoot
        $manifest.library_override_sha256 = [ordered]@{}
        Get-ChildItem -LiteralPath $libraryRoot -Recurse -File | ForEach-Object {
            $relative = $_.FullName.Substring($libraryRoot.Length + 1).Replace('\', '/')
            $manifest.library_override_sha256[$relative] = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
        }
    }
    $manifestPath = Join-Path $outputDirectoryPath "unoq_mcsdk_scalar.build-manifest.json"
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding utf8

    Write-Host "UNO Q artifacts: $outputDirectoryPath"
    Write-Host "UNO Q flash artifact: $(Join-Path $outputDirectoryPath "$artifactPrefix.elf-zsk.bin")"
    Write-Host "Manifest: $manifestPath"
}
finally {
    if (Test-Path -LiteralPath $stagingDirectory) {
        $resolvedStaging = (Resolve-Path -LiteralPath $stagingDirectory).Path
        $resolvedTemp = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd('\')
        $stagingLeaf = Split-Path -Leaf $resolvedStaging
        if (-not $resolvedStaging.StartsWith($resolvedTemp + '\', [System.StringComparison]::OrdinalIgnoreCase) `
                -or $stagingLeaf -notmatch '^mic_practice_unoq_[a-f0-9]{32}$') {
            throw "Refusing cleanup outside the allocated UNO Q temporary build directory."
        }
        Remove-Item -LiteralPath $resolvedStaging -Recurse -Force
    }
}
