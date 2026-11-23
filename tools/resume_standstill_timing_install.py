"""Complete the verified 2933/2934 install without additional flash writes."""
import resume_standstill_install as recovery
import install_standstill_timing as package
recovery.wrap=package
recovery.p=package.p
recovery.io=package.install.io
if __name__=='__main__':raise SystemExit(recovery.main())
