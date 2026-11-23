# Uno Q Linux/HMI updates over Wi-Fi

## Verified Access

Uno Q already had a key-only OpenSSH listener on port **2222**. The standard
port 22 was closed; checking only port 22 incorrectly suggested SSH was absent.
The existing listener, client key and reboot/recovery cron entries were retained.
No new SSH daemon, password login or root access was enabled.

The board host key was read over the exact Uno ADB serial 3880458060 and matched
the previously trusted key. A board-specific pin is stored in ignored local
`.unoq_ssh/known_hosts`. The client now uses StrictHostKeyChecking=yes,
IdentitiesOnly=yes, BatchMode=yes and disabled password/interactive fallbacks.
It never accepts a new host key automatically.

The board's address 192.168.1.138 belongs to wlan0. The PC reaches this LAN over
Ethernet; SSH/SFTP and HTTP therefore reach Uno over its Wi-Fi interface, not ADB.

## Scoped Deployer

`tools/unoq_wifi_hmi_deploy.py` deploys only Linux `web_hmi/server.py` by default.
It stages files via SFTP, compares SHA256, and reuses the existing remote installer
for a final live precheck, atomic copy, onboard backup, owned-process restart,
installed hash verification and unchanged calibration check. It uses no sudo,
does not flash MCU firmware and sends no motor/ARM/START commands.

Default deployment requires a disarmed SAFE stand, fresh known measurement
contract, clean transport and Vdc <=2 V. The explicit <=10 V alternative is for
Linux-only updates with mains/J4 physically off, never powered operation or MCU
programming. Physical isolation must be confirmed by the operator; telemetry
alone cannot prove that a mains cable was removed.

Preflight without changing files:

```powershell
.venv/Scripts/python.exe tools/unoq_wifi_hmi_deploy.py --dry-run --outdir artifacts/wifi_deploy_preflight
```

Normal server update after physical isolation/discharge:

```powershell
.venv/Scripts/python.exe tools/unoq_wifi_hmi_deploy.py --confirm-mains-j4-off --outdir artifacts/wifi_deploy
```

The local private key and board pins live in ignored `.unoq_ssh`; do not publish
private keys or tokens. Source and SSH targets must be the same guarded HMI host.
An unexpected host-key change must be investigated, not bypassed.

Already-current content is verified without a restart. `--reinstall-identical`
explicitly exercises the install/restart path for testing. `--include-app-js`
adds only the explicitly requested frontend file, not unrelated assets or MCU
flash recipes. The generic MCU update workflow remains separate.

## Retained Verification

Under `artifacts/live_bench_20261010/uart_v3_candidate/`:

- `ssh_wifi_deploy_regression_r1/report.json`: 45/45 unchanged-source suites.
- `wifi_ssh_deploy_preflight_r1/report.json`: pinned SSH dry-run, unchanged calibration.
- `wifi_ssh_deploy_verified_r1/report.json`: actual same-content SSH/SFTP install,
  backup and HMI restart; MCU identities unchanged; zero actuation/flash commands.

HMI SHA256 remained:
0f8a321491ff09624a9afd521ae431db381e7446a8d461dde6f3f3722aec17ce

Calibration SHA256 remained:
a89603c26f3dfa6287c304134121028db6ebdb9adeda4b58d99040530ffeea17

This resolves Linux/HMI deployment transport. It does not resolve the separate
MC_DP fault during the extended powered motor trial or approve another start.
