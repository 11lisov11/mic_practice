"""Read-only audit of installed ST board descriptions. Does not generate firmware."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
SDK=Path(r'C:\Program Files (x86)\STMicroelectronics\MC_SDK_6.4.2\Utilities\PC_Software\STMCWB\assets\hardware\board')
names={'eval':'power/EVALSTDRIVE101.json','ihm08':'power/X-NUCLEO-IHM08M1.json',
       'adapter':'adapter/X-NUCLEO-IHM09M2.json','nucleo':'control/NUCLEO-G431RB.json'}
docs={k:json.loads((SDK/p).read_text(encoding='utf-8-sig')) for k,p in names.items()}
files={k:{'path':str(SDK/p),'sha256':hashlib.sha256((SDK/p).read_bytes()).hexdigest()} for k,p in names.items()}
term=docs['nucleo']['connectors'][0]['terminals']
adapt=docs['adapter']['powerSideConnectors'][0]['controlSideConnectors'][0]['powerTerminals']
routes={}
for mc,options in adapt.items():
    routes[mc]=[{'morpho':o['name'],'mcu_or_power':p['name'],'adapter_help':o.get('help'),
                 'nucleo_help':p.get('help')} for o in options for p in term.get(o['name'],[])]
power={}
for key in ['eval','ihm08']:
    drive=docs[key]['motorDrives'][0]
    bytype={f['type']:f for f in drive['features']}
    power[key]={'name':docs[key]['name'],'voltage_min':drive['minRatedVoltage'],
                'voltage_max':drive['maxRatedVoltage'],'connector':drive['connectorType'],
                'workbench_maxRatedCurrent_field_not_continuous_rms':drive['maxRatedCurrent'],
                'three_shunt':next(v for v in bytype['CurrentSensing']['hwVariants'] if v['type']=='ThreeShunt_AmplifiedCurrents'),
                'six_input_mode':next(v for v in bytype['PhaseVoltageGeneration']['hwVariants'] if v['type']=='DrivingHighAndLowSides')}
data={'status':'catalog_and_pin_routes_only_not_hardware_qualification_not_ACIM_port',
      'sources':files,'power_boards':power,'adapter_routes_to_nucleo':routes,
      'public_current_rms_limits_A':{'EVALSTDRIVE101':20,'X-NUCLEO-IHM08M1':15},
      'notes':['PWM alternate functions, selected solder bridges and power routing must be checked against actual boards.',
               'ST MCSDK board catalog presence does not prove a ready ACIM implementation.',
               'No MCU writes, firmware generation, flash, commands or hardware connection were performed.']}
ROOT.mkdir(exist_ok=True)
(ROOT/'installed_board_audit.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
print(json.dumps({'catalog_boards':list(power),'eval_required_MC_signals':list(power['eval']['six_input_mode']['signals']),
                  'three_shunt_amplified_available':all('three_shunt' in p for p in power.values()),
                  'nucleo_mcu':docs['nucleo']['mcu'],'files':len(files)}))
