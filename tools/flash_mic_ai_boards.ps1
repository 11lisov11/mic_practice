[CmdletBinding()]
param(
    [ValidateSet("All", "Nucleo", "UnoQ", "Linux")]
    [string]$Target = "All",
    [string]$PackageDirectory = (Join-Path $PSScriptRoot "..\firmware\ready_to_flash"),
    [string]$UnoPort,
    [string]$StLinkSerial,
    [string]$AdbDevice,
    [ValidateSet("standalone-hv", "standalone-lv")]
    [string]$LinuxProfile = "standalone-hv",
    [switch]$Execute,
    [switch]$ConfirmDcBusDisconnected
)

$ErrorActionPreference = "Stop"
$package = [System.IO.Path]::GetFullPath($PackageDirectory)
$python = (Get-Command py -ErrorAction Stop).Source
& $python -3 (Join-Path $PSScriptRoot "verify_board_flash_package.py") $package
if ($LASTEXITCODE -ne 0) { throw "Package verification failed; nothing was flashed." }

$targets = if ($Target -eq "All") { @("Nucleo", "UnoQ", "Linux") } else { @($Target) }
if ($targets -contains "UnoQ" -and [string]::IsNullOrWhiteSpace($UnoPort)) {
    throw "-UnoPort COMx is required for the Arduino UNO Q MCU."
}
if ($Execute -and -not $ConfirmDcBusDisconnected) {
    throw "Actual flashing requires -ConfirmDcBusDisconnected. Disconnect J7/DC bus and discharge the capacitors first."
}

$nucleoHex = Join-Path $package "nucleo\ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex"
$unoImage = Join-Path $package "uno_q_mcu\UNOQ_MOTOR.ino.elf-zsk.bin"
$linuxDeploy = Join-Path $package "linux\tools\adb_deploy_web_hmi.py"
$stmProgrammer = "C:\Program Files\STMicroelectronics\STM32Cube\STM32CubeProgrammer\bin\STM32_Programmer_CLI.exe"
$arduinoCli = (Get-Command arduino-cli -ErrorAction Stop).Source

Write-Host "Plan: $($targets -join ', ')"
Write-Host "Package: $package"
if (-not $Execute) {
    Write-Host "DRY RUN only. Add -Execute -ConfirmDcBusDisconnected to write the boards."
    return
}

if ($targets -contains "Nucleo") {
    if (-not (Test-Path -LiteralPath $stmProgrammer -PathType Leaf)) {
        throw "STM32CubeProgrammer CLI not found: $stmProgrammer"
    }
    $connect = @("-c", "port=SWD", "mode=UR", "reset=HWrst")
    if (-not [string]::IsNullOrWhiteSpace($StLinkSerial)) { $connect += "sn=$StLinkSerial" }
    & $stmProgrammer @connect "-w" $nucleoHex "-v" "-rst"
    if ($LASTEXITCODE -ne 0) { throw "Nucleo programming or verification failed." }
}

if ($targets -contains "UnoQ") {
    & $arduinoCli upload -p $UnoPort -b arduino:zephyr:unoq -i $unoImage
    if ($LASTEXITCODE -ne 0) { throw "Arduino UNO Q MCU upload failed." }
}

if ($targets -contains "Linux") {
    $deployArgs = @("-3", $linuxDeploy, "--restart", "--$LinuxProfile")
    if (-not [string]::IsNullOrWhiteSpace($AdbDevice)) { $deployArgs += @("--device", $AdbDevice) }
    & $python @deployArgs
    if ($LASTEXITCODE -ne 0) { throw "Arduino UNO Q Linux HMI deployment failed." }
}

Write-Host "Programming completed. Keep the DC bus disconnected until the low-voltage bring-up checks in FLASHING_RU.md pass."
