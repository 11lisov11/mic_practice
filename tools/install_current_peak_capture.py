"""Install raw ADC peak capture and inverted-mount display fix on the deenergized bench."""
import install_current_shunt_monitor as install
import prepare_current_peak_capture as package

install.ROOT = package.ROOT
install.C = package.OUT
install.OLD = package.OLD
install.NEW = package.NEW
install.GUARD = install.GUARD.replace(
    '((2026102403,2026102402),(2026102405,2026102406))',
    '((2026102411,2026102412),(2026102501,2026102502))')
exec(install.GUARD, install.__dict__)

if __name__ == '__main__':
    raise SystemExit(install.main())
