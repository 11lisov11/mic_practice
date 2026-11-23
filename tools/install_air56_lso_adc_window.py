"""Install the sealed LSO ADC window pair with J1 physically off."""
import argparse

from install_air56_lso_uno_capture import install
from prepare_air56_lso_adc_window import BASE, NEW, OLD, OUT


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--confirmed-j1-off-both-usb', required=True, action='store_true')
    parser.parse_args()
    raise SystemExit(install(out=OUT, pair=NEW, previous_native=BASE,
        previous_uno=BASE / 'image/UNOQ-LSO_CAPTURE.elf-zsk.bin', previous_uno_build=OLD[0],
        verification='verification.json', verify_uart_startup=True))
