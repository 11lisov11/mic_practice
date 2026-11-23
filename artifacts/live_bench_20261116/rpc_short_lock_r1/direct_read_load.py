import sys,time,json,pathlib
sys.path.insert(0,"/home/arduino/ArduinoApps/UNOQ_MOTOR/web_hmi")
from server import RouterClient
root=pathlib.Path("/tmp/mic_rpc1609_direct_r1");c=RouterClient(str(root/"rpc.sock"));report=dict(GET=0,START=0,CLEAR=0,passed=False)
try:
 with (root/"load_GETs.jsonl").open("w") as f:
  for i in range(80):
   t=time.monotonic();r=c.call("get",[],timeout=4,retries=0)
   assert r and r[2] is None,r
   fields=dict(x.split("=",1) for x in r[3].split() if "=" in x)
   assert fields["pwm"]=="0" and fields["state"]=="SAFE"
   report["GET"]+=1;f.write(json.dumps(dict(latency=time.monotonic()-t,response=r))+"\n");f.flush();time.sleep(.2)
 report["passed"]=True
except Exception as e:report["error"]=str(e)
finally:
 c.close();(root/"load_report.json").write_text(json.dumps(report,indent=2)+"\n");print(json.dumps(report))
