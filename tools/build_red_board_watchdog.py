"""Build only; never opens USB devices or runs a firmware upload command.

Candidate: Artery AT32F403RCT6, 256K flash / 96K base RAM, 8MHz crystal.
Actual MCU, crystal, PC6 output polarity and board map remain unqualified.
Uses the vendor's pinned BSP and the existing Arm GCC toolchain.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'load_bench/red_watchdog_firmware'
OUT=ROOT/'artifacts/red_board_stock_20261122'
SDK_COMMIT='60e5d064d4560c38f32984e5c53ca810c77303f6'
SDK_URL=f'https://codeload.github.com/ArteryTek/AT32F403_Firmware_Library/zip/{SDK_COMMIT}'
SDK_ARCHIVE_SHA256='1092b3c3de2415fc91ef127a1a4d08f2d92f76b6965bce7cfda794bd3720787e'
SDK=OUT/'sources/at32_sdk'
BUILD=PROJECT/'build/at32f403rc'


def sdk():
    archive=OUT/'sources/AT32F403_BSP_60e5d064.zip'
    archive.parent.mkdir(parents=True,exist_ok=True)
    if not archive.exists():
        with urllib.request.urlopen(SDK_URL,timeout=30) as response:archive.write_bytes(response.read())
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=SDK_ARCHIVE_SHA256:
        raise RuntimeError('Vendor BSP archive differs from the reviewed pinned source')
    SDK.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            parts=Path(item.filename).parts[1:]
            if not parts or item.is_dir():continue
            if parts[0] not in ('libraries','middlewares','LICENSE'):continue
            target=(SDK/Path(*parts)).resolve()
            if not target.is_relative_to(SDK.resolve()):raise RuntimeError('Unsafe archive path')
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(z.read(item))


def main():
    sdk();BUILD.mkdir(parents=True,exist_ok=True)
    cc=Path.home()/'.platformio/packages/toolchain-gccarmnoneeabi/bin/arm-none-eabi-gcc.exe'
    if not cc.exists():raise RuntimeError('Existing PlatformIO Arm GCC toolchain was not found')
    cpp=cc.with_name('arm-none-eabi-g++.exe')
    device=SDK/'libraries/cmsis/cm4/device_support'
    drivers=SDK/'libraries/drivers'
    usb=SDK/'middlewares/usbd_drivers'
    cdc=SDK/'middlewares/usbd_class/cdc'
    copied=BUILD/'vendor_cdc';copied.mkdir(exist_ok=True)
    for source in cdc.glob('*.[ch]'):shutil.copy2(source,copied/source.name)
    desc=copied/'cdc_desc.h'
    text=desc.read_text(encoding='utf-8')
    text=text.replace('"AT32 Virtual Com Port  "','"MIC RNR Load Watchdog"')
    desc.write_text(text,encoding='utf-8')
    linker=BUILD/'AT32F403RC_FLASH.ld'
    text=(device/'startup/gcc/linker/AT32F403xC_FLASH.ld').read_text(encoding='utf-8')
    text,count=re.subn(r'/DISCARD/\s*:\s*\{.*?\}', '',text,flags=re.S)
    if count!=1:raise RuntimeError('Vendor linker layout changed')
    linker.write_text(text,encoding='utf-8')
    includes=[PROJECT/'include',SDK/'libraries/cmsis/cm4/core_support',device,drivers/'inc',usb/'inc',copied]
    base=['-mcpu=cortex-m4','-mthumb','-mfpu=fpv4-sp-d16','-mfloat-abi=hard','-Os','-g3',
          '-ffunction-sections','-fdata-sections','-DAT32F403RCT6','-DUSE_STDPERIPH_DRIVER','-DHEXT_VALUE=8000000']
    for inc in includes:base+=['-I',str(inc)]
    sources=[device/'system_at32f403.c',device/'startup/gcc/startup_at32f403.s']
    sources += [drivers/'src'/f'at32f403_{name}.c' for name in ('crm','gpio','misc','usb','wdt')]
    sources += sorted((usb/'src').glob('*.c'))
    sources += [copied/'cdc_class.c',copied/'cdc_desc.c',PROJECT/'src/main.cpp']
    objects=[];log=[]
    def run(command):
        result=subprocess.run([str(x) for x in command],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',errors='replace')
        log.append(dict(command=[str(x) for x in command],returncode=result.returncode,stdout=result.stdout,stderr=result.stderr))
        if result.returncode:
            (OUT/'firmware_build_log.json').write_text(json.dumps(log,indent=2),encoding='utf-8')
            raise RuntimeError(result.stdout+'\n'+result.stderr)
        return result.stdout
    for index,source in enumerate(sources):
        obj=BUILD/f'{index:02}_{source.stem}.o';objects.append(obj)
        compiler=cpp if source.suffix=='.cpp' else cc
        flags=['-std=c++17','-fno-exceptions','-fno-rtti','-Wall','-Wextra','-Werror'] if source.suffix=='.cpp' else []
        run([compiler,*base,*flags,'-c',source,'-o',obj])
    elf=BUILD/'RNR_WATCHDOG_AT32F403RC_CANDIDATE.elf'
    run([cpp,*base,'-nostartfiles','--specs=nano.specs','--specs=nosys.specs',*objects,
         '-T',linker,'-Wl,--gc-sections','-Wl,--build-id=none',f'-Wl,-Map={BUILD / "firmware.map"}','-o',elf])
    binary=elf.with_suffix('.bin')
    run([cc.with_name('arm-none-eabi-objcopy.exe'),'-O','binary',elf,binary])
    size=run([cc.with_name('arm-none-eabi-size.exe'),elf])
    values=[int(x) for x in size.splitlines()[1].split()[:3]]
    result=dict(candidate_mcu='AT32F403RCT6',physical_mcu_confirmed=False,board_gpio_map_verified=False,
                crystal_hz_assumed=8000000,permit_pin='PC6 / OUT1',output_active_level_assumed='HIGH',
                image_id='RNRWD_AT32F403RC_20261122',sdk_commit=SDK_COMMIT,sdk_archive_sha256=SDK_ARCHIVE_SHA256,
                source='https://github.com/ArteryTek/AT32F403_Firmware_Library',
                compiler=run([cc,'--version']).splitlines()[0],text_bytes=values[0],data_bytes=values[1],bss_bytes=values[2],
                flash_bytes=values[0]+values[1],ram_bytes=values[1]+values[2],
                firmware_uploaded=False,hardware_validated=False,usb_commands_sent=0,
                binary=str(binary),elf=str(elf),binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest())
    (OUT/'firmware_build_log.json').write_text(json.dumps(log,indent=2),encoding='utf-8')
    (OUT/'firmware_build.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
