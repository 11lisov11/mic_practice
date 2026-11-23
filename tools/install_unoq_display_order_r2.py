"""Install only the UNO display mapping and corresponding HMI identity support."""
import install_unoq_bus_display as install
import prepare_unoq_display_order_r2 as package

install.ROOT=package.ROOT
install.C=package.OUT
install.OLD=package.OLD
install.NEW=package.NEW
install.GUARD=install.GUARD.replace(
    '((2026102401,2026102402),(2026102403,2026102402))',
    '((2026102501,2026102502),(2026102503,2026102502))')
exec(install.GUARD,install.__dict__)

if __name__=='__main__':
    raise SystemExit(install.main())
