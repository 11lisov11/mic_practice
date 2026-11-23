"""Offline ARM build; no programmer invocation."""
import build_standstill_timing as build
import prepare_observer_current_window as package
build.p=package
if __name__=='__main__':build.main()
