"""Install sealed2509/2510 after J1OFF/meter<20V/both USB confirmation."""
import install_current_shunt_monitor as install
import prepare_current_adc_apex_fix as package

install.ROOT=package.ROOT
install.C=package.OUT
install.OLD=package.OLD
install.NEW=package.NEW
install.GUARD=install.GUARD.replace('((2026102403,2026102402),(2026102405,2026102406))',
    '((2026102507,2026102508),(2026102509,2026102510))')
exec(install.GUARD,install.__dict__)

if __name__=='__main__':raise SystemExit(install.main())
