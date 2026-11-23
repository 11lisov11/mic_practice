"""Install the verified zero-estimator/history pair on the discharged bench."""
import install_current_shunt_monitor as install
import prepare_current_zero_noise as package

install.ROOT=package.ROOT
install.C=package.OUT
install.OLD=package.OLD
install.NEW=package.NEW
install.GUARD=install.GUARD.replace('((2026102403,2026102402),(2026102405,2026102406))',
    '((2026102503,2026102502),(2026102505,2026102506))')
exec(install.GUARD,install.__dict__)

if __name__=='__main__':raise SystemExit(install.main())
