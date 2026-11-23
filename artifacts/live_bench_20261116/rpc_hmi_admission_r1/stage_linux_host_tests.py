from pathlib import Path
import shutil
root=Path('/tmp/mic_rpc_hmi_host_tests');root.mkdir(exist_ok=False)
for name,source in [('baseline','/tmp/mic_rpc_hmi_old_server.py'),('candidate','/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi/server.py')]:
 target=root/name/'web_hmi';target.mkdir(parents=True);shutil.copyfile(source,target/'server.py')
(root/'prepare_rpc_hmi_admission.py').write_text("from pathlib import Path\nBASE=Path('/tmp/mic_rpc_hmi_host_tests/baseline')\nOUT=Path('/tmp/mic_rpc_hmi_host_tests/candidate')\n")
