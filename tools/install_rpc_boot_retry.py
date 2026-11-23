"""Install reusable bounded boot RPC, only Uno on confirmed discharged bench."""
import install_rpc_coldboot_fix as wrapper
import prepare_rpc_boot_retry as p
wrapper.p=p
install=wrapper.install
install.C,install.OLD,install.NEW=p.OUT,p.OLD,p.NEW
install.GUARD=install.GUARD.replace('((2026102605,2026102604),(2026102607,2026102604))','((2026102607,2026102604),(2026102609,2026102604))')
exec(install.GUARD,install.__dict__)
if __name__=='__main__':raise SystemExit(install.main())
