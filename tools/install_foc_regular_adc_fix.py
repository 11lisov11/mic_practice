from types import SimpleNamespace
import install_standstill_stack_offline as install
import prepare_foc_regular_adc_fix as package
install.p=package;install.OLD=(2026103003,2026103004)
guard=package.read(package.ROOT/'tools/uart_resync_fix/update_guard.py').replace(
 '((2026101805,2026101804),(2026101807,2026101806))',str((install.OLD,package.NEW)))
scope={'math':__import__('math')};exec(guard,scope)
install.GUARD=guard;install.precheck=scope['precheck'];install.base.GUARD=guard
install.hmi.p=SimpleNamespace(ROOT=package.ROOT,OUT=package.OUT,NEW=package.NEW,OLD=install.OLD,
 read=package.read,write=package.write,once=package.once,sha=install.sha)
if __name__=='__main__':raise SystemExit(install.main())
