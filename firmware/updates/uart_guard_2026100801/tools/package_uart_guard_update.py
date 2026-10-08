"""Package verified offline images; no device connections or flash operations."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import struct
import zipfile


BUILDS = {"uno_q": 2026100709, "nucleo": 2026100801}
PROJECT = "mcsdk_reference/AIR56B2_025KW_220V_DELTA_NAMEPLATE_VF_NOT_FOR_HV"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_payload(files):
    manifest = json.loads(files["manifest.json"].decode("utf-8-sig"))
    if manifest.get("schema") != "mic_ai.offline_uart_update.v1" or manifest.get("builds") != BUILDS:
        raise ValueError("Unexpected package schema or firmware identities")
    for key in ("flashed_by_this_task", "hardware_acceptance", "hv_release_approved"):
        if manifest.get(key) is not False:
            raise ValueError("Unverified hardware acceptance claim: " + key)
    if manifest.get("software_checks_pass") is not True:
        raise ValueError("Software checks did not pass")
    entries = manifest["files"]
    names = [entry["file"] for entry in entries]
    if len(names) != len(set(names)) or set(files) != set(names) | {"manifest.json"}:
        raise ValueError("Unexpected, duplicated or missing package files")
    for entry in entries:
        name = entry["file"]
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
            raise ValueError("Invalid package path")
        data = files[name]
        if len(data) != entry["bytes"] or sha(data) != entry["sha256"]:
            raise ValueError("Package checksum mismatch: " + name)
    for board, build in BUILDS.items():
        prefix = board + "/"
        candidates = [n for n in names if n.startswith(prefix) and n.endswith(".build-manifest.json")]
        if len(candidates) != 1:
            raise ValueError("Expected one build manifest per board")
        build_manifest = json.loads(files[candidates[0]].decode("utf-8-sig"))
        if build_manifest["firmware_build_id"] != build:
            raise ValueError("Build manifest identity mismatch")
        for artifact in build_manifest["artifacts"]:
            data = files[prefix + artifact["file"]]
            if len(data) != artifact["bytes"] or sha(data) != artifact["sha256"].lower():
                raise ValueError("Artifact/build manifest mismatch")
        image = ("UNOQ_MOTOR.ino.elf-zsk.bin" if board == "uno_q"
                 else "ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin")
        if struct.pack("<I", build) not in files[prefix + image]:
            raise ValueError("Compiled image build identity absent")
    regression = json.loads(files["reports/regression/report.json"].decode("utf-8"))
    if (regression.get("pass") is not True or len(regression["tests"]) != 26
            or regression.get("sources_unchanged_during_tests") is not True
            or regression.get("hardware_commands") != 0
            or len({t["test"] for t in regression["tests"]}) != 26
            or any(t.get("pass") is not True or t.get("exit_code") != 0 for t in regression["tests"])):
        raise ValueError("Regression report missing or failed")
    for test in regression["tests"]:
        if "report" in test:
            detail = json.loads(files["reports/regression/" + test["report"]])
            if detail.get("pass") is not True:
                raise ValueError("Detailed regression failed: " + test["test"])
    prefixes = ((PROJECT + "/", "source/nucleo/"), ("UNOQ_MOTOR/", "source/UNOQ_MOTOR/"),
                ("web_hmi/", "linux/web_hmi/"))
    for path, expected in regression["source_sha256"].items():
        for prefix, replacement in prefixes:
            if path.startswith(prefix):
                packaged = replacement + path[len(prefix):]
                if sha(files[packaged]) != expected:
                    raise ValueError("Packaged source differs from tested source: " + path)
    guard = json.loads(files["reports/regression/uart_guard_release_selftest/report.json"])
    source = files["source/nucleo/Src/main.c"]
    if guard.get("pass") is not True or guard["source_sha256"] != sha(source):
        raise ValueError("UART guard report is not for the packaged source")
    audit = json.loads(files["reports/source_audit.json"])
    if audit.get("pass") is not True:
        raise ValueError("Measurement compatibility audit failed")
    return {"pass": True, "files": len(entries), "builds": BUILDS,
            "hardware_commands": 0, "scope": "Integrity and metadata, not a hardware test"}


def verify_archive(path):
    with zipfile.ZipFile(path) as archive:
        if len(archive.namelist()) != len(set(archive.namelist())):
            raise ValueError("Duplicate ZIP entries")
        files = {name: archive.read(name) for name in archive.namelist()}
    return verify_payload(files)


def copy_file(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def package(root, args):
    from uart_update_regression import source_hashes

    evidence = args.evidence.resolve(strict=True)
    tests = evidence / "regression_final"
    regression = read_json(tests / "report.json")
    if regression.get("pass") is not True or regression["source_sha256"] != source_hashes(root):
        raise ValueError("Tests failed or source files changed since the regression")
    build_folder = root / PROJECT / "STM32CubeIDE/Debug"
    nucleo_manifest = read_json(build_folder / "ACIM-NUCLEOG431RB-IPM15B-VF_OL.build-manifest.json")
    if any(nucleo_manifest.get(k) != 0 for k in ("build_exit_code", "build_errors", "build_warnings")):
        raise ValueError("Nucleo build errors/warnings must be reviewed before packaging")
    current_main = (root / PROJECT / "Src/main.c").read_text(encoding="utf-8-sig")
    old_main = (evidence / "baseline/main_708.c").read_text(encoding="utf-8-sig")
    before = "static bool uno_abort_pending_rx_fault(void);"
    current_prefix = current_main[:current_main.index(before)]
    old_prefix = old_main[:old_main.index("static void uno_handle_valid_frame(")]
    current_prefix = current_prefix.replace("2026100801UL", "2026100708UL")
    tail = "static void MX_USART1_UART_Init(void) {"
    server = (root / "web_hmi/server.py").read_text(encoding="utf-8-sig")
    old_server = (evidence / "baseline/server_before_710.py").read_text(encoding="utf-8-sig")
    expected_server = old_server.replace("(2026100709, 2026100708),",
                                        "(2026100709, 2026100708), (2026100709, 2026100710), (2026100709, 2026100801),")
    audit = {"uno_source_matches_previous_709": sha((root / "UNOQ_MOTOR/UNOQ_MOTOR.ino").read_bytes())
             == "b9640c393957f9997cdb6b635b87bc8c8a4513824d51c5fdd4b9bf46b11098e9",
             "nucleo_measurements_and_reply_unchanged": current_prefix.rstrip() == old_prefix.rstrip(),
             "nucleo_uart_adc_initialization_unchanged": current_main[current_main.index(tail):]
             == old_main[old_main.index(tail):],
             "hmi_change_is_only_reviewed_build_pair": server == expected_server,
             "calibration_points_rewritten": False,
             "scope": "Relative to saved local 708 Nucleo and HMI snapshots. Other source hashes are frozen in regression report."}
    audit["pass"] = all(audit[k] for k in (
        "uno_source_matches_previous_709", "nucleo_measurements_and_reply_unchanged",
        "nucleo_uart_adc_initialization_unchanged", "hmi_change_is_only_reviewed_build_pair"))
    if not audit["pass"]:
        raise ValueError("Measurement compatibility audit failed: " + json.dumps(audit))
    destination = args.outdir.resolve()
    archive_path = destination.with_suffix(".zip")
    if destination.exists() or archive_path.exists():
        raise ValueError("Refusing to replace an existing package")
    destination.mkdir(parents=True)
    for board, folder in (("nucleo", build_folder), ("uno_q", evidence / "uno_q_rebuild")):
        manifests = list(folder.glob("*.build-manifest.json"))
        if len(manifests) != 1:
            raise ValueError("Expected one build manifest: " + str(folder))
        build = read_json(manifests[0])
        if build["firmware_build_id"] != BUILDS[board]:
            raise ValueError("Wrong board build identity")
        for artifact in build["artifacts"]:
            src = folder / artifact["file"]
            if sha(src.read_bytes()) != artifact["sha256"].lower():
                raise ValueError("Build artifact checksum mismatch: " + str(src))
            copy_file(src, destination / board / src.name)
        copy_file(manifests[0], destination / board / manifests[0].name)
    for name in ("server.py", "requirements.txt", "flash_unoq_sketch_090.cfg",
                 "static/index.html", "static/app.js", "static/style.css"):
        copy_file(root / "web_hmi" / name, destination / "linux/web_hmi" / name)
    for file in tests.rglob("*"):
        if file.is_file() and file.suffix in (".json", ".log"):
            copy_file(file, destination / "reports/regression" / file.relative_to(tests))
    for name in ("mcsdk_release_preflight.json", "ACIM-NUCLEOG431RB-IPM15B-VF_OL.build.log"):
        copy_file(build_folder / name, destination / "reports" / name)
    for name in ("package_uart_guard_update.py", "uart_update_regression.py",
                 "install_vbus_hmi_fix_remote.py", "verify_unoq_sketch.cfg"):
        copy_file(root / "tools" / name, destination / "tools" / name)
    for folder in ("Src", "Inc"):
        for src in (root / PROJECT / folder).iterdir():
            if src.suffix in (".c", ".h"):
                copy_file(src, destination / "source/nucleo" / folder / src.name)
    for src in (root / "UNOQ_MOTOR").iterdir():
        if src.suffix in (".ino", ".cpp", ".h"):
            copy_file(src, destination / "source/UNOQ_MOTOR" / src.name)
    (destination / "reports/source_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    (destination / "README_RU.txt").write_text(
        "КОМПЛЕКТ ОБНОВЛЕНИЯ UART: UNO Q 2026100709 / NUCLEO 2026100801\n\n"
        "Подготовлено и проверено программно. В этом задании платы НЕ прошивались.\n"
        "Это рабочее скалярное V/f управление, не диагностическая прошивка с обходом защит.\n\n"
        "ФАЙЛЫ ДЛЯ ЗАПИСИ\n"
        "Nucleo G431RB: nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex через ST-Link.\n"
        "UNO Q MCU: uno_q/UNOQ_MOTOR.ino.elf-zsk.bin через штатный загрузчик UNO Q.\n"
        "Не заменять этот файл обычным UNOQ_MOTOR.ino.bin: это другой формат.\n"
        "Uno Q 709 пересобран; если на плате уже точный образ 709, повторная запись не нужна.\n"
        "Linux UNO Q: linux/web_hmi; сервер принимает пару 709/801, калибровка сохранена.\n"
        "Не удалять существующие калибровку, ключ управления, настройки и журналы.\n\n"
        "ИСПРАВЛЕНИЯ И ПРОВЕРКИ\n"
        "Приём UART повторно проверяется перед обработкой команды и после START.\n"
        "Последняя проверка и публикация рампы/START защищены общей USART1-секцией.\n"
        "Проверены границы возврата guard и вызова START, пропущенные тестами версии 710.\n"
        "Версия 710 заменена этим комплектом; старый архив сохранён только как история.\n"
        "При ошибке команда отменяется, очередь очищается, STOP и защёлка сохраняют причину.\n"
        "Сохранены предыдущие исправления рампы, таймаутов, STOP, диагностики, BKIN и матрицы.\n"
        "NE/FE/ORE/PE не игнорируются; ADC/TIM защитные прерывания не маскируются.\n"
        "Скорость 115200, протокол v2, V/f и измерительные преобразования не изменены.\n"
        "DMA, CRC16 и смена скорости не включены как непроверенные гипотезы.\n"
        "26 программных наборов пройдены; отчёты и контрольные суммы находятся в комплекте.\n\n"
        "ГРАНИЦЫ ПРОВЕРКИ\n"
        "Тесты выполнялись на ПК с моделью HAL/MCSDK, без выдачи команд стенду.\n"
        "Измерения физического ШИМ, задержек защит и испытание под нагрузкой этим комплектом\n"
        "не подтверждены. Причина UART_NE при силовом запуске пока не установлена.\n"
        "Preflight сохраняет две незакрытые аппаратные проверки: soft-start и SD/BKIN.\n"
        "Не выдаётся разрешение на подачу 220 В; установка требует последующей проверки.\n"
        "Старый скрипт первого силового пуска не разрешает 801: его ограничения не ослаблялись.\n\n"
        "ПОРЯДОК УСТАНОВКИ\n"
        "При отключённом силовом вводе и разряженной шине записать Nucleo, проверить flash\n"
        "сравнением с HEX, затем обновить HMI с сохранением пользовательских данных.\n"
        "Инструмент install_vbus_hmi_fix_remote.py предназначен только для Linux UNO Q;\n"
        "он проверяет SAFE, выключенный ШИМ и разряженную шину перед заменой сервера.\n"
        "После установки проверить по Wi-Fi build IDs 709/801, SAFE, PWM=0, ARM=0,\n"
        "свежесть телеметрии и сохранность калибровки. Автоматический START не выполняется.\n"
        "Не подключать ПК/анализатор к неразвязанному стенду с силовым напряжением.\n\n"
        "ПРОВЕРКА АРХИВА (БЕЗ ПОДКЛЮЧЕНИЯ ПЛАТ)\n"
        "python tools/package_uart_guard_update.py --verify-archive <путь к ZIP>\n"
        "Содержимое и manifest проверяются по SHA-256; это не цифровая подпись.\n",
        encoding="utf-8")
    files = [{"file": p.relative_to(destination).as_posix(), "bytes": p.stat().st_size,
              "sha256": sha(p.read_bytes())} for p in sorted(destination.rglob("*")) if p.is_file()]
    manifest = {"schema": "mic_ai.offline_uart_update.v1", "generated_at": datetime.now(timezone.utc).isoformat(),
                "builds": BUILDS, "software_checks_pass": True, "flashed_by_this_task": False,
                "hardware_acceptance": False, "hv_release_approved": False,
                "uart_noise_physical_root_cause_proven": False, "calibration_points_rewritten": False,
                "older_packages_replaced": False, "files": files}
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    payload = {p.relative_to(destination).as_posix(): p.read_bytes()
               for p in destination.rglob("*") if p.is_file()}
    verify_payload(payload)
    with zipfile.ZipFile(archive_path, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            archive.writestr(name, data)
    report = verify_archive(archive_path)
    mutations = {}
    for name in ("nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.bin", "uno_q/UNOQ_MOTOR.ino.elf-zsk.bin",
                 "linux/web_hmi/server.py"):
        altered = dict(payload)
        data = bytearray(altered[name])
        data[len(data) // 2] ^= 1
        altered[name] = bytes(data)
        try:
            verify_payload(altered)
            mutations[name] = False
        except ValueError:
            mutations[name] = True
    report.update({"corruption_tests_rejected": mutations, "archive": str(archive_path),
                   "archive_sha256": sha(archive_path.read_bytes())})
    if not all(mutations.values()):
        raise ValueError("Package verifier failed deliberate corruption test")
    (evidence / "package_verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-archive", type=Path)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--outdir", type=Path)
    args = parser.parse_args()
    if args.verify_archive:
        result = verify_archive(args.verify_archive)
    else:
        if not args.evidence or not args.outdir:
            parser.error("--evidence and --outdir are required for packaging")
        result = package(Path(__file__).resolve().parents[1], args)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
