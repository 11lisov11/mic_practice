import seal_full_mcsdk_edges as seal
import full_mcsdk_edges_host as host
from prepare_full_edges_busy_wait import OUT,OLD,BUILD
seal.OUT=OUT;seal.OLD=OLD;seal.BUILD=BUILD
host.BUILD=BUILD
if __name__=='__main__':
 seal.main()
 import json
 import prepare_no_switch_diag as p
 m=json.loads(p.read(OUT/'manifest.json'))
 for name in ('prepare_full_edges_busy_wait.py','check_edges_busy_wait.py','full_edges_busy_wait_host.py','seal_edges_busy_wait.py'):
  m['tools_sha256'][name]=p.sha(p.ROOT/'tools'/name)
 p.write(OUT/'manifest.json',json.dumps(m,indent=2)+'\n')
