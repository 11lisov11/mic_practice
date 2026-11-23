"""Install bounded zero verification and its diagnostic telemetry, J1 OFF."""
import install_current_shunt_monitor as install
import prepare_current_shunt_zero_blocks as package

install.ROOT=package.ROOT
install.C=package.OUT
install.OLD=package.OLD
install.NEW=package.NEW
install.GUARD=install.GUARD.replace('((2026102403,2026102402),(2026102405,2026102406))',
                                  '((2026102409,2026102410),(2026102411,2026102412))')
exec(install.GUARD,install.__dict__)

if __name__=='__main__':raise SystemExit(install.main())
