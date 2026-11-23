"""Complete the unspent single CLEAR after bus/ADC settling; no motor commands."""
import inspect,json
import prepare_observer_current_window as p
import clear_observer_window_after_recovery_once as prior
from clear_observer_window_deenergized_20261117_once import off
OUT=p.OUT/'one_CLEAR_deenergized_after_Uno_boot_20261117_r2'
def main():
    for name in ('one_CLEAR_powered_20261117_r1','one_CLEAR_deenergized_after_Uno_boot_20261117_r1'):
        folder=p.OUT/name
        assert json.loads(p.read(folder/'report.json'))['CLEAR']==0
        assert not (folder/'CLEAR_response.json').exists(),'Do not repeat CLEAR'
    source=inspect.getsource(prior.main)
    source=source.replace("prior=p.OUT/'one_CLEAR_idle_r1'", "prior=p.OUT/'one_CLEAR_deenergized_after_Uno_boot_20261117_r1'")
    source=source.replace('http://127.0.0.1:18080','http://192.168.1.138:8080')
    source=source.replace("('hardware_install_r1','post_install_idle_r1','installation_verified_r1','one_CLEAR_idle_r1')",
        "('hardware_install_r1','post_install_idle_r1','installation_verified_r1','one_CLEAR_idle_r1','one_CLEAR_after_RPC_recovery_r1','autonomous_before_FOC_20261117_r1','powered_before_FOC_20261117_r1','one_CLEAR_powered_20261117_r1','one_CLEAR_deenergized_after_Uno_boot_20261117_r1')")
    scope=dict(prior.__dict__,p=p,OUT=OUT,off=off)
    exec(compile(source,__file__,'exec'),scope);return scope['main']()
if __name__=='__main__':raise SystemExit(main())
