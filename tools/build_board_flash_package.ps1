[CmdletBinding()]
param(
    [string]$OutputDirectory = "",
    [switch]$SkipBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $repoRoot "firmware\ready_to_flash"
}
$output = [System.IO.Path]::GetFullPath($OutputDirectory)
if (-not $output.StartsWith($repoRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Output directory must stay inside the repository: $output"
}
if ($output -eq $repoRoot) {
    throw "Refusing to replace repository root."
}

if (-not $SkipBuild) {
    & (Join-Path $PSScriptRoot "build_firmware_bundle.ps1")
    if ($LASTEXITCODE -ne 0) { throw "Firmware build failed." }
}

if (Test-Path -LiteralPath $output) {
    $resolved = (Resolve-Path -LiteralPath $output).Path
    if (-not $resolved.StartsWith($repoRoot + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove output outside repository: $resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}

$directories = @(
    $output,
    (Join-Path $output "nucleo"),
    (Join-Path $output "uno_q_mcu"),
    (Join-Path $output "tools"),
    (Join-Path $output "linux\web_hmi\static"),
    (Join-Path $output "linux\tools"),
    (Join-Path $output "reports")
)
foreach ($directory in $directories) {
    New-Item -ItemType Directory -Force -Path $directory | Out-Null
}

$nucleoBuild = Join-Path $repoRoot "mcsdk_reference\AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV\STM32CubeIDE\Debug"
$unoBuild = Join-Path $repoRoot "firmware\unoq_mcsdk_scalar"
$copyMap = [ordered]@{
    (Join-Path $nucleoBuild "ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex") = (Join-Path $output "nucleo\ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex")
    (Join-Path $nucleoBuild "ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin") = (Join-Path $output "nucleo\ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin")
    (Join-Path $nucleoBuild "ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf") = (Join-Path $output "nucleo\ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf")
    (Join-Path $nucleoBuild "ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json") = (Join-Path $output "nucleo\ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json")
    (Join-Path $unoBuild "UNOQ_MOTOR.ino.elf-zsk.bin") = (Join-Path $output "uno_q_mcu\UNOQ_MOTOR.ino.elf-zsk.bin")
    (Join-Path $unoBuild "UNOQ_MOTOR.ino.bin") = (Join-Path $output "uno_q_mcu\UNOQ_MOTOR.ino.bin")
    (Join-Path $unoBuild "UNOQ_MOTOR.ino.elf") = (Join-Path $output "uno_q_mcu\UNOQ_MOTOR.ino.elf")
    (Join-Path $unoBuild "UNOQ_MOTOR.ino.hex") = (Join-Path $output "uno_q_mcu\UNOQ_MOTOR.ino.hex")
    (Join-Path $unoBuild "unoq_mcsdk_scalar.build-manifest.json") = (Join-Path $output "uno_q_mcu\unoq_mcsdk_scalar.build-manifest.json")
    (Join-Path $repoRoot "web_hmi\server.py") = (Join-Path $output "linux\web_hmi\server.py")
    (Join-Path $repoRoot "web_hmi\requirements.txt") = (Join-Path $output "linux\web_hmi\requirements.txt")
    (Join-Path $repoRoot "web_hmi\flash_unoq_sketch_090.cfg") = (Join-Path $output "linux\web_hmi\flash_unoq_sketch_090.cfg")
    (Join-Path $repoRoot "web_hmi\static\index.html") = (Join-Path $output "linux\web_hmi\static\index.html")
    (Join-Path $repoRoot "web_hmi\static\app.js") = (Join-Path $output "linux\web_hmi\static\app.js")
    (Join-Path $repoRoot "web_hmi\static\style.css") = (Join-Path $output "linux\web_hmi\static\style.css")
    (Join-Path $repoRoot "tools\adb_deploy_web_hmi.py") = (Join-Path $output "linux\tools\adb_deploy_web_hmi.py")
    (Join-Path $repoRoot "tools\configure_unoq_autonomous_wifi.py") = (Join-Path $output "linux\tools\configure_unoq_autonomous_wifi.py")
    (Join-Path $repoRoot "tools\capture_as5600_teacher_dataset.py") = (Join-Path $output "linux\tools\capture_as5600_teacher_dataset.py")
    (Join-Path $repoRoot "tools\flash_mic_ai_boards.ps1") = (Join-Path $output "tools\flash_mic_ai_boards.ps1")
    (Join-Path $repoRoot "tools\verify_board_flash_package.py") = (Join-Path $output "tools\verify_board_flash_package.py")
    (Join-Path $nucleoBuild "mcsdk_release_preflight.json") = (Join-Path $output "reports\mcsdk_release_preflight.json")
    (Join-Path $repoRoot "docs\BOARD_FIRMWARE_FLASH_RU.md") = (Join-Path $output "FLASHING_RU.md")
    (Join-Path $repoRoot "docs\FIRMWARE_STAGES_RU.md") = (Join-Path $output "FIRMWARE_STAGES_RU.md")
    (Join-Path $repoRoot "docs\AUTONOMOUS_WIFI_OPERATION_RU.md") = (Join-Path $output "AUTONOMOUS_WIFI_OPERATION_RU.md")
    (Join-Path $repoRoot "firmware\firmware_stages.json") = (Join-Path $output "firmware_stages.json")
}
foreach ($entry in $copyMap.GetEnumerator()) {
    if (-not (Test-Path -LiteralPath $entry.Key -PathType Leaf)) {
        throw "Required package input is missing: $($entry.Key)"
    }
    Copy-Item -LiteralPath $entry.Key -Destination $entry.Value -Force
}

$gitCommit = (& git -C $repoRoot rev-parse HEAD).Trim()
$gitDirty = [bool](& git -C $repoRoot status --porcelain)
$artifacts = @(
    Get-ChildItem -LiteralPath $output -Recurse -File |
        Where-Object { $_.Name -ne "flash-package-manifest.json" } |
        Sort-Object FullName |
        ForEach-Object {
            $relativePath = $_.FullName.Substring($output.Length).TrimStart([char[]]@("\", "/")).Replace("\", "/")
            [ordered]@{
                path = $relativePath
                bytes = $_.Length
                sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash
            }
        }
)
$manifest = [ordered]@{
    schema = "mic_ai.board_flash_package.v1"
    generated_at = (Get-Date).ToUniversalTime().ToString("o")
    source_commit = $gitCommit
    source_worktree_dirty = $gitDirty
    identity = [ordered]@{
        nucleo_board = "NUCLEO-G431RB"
        nucleo_mcu = "STM32G431RBT6"
        power_stage = "X-NUCLEO-IHM09M2 + STEVAL-IPM15B"
        uno_board = "Arduino UNO Q"
        motor = "IEK AIR56B2 0.25 kW, 1 pole pair, 50 Hz, 2720 rpm"
        motor_connection = "220 V delta"
        protocol = "UART v0x02, 115200 8N1"
        rpc_schema = "UNO Q get-array v2, 78 append-only elements"
        telemetry_api = "mc_* canonical; bp_* deprecated compatibility aliases"
        supported_motor_modes = @("VF")
        uart_topology = "direct 3.3 V UART; UNO Q GND and Nucleo GND are common HOT_GND = STEVAL J7 DC-"
        external_interface_in_hv = "Wi-Fi only; no USB/ST-Link/Ethernet/HDMI/UART cables"
    }
    software_verified = $true
    hardware_validated = $false
    active_stage = "S1_VF_SENSORLESS_FIRST_SPIN"
    mcu_controlled_precharge_relay = $false
    external_softstart = "autonomous AC module ahead of rectifier"
    open_release_checks = @(
        "external_softstart_hil_validated",
        "motor_profile_is_real_acim",
        "generated_motor_configuration_matches_profile"
    )
    artifacts = $artifacts
}
$manifestPath = Join-Path $output "flash-package-manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $manifestPath -Encoding utf8

$python = (Get-Command py -ErrorAction Stop).Source
& $python -3 (Join-Path $PSScriptRoot "verify_board_flash_package.py") $output
if ($LASTEXITCODE -ne 0) { throw "Flash package verification failed." }

$zipPath = "$output.zip"
if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
Compress-Archive -Path (Join-Path $output "*") -DestinationPath $zipPath -CompressionLevel Optimal
Write-Host "Flash package: $output"
Write-Host "Flash package ZIP: $zipPath"
