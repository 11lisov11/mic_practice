"""Reuse checked installer negative gates with1611/1612 assets, offline."""
import inspect
import prepare_observer_current_window as p
import install_observer_current_window as installer
import test_clear_recovery_installer as prior
def main():
    s=inspect.getsource(prior.main)
    s=s.replace('        installer.safe(s,installer.OLD)',
        "        s['fw_build']=2026111609\n        installer.safe(s,installer.OLD)")
    s=s.replace('tools/verify_clear_recovery_idle.py','tools/verify_observer_current_window_idle.py')
    s=s.replace('tools/install_clear_recovery.py','tools/install_observer_current_window.py')
    s=s.replace('preserved_capture_hashes.json','preserved_all_hashes.json')
    a=s.index('    scripts=');b=s.index('    for f in scripts:',a)
    s=s[:a]+"    scripts=('prepare_observer_window_installer.py','install_observer_current_window.py','verify_observer_current_window_idle.py','test_observer_window_installer.py')\n"+s[b:]
    scope=dict(prior.__dict__,p=p,installer=installer)
    exec(compile(s,__file__,'exec'),scope);scope['main']()
if __name__=='__main__':main()
