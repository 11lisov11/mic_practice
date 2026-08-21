[CmdletBinding()]
param(
    [string]$Sketch = (Join-Path $PSScriptRoot "..\UNOQ_MOTOR"),
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "..\firmware\unoq_mcsdk_scalar")
)

$ErrorActionPreference = "Stop"

$arduinoCli = (Get-Command arduino-cli -ErrorAction Stop).Source
$sketchPath = (Resolve-Path -LiteralPath $Sketch).Path
$outputDirectoryPath = [System.IO.Path]::GetFullPath($OutputDirectory)
$sketchName = Split-Path -Leaf $sketchPath
$artifactPrefix = "$sketchName.ino"
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
    & $arduinoCli compile `
        --fqbn arduino:zephyr:unoq `
        --output-dir $stagingDirectory `
        $sketchPath
    if ($LASTEXITCODE -ne 0) {
        throw "Arduino UNO Q build failed with exit code $LASTEXITCODE."
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
        transport = "Serial1 / D0-D1, 115200 8N1, protocol v0x02"
        control_mode = "Scalar V/F only; raw DUTY, FOC, MIC and service outputs are not sent to MCSDK"
        flash_artifact = "$artifactPrefix.elf-zsk.bin"
        artifacts = $artifacts
    }
    $manifestPath = Join-Path $outputDirectoryPath "unoq_mcsdk_scalar.build-manifest.json"
    $manifest | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $manifestPath -Encoding utf8

    Write-Host "UNO Q artifacts: $outputDirectoryPath"
    Write-Host "UNO Q flash artifact: $(Join-Path $outputDirectoryPath "$artifactPrefix.elf-zsk.bin")"
    Write-Host "Manifest: $manifestPath"
}
finally {
    if (Test-Path -LiteralPath $stagingDirectory) {
        Remove-Item -LiteralPath $stagingDirectory -Recurse -Force
    }
}
