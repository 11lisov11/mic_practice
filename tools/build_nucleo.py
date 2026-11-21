"""Build the Nucleo bench firmware from the committed source list."""

import argparse
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'firmware/nucleo'
CPU = ['-mcpu=cortex-m4', '-mfpu=fpv4-sp-d16', '-mfloat-abi=hard', '-mthumb']
SPEC = ['--specs=nano.specs']
INCLUDES = [
    'Inc',
    'Drivers/STM32G4xx_HAL_Driver/Inc',
    'Drivers/STM32G4xx_HAL_Driver/Inc/Legacy',
    'MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLibACIM/Any/Inc',
    'MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLib/Any/Inc',
    'MCSDK_v6.4.2-Full/MotorControl/MCSDK/MCLib/G4xx/Inc',
    'Drivers/CMSIS/Device/ST/STM32G4xx/Include',
    'Drivers/CMSIS/Include',
    'Drivers/CMSIS/DSP/Include',
]


def build(output, toolchain, jobs):
    def run(tool, *args):
        command = f'arm-none-eabi-{tool}'
        if toolchain is not None:
            command = str(toolchain / (command + ('.exe' if os.name == 'nt' else '')))
        subprocess.run([command, *args], cwd=PROJECT, check=True)

    output.mkdir(parents=True, exist_ok=True)
    sources = (PROJECT / 'sources.txt').read_text(encoding='utf-8').splitlines()
    common = CPU + SPEC + ['-g3', '-DDEBUG']
    c_flags = ['-std=gnu11', '-DARM_MATH_CM4', '-DUSE_HAL_DRIVER', '-DSTM32G431xx',
               '-Ofast', '-ffunction-sections', '-fdata-sections', '-Wall']
    c_flags += [f'-I{path}' for path in INCLUDES]

    def compile_unit(item):
        index, source = item
        target = output / f'{index:03d}-{Path(source).stem}.o'
        flags = ['-x', 'assembler-with-cpp'] if Path(source).suffix.lower() == '.s' else c_flags
        run('gcc', *common, *flags, '-c', source, '-o', str(target))
        return str(target)

    with ThreadPoolExecutor(max_workers=jobs) as executor:
        objects = list(executor.map(compile_unit, enumerate(sources)))
    image = output / 'nucleo-air56.elf'
    run('gcc', *objects, *CPU, '--specs=nosys.specs', *SPEC, '-T',
        'STM32CubeIDE/STM32G431RBTX_FLASH.ld', '-Wl,--gc-sections', '-static',
        '-Wl,--start-group', '-lc', '-lm', '-Wl,--end-group', '-o', str(image))
    run('size', str(image))
    run('objcopy', '-O', 'ihex', str(image), str(image.with_suffix('.hex')))
    run('objcopy', '-O', 'binary', str(image), str(image.with_suffix('.bin')))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--toolchain', type=Path, help='Directory containing arm-none-eabi-gcc')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/nucleo')
    parser.add_argument('--jobs', type=int, default=4)
    args = parser.parse_args()
    build(args.output.resolve(), args.toolchain.resolve() if args.toolchain else None, args.jobs)
